use crate::converge::domain::ConvergeTransactionDomain;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct InvariantViolation {
    pub invariant: String,
    pub message: String,
}

pub fn check_i1_unsettled_request_limit(
    d: &ConvergeTransactionDomain,
) -> Result<(), InvariantViolation> {
    let unsettled: Vec<_> = d
        .handles
        .values()
        .filter(|s| {
            s.settlement.is_none() && s.state != "Aborted" && s.state != "ConfirmedNotDelivered"
        })
        .collect();
    if unsettled.len() > 1 {
        return Err(InvariantViolation {
            invariant: "I1".to_string(),
            message: format!(
                "I1 violated: {} unsettled requests in flight (limit is 1)",
                unsettled.len()
            ),
        });
    }
    Ok(())
}

pub fn check_i2_terminal_no_in_flight(
    d: &ConvergeTransactionDomain,
) -> Result<(), InvariantViolation> {
    if d.frame_status.is_terminal() {
        let in_flight = d.handles.values().any(|s| {
            s.settlement.is_none() && s.state != "Aborted" && s.state != "ConfirmedNotDelivered"
        });
        if in_flight {
            return Err(InvariantViolation {
                invariant: "I2".to_string(),
                message: "I2 violated: terminal frame status with active in-flight requests"
                    .to_string(),
            });
        }
    }
    Ok(())
}

pub fn check_i3_terminal_no_commitments(
    d: &ConvergeTransactionDomain,
) -> Result<(), InvariantViolation> {
    if d.frame_status.is_terminal() {
        let committed = d.scope_committed.values().sum::<u64>();
        let reserved = d.intent_reserved.values().sum::<u64>();
        if committed > 0 || reserved > 0 {
            return Err(InvariantViolation {
                invariant: "I3".to_string(),
                message: format!(
                    "I3 violated: terminal frame with active scope commitment ({}) or intent reservation ({})",
                    committed, reserved
                ),
            });
        }
    }
    Ok(())
}

pub fn check_i6_completion_applied_at_most_once(
    d: &ConvergeTransactionDomain,
) -> Result<(), InvariantViolation> {
    let mut seen = std::collections::BTreeSet::new();
    for c_id in &d.applied_completions {
        if !seen.insert(c_id) {
            return Err(InvariantViolation {
                invariant: "I6".to_string(),
                message: format!("I6 violated: completion '{}' applied more than once", c_id),
            });
        }
    }
    Ok(())
}

pub fn check_i7_settlement_reconciled_once(
    d: &ConvergeTransactionDomain,
) -> Result<(), InvariantViolation> {
    for (h_id, count) in &d.settlement_reconciliations {
        if *count > 1 {
            return Err(InvariantViolation {
                invariant: "I7".to_string(),
                message: format!("I7 violated: handle '{}' settled {} times", h_id, count),
            });
        }
    }
    Ok(())
}

pub fn check_i8_closing_frontier_frozen(
    d: &ConvergeTransactionDomain,
) -> Result<(), InvariantViolation> {
    if d.frontier_mutations_during_closing > 0 {
        return Err(InvariantViolation {
            invariant: "I8".to_string(),
            message: format!(
                "I8 violated: {} frontier mutations occurred during Closing",
                d.frontier_mutations_during_closing
            ),
        });
    }
    Ok(())
}

pub fn check_i9_visited_matches_dispatch(
    d: &ConvergeTransactionDomain,
) -> Result<(), InvariantViolation> {
    for v in &d.visited {
        let has_dispatch = d.dispatches.iter().any(|disp| {
            disp.node_id == v.node_id && disp.op_id == v.op_id && disp.visit_no == v.visit_no
        });
        if !has_dispatch {
            return Err(InvariantViolation {
                invariant: "I9".to_string(),
                message: format!(
                    "I9 violated: visited record {}:{}#{} has no matching dispatch record",
                    v.op_id, v.node_id, v.visit_no
                ),
            });
        }
    }
    Ok(())
}

pub fn check_i10_budget_scope_conservation(
    d: &ConvergeTransactionDomain,
) -> Result<(), InvariantViolation> {
    for (res, spent) in &d.scope_spent {
        let committed = d.scope_committed.get(res).unwrap_or(&0);
        let limit = d.scope_limit.get(res).unwrap_or(&0);
        if spent + committed > *limit {
            return Err(InvariantViolation {
                invariant: "I10".to_string(),
                message: format!(
                    "I10 violated: scope spent ({}) + committed ({}) exceeds scope limit ({}) for {}",
                    spent, committed, limit, res
                ),
            });
        }
    }
    Ok(())
}

pub fn check_all_invariants(d: &ConvergeTransactionDomain) -> Result<(), InvariantViolation> {
    check_i1_unsettled_request_limit(d)?;
    check_i2_terminal_no_in_flight(d)?;
    check_i3_terminal_no_commitments(d)?;
    check_i6_completion_applied_at_most_once(d)?;
    check_i7_settlement_reconciled_once(d)?;
    check_i8_closing_frontier_frozen(d)?;
    check_i9_visited_matches_dispatch(d)?;
    check_i10_budget_scope_conservation(d)?;
    Ok(())
}
