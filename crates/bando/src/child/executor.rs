use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};

use crate::{
    child::{
        budget::{BudgetError, FrameBudget},
        handle::{ChildHandleRecord, ChildSettlementState},
        provenance::ChildResultProvenance,
    },
    ir::{
        effects::{Effect, EffectRow},
        values::{BeliefValue, Value as VmValue},
    },
    registry::IntentInvocationDescriptor,
};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ChildScenarioConfig {
    pub mode: String, // "success", "semantic_failure", "settlement_unknown", "outstanding_commitment", "spawn_failure", "returns_claim", "returns_belief", "nested_delegation", etc.
    pub payload_string: Option<String>,
    pub spend_amount: Option<u64>,
    pub reserved_amount: Option<u64>,
    pub attempt_out_of_ceiling_effect: Option<Effect>,
    pub claim_predicate: Option<String>,
    pub nested_grandchild_spend: Option<u64>,
    #[serde(default)]
    pub auto_resume_settlement: bool,
}

pub trait ChildExecutor: Send + Sync {
    fn spawn_child(
        &mut self,
        descriptor: &IntentInvocationDescriptor,
        effective_authority: &BTreeSet<Effect>,
        requested_effects: &EffectRow,
        budget: FrameBudget,
        args: &[VmValue],
        parent_id: &str,
        generation_token: &str,
    ) -> Result<ChildHandleRecord, String>;

    fn poll_await(
        &mut self,
        handle: &mut ChildHandleRecord,
    ) -> Result<Option<Result<VmValue, VmValue>>, String>;

    fn settle(
        &mut self,
        handle: &mut ChildHandleRecord,
        parent_budget: &mut FrameBudget,
    ) -> Result<BTreeMap<String, u64>, String>;

    fn get_scenario(&self, intent_id: &str) -> Option<ChildScenarioConfig>;

    fn take_extra_child_handles(&mut self) -> Vec<ChildHandleRecord> {
        Vec::new()
    }

    fn take_extra_child_events(&mut self) -> Vec<String> {
        Vec::new()
    }
}

#[derive(Debug, Clone, Default)]
pub struct DefaultTestChildExecutor {
    pub scenarios: BTreeMap<String, ChildScenarioConfig>,
    pub next_child_seq: u64,
    pub observed_child_effects: Vec<String>,
    pub child_budgets: BTreeMap<String, FrameBudget>,
    pub settled_handle_ids: BTreeSet<String>,
    pub extra_child_handles: Vec<ChildHandleRecord>,
    pub extra_child_events: Vec<String>,
    pub mutations: crate::lowering::CompilerMutations,
}

impl ChildExecutor for DefaultTestChildExecutor {
    fn spawn_child(
        &mut self,
        descriptor: &IntentInvocationDescriptor,
        effective_authority: &BTreeSet<Effect>,
        requested_effects: &EffectRow,
        mut budget: FrameBudget,
        args: &[VmValue],
        parent_id: &str,
        generation_token: &str,
    ) -> Result<ChildHandleRecord, String> {
        let intent_name = descriptor.intent_id.0.clone();
        let scenario = self.scenarios.get(&intent_name).cloned();

        if let Some(sc) = &scenario {
            if sc.mode == "spawn_failure" {
                return Err("SpawnFailure: Target agent rejected spawn request".to_string());
            }
        }

        self.next_child_seq += 1;
        let child_id = format!(
            "child_{}_{}",
            descriptor.target_agent_id, self.next_child_seq
        );
        let handle_id = format!("h_{}", self.next_child_seq);

        // Section 12: Confinement check on attempted child effects
        if let Some(sc) = &scenario {
            if let Some(attempted_eff) = &sc.attempt_out_of_ceiling_effect {
                if !requested_effects.contains(attempted_eff)
                    && !self.mutations.s3m06_child_runtime_allows_out_of_ceiling
                {
                    return Err(format!(
                        "ConfinementViolation: child attempted effect {:?} outside invocation ceiling {:?}",
                        attempted_eff, requested_effects
                    ));
                }
            }
        }

        // Record child effects within invocation ceiling
        for eff in &descriptor.child_effects.effects {
            if effective_authority.contains(eff) {
                self.observed_child_effects.push(eff.to_string());
            }
        }

        // Child budget execution
        if let Some(sc) = &scenario {
            if sc.mode == "nested_delegation" {
                // Section 19: Root -> Child -> Grandchild nested delegation
                let gc_handle_id = format!("{}_gc", handle_id);
                let gc_child_id = format!("child_grandchild_{}", self.next_child_seq);
                let mut grandchild_budget = FrameBudget::new();
                let _ = budget.transfer_to_child("compute", 15, &mut grandchild_budget);
                let gc_spend = sc.nested_grandchild_spend.unwrap_or(7);
                let _ = grandchild_budget.spend_direct("compute", gc_spend);

                let mut gc_rec = ChildHandleRecord::new(
                    gc_handle_id.clone(),
                    gc_child_id.clone(),
                    child_id.clone(),
                    generation_token,
                    descriptor.child_effects.clone(),
                    ChildResultProvenance::new(
                        gc_child_id.clone(),
                        "grandchild_intent".to_string(),
                        "grandchild_agent".to_string(),
                        format!("evt_{}_gc", self.next_child_seq),
                    ),
                );

                self.extra_child_events
                    .push("Spawned(grandchild_intent)".to_string());

                let _ = budget.settle_from_child(&mut grandchild_budget);
                gc_rec.settlement_state = ChildSettlementState::Settled;
                gc_rec.budget = grandchild_budget.clone();
                self.extra_child_events
                    .push(format!("Settled({})", gc_handle_id));

                self.child_budgets
                    .insert(gc_handle_id.clone(), grandchild_budget);
                self.extra_child_handles.push(gc_rec);

                let child_spend = sc.spend_amount.unwrap_or(5);
                let _ = budget.spend_direct("compute", child_spend);
            } else {
                if let Some(sp) = sc.spend_amount {
                    let _ = budget.spend_direct("compute", sp);
                }
                if let Some(res) = sc.reserved_amount {
                    let _ = budget.reserve("compute", res);
                }
            }
        }

        let mut rec = ChildHandleRecord::new(
            handle_id.clone(),
            child_id.clone(),
            parent_id,
            generation_token,
            descriptor.child_effects.clone(),
            ChildResultProvenance::new(
                child_id.clone(),
                descriptor.intent_id.0.clone(),
                descriptor.target_agent_id.0.clone(),
                format!("evt_{}", self.next_child_seq),
            ),
        );

        // Build result
        let result_val = if let Some(sc) = &scenario {
            match sc.mode.as_str() {
                "semantic_failure" => {
                    let err_str = sc
                        .payload_string
                        .clone()
                        .unwrap_or_else(|| "WorkerSemanticError".to_string());
                    Err(VmValue::String(err_str))
                }
                "settlement_unknown" => {
                    rec.settlement_state = ChildSettlementState::SettlementUnknown;
                    let payload_str = sc
                        .payload_string
                        .clone()
                        .unwrap_or_else(|| "result_data".to_string());
                    Ok(VmValue::String(payload_str))
                }
                "outstanding_commitment" => {
                    rec.outstanding_commitments = sc.reserved_amount.unwrap_or(10);
                    let payload_str = sc
                        .payload_string
                        .clone()
                        .unwrap_or_else(|| "result_data".to_string());
                    Ok(VmValue::String(payload_str))
                }
                "returns_claim" => {
                    let claim_payload = if let Some(s) = &sc.payload_string {
                        VmValue::String(s.clone())
                    } else if let Some(first_arg) = args.first() {
                        first_arg.clone()
                    } else {
                        VmValue::String("claim_fact".to_string())
                    };
                    Ok(VmValue::claim(claim_payload))
                }
                "returns_belief" => {
                    let belief_payload = if let Some(s) = &sc.payload_string {
                        VmValue::String(s.clone())
                    } else {
                        VmValue::String("belief_data".to_string())
                    };
                    Ok(VmValue::Belief(BeliefValue {
                        payload: Box::new(belief_payload),
                        owner_agent_id: descriptor.target_agent_id.0.clone(),
                        provenance: vec![format!("child_invocation({})", descriptor.intent_id)],
                        policy_binding: "default_child_policy".to_string(),
                    }))
                }
                _ => {
                    let payload_str = sc
                        .payload_string
                        .clone()
                        .unwrap_or_else(|| "result_data".to_string());
                    Ok(VmValue::String(payload_str))
                }
            }
        } else {
            let payload_str = if let Some(VmValue::String(s)) = args.first() {
                format!("processed({})", s)
            } else {
                "worker_success".to_string()
            };
            if matches!(descriptor.output_type, crate::ir::types::Type::Claim { .. }) {
                Ok(VmValue::claim(VmValue::String(payload_str)))
            } else if matches!(
                descriptor.output_type,
                crate::ir::types::Type::Belief { .. }
            ) {
                Ok(VmValue::Belief(BeliefValue {
                    payload: Box::new(VmValue::String(payload_str)),
                    owner_agent_id: descriptor.target_agent_id.0.clone(),
                    provenance: vec![format!("child_invocation({})", descriptor.intent_id)],
                    policy_binding: "default_child_policy".to_string(),
                }))
            } else {
                Ok(VmValue::String(payload_str))
            }
        };

        rec.result = Some(result_val);
        rec.unspent_budget = budget.available.clone();
        rec.budget = budget.clone();
        self.child_budgets.insert(handle_id, budget);

        Ok(rec)
    }

    fn poll_await(
        &mut self,
        handle: &mut ChildHandleRecord,
    ) -> Result<Option<Result<VmValue, VmValue>>, String> {
        if handle.is_cancelled {
            return Err("HandleCancelled".to_string());
        }

        if handle.settlement_state == ChildSettlementState::SettlementUnknown {
            // Suspends until settlement resolves
            return Ok(None);
        }

        Ok(handle.result.clone())
    }

    fn settle(
        &mut self,
        handle: &mut ChildHandleRecord,
        parent_budget: &mut FrameBudget,
    ) -> Result<BTreeMap<String, u64>, String> {
        if handle.settlement_state == ChildSettlementState::SettlementUnknown {
            return Err("SettlementUnknown: Child settlement state unresolved".to_string());
        }

        // Section 22: CAS Unsettled -> Settled exactly once
        if self.settled_handle_ids.contains(&handle.handle_id)
            || handle.settlement_state == ChildSettlementState::Settled
        {
            return Err(BudgetError::DuplicateSettlement.to_string());
        }

        if handle.outstanding_commitments > 0 {
            return Err(BudgetError::OutstandingCommitmentsBlockSettlement {
                reserved: handle.outstanding_commitments,
            }
            .to_string());
        }

        if let Some(child_budget) = self.child_budgets.get_mut(&handle.handle_id) {
            let refund = parent_budget
                .settle_from_child(child_budget)
                .map_err(|e| e.to_string())?;
            handle.settlement_state = ChildSettlementState::Settled;
            handle.budget = child_budget.clone();
            self.settled_handle_ids.insert(handle.handle_id.clone());
            Ok(refund)
        } else {
            handle.settlement_state = ChildSettlementState::Settled;
            self.settled_handle_ids.insert(handle.handle_id.clone());
            Ok(BTreeMap::new())
        }
    }

    fn get_scenario(&self, intent_id: &str) -> Option<ChildScenarioConfig> {
        self.scenarios.get(intent_id).cloned()
    }

    fn take_extra_child_handles(&mut self) -> Vec<ChildHandleRecord> {
        std::mem::take(&mut self.extra_child_handles)
    }

    fn take_extra_child_events(&mut self) -> Vec<String> {
        std::mem::take(&mut self.extra_child_events)
    }
}
