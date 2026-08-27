use serde::{Deserialize, Serialize};

use crate::{
    ir::{
        effects::{Effect, EffectRow},
        facts::{ActLatentPostconditions, LatentPostconditions},
        types::Type,
        values::{BlockId, Value, ValueId},
    },
    registry::{IntentId, OperationId, PolicyId, VerifierId},
};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Region {
    pub instructions: Vec<Instruction>,
    pub terminator: RegionTerminator,
}

impl Region {
    pub fn new(terminator: RegionTerminator) -> Self {
        Self {
            instructions: Vec::new(),
            terminator,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum RegionTerminator {
    Return(Option<ValueId>),
    Br { target: BlockId, args: Vec<ValueId> },
    Unreachable,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum Instruction {
    Pure {
        dest: ValueId,
        val: Value,
        ty: Type,
    },
    Read {
        dest: ValueId,
        domain: String,
        ok_type: Type,
        err_type: Type,
        latent: LatentPostconditions,
    },
    Infer {
        dest: ValueId,
        prompt: String,
        ok_type: Type,
        err_type: Type,
        latent: LatentPostconditions,
    },
    Assign {
        dest: ValueId,
        source: ValueId,
        ty: Type,
    },
    Verify {
        dest: ValueId,
        verifier_id: VerifierId,
        subject: ValueId,
        #[serde(default)]
        output_predicate: String,
        #[serde(default = "default_subject_type")]
        subject_type: Type,
        #[serde(default)]
        verifier_effects: Vec<Effect>,
    },
    Act {
        dest: ValueId,
        op_id: OperationId,
        #[serde(default)]
        target_domain: String,
        success_type: Type,
        failure_type: Type,
        args: Vec<ValueId>,
        evidence: Vec<ValueId>,
        #[serde(default)]
        gate_effects: Vec<Effect>,
        #[serde(default)]
        latent: ActLatentPostconditions,
    },
    // Slice 3 Instructions
    Delegate {
        dest: ValueId,
        intent_id: IntentId,
        args: Vec<ValueId>,
        #[serde(default)]
        requested_effects: Vec<Effect>,
        #[serde(default)]
        authority_grant: Vec<Effect>,
        #[serde(default)]
        budget_grant: u64,
    },
    Await {
        dest: ValueId,
        handle: ValueId,
    },
    Internalize {
        dest: ValueId,
        policy_id: PolicyId,
        claim: ValueId,
    },
    // Slice 4: soma.converge
    Converge {
        dest: ValueId,
        root_node: String,
        #[serde(default)]
        initial_frontier: Vec<String>,
        #[serde(default)]
        successors: std::collections::BTreeMap<String, Vec<String>>,
        #[serde(default)]
        node_ops: std::collections::BTreeMap<String, SpaceOpDef>,
        #[serde(default)]
        satisfier: SatisfierDef,
        #[serde(default)]
        partial_map: std::collections::BTreeMap<String, Value>,
        #[serde(default)]
        space_faults: std::collections::BTreeMap<String, serde_json::Value>,
        #[serde(default)]
        fault_spec: ConvergeFaultSpec,
        #[serde(default)]
        space_ops: Vec<OperationId>,
        #[serde(default)]
        satisfier_op: OperationId,
        search_policy: SearchPolicyDescriptor,
        budget_scope: BudgetScopeConfig,
        max_steps: u64,
        max_satisfaction_attempts: u64,
        #[serde(default)]
        space_effects: EffectRow,
        #[serde(default)]
        satisfier_effects: EffectRow,
        partial_type: Type,
        satisfied_type: Type,
    },
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct SpaceOpDef {
    pub op_id: String,
    #[serde(default = "default_local_kind")]
    pub kind: String, // "local" | "external"
    #[serde(default)]
    pub cost: u64,
    #[serde(default)]
    pub actual_cost: Option<u64>,
    #[serde(default)]
    pub request_id: Option<String>,
    #[serde(default = "default_true")]
    pub dedup_capable: bool,
    #[serde(default = "default_true")]
    pub idempotent: bool,
    #[serde(default)]
    pub required_effects: Vec<Effect>,
}

impl SpaceOpDef {
    pub fn effective_effects(&self) -> Vec<Effect> {
        if !self.required_effects.is_empty() {
            self.required_effects.clone()
        } else if self.kind == "external" {
            vec![Effect::Act(self.op_id.clone())]
        } else {
            Vec::new()
        }
    }
}

impl Default for SpaceOpDef {
    fn default() -> Self {
        Self {
            op_id: "op".to_string(),
            kind: "local".to_string(),
            cost: 0,
            actual_cost: None,
            request_id: None,
            dedup_capable: true,
            idempotent: true,
            required_effects: Vec::new(),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct SatisfierDef {
    #[serde(default = "default_local_kind")]
    pub kind: String, // "local" | "external"
    #[serde(default)]
    pub effectful_op: Option<SpaceOpDef>,
    #[serde(default)]
    pub satisfier_map: std::collections::BTreeMap<String, serde_json::Value>,
}

impl Default for SatisfierDef {
    fn default() -> Self {
        Self {
            kind: "local".to_string(),
            effectful_op: None,
            satisfier_map: std::collections::BTreeMap::new(),
        }
    }
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct ConvergeFaultSpec {
    #[serde(default)]
    pub delivery_unknown: bool,
    #[serde(default)]
    pub delivery_unknown_ops: Vec<String>,
    #[serde(default)]
    pub safe_retry: bool,
    #[serde(default)]
    pub double_delivery_unknown: bool,
    #[serde(default)]
    pub duplicate_completion: bool,
    #[serde(default)]
    pub crash_after_settlement: bool,
    #[serde(default)]
    pub cancel_in_flight: bool,
}

fn default_local_kind() -> String {
    "local".to_string()
}

fn default_true() -> bool {
    true
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct SearchPolicyDescriptor {
    pub policy_id: String,
    #[serde(default = "default_abort_policy")]
    pub on_step_failure: String, // "abort" | "prune" | "requeue"
    #[serde(default = "default_abort_policy")]
    pub on_satisfier_error: String, // "abort" | "retry"
    #[serde(default)]
    pub policy_effects: EffectRow,
}

fn default_abort_policy() -> String {
    "abort".to_string()
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct BudgetScopeConfig {
    pub resource: String,
    pub limit: u64,
}

fn default_subject_type() -> Type {
    Type::String
}

impl Instruction {
    pub fn dest(&self) -> ValueId {
        match self {
            Instruction::Pure { dest, .. } => *dest,
            Instruction::Read { dest, .. } => *dest,
            Instruction::Infer { dest, .. } => *dest,
            Instruction::Assign { dest, .. } => *dest,
            Instruction::Verify { dest, .. } => *dest,
            Instruction::Act { dest, .. } => *dest,
            Instruction::Delegate { dest, .. } => *dest,
            Instruction::Await { dest, .. } => *dest,
            Instruction::Internalize { dest, .. } => *dest,
            Instruction::Converge { dest, .. } => *dest,
        }
    }

    pub fn required_effects(&self) -> Vec<Effect> {
        match self {
            Instruction::Pure { .. } => Vec::new(),
            Instruction::Read { domain, .. } => vec![Effect::Read(domain.clone())],
            Instruction::Infer { .. } => vec![Effect::Infer],
            Instruction::Assign { .. } => Vec::new(),
            Instruction::Verify {
                verifier_effects, ..
            } => verifier_effects.clone(),
            Instruction::Act {
                target_domain,
                gate_effects,
                ..
            } => {
                let mut effs = vec![Effect::Act(target_domain.clone())];
                effs.extend(gate_effects.iter().cloned());
                effs
            }
            // Section 8: delegate carries Σ_child (requested_effects as IR placeholder)
            Instruction::Delegate {
                requested_effects, ..
            } => requested_effects.clone(),
            // Section 24: Σ_await = ∅
            Instruction::Await { .. } => Vec::new(),
            // Section 46: Σ_internalize = Σ_validation
            Instruction::Internalize { .. } => Vec::new(),
            // Slice 4: Σ_converge = Σ_space ∪ Σ_satisfier, Σ_search_policy = ∅
            Instruction::Converge {
                space_effects,
                satisfier_effects,
                ..
            } => {
                let mut effs = space_effects.effects.clone();
                effs.extend(satisfier_effects.effects.clone());
                effs.into_iter().collect()
            }
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum Terminator {
    Return(Option<ValueId>),
    Br {
        target: BlockId,
        args: Vec<ValueId>,
    },
    CondBr {
        cond: ValueId,
        true_target: BlockId,
        true_args: Vec<ValueId>,
        false_target: BlockId,
        false_args: Vec<ValueId>,
    },
    MatchResult {
        result_val: ValueId,
        ok_arg: ValueId,
        ok_body: Region,
        err_arg: ValueId,
        err_body: Region,
    },
    MatchActOutcome {
        outcome_val: ValueId,
        success_arg: ValueId,
        success_body: Region,
        failure_arg: ValueId,
        failure_body: Region,
        partial_arg: ValueId,
        partial_body: Region,
        unknown_arg: ValueId,
        unknown_body: Region,
    },
    Unreachable,
}
