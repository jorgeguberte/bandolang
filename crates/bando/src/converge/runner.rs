use std::collections::BTreeMap;

use crate::{
    conformance::schema::{ConvergeObservationV0, ConvergeScenarioConfig},
    converge::{
        domain::{
            ClosingReason, CompletionRecord, ConvergeTransactionDomain, ExecutionReceipt,
            SatisfierOutcome, SearchStatus, SemanticPayload, SpaceOutcome,
        },
        engine::{
            admit_completion, apply_semantic, cancel, check_satisfaction, close_frame,
            confirmed_not_delivered, discover_successors, dispatch_local, emit_external, exhaust,
            finish_if_drained, reconcile_settlement, stage_local, terminalize,
        },
        invariants::check_all_invariants,
        scheduler::{
            scheduler_step, ActionCheckSatisfaction, ActionExpand, SatisfierOpInfo,
            SchedulerAction, SpaceOpInfo,
        },
    },
    ir::values::Value,
    lowering::CompilerMutations,
};

fn parse_sat_entry(v: &serde_json::Value, attempt_no: u64) -> (String, bool, Option<Value>, Option<String>) {
    let item = if let Some(arr) = v.as_array() {
        if !arr.is_empty() && arr[0].is_array() {
            let idx = (attempt_no.saturating_sub(1) as usize).min(arr.len() - 1);
            &arr[idx]
        } else {
            v
        }
    } else {
        v
    };

    if let Some(arr) = item.as_array() {
        let tag = arr.get(0).and_then(|x| x.as_str()).unwrap_or("ok").to_string();
        let satisfied = arr.get(1).and_then(|x| x.as_bool()).unwrap_or(false);
        let val_json = arr.get(2);
        if tag == "ok" {
            let val = val_json.and_then(|j| {
                if j.is_null() {
                    None
                } else if let Ok(v) = serde_json::from_value::<Value>(j.clone()) {
                    Some(v)
                } else if let Some(s) = j.as_str() {
                    Some(Value::String(s.to_string()))
                } else {
                    None
                }
            });
            ("ok".to_string(), satisfied, val, None)
        } else {
            let err_msg = val_json.and_then(|j| {
                if let Some(s) = j.as_str() {
                    Some(s.to_string())
                } else if let Some(p) = j.get("payload").and_then(|x| x.as_str()) {
                    Some(p.to_string())
                } else {
                    Some("SatisfierError".to_string())
                }
            }).unwrap_or_else(|| "SatisfierError".to_string());
            ("err".to_string(), false, None, Some(err_msg))
        }
    } else {
        ("ok".to_string(), false, None, None)
    }
}

pub fn run_converge_scenario(
    cfg: &ConvergeScenarioConfig,
    mutations: &CompilerMutations,
) -> (ConvergeTransactionDomain, ConvergeObservationV0) {
    let mut d = ConvergeTransactionDomain::default();
    d.on_satisfier_error = cfg.on_satisfier_error.clone();
    d.on_step_failure = cfg.on_step_failure.clone();
    d.max_satisfaction_attempts = cfg.max_satisfaction_attempts;
    d.max_steps = cfg.max_steps;

    let initial_usd = 100;
    d.scope_limit.insert("usd".to_string(), cfg.budget_limit);
    d.intent_initial_total.insert("usd".to_string(), initial_usd);
    d.intent_available.insert("usd".to_string(), initial_usd);

    let _ = discover_successors(
        &mut d,
        &cfg.initial_frontier,
        mutations.s4m15_closing_mutates_frontier,
    );

    let mut space_attempts: BTreeMap<String, u64> = BTreeMap::new();
    let mut satisfier_attempts: BTreeMap<String, u64> = BTreeMap::new();

    let mut node_ops = BTreeMap::new();
    for (node, op) in &cfg.node_ops {
        node_ops.insert(
            node.clone(),
            SpaceOpInfo {
                op_id: op.op_id.clone(),
                kind: op.kind.clone(),
                cost: op.cost,
            },
        );
    }

    let effectful_sat = cfg.effectful_satisfier.as_ref().map(|es| SatisfierOpInfo {
        op_id: es.op_id.clone(),
        kind: es.kind.clone(),
        cost: es.cost,
    });

    let mut loop_steps = 0;
    while (d.frame_status == SearchStatus::Searching
        || (mutations.s4m08_second_unsettled_request_allowed && !d.frontier.is_empty()))
        && loop_steps < 100
    {
        loop_steps += 1;
        let _ = check_all_invariants(&d);

        let action = scheduler_step(
            &mut d,
            &node_ops,
            &cfg.partial_map,
            effectful_sat.as_ref(),
            mutations.s4m01_scheduler_pops_unaffordable_node,
            mutations.s4m17_budget_scope_mints_ownership,
            mutations.s4m20_satisfaction_retry_bypasses_attempt_ceiling,
            mutations.s4m08_second_unsettled_request_allowed,
        );

        match action {
            SchedulerAction::Stop { reason } => {
                exhaust(&mut d, &reason);
                let _ = terminalize(&mut d, mutations.s4m16_terminalizes_with_commitment);
                break;
            }
            SchedulerAction::Wait { .. } => {
                break;
            }
            SchedulerAction::Expand(ActionExpand {
                node_id,
                op_id,
                kind,
                cost,
            }) => {
                let count = space_attempts.entry(node_id.clone()).or_insert(0);
                *count += 1;
                let attempt_no = *count;

                let op_def = cfg.node_ops.get(&node_id);
                let succs = cfg
                    .successors
                    .get(&node_id)
                    .cloned()
                    .unwrap_or_default();

                let op_is_deliv_unknown = cfg.fault_spec.delivery_unknown
                    || cfg
                        .fault_spec
                        .delivery_unknown_ops
                        .contains(&op_id);

                if kind == "local" {
                    let _ = dispatch_local(&mut d, &node_id, &op_id, &succs);
                } else {
                    let req_id = if mutations.s4m18_requeue_reuses_request_id && attempt_no > 1 {
                        format!("req:{}:{}:1", op_id, node_id)
                    } else {
                        op_def
                            .and_then(|o| o.request_id.clone())
                            .unwrap_or_else(|| format!("req:{}:{}:{}", op_id, node_id, attempt_no))
                    };

                    let dedup = op_def.map(|o| o.dedup_capable).unwrap_or(true);
                    let idemp = op_def.map(|o| o.idempotent).unwrap_or(true);

                    let handle_res = stage_local(
                        &mut d,
                        &node_id,
                        &op_id,
                        &req_id,
                        "usd",
                        cost,
                        dedup,
                        idemp,
                        false,
                        true,
                        mutations.s4m08_second_unsettled_request_allowed,
                        mutations.s4m04_stage_rejected_leaves_reservation,
                        mutations.s4m17_budget_scope_mints_ownership,
                    );

                    let handle = match handle_res {
                        Ok(h) => h,
                        Err(_) => break,
                    };

                    let emit_res = emit_external(
                        &mut d,
                        &handle,
                        op_is_deliv_unknown,
                        mutations.s4m06_transport_retry_increments_step,
                        mutations.s4m05_first_emit_fails_step,
                        mutations.s4m07_transport_retry_changes_request_id,
                        mutations.s4m09_delivery_unknown_releases_commitment,
                    );
                    if emit_res.is_err() {
                        break;
                    }

                    if op_is_deliv_unknown {
                        if cfg.fault_spec.cancel_in_flight {
                            cancel(&mut d);
                            let _ = confirmed_not_delivered(&mut d, &handle);
                            let _ = finish_if_drained(&mut d);
                            break;
                        } else if cfg.fault_spec.safe_retry && (dedup || idemp) {
                            if cfg.fault_spec.double_delivery_unknown {
                                let _ = emit_external(
                                    &mut d,
                                    &handle,
                                    true,
                                    mutations.s4m06_transport_retry_increments_step,
                                    mutations.s4m05_first_emit_fails_step,
                                    mutations.s4m07_transport_retry_changes_request_id,
                                    mutations.s4m09_delivery_unknown_releases_commitment,
                                );
                                break;
                            } else {
                                let _ = emit_external(
                                    &mut d,
                                    &handle,
                                    false,
                                    mutations.s4m06_transport_retry_increments_step,
                                    mutations.s4m05_first_emit_fails_step,
                                    mutations.s4m07_transport_retry_changes_request_id,
                                    mutations.s4m09_delivery_unknown_releases_commitment,
                                );
                            }
                        } else {
                            if mutations.s4m16_terminalizes_with_commitment {
                                exhaust(&mut d, "ForcedTerminal");
                                let _ = terminalize(&mut d, true);
                            }
                            if !mutations.s4m08_second_unsettled_request_allowed {
                                break;
                            }
                        }
                    }

                    // Space outcome completion
                    let is_space_fault = cfg.space_faults.get(&op_id);
                    let (is_failure, fault_err) = if let Some(v) = is_space_fault {
                        if let Some(arr) = v.as_array() {
                            let idx = (attempt_no.saturating_sub(1) as usize).min(arr.len() - 1);
                            if arr[idx].is_null() || arr[idx].as_str() == Some("null") {
                                (false, None)
                            } else {
                                let msg = arr[idx].as_str().unwrap_or("SpaceFault").to_string();
                                (true, Some(msg))
                            }
                        } else if v.is_null() || v.as_str() == Some("null") {
                            (false, None)
                        } else if let Some(msg) = v.as_str() {
                            (true, Some(msg.to_string()))
                        } else {
                            (false, None)
                        }
                    } else {
                        (false, None)
                    };

                    let space_payload = SpaceOutcome {
                        successors: if is_failure && !mutations.s4m19_failed_requeue_incorporates_successors {
                            Vec::new()
                        } else {
                            succs
                        },
                        error: fault_err,
                        is_failure,
                    };

                    let receipt_id = format!("receipt-{}", req_id);
                    let completion = CompletionRecord {
                        handle_id: handle.clone(),
                        receipt_id: receipt_id.clone(),
                        digest: format!("digest-{}", req_id),
                        outcome: if is_failure {
                            "Failure".to_string()
                        } else {
                            "Success".to_string()
                        },
                        semantic_payload: Some(SemanticPayload::Space(space_payload)),
                        receipt: Some(ExecutionReceipt {
                            request_id: req_id.clone(),
                            receipt_id: receipt_id.clone(),
                            resource: "usd".to_string(),
                            amount: op_def.and_then(|o| o.actual_cost).unwrap_or(cost),
                        }),
                    };

                    if cfg.fault_spec.cancel_in_flight {
                        let _ = admit_completion(
                            &mut d,
                            &handle,
                            completion.clone(),
                            mutations.s4m09_delivery_unknown_releases_commitment,
                        );
                        cancel(&mut d);
                        let charge = op_def.and_then(|o| o.actual_cost).unwrap_or(cost);
                        let receipt = ExecutionReceipt {
                            request_id: req_id.clone(),
                            receipt_id: receipt_id.clone(),
                            resource: "usd".to_string(),
                            amount: charge,
                        };
                        let _ = reconcile_settlement(
                            &mut d,
                            &handle,
                            receipt,
                            mutations.s4m11_duplicate_settlement_reconciles_twice,
                            mutations.s4m12_settlement_marks_applied_automatically,
                        );
                        let _ = apply_semantic(
                            &mut d,
                            &handle,
                            mutations.s4m10_duplicate_completion_applies_twice,
                            mutations.s4m14_closing_accepts_late_payload,
                            mutations.s4m03_ranking_promotes_satisfied,
                            mutations.s4m15_closing_mutates_frontier,
                        );
                        let _ = finish_if_drained(&mut d);
                        break;
                    }

                    let _ = admit_completion(
                        &mut d,
                        &handle,
                        completion.clone(),
                        mutations.s4m09_delivery_unknown_releases_commitment,
                    );
                    if cfg.fault_spec.duplicate_completion {
                        let _ = admit_completion(
                            &mut d,
                            &handle,
                            completion.clone(),
                            mutations.s4m09_delivery_unknown_releases_commitment,
                        );
                    }

                    let charge = op_def.and_then(|o| o.actual_cost).unwrap_or(cost);
                    let receipt = ExecutionReceipt {
                        request_id: req_id.clone(),
                        receipt_id: receipt_id.clone(),
                        resource: "usd".to_string(),
                        amount: charge,
                    };
                    let _ = reconcile_settlement(
                        &mut d,
                        &handle,
                        receipt.clone(),
                        mutations.s4m11_duplicate_settlement_reconciles_twice,
                        mutations.s4m12_settlement_marks_applied_automatically,
                    );

                    if cfg.fault_spec.duplicate_completion {
                        let _ = reconcile_settlement(
                            &mut d,
                            &handle,
                            receipt,
                            mutations.s4m11_duplicate_settlement_reconciles_twice,
                            mutations.s4m12_settlement_marks_applied_automatically,
                        );
                    }

                    if cfg.fault_spec.crash_after_settlement {
                        if mutations.s4m13_crash_after_settlement_loses_semantic_result {
                            // Drop unapplied in-flight completion on recovery
                            if let Some(st) = d.handles.get_mut(&handle) {
                                st.completion = None;
                            }
                        } else {
                            // Deterministic snapshot serialization and reconstruction
                            if let Ok(serialized) = serde_json::to_string(&d) {
                                if let Ok(restored) = serde_json::from_str::<ConvergeTransactionDomain>(&serialized) {
                                    d = restored;
                                }
                            }
                        }
                    }

                    let _ = apply_semantic(
                        &mut d,
                        &handle,
                        mutations.s4m10_duplicate_completion_applies_twice,
                        mutations.s4m14_closing_accepts_late_payload,
                        mutations.s4m03_ranking_promotes_satisfied,
                        mutations.s4m15_closing_mutates_frontier,
                    );

                    if cfg.fault_spec.duplicate_completion && mutations.s4m10_duplicate_completion_applies_twice {
                        let _ = apply_semantic(
                            &mut d,
                            &handle,
                            true,
                            mutations.s4m14_closing_accepts_late_payload,
                            mutations.s4m03_ranking_promotes_satisfied,
                            mutations.s4m15_closing_mutates_frontier,
                        );
                    }

                    if is_failure && d.on_step_failure == "abort" {
                        let _ = finish_if_drained(&mut d);
                        break;
                    }
                }
            }
            SchedulerAction::CheckSatisfaction(ActionCheckSatisfaction {
                node_id,
                partial: _,
                op_id,
                kind,
                cost,
            }) => {
                let count = satisfier_attempts.entry(node_id.clone()).or_insert(0);
                *count += 1;
                let attempt_no = *count;

                let sat_json = cfg.satisfier_map.get(&node_id).unwrap_or(&serde_json::Value::Null);
                let (status_tag, satisfied, sat_val_opt, err_opt) = parse_sat_entry(sat_json, attempt_no);

                let op_is_deliv_unknown = cfg.fault_spec.delivery_unknown
                    || cfg
                        .fault_spec
                        .delivery_unknown_ops
                        .contains(&op_id);

                if kind == "local" {
                    let res = check_satisfaction(
                        &mut d,
                        &node_id,
                        &op_id,
                        satisfied,
                        sat_val_opt,
                        err_opt,
                        mutations.s4m03_ranking_promotes_satisfied,
                        mutations.s4m20_satisfaction_retry_bypasses_attempt_ceiling,
                    );
                    if let Ok(true) = res {
                        close_frame(
                            &mut d,
                            ClosingReason {
                                kind: "PendingSatisfied".to_string(),
                                error: None,
                            },
                        );
                        let _ = terminalize(&mut d, mutations.s4m16_terminalizes_with_commitment);
                        break;
                    }
                    if d.frame_status == SearchStatus::Closing {
                        let _ = finish_if_drained(&mut d);
                        break;
                    }
                } else {
                    let es_def = cfg.effectful_satisfier.as_ref();
                    let req_id = es_def
                        .and_then(|o| o.request_id.clone())
                        .unwrap_or_else(|| format!("req:{}:{}:{}", op_id, node_id, attempt_no));
                    let dedup = es_def.map(|o| o.dedup_capable).unwrap_or(true);
                    let idemp = es_def.map(|o| o.idempotent).unwrap_or(true);

                    let handle_res = stage_local(
                        &mut d,
                        &node_id,
                        &op_id,
                        &req_id,
                        "usd",
                        cost,
                        dedup,
                        idemp,
                        false,
                        false,
                        mutations.s4m08_second_unsettled_request_allowed,
                        mutations.s4m04_stage_rejected_leaves_reservation,
                        mutations.s4m17_budget_scope_mints_ownership,
                    );

                    let handle = match handle_res {
                        Ok(h) => h,
                        Err(_) => break,
                    };

                    let emit_res = emit_external(
                        &mut d,
                        &handle,
                        op_is_deliv_unknown,
                        mutations.s4m06_transport_retry_increments_step,
                        mutations.s4m05_first_emit_fails_step,
                        mutations.s4m07_transport_retry_changes_request_id,
                        mutations.s4m09_delivery_unknown_releases_commitment,
                    );
                    if emit_res.is_err() {
                        break;
                    }

                    if op_is_deliv_unknown {
                        if cfg.fault_spec.cancel_in_flight {
                            cancel(&mut d);
                            let _ = confirmed_not_delivered(&mut d, &handle);
                            let _ = finish_if_drained(&mut d);
                            break;
                        }
                        if cfg.fault_spec.safe_retry && (dedup || idemp) {
                            if cfg.fault_spec.double_delivery_unknown {
                                let _ = emit_external(
                                    &mut d,
                                    &handle,
                                    true,
                                    mutations.s4m06_transport_retry_increments_step,
                                    mutations.s4m05_first_emit_fails_step,
                                    mutations.s4m07_transport_retry_changes_request_id,
                                    mutations.s4m09_delivery_unknown_releases_commitment,
                                );
                                break;
                            } else {
                                let _ = emit_external(
                                    &mut d,
                                    &handle,
                                    false,
                                    mutations.s4m06_transport_retry_increments_step,
                                    mutations.s4m05_first_emit_fails_step,
                                    mutations.s4m07_transport_retry_changes_request_id,
                                    mutations.s4m09_delivery_unknown_releases_commitment,
                                );
                            }
                        } else {
                            if mutations.s4m16_terminalizes_with_commitment {
                                exhaust(&mut d, "ForcedTerminal");
                                let _ = terminalize(&mut d, true);
                            }
                            break;
                        }
                    }

                    let sat_payload = SatisfierOutcome {
                        node_id: node_id.clone(),
                        op_id: op_id.clone(),
                        satisfied,
                        value: sat_val_opt,
                        error: err_opt,
                    };

                    let receipt_id = format!("receipt-{}", req_id);
                    let completion = CompletionRecord {
                        handle_id: handle.clone(),
                        receipt_id: receipt_id.clone(),
                        digest: format!("digest-{}", req_id),
                        outcome: if status_tag == "ok" {
                            "Success".to_string()
                        } else {
                            "Failure".to_string()
                        },
                        semantic_payload: Some(SemanticPayload::Satisfier(sat_payload)),
                        receipt: Some(ExecutionReceipt {
                            request_id: req_id.clone(),
                            receipt_id: receipt_id.clone(),
                            resource: "usd".to_string(),
                            amount: es_def.and_then(|o| o.actual_cost).unwrap_or(cost),
                        }),
                    };

                    let _ = admit_completion(
                        &mut d,
                        &handle,
                        completion.clone(),
                        mutations.s4m09_delivery_unknown_releases_commitment,
                    );
                    let charge = es_def.and_then(|o| o.actual_cost).unwrap_or(cost);
                    let receipt = ExecutionReceipt {
                        request_id: req_id.clone(),
                        receipt_id: receipt_id.clone(),
                        resource: "usd".to_string(),
                        amount: charge,
                    };
                    let _ = reconcile_settlement(
                        &mut d,
                        &handle,
                        receipt,
                        mutations.s4m11_duplicate_settlement_reconciles_twice,
                        mutations.s4m12_settlement_marks_applied_automatically,
                    );

                    let _ = apply_semantic(
                        &mut d,
                        &handle,
                        mutations.s4m10_duplicate_completion_applies_twice,
                        mutations.s4m14_closing_accepts_late_payload,
                        mutations.s4m03_ranking_promotes_satisfied,
                        mutations.s4m15_closing_mutates_frontier,
                    );

                    if d.frame_status == SearchStatus::Satisfied {
                        close_frame(
                            &mut d,
                            ClosingReason {
                                kind: "PendingSatisfied".to_string(),
                                error: None,
                            },
                        );
                        let _ = terminalize(&mut d, mutations.s4m16_terminalizes_with_commitment);
                        break;
                    }
                    if d.frame_status == SearchStatus::Closing {
                        let _ = finish_if_drained(&mut d);
                        break;
                    }
                }
            }
        }
    }

    let _ = check_all_invariants(&d);

    let status_str = match d.frame_status {
        SearchStatus::Searching => "Searching".to_string(),
        SearchStatus::Waiting => "Waiting".to_string(),
        SearchStatus::Closing => "Closing".to_string(),
        SearchStatus::Failed => "Failed".to_string(),
        SearchStatus::Satisfied => "Satisfied".to_string(),
        SearchStatus::Exhausted => "Exhausted".to_string(),
        SearchStatus::Cancelled => "Cancelled".to_string(),
    };

    let error_str = if d.frame_status == SearchStatus::Failed || d.frame_status == SearchStatus::Closing {
        d.closing_reason
            .as_ref()
            .and_then(|r| r.error.clone().or_else(|| Some(r.kind.clone())))
    } else {
        None
    };

    let curr_avail = *d.intent_available.get("usd").unwrap_or(&initial_usd);
    let avail_consumed = initial_usd.saturating_sub(curr_avail);
    let attr_reserved = d.intent_reserved.values().sum::<u64>();
    let unsettled_count = d
        .handles
        .values()
        .filter(|s| s.settlement.is_none() && s.state != "Aborted" && s.state != "ConfirmedNotDelivered")
        .count() as u64;

    let mut effs: Vec<String> = d
        .outbox
        .values()
        .filter(|rec| {
            d.first_emission_flags.get(&rec.request_id).copied().unwrap_or(false)
                && !rec.local_only
        })
        .map(|rec| format!("external({})", rec.op_id))
        .collect();
    effs.sort();

    let obs = ConvergeObservationV0 {
        status: status_str,
        value: d.satisfied_value.clone(),
        error: error_str,
        step_count: d.step_count,
        satisfaction_attempts: d.satisfaction_attempts,
        visited: d.visited.iter().map(|v| v.node_id.clone()).collect(),
        frontier: d.frontier.clone(),
        budget_spent: d.scope_spent.values().sum(),
        outstanding_scope_commitment: d.scope_committed.values().sum(),
        unsettled_request_count: unsettled_count,
        attributable_owner_reserved: attr_reserved,
        intent_available_consumed: avail_consumed,
        effects: effs,
        exhaustion_reason: if d.frame_status == SearchStatus::Exhausted {
            d.exhaustion_reason.clone()
        } else {
            None
        },
    };

    (d, obs)
}
