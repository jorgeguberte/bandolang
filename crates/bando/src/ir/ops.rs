use serde::{Deserialize, Serialize};
use super::{
    effects::Effect,
    facts::LatentPostconditions,
    types::Type,
    values::{BlockId, Value, ValueId},
};

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
}

impl Instruction {
    pub fn dest(&self) -> ValueId {
        match self {
            Instruction::Pure { dest, .. } => *dest,
            Instruction::Read { dest, .. } => *dest,
            Instruction::Infer { dest, .. } => *dest,
            Instruction::Assign { dest, .. } => *dest,
        }
    }

    pub fn required_effects(&self) -> Vec<Effect> {
        match self {
            Instruction::Pure { .. } => Vec::new(),
            Instruction::Read { domain, .. } => vec![Effect::Read(domain.clone())],
            Instruction::Infer { .. } => vec![Effect::Infer],
            Instruction::Assign { .. } => Vec::new(),
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
        ok_target: BlockId,
        ok_arg: ValueId,
        err_target: BlockId,
        err_arg: ValueId,
    },
    Unreachable,
}
