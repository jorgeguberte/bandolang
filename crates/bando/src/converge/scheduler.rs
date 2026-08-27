use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

use crate::{
    converge::domain::{ConvergeTransactionDomain, SatisfactionState, SearchStatus},
    ir::values::Value,
};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ActionExpand {
    pub node_id: String,
    pub op_id: String,
    pub kind: String, // "local" | "external"
    pub cost: u64,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ActionCheckSatisfaction {
    pub node_id: String,
    pub partial: Value,
    pub op_id: String,
    pub kind: String, // "local" | "external"
    pub cost: u64,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum SchedulerAction {
    Expand(ActionExpand),
    CheckSatisfaction(ActionCheckSatisfaction),
    Wait { reason: String },
    Stop { reason: String }, // "BudgetDepleted" | "FrontierEmpty" | "FuelExhausted"
}

pub fn classify_runnable(
    d: &ConvergeTransactionDomain,
    cost: u64,
    resource: &str,
    mints_ownership: bool,
) -> bool {
    if cost == 0 {
        return true;
    }
    let spent = *d.scope_spent.get(resource).unwrap_or(&0);
    let committed = *d.scope_committed.get(resource).unwrap_or(&0);
    let limit = *d.scope_limit.get(resource).unwrap_or(&0);
    let avail_scope = limit.saturating_sub(spent + committed);
    let avail_intent = *d.intent_available.get(resource).unwrap_or(&0);
    if mints_ownership {
        avail_scope >= cost
    } else {
        avail_scope >= cost && avail_intent >= cost
    }
}

#[derive(Debug, Clone, Default)]
pub struct SpaceOpInfo {
    pub op_id: String,
    pub kind: String,
    pub cost: u64,
}

#[derive(Debug, Clone, Default)]
pub struct SatisfierOpInfo {
    pub op_id: String,
    pub kind: String,
    pub cost: u64,
}

pub fn scheduler_step(
    d: &mut ConvergeTransactionDomain,
    node_ops: &BTreeMap<String, SpaceOpInfo>,
    partial_map: &BTreeMap<String, Value>,
    effectful_satisfier: Option<&SatisfierOpInfo>,
    mutations_scheduler_pops_unaffordable: bool,
    mutations_budget_scope_mints_ownership: bool,
    mutations_satisfaction_retry_bypasses_limit: bool,
    mutations_second_unsettled_allowed: bool,
) -> SchedulerAction {
    // 1. In-flight check
    let unsettled: Vec<_> = d
        .handles
        .values()
        .filter(|s| {
            s.settlement.is_none() && s.state != "Aborted" && s.state != "ConfirmedNotDelivered"
        })
        .collect();
    if !unsettled.is_empty() && !mutations_second_unsettled_allowed {
        d.frame_status = SearchStatus::Waiting;
        return SchedulerAction::Wait {
            reason: format!("InFlight({})", unsettled[0].handle_id),
        };
    }

    let mut eligible_checks = Vec::new();
    let mut eligible_expansions = Vec::new();

    // 2. Eligible satisfaction checks
    if d.satisfaction_attempts < d.max_satisfaction_attempts
        || mutations_satisfaction_retry_bypasses_limit
    {
        for (n, node_obj) in &d.nodes {
            if let Some(partial_val) = partial_map.get(n) {
                if matches!(
                    node_obj.satisfaction_state,
                    SatisfactionState::Untested | SatisfactionState::RetryableFailure
                ) {
                    if let Some(es) = effectful_satisfier {
                        if classify_runnable(
                            d,
                            es.cost,
                            "usd",
                            mutations_budget_scope_mints_ownership,
                        ) {
                            eligible_checks.push(ActionCheckSatisfaction {
                                node_id: n.clone(),
                                partial: partial_val.clone(),
                                op_id: es.op_id.clone(),
                                kind: es.kind.clone(),
                                cost: es.cost,
                            });
                        }
                    } else {
                        eligible_checks.push(ActionCheckSatisfaction {
                            node_id: n.clone(),
                            partial: partial_val.clone(),
                            op_id: "local_satisfier".to_string(),
                            kind: "local".to_string(),
                            cost: 0,
                        });
                    }
                }
            }
        }
    }

    // 3. Eligible expansions from frontier
    if d.step_count < d.max_steps {
        for n in &d.frontier {
            let op = node_ops.get(n);
            let cost = op
                .map(|o| if o.kind == "external" { o.cost } else { 0 })
                .unwrap_or(0);
            let kind = op
                .map(|o| o.kind.clone())
                .unwrap_or_else(|| "local".to_string());
            let op_id = op
                .map(|o| o.op_id.clone())
                .unwrap_or_else(|| format!("op:{}", n));

            if classify_runnable(d, cost, "usd", mutations_budget_scope_mints_ownership)
                || mutations_scheduler_pops_unaffordable
            {
                eligible_expansions.push(ActionExpand {
                    node_id: n.clone(),
                    op_id,
                    kind,
                    cost,
                });
            }
        }
    }

    if let Some(chk) = eligible_checks.into_iter().next() {
        return SchedulerAction::CheckSatisfaction(chk);
    }
    if let Some(exp) = eligible_expansions.into_iter().next() {
        return SchedulerAction::Expand(exp);
    }

    if d.step_count >= d.max_steps {
        return SchedulerAction::Stop {
            reason: "FuelExhausted".to_string(),
        };
    }
    if d.frontier.is_empty() {
        return SchedulerAction::Stop {
            reason: "FrontierEmpty".to_string(),
        };
    }
    SchedulerAction::Stop {
        reason: "BudgetDepleted".to_string(),
    }
}
