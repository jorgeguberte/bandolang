use std::collections::BTreeMap;

use crate::{
    converge::domain::{
        ClosingReason, CompletionRecord, ConvergeTransactionDomain, DispatchRecord,
        ExecutionReceipt, InFlightLifecycleState, NodeStatus, OutboxRecord, SatisfactionState,
        SearchNode, SearchStatus, SemanticPayload, SettlementRecord, VisitedRecord,
    },
    ir::values::Value,
};

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum EngineError {
    TransitionError(String),
    FatalInvariantViolation(String),
}

impl std::fmt::Display for EngineError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            EngineError::TransitionError(msg) => write!(f, "TransitionError: {}", msg),
            EngineError::FatalInvariantViolation(msg) => {
                write!(f, "FatalInvariantViolation: {}", msg)
            }
        }
    }
}

impl std::error::Error for EngineError {}

static NEXT_ID_COUNTER: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(1);

pub fn next_id(prefix: &str) -> String {
    let id = NEXT_ID_COUNTER.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
    format!("{}-{}", prefix, id)
}

pub fn discover_successors(
    d: &mut ConvergeTransactionDomain,
    succs: &[String],
    mutations_closing_mutates_frontier: bool,
) -> Result<(), EngineError> {
    if d.frame_status.is_terminal() || d.frame_status == SearchStatus::Closing {
        d.frontier_mutations_during_closing += 1;
        if !mutations_closing_mutates_frontier {
            return Err(EngineError::TransitionError(
                "I8: frontier mutation during Closing".to_string(),
            ));
        }
    }
    for s in succs {
        if !d.nodes.contains_key(s) {
            d.nodes.insert(s.clone(), SearchNode::new(s.clone()));
            d.frontier.push(s.clone());
        }
    }
    Ok(())
}

pub fn dispatch_local(
    d: &mut ConvergeTransactionDomain,
    node_id: &str,
    op_id: &str,
    succs: &[String],
) -> Result<(), EngineError> {
    if d.frame_status != SearchStatus::Searching {
        return Err(EngineError::TransitionError(
            "dispatch_local outside Searching frame".to_string(),
        ));
    }

    let unsettled: Vec<_> = d
        .handles
        .values()
        .filter(|s| {
            s.settlement.is_none() && s.state != "Aborted" && s.state != "ConfirmedNotDelivered"
        })
        .collect();
    if !unsettled.is_empty() {
        return Err(EngineError::TransitionError(
            "sequential in-flight: previous request still unsettled (I1/R7)".to_string(),
        ));
    }

    d.step_count += 1;
    let existing_node = d.nodes.get(node_id).cloned();
    let sat_state = existing_node
        .as_ref()
        .map(|n| n.satisfaction_state.clone())
        .unwrap_or(SatisfactionState::Untested);
    let sat_retries = existing_node
        .as_ref()
        .map(|n| n.satisfaction_retries)
        .unwrap_or(0);

    d.nodes.insert(
        node_id.to_string(),
        SearchNode {
            node_id: node_id.to_string(),
            status: NodeStatus::Expanding,
            satisfaction_state: sat_state,
            satisfaction_retries: sat_retries,
        },
    );

    let visit_key = format!("{}:{}", op_id, node_id);
    let visit_no = d
        .visited
        .iter()
        .filter(|v| v.visit_key == visit_key)
        .count() as u64
        + 1;
    d.visited.push(VisitedRecord {
        visit_key,
        node_id: node_id.to_string(),
        op_id: op_id.to_string(),
        visit_no,
    });
    d.dispatches.push(DispatchRecord {
        node_id: node_id.to_string(),
        op_id: op_id.to_string(),
        visit_no,
        kind: "Local".to_string(),
    });

    if let Some(pos) = d.frontier.iter().position(|x| x == node_id) {
        d.frontier.remove(pos);
    }

    discover_successors(d, succs, false)?;
    Ok(())
}

pub fn stage_local(
    d: &mut ConvergeTransactionDomain,
    node_id: &str,
    op_id: &str,
    request_id: &str,
    resource: &str,
    amount: u64,
    dedup_capable: bool,
    idempotent: bool,
    local_only: bool,
    is_expansion: bool,
    mutations_second_unsettled_allowed: bool,
    mutations_stage_rejected_leaves_reservation: bool,
    mutations_budget_scope_mints_ownership: bool,
) -> Result<String, EngineError> {
    if d.outbox.contains_key(request_id) {
        return Err(EngineError::TransitionError(format!(
            "RequestIdAlreadyUsed: cannot stage new request with historical request_id '{}'",
            request_id
        )));
    }

    let unsettled: Vec<_> = d
        .handles
        .values()
        .filter(|s| {
            s.settlement.is_none() && s.state != "Aborted" && s.state != "ConfirmedNotDelivered"
        })
        .collect();
    if !unsettled.is_empty() && !mutations_second_unsettled_allowed {
        return Err(EngineError::TransitionError(
            "sequential in-flight: previous request still unsettled (I1/R7)".to_string(),
        ));
    }

    if d.frame_status != SearchStatus::Searching {
        return Err(EngineError::TransitionError(
            "StageLocal outside Searching frame".to_string(),
        ));
    }

    if !is_expansion {
        if d.satisfaction_attempts >= d.max_satisfaction_attempts {
            return Err(EngineError::TransitionError(format!(
                "SatisfactionLimitReached: attempts {} >= limit {}",
                d.satisfaction_attempts, d.max_satisfaction_attempts
            )));
        }
        if let Some(existing_node) = d.nodes.get(node_id) {
            if matches!(
                existing_node.satisfaction_state,
                SatisfactionState::CheckedNotSatisfied | SatisfactionState::Satisfied
            ) {
                return Err(EngineError::TransitionError(format!(
                    "IneligibleCheck: node '{}' is already {:?}",
                    node_id, existing_node.satisfaction_state
                )));
            }
        }
    }

    let avail = *d.intent_available.get(resource).unwrap_or(&0);
    if avail < amount && !mutations_budget_scope_mints_ownership {
        if mutations_stage_rejected_leaves_reservation {
            let res = *d.intent_reserved.get(resource).unwrap_or(&0);
            d.intent_reserved.insert(resource.to_string(), res + amount);
        }
        return Err(EngineError::TransitionError(
            "StageLocal rejected: insufficient available intent".to_string(),
        ));
    }

    let spent = *d.scope_spent.get(resource).unwrap_or(&0);
    let committed = *d.scope_committed.get(resource).unwrap_or(&0);
    let limit = *d.scope_limit.get(resource).unwrap_or(&0);
    if spent + committed + amount > limit && !mutations_budget_scope_mints_ownership {
        if mutations_stage_rejected_leaves_reservation {
            let res = *d.intent_reserved.get(resource).unwrap_or(&0);
            d.intent_reserved.insert(resource.to_string(), res + amount);
        }
        return Err(EngineError::TransitionError(
            "StageLocal rejected: exceeds scope limit".to_string(),
        ));
    }

    let res = *d.intent_reserved.get(resource).unwrap_or(&0);
    d.intent_reserved.insert(resource.to_string(), res + amount);
    d.intent_available
        .insert(resource.to_string(), avail.saturating_sub(amount));
    d.scope_committed
        .insert(resource.to_string(), committed + amount);

    let handle_id = format!("handle-{}", next_id("h"));
    d.outbox.insert(
        request_id.to_string(),
        OutboxRecord {
            request_id: request_id.to_string(),
            op_id: op_id.to_string(),
            payload_digest: format!("digest-{}", request_id),
            dedup_capable,
            idempotent,
            node_id: Some(node_id.to_string()),
            local_only,
            reserved_resource: resource.to_string(),
            reserved_amount: amount,
            is_expansion,
        },
    );

    let st = InFlightLifecycleState {
        handle_id: handle_id.clone(),
        request_id: request_id.to_string(),
        state: "Staged".to_string(),
        delivery_unknown: false,
        transport_attempts: 1,
        completion: None,
        settlement: None,
        applied: false,
        semantic_disposition: None,
        reserved_resource: resource.to_string(),
        reserved_amount: amount,
    };
    d.handles.insert(handle_id.clone(), st);
    Ok(handle_id)
}

pub fn emit_external(
    d: &mut ConvergeTransactionDomain,
    request_or_handle_id: &str,
    deliver_unknown: bool,
    mutations_transport_retry_increments_step: bool,
    mutations_first_emit_fails_step: bool,
    mutations_transport_retry_changes_request_id: bool,
    mutations_delivery_unknown_releases_commitment: bool,
) -> Result<String, EngineError> {
    let handle_id = if d.handles.contains_key(request_or_handle_id) {
        request_or_handle_id.to_string()
    } else if let Some(st) = d
        .handles
        .values()
        .find(|s| s.request_id == request_or_handle_id)
    {
        st.handle_id.clone()
    } else {
        return Err(EngineError::TransitionError(
            "unknown request/handle".to_string(),
        ));
    };

    let st = d.handles.get_mut(&handle_id).unwrap();
    let req_id = st.request_id.clone();
    let rec = d
        .outbox
        .get(&req_id)
        .cloned()
        .ok_or_else(|| EngineError::TransitionError("unknown request in outbox".to_string()))?;

    // Safe transport retry
    if st.delivery_unknown && st.state == "DeliveryUnknown" {
        if !rec.dedup_capable && !rec.idempotent {
            return Err(EngineError::TransitionError(
                "BLIND RETRY: unsafe retry without adapter dedup/idempotence guarantee".to_string(),
            ));
        }
        st.transport_attempts += 1;
        if mutations_transport_retry_increments_step {
            d.step_count += 1;
        }
        if mutations_transport_retry_changes_request_id {
            st.request_id = format!("{}-mutated", st.request_id);
        }
        if deliver_unknown {
            st.state = "DeliveryUnknown".to_string();
            if mutations_delivery_unknown_releases_commitment {
                d.scope_committed.clear();
            }
            d.current_in_flight = Some(st.clone());
            d.frame_status = SearchStatus::Waiting;
            return Ok(st.handle_id.clone());
        }
        st.delivery_unknown = false;
        st.state = "InFlight".to_string();
        d.current_in_flight = Some(st.clone());
        d.frame_status = SearchStatus::Waiting;
        return Ok(st.handle_id.clone());
    }

    if st.state != "Staged" {
        return Err(EngineError::TransitionError(format!(
            "emit_external called on handle in invalid state '{}' — must be Staged",
            st.state
        )));
    }

    if deliver_unknown {
        st.delivery_unknown = true;
        st.state = "DeliveryUnknown".to_string();
        if mutations_delivery_unknown_releases_commitment {
            d.scope_committed.clear();
        }
    } else {
        st.state = "InFlight".to_string();
    }

    if !d.first_emission_flags.contains_key(&req_id) {
        d.first_emission_flags.insert(req_id.clone(), true);
        if rec.is_expansion {
            if !mutations_first_emit_fails_step {
                d.step_count += 1;
            }
            if let Some(nid) = &rec.node_id {
                let existing_node = d.nodes.get(nid).cloned();
                let sat_state = existing_node
                    .as_ref()
                    .map(|n| n.satisfaction_state.clone())
                    .unwrap_or(SatisfactionState::Untested);
                let sat_retries = existing_node
                    .as_ref()
                    .map(|n| n.satisfaction_retries)
                    .unwrap_or(0);

                d.nodes.insert(
                    nid.clone(),
                    SearchNode {
                        node_id: nid.clone(),
                        status: NodeStatus::Expanding,
                        satisfaction_state: sat_state,
                        satisfaction_retries: sat_retries,
                    },
                );

                let visit_key = format!("{}:{}", rec.op_id, nid);
                let visit_no = d
                    .visited
                    .iter()
                    .filter(|v| &v.visit_key == &visit_key)
                    .count() as u64
                    + 1;
                d.visited.push(VisitedRecord {
                    visit_key,
                    node_id: nid.clone(),
                    op_id: rec.op_id.clone(),
                    visit_no,
                });
                d.dispatches.push(DispatchRecord {
                    node_id: nid.clone(),
                    op_id: rec.op_id.clone(),
                    visit_no,
                    kind: "External".to_string(),
                });

                if let Some(pos) = d.frontier.iter().position(|x| x == nid) {
                    d.frontier.remove(pos);
                }
            }
        } else {
            d.satisfaction_attempts += 1;
            if let Some(nid) = &rec.node_id {
                if let Some(node_obj) = d.nodes.get_mut(nid) {
                    node_obj.satisfaction_retries += 1;
                }
            }
        }
    }

    d.current_in_flight = Some(st.clone());
    d.frame_status = SearchStatus::Waiting;
    Ok(st.handle_id.clone())
}

pub fn admit_completion(
    d: &mut ConvergeTransactionDomain,
    handle_id: &str,
    completion: CompletionRecord,
    mutations_delivery_unknown_releases_commitment: bool,
) -> Result<(), EngineError> {
    let st = d
        .handles
        .get_mut(handle_id)
        .ok_or_else(|| EngineError::TransitionError(format!("unknown handle '{}'", handle_id)))?;

    let req_id = st.request_id.clone();
    let _rec = d
        .outbox
        .get(&req_id)
        .ok_or_else(|| EngineError::TransitionError("unknown request in outbox".to_string()))?;

    if completion.digest != format!("digest-{}", req_id) {
        return Err(EngineError::TransitionError("digest mismatch".to_string()));
    }

    if let Some(existing) = &st.completion {
        if existing.receipt_id != completion.receipt_id {
            // Receipt equivocation -> Fatal protocol violation
            let mut v = BTreeMap::new();
            v.insert("handle_id".to_string(), handle_id.to_string());
            v.insert("request_id".to_string(), req_id.clone());
            v.insert(
                "existing_receipt_id".to_string(),
                existing.receipt_id.clone(),
            );
            v.insert("new_receipt_id".to_string(), completion.receipt_id.clone());
            d.protocol_violations.push(v);
            d.frame_status = SearchStatus::Closing;
            d.closing_reason = Some(ClosingReason {
                kind: "PendingFailure".to_string(),
                error: Some("RECEIPT_EQUIVOCATION".to_string()),
            });
            return Err(EngineError::FatalInvariantViolation(
                "RECEIPT_EQUIVOCATION".to_string(),
            ));
        }
        return Ok(()); // Duplicate identical completion -> idempotent no-op
    }

    st.state = "Delivered".to_string();
    st.delivery_unknown = false;
    st.completion = Some(completion.clone());
    d.completions.insert(handle_id.to_string(), completion);

    if mutations_delivery_unknown_releases_commitment {
        d.scope_committed.clear();
    }

    Ok(())
}

pub fn reconcile_settlement(
    d: &mut ConvergeTransactionDomain,
    handle_id: &str,
    receipt: ExecutionReceipt,
    mutations_duplicate_settlement_reconciles_twice: bool,
    mutations_settlement_marks_applied: bool,
) -> Result<(), EngineError> {
    let st = d
        .handles
        .get_mut(handle_id)
        .ok_or_else(|| EngineError::TransitionError(format!("unknown handle '{}'", handle_id)))?;

    if st.settlement.is_some() && !mutations_duplicate_settlement_reconciles_twice {
        return Ok(()); // Exactly-once reconciliation
    }

    if receipt.request_id != st.request_id {
        return Err(EngineError::TransitionError(
            "receipt request_id mismatch".to_string(),
        ));
    }

    let res = receipt.resource.clone();
    let amt = receipt.amount;
    let reserved = st.reserved_amount;

    if amt > reserved {
        return Err(EngineError::TransitionError(format!(
            "settlement charge {} exceeds reserved ceiling {}",
            amt, reserved
        )));
    }

    let cur_spent = *d.scope_spent.get(&res).unwrap_or(&0);
    d.scope_spent.insert(res.clone(), cur_spent + amt);

    let cur_committed = *d.scope_committed.get(&res).unwrap_or(&0);
    d.scope_committed
        .insert(res.clone(), cur_committed.saturating_sub(reserved));

    let cur_res = *d.intent_reserved.get(&res).unwrap_or(&0);
    d.intent_reserved
        .insert(res.clone(), cur_res.saturating_sub(reserved));

    let cur_ispent = *d.intent_spent.get(&res).unwrap_or(&0);
    d.intent_spent.insert(res.clone(), cur_ispent + amt);

    let unspent = reserved.saturating_sub(amt);
    let cur_avail = *d.intent_available.get(&res).unwrap_or(&0);
    d.intent_available.insert(res.clone(), cur_avail + unspent);

    st.state = "Settled".to_string();
    st.settlement = Some(SettlementRecord {
        handle_id: handle_id.to_string(),
        receipt_id: receipt.receipt_id.clone(),
        resource: res,
        amount: amt,
    });

    let count = d
        .settlement_reconciliations
        .get(handle_id)
        .cloned()
        .unwrap_or(0);
    d.settlement_reconciliations
        .insert(handle_id.to_string(), count + 1);

    if mutations_settlement_marks_applied {
        st.applied = true;
    }

    Ok(())
}

pub fn apply_semantic(
    d: &mut ConvergeTransactionDomain,
    handle_id: &str,
    mutations_duplicate_completion_applies_twice: bool,
    mutations_closing_accepts_late_payload: bool,
    mutations_ranking_promotes_satisfied: bool,
    mutations_closing_mutates_frontier: bool,
) -> Result<(), EngineError> {
    let (req_id, completion) = {
        let st = d.handles.get_mut(handle_id).ok_or_else(|| {
            EngineError::TransitionError(format!("unknown handle '{}'", handle_id))
        })?;

        if st.applied && !mutations_duplicate_completion_applies_twice {
            return Ok(()); // Exactly-once semantic apply
        }

        let completion = st
            .completion
            .as_ref()
            .ok_or_else(|| {
                EngineError::TransitionError("handle has no completion admitted".to_string())
            })?
            .clone();

        if d.frame_status == SearchStatus::Closing && !mutations_closing_accepts_late_payload {
            st.semantic_disposition = Some("DiscardedDueToClosing".to_string());
            st.applied = true;
            d.applied_completions.push(completion.receipt_id);
            return Ok(());
        }

        st.semantic_disposition = Some("Applied".to_string());
        st.applied = true;
        d.applied_completions.push(completion.receipt_id.clone());
        (st.request_id.clone(), completion)
    };

    if let Some(payload) = &completion.semantic_payload {
        match payload {
            SemanticPayload::Space(space) => {
                if space.is_failure {
                    if !space.successors.is_empty() {
                        let _ = discover_successors(
                            d,
                            &space.successors,
                            mutations_closing_mutates_frontier,
                        );
                    }
                    // Step failure
                    match d.on_step_failure.as_str() {
                        "abort" => {
                            d.frame_status = SearchStatus::Failed;
                            d.closing_reason = Some(ClosingReason {
                                kind: "PendingFailure".to_string(),
                                error: space
                                    .error
                                    .clone()
                                    .or_else(|| Some("StepFailure".to_string())),
                            });
                        }
                        "prune" => {
                            // Prune failed node
                            if let Some(rec) = d.outbox.get(&req_id) {
                                if let Some(nid) = &rec.node_id {
                                    if let Some(node_obj) = d.nodes.get_mut(nid) {
                                        node_obj.status = NodeStatus::Pruned;
                                    }
                                }
                            }
                            if d.frame_status == SearchStatus::Waiting {
                                d.frame_status = SearchStatus::Searching;
                            }
                        }
                        "requeue" => {
                            // Requeue node to frontier
                            if let Some(rec) = d.outbox.get(&req_id) {
                                if let Some(nid) = &rec.node_id {
                                    if !d.frontier.contains(nid) {
                                        d.frontier.push(nid.clone());
                                    }
                                    if let Some(node_obj) = d.nodes.get_mut(nid) {
                                        node_obj.status = NodeStatus::Frontier;
                                    }
                                }
                            }
                            if d.frame_status == SearchStatus::Waiting {
                                d.frame_status = SearchStatus::Searching;
                            }
                        }
                        _ => {}
                    }
                } else {
                    if mutations_duplicate_completion_applies_twice {
                        d.frontier.extend(space.successors.clone());
                    } else {
                        discover_successors(
                            d,
                            &space.successors,
                            mutations_closing_mutates_frontier
                                || mutations_closing_accepts_late_payload,
                        )?;
                    }
                    if let Some(rec) = d.outbox.get(&req_id) {
                        if let Some(nid) = &rec.node_id {
                            if let Some(node_obj) = d.nodes.get_mut(nid) {
                                node_obj.status = NodeStatus::Expanded;
                            }
                        }
                    }
                    if d.frame_status == SearchStatus::Waiting {
                        d.frame_status = SearchStatus::Searching;
                    }
                }
            }
            SemanticPayload::Satisfier(sat) => {
                if sat.satisfied || mutations_ranking_promotes_satisfied {
                    d.frame_status = SearchStatus::Satisfied;
                    d.satisfied_value = sat.value.clone();
                    if let Some(node_obj) = d.nodes.get_mut(&sat.node_id) {
                        node_obj.satisfaction_state = SatisfactionState::Satisfied;
                    }
                } else if let Some(err) = &sat.error {
                    d.satisfier_error = Some(err.clone());
                    match d.on_satisfier_error.as_str() {
                        "abort" => {
                            d.frame_status = SearchStatus::Failed;
                            d.closing_reason = Some(ClosingReason {
                                kind: "PendingFailure".to_string(),
                                error: Some(err.clone()),
                            });
                        }
                        "retry" => {
                            if let Some(node_obj) = d.nodes.get_mut(&sat.node_id) {
                                node_obj.satisfaction_state = SatisfactionState::RetryableFailure;
                            }
                            if d.frame_status == SearchStatus::Waiting {
                                d.frame_status = SearchStatus::Searching;
                            }
                        }
                        _ => {}
                    }
                } else {
                    if let Some(node_obj) = d.nodes.get_mut(&sat.node_id) {
                        node_obj.satisfaction_state = SatisfactionState::CheckedNotSatisfied;
                    }
                    if d.frame_status == SearchStatus::Waiting {
                        d.frame_status = SearchStatus::Searching;
                    }
                }
            }
        }
    }

    Ok(())
}

pub fn close_frame(d: &mut ConvergeTransactionDomain, reason: ClosingReason) {
    d.frame_status = SearchStatus::Closing;
    d.closing_reason = Some(reason);
}

pub fn fatal_close(d: &mut ConvergeTransactionDomain, err: &str) {
    let mut v = BTreeMap::new();
    v.insert("fatal".to_string(), err.to_string());
    d.protocol_violations.push(v);
    d.frame_status = SearchStatus::Closing;
    d.closing_reason = Some(ClosingReason {
        kind: "PendingFailure".to_string(),
        error: Some(err.to_string()),
    });
}

pub fn cancel(d: &mut ConvergeTransactionDomain) {
    if d.frame_status == SearchStatus::Closing || d.frame_status.is_terminal() {
        return;
    }
    d.frame_status = SearchStatus::Closing;
    d.closing_reason = Some(ClosingReason {
        kind: "PendingCancelled".to_string(),
        error: None,
    });

    for st in d.handles.values_mut() {
        if st.state == "Staged" {
            st.state = "Aborted".to_string();
            let amt = st.reserved_amount;
            let res = &st.reserved_resource;
            let cur_res = *d.intent_reserved.get(res).unwrap_or(&0);
            d.intent_reserved
                .insert(res.clone(), cur_res.saturating_sub(amt));
            let cur_avail = *d.intent_available.get(res).unwrap_or(&0);
            d.intent_available.insert(res.clone(), cur_avail + amt);
            let cur_com = *d.scope_committed.get(res).unwrap_or(&0);
            d.scope_committed
                .insert(res.clone(), cur_com.saturating_sub(amt));
        }
    }
    if let Some(cur_inf) = &d.current_in_flight {
        if cur_inf.state == "Staged" || cur_inf.state == "Aborted" {
            d.current_in_flight = None;
        }
    }
}

pub fn confirmed_not_delivered(
    d: &mut ConvergeTransactionDomain,
    handle_id: &str,
) -> Result<(), EngineError> {
    let st = d
        .handles
        .get_mut(handle_id)
        .ok_or_else(|| EngineError::TransitionError(format!("unknown handle '{}'", handle_id)))?;

    st.state = "ConfirmedNotDelivered".to_string();
    let amt = st.reserved_amount;
    let res = st.reserved_resource.clone();
    let cur_res = *d.intent_reserved.get(&res).unwrap_or(&0);
    d.intent_reserved
        .insert(res.clone(), cur_res.saturating_sub(amt));
    let cur_avail = *d.intent_available.get(&res).unwrap_or(&0);
    d.intent_available.insert(res.clone(), cur_avail + amt);
    let cur_com = *d.scope_committed.get(&res).unwrap_or(&0);
    d.scope_committed
        .insert(res.clone(), cur_com.saturating_sub(amt));

    if let Some(cur_inf) = &d.current_in_flight {
        if cur_inf.handle_id == handle_id {
            d.current_in_flight = None;
        }
    }

    if d.frame_status == SearchStatus::Waiting {
        d.frame_status = SearchStatus::Searching;
    }

    Ok(())
}

pub fn exhaust(d: &mut ConvergeTransactionDomain, reason: &str) {
    d.exhaustion_reason = Some(reason.to_string());
    if d.frame_status != SearchStatus::Searching && d.frame_status != SearchStatus::Waiting {
        return;
    }
    let unsettled = d.handles.values().any(|s| {
        s.settlement.is_none() && s.state != "Aborted" && s.state != "ConfirmedNotDelivered"
    });
    let pending_scope = d.scope_committed.values().any(|v| *v > 0);
    if unsettled || pending_scope {
        d.frame_status = SearchStatus::Closing;
        d.closing_reason = Some(ClosingReason {
            kind: "PendingExhausted".to_string(),
            error: None,
        });
        return;
    }
    d.frame_status = SearchStatus::Exhausted;
    d.current_in_flight = None;
}

pub fn finish_if_drained(d: &mut ConvergeTransactionDomain) -> bool {
    if d.frame_status != SearchStatus::Closing {
        return false;
    }
    let unsettled = d.handles.values().any(|s| {
        s.settlement.is_none() && s.state != "Aborted" && s.state != "ConfirmedNotDelivered"
    });
    let pending_scope = d.scope_committed.values().any(|v| *v > 0);
    if unsettled || pending_scope {
        return false;
    }
    let kind = d
        .closing_reason
        .as_ref()
        .map(|r| r.kind.as_str())
        .unwrap_or("Draining");
    d.current_in_flight = None;
    match kind {
        "PendingFailure" => {
            d.frame_status = SearchStatus::Failed;
        }
        "PendingCancelled" => {
            d.frame_status = SearchStatus::Cancelled;
        }
        "PendingExhausted" => {
            d.frame_status = SearchStatus::Exhausted;
        }
        "PendingSatisfied" => {
            d.frame_status = SearchStatus::Satisfied;
        }
        _ => {
            d.frame_status = SearchStatus::Exhausted;
        }
    }
    true
}

pub fn check_satisfaction(
    d: &mut ConvergeTransactionDomain,
    node_id: &str,
    _op_id: &str,
    satisfied: bool,
    value: Option<Value>,
    error: Option<String>,
    mutations_ranking_promotes_satisfied: bool,
    mutations_satisfaction_retry_bypasses_limit: bool,
) -> Result<bool, EngineError> {
    if d.frame_status != SearchStatus::Searching && d.frame_status != SearchStatus::Waiting {
        return Ok(false);
    }

    if d.satisfaction_attempts >= d.max_satisfaction_attempts
        && !mutations_satisfaction_retry_bypasses_limit
    {
        return Err(EngineError::TransitionError(format!(
            "SatisfactionLimitReached: attempts {} >= limit {} (A1)",
            d.satisfaction_attempts, d.max_satisfaction_attempts
        )));
    }

    if let Some(existing_node) = d.nodes.get(node_id) {
        if matches!(
            existing_node.satisfaction_state,
            SatisfactionState::CheckedNotSatisfied | SatisfactionState::Satisfied
        ) {
            return Err(EngineError::TransitionError(format!(
                "IneligibleCheck: node '{}' is already {:?}",
                node_id, existing_node.satisfaction_state
            )));
        }
    }

    d.satisfaction_attempts += 1;
    let existing_node = d.nodes.get(node_id).cloned();
    let cur_status = existing_node
        .as_ref()
        .map(|n| n.status.clone())
        .unwrap_or(NodeStatus::Frontier);

    if satisfied || mutations_ranking_promotes_satisfied {
        d.nodes.insert(
            node_id.to_string(),
            SearchNode {
                node_id: node_id.to_string(),
                status: cur_status,
                satisfaction_state: SatisfactionState::Satisfied,
                satisfaction_retries: existing_node
                    .as_ref()
                    .map(|n| n.satisfaction_retries)
                    .unwrap_or(0),
            },
        );
        d.satisfied_value = value;
        d.frame_status = SearchStatus::Satisfied;
        d.current_in_flight = None;
        return Ok(true);
    } else if let Some(err) = error {
        let retries = existing_node
            .as_ref()
            .map(|n| n.satisfaction_retries + 1)
            .unwrap_or(1);
        d.nodes.insert(
            node_id.to_string(),
            SearchNode {
                node_id: node_id.to_string(),
                status: cur_status,
                satisfaction_state: SatisfactionState::RetryableFailure,
                satisfaction_retries: retries,
            },
        );
        d.satisfier_error = Some(err.clone());
        if d.on_satisfier_error == "abort" {
            fatal_close(d, &err);
        }
        return Ok(false);
    } else {
        let retries = existing_node
            .as_ref()
            .map(|n| n.satisfaction_retries)
            .unwrap_or(0);
        d.nodes.insert(
            node_id.to_string(),
            SearchNode {
                node_id: node_id.to_string(),
                status: cur_status,
                satisfaction_state: SatisfactionState::CheckedNotSatisfied,
                satisfaction_retries: retries,
            },
        );
        return Ok(false);
    }
}

pub fn terminalize(
    d: &mut ConvergeTransactionDomain,
    mutations_terminalizes_with_commitment: bool,
) -> Result<SearchStatus, EngineError> {
    let committed = d.scope_committed.values().sum::<u64>();
    let reserved = d.intent_reserved.values().sum::<u64>();
    let in_flight = d.handles.values().any(|s| {
        s.settlement.is_none() && s.state != "Aborted" && s.state != "ConfirmedNotDelivered"
    });

    if (committed > 0 || reserved > 0 || in_flight) && !mutations_terminalizes_with_commitment {
        return Err(EngineError::TransitionError(
            "Terminal obligation barrier: cannot terminalize with outstanding commitments/in-flight handles"
                .to_string(),
        ));
    }

    if let Some(reason) = &d.closing_reason {
        match reason.kind.as_str() {
            "PendingSatisfied" => {
                d.frame_status = SearchStatus::Satisfied;
            }
            "PendingExhausted" => {
                d.frame_status = SearchStatus::Exhausted;
            }
            "PendingCancelled" => {
                d.frame_status = SearchStatus::Cancelled;
            }
            "PendingFailure" => {
                d.frame_status = SearchStatus::Failed;
            }
            _ => {}
        }
    } else if d.frame_status == SearchStatus::Searching {
        if d.satisfied_value.is_some() {
            d.frame_status = SearchStatus::Satisfied;
        } else {
            d.frame_status = SearchStatus::Exhausted;
        }
    }

    Ok(d.frame_status.clone())
}
