use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

use crate::{
    ir::{
        effects::{Effect, EffectRow},
        facts::{ActLatentPostconditions, LatentPostconditions},
        types::Type,
        values::Value as VmValue,
    },
    registry::{IntentId, OperationId, PolicyId, VerifierId},
};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
pub struct VmValueId(pub u32);

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
pub struct VmBlockId(pub u32);

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum VmInstruction {
    VmPure {
        dest: VmValueId,
        val: VmValue,
        ty: Type,
    },
    VmRead {
        dest: VmValueId,
        domain: String,
        ok_type: Type,
        err_type: Type,
        latent: LatentPostconditions,
    },
    VmInfer {
        dest: VmValueId,
        prompt: String,
        ok_type: Type,
        err_type: Type,
        latent: LatentPostconditions,
    },
    VmAssign {
        dest: VmValueId,
        source: VmValueId,
        ty: Type,
    },
    VmVerify {
        dest: VmValueId,
        verifier_id: VerifierId,
        subject: VmValueId,
        output_predicate: String,
        subject_type: Type,
        verifier_effects: Vec<Effect>,
    },
    VmAct {
        dest: VmValueId,
        op_id: OperationId,
        target_domain: String,
        success_type: Type,
        failure_type: Type,
        args: Vec<VmValueId>,
        evidence: Vec<VmValueId>,
        gate_effects: Vec<Effect>,
        latent: ActLatentPostconditions,
    },
    // Slice 3 VM Instructions
    VmSpawnChild {
        dest: VmValueId,
        intent_id: IntentId,
        args: Vec<VmValueId>,
        requested_effects: Vec<Effect>,
        authority_grant: Vec<Effect>,
        budget_grant: u64,
        child_effects: Vec<Effect>,
        ok_type: Type,
        err_type: Type,
    },
    VmAwaitChild {
        dest: VmValueId,
        handle: VmValueId,
        ok_type: Type,
        err_type: Type,
    },
    VmInternalize {
        dest: VmValueId,
        policy_id: PolicyId,
        claim: VmValueId,
        validation_effects: Vec<Effect>,
        payload_type: Type,
        latent: LatentPostconditions,
    },
    // Slice 4: soma.converge explicit machine operations
    VmConvergeInit {
        frame_var: VmValueId,
        root_node: String,
        budget_resource: String,
        budget_limit: u64,
        max_steps: u64,
        max_satisfaction_attempts: u64,
        on_step_failure: String,
        on_satisfier_error: String,
    },
    VmConvergeStep {
        dest: VmValueId,
        frame_var: VmValueId,
        space_ops: Vec<OperationId>,
        satisfier_op: OperationId,
        space_effects: EffectRow,
        satisfier_effects: EffectRow,
        partial_type: Type,
        satisfied_type: Type,
    },
}

impl VmInstruction {
    pub fn dest(&self) -> VmValueId {
        match self {
            VmInstruction::VmPure { dest, .. } => *dest,
            VmInstruction::VmRead { dest, .. } => *dest,
            VmInstruction::VmInfer { dest, .. } => *dest,
            VmInstruction::VmAssign { dest, .. } => *dest,
            VmInstruction::VmVerify { dest, .. } => *dest,
            VmInstruction::VmAct { dest, .. } => *dest,
            VmInstruction::VmSpawnChild { dest, .. } => *dest,
            VmInstruction::VmAwaitChild { dest, .. } => *dest,
            VmInstruction::VmInternalize { dest, .. } => *dest,
            VmInstruction::VmConvergeInit { frame_var, .. } => *frame_var,
            VmInstruction::VmConvergeStep { dest, .. } => *dest,
        }
    }

    pub fn required_effects(&self) -> Vec<Effect> {
        match self {
            VmInstruction::VmPure { .. } => Vec::new(),
            VmInstruction::VmRead { domain, .. } => vec![Effect::Read(domain.clone())],
            VmInstruction::VmInfer { .. } => vec![Effect::Infer],
            VmInstruction::VmAssign { .. } => Vec::new(),
            VmInstruction::VmVerify {
                verifier_effects, ..
            } => verifier_effects.clone(),
            VmInstruction::VmAct {
                target_domain,
                gate_effects,
                ..
            } => {
                let mut effs = vec![Effect::Act(target_domain.clone())];
                effs.extend(gate_effects.iter().cloned());
                effs
            }
            VmInstruction::VmSpawnChild { child_effects, .. } => child_effects.clone(),
            VmInstruction::VmAwaitChild { .. } => Vec::new(),
            VmInstruction::VmInternalize {
                validation_effects, ..
            } => validation_effects.clone(),
            VmInstruction::VmConvergeInit { .. } => Vec::new(),
            VmInstruction::VmConvergeStep {
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
pub enum VmTerminator {
    Return(Option<VmValueId>),
    Br {
        target: VmBlockId,
        args: Vec<VmValueId>,
    },
    CondBr {
        cond: VmValueId,
        true_target: VmBlockId,
        true_args: Vec<VmValueId>,
        false_target: VmBlockId,
        false_args: Vec<VmValueId>,
    },
    SwitchResult {
        result_val: VmValueId,
        ok_target: VmBlockId,
        ok_arg: VmValueId,
        err_target: VmBlockId,
        err_arg: VmValueId,
    },
    SwitchActOutcome {
        outcome_val: VmValueId,
        success_target: VmBlockId,
        success_arg: VmValueId,
        failure_target: VmBlockId,
        failure_arg: VmValueId,
        partial_target: VmBlockId,
        partial_arg: VmValueId,
        unknown_target: VmBlockId,
        unknown_arg: VmValueId,
    },
    Unreachable,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct VmBlock {
    pub id: VmBlockId,
    pub name: Option<String>,
    pub params: Vec<(VmValueId, Type)>,
    pub instructions: Vec<VmInstruction>,
    pub terminator: VmTerminator,
}

impl VmBlock {
    pub fn new(id: VmBlockId, terminator: VmTerminator) -> Self {
        Self {
            id,
            name: None,
            params: Vec::new(),
            instructions: Vec::new(),
            terminator,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct VmFunction {
    pub name: String,
    pub params: Vec<(VmValueId, Type)>,
    pub return_type: Type,
    pub declared_effects: EffectRow,
    pub entry: VmBlockId,
    pub blocks: BTreeMap<VmBlockId, VmBlock>,
}

impl VmFunction {
    pub fn new(name: impl Into<String>, entry: VmBlockId, return_type: Type) -> Self {
        Self {
            name: name.into(),
            params: Vec::new(),
            return_type,
            declared_effects: EffectRow::empty(),
            entry,
            blocks: BTreeMap::new(),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct VmModule {
    pub name: String,
    pub functions: Vec<VmFunction>,
}

impl VmModule {
    pub fn new(name: impl Into<String>) -> Self {
        Self {
            name: name.into(),
            functions: Vec::new(),
        }
    }
}
