use serde::{Deserialize, Serialize};

use crate::registry::{OperationId, VerifierId};

use super::{
    effects::Effect,
    facts::{ActLatentPostconditions, LatentPostconditions},
    types::Type,
    values::{BlockId, Value, ValueId},
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
    Br {
        target: BlockId,
        args: Vec<ValueId>,
    },
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
        }
    }

    pub fn required_effects(&self) -> Vec<Effect> {
        match self {
            Instruction::Pure { .. } => Vec::new(),
            Instruction::Read { domain, .. } => vec![Effect::Read(domain.clone())],
            Instruction::Infer { .. } => vec![Effect::Infer],
            Instruction::Assign { .. } => Vec::new(),
            // Rule #1: verify inherits exactly the verifier's effect envelope (NO phantom Effect::Verify)
            Instruction::Verify { verifier_effects, .. } => verifier_effects.clone(),
            // Rule #9: Σ_act = { act[D] } ∪ Σ_gate
            Instruction::Act { target_domain, gate_effects, .. } => {
                let mut effs = vec![Effect::Act(target_domain.clone())];
                effs.extend(gate_effects.iter().cloned());
                effs
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
