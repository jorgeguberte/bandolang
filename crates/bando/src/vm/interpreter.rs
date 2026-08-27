use std::collections::{BTreeMap, BTreeSet};
use serde::{Deserialize, Serialize};

use crate::{
    analysis::PathFactAnalyzer,
    ir::{
        facts::{Fact, LatentPostconditions},
        types::Type,
        values::Value as VmValue,
    },
    vm::adapters::RuntimeAdapters,
    vm_ir::{VmBlockId, VmFunction, VmInstruction, VmTerminator, VmValueId},
};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum VmStatus {
    Running,
    Terminated,
    ProtocolViolation(String),
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct VmExecutionState {
    pub current_block: VmBlockId,
    pub env: BTreeMap<String, VmValue>,
    pub types: BTreeMap<String, Type>,
    pub latent: BTreeMap<String, LatentPostconditions>,
    pub observable_effects: Vec<String>,
    pub lineage: BTreeMap<String, Vec<String>>,
    pub active_facts: BTreeSet<Fact>,
    pub status: VmStatus,
    pub return_value: Option<VmValue>,
}

pub struct VmInterpreter<'a> {
    func: &'a VmFunction,
    adapters: &'a RuntimeAdapters,
    mutations: crate::lowering::CompilerMutations,
}

impl<'a> VmInterpreter<'a> {
    pub fn new(func: &'a VmFunction, adapters: &'a RuntimeAdapters) -> Self {
        Self {
            func,
            adapters,
            mutations: crate::lowering::CompilerMutations::default(),
        }
    }

    pub fn with_mutations(
        func: &'a VmFunction,
        adapters: &'a RuntimeAdapters,
        mutations: crate::lowering::CompilerMutations,
    ) -> Self {
        Self { func, adapters, mutations }
    }

    pub fn execute(&self, inputs: BTreeMap<VmValueId, VmValue>, max_steps: usize) -> VmExecutionState {
        let mut state = VmExecutionState {
            current_block: self.func.entry,
            env: BTreeMap::new(),
            types: BTreeMap::new(),
            latent: BTreeMap::new(),
            observable_effects: Vec::new(),
            lineage: BTreeMap::new(),
            active_facts: BTreeSet::new(),
            status: VmStatus::Running,
            return_value: None,
        };

        // Populate function parameters
        for (param_id, param_type) in &self.func.params {
            state.types.insert(format!("v{}", param_id.0), param_type.clone());
            if let Some(val) = inputs.get(param_id) {
                state.env.insert(format!("v{}", param_id.0), val.clone());
            }
        }

        // Run static path fact analysis to compute fixed point facts for blocks
        let analysis = PathFactAnalyzer::with_mutations(self.func, self.mutations.clone()).analyze();

        let mut steps = 0;
        while state.status == VmStatus::Running && steps < max_steps {
            steps += 1;

            let block = match self.func.blocks.get(&state.current_block) {
                Some(b) => b,
                None => {
                    state.status = VmStatus::ProtocolViolation(format!("Block {:?} not found", state.current_block));
                    break;
                }
            };

            // Update active facts from block entry fixed point
            if let Some(in_facts) = analysis.block_in_facts.get(&state.current_block) {
                state.active_facts = in_facts.clone();
            }

            // Execute instructions
            for inst in &block.instructions {
                self.exec_instruction(inst, &mut state);
                if state.status != VmStatus::Running {
                    break;
                }
            }

            if state.status != VmStatus::Running {
                break;
            }

            // Execute terminator
            self.exec_terminator(&block.terminator, &mut state);
        }

        state
    }

    fn exec_instruction(&self, inst: &VmInstruction, state: &mut VmExecutionState) {
        match inst {
            VmInstruction::VmPure { dest, val, ty } => {
                let sym = format!("v{}", dest.0);
                state.env.insert(sym.clone(), val.clone());
                state.types.insert(sym, ty.clone());
            }
            VmInstruction::VmRead {
                dest,
                domain,
                ok_type,
                err_type,
                latent,
            } => {
                let sym = format!("v{}", dest.0);
                state.observable_effects.push(format!("read[{}]", domain));
                state.latent.insert(sym.clone(), latent.clone());
                state.types.insert(sym.clone(), Type::result(ok_type.clone(), err_type.clone()));
                state.lineage.insert(sym.clone(), vec![format!("read({})", domain)]);

                let val = match self.adapters.read.read(domain) {
                    Ok(v) => VmValue::ok(v),
                    Err(e) => VmValue::err(e),
                };
                state.env.insert(sym, val);
            }
            VmInstruction::VmInfer {
                dest,
                prompt,
                ok_type,
                err_type,
                latent,
            } => {
                let sym = format!("v{}", dest.0);
                state.observable_effects.push("infer".to_string());
                state.latent.insert(sym.clone(), latent.clone());
                state.types.insert(sym.clone(), Type::result(ok_type.clone(), err_type.clone()));
                state.lineage.insert(sym.clone(), vec![format!("infer({})", prompt)]);

                let val = match self.adapters.infer.infer(prompt) {
                    Ok(v) => VmValue::ok(v),
                    Err(e) => VmValue::err(e),
                };
                state.env.insert(sym, val);
            }
            VmInstruction::VmAssign { dest, source, ty } => {
                let dest_sym = format!("v{}", dest.0);
                let src_sym = format!("v{}", source.0);

                if let Some(val) = state.env.get(&src_sym).cloned() {
                    state.env.insert(dest_sym.clone(), val);
                }
                if let Some(lat) = state.latent.get(&src_sym).cloned() {
                    state.latent.insert(dest_sym.clone(), lat);
                }
                if let Some(lin) = state.lineage.get(&src_sym).cloned() {
                    state.lineage.insert(dest_sym.clone(), lin);
                }
                state.types.insert(dest_sym, ty.clone());
            }
        }
    }

    fn exec_terminator(&self, term: &VmTerminator, state: &mut VmExecutionState) {
        match term {
            VmTerminator::Return(val_opt) => {
                state.status = VmStatus::Terminated;
                if let Some(val_id) = val_opt {
                    let sym = format!("v{}", val_id.0);
                    state.return_value = state.env.get(&sym).cloned();
                }
            }
            VmTerminator::Br { target, args } => {
                self.transfer_control(*target, args, state);
            }
            VmTerminator::CondBr {
                cond,
                true_target,
                true_args,
                false_target,
                false_args,
            } => {
                let cond_sym = format!("v{}", cond.0);
                let cond_val = state.env.get(&cond_sym);
                match cond_val {
                    Some(VmValue::Bool(true)) => {
                        self.transfer_control(*true_target, true_args, state);
                    }
                    Some(VmValue::Bool(false)) => {
                        self.transfer_control(*false_target, false_args, state);
                    }
                    _ => {
                        state.status = VmStatus::ProtocolViolation(format!("Non-boolean CondBr condition {:?}", cond_val));
                    }
                }
            }
            VmTerminator::SwitchResult {
                result_val,
                ok_target,
                ok_arg,
                err_target,
                err_arg,
            } => {
                let res_sym = format!("v{}", result_val.0);
                let res_val = state.env.get(&res_sym).cloned();

                match res_val {
                    Some(VmValue::Ok(inner)) => {
                        let arg_sym = format!("v{}", ok_arg.0);
                        state.env.insert(arg_sym, *inner);
                        self.transfer_control(*ok_target, &[*ok_arg], state);
                    }
                    Some(VmValue::Err(inner)) => {
                        let arg_sym = format!("v{}", err_arg.0);
                        state.env.insert(arg_sym, *inner);
                        self.transfer_control(*err_target, &[*err_arg], state);
                    }
                    _ => {
                        state.status = VmStatus::ProtocolViolation(format!("SwitchResult on non-Result value {:?}", res_val));
                    }
                }
            }
            VmTerminator::Unreachable => {
                state.status = VmStatus::ProtocolViolation("Executed Unreachable terminator".to_string());
            }
        }
    }

    fn transfer_control(&self, target: VmBlockId, args: &[VmValueId], state: &mut VmExecutionState) {
        let target_block = match self.func.blocks.get(&target) {
            Some(b) => b,
            None => {
                state.status = VmStatus::ProtocolViolation(format!("Target block {:?} not found", target));
                return;
            }
        };

        // Bind block arguments to target parameters
        for (i, (param_id, param_ty)) in target_block.params.iter().enumerate() {
            let param_sym = format!("v{}", param_id.0);
            state.types.insert(param_sym.clone(), param_ty.clone());
            if i < args.len() {
                let arg_sym = format!("v{}", args[i].0);
                if let Some(val) = state.env.get(&arg_sym).cloned() {
                    state.env.insert(param_sym.clone(), val);
                }
                if let Some(lat) = state.latent.get(&arg_sym).cloned() {
                    state.latent.insert(param_sym.clone(), lat);
                }
                if let Some(lin) = state.lineage.get(&arg_sym).cloned() {
                    state.lineage.insert(param_sym.clone(), lin);
                }
            }
        }

        state.current_block = target;
    }
}
