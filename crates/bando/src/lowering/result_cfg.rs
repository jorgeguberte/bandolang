use std::collections::BTreeMap;

use crate::{
    ir::{
        ops::{Instruction, Terminator},
        Function, Module,
    },
    vm_ir::{
        VmBlock, VmBlockId, VmFunction, VmInstruction, VmModule, VmTerminator, VmValueId,
    },
};

pub struct LoweringContext {
    value_map: BTreeMap<crate::ir::ValueId, VmValueId>,
    block_map: BTreeMap<crate::ir::BlockId, VmBlockId>,
}

impl LoweringContext {
    pub fn new() -> Self {
        Self {
            value_map: BTreeMap::new(),
            block_map: BTreeMap::new(),
        }
    }

    pub fn map_value(&mut self, val: crate::ir::ValueId) -> VmValueId {
        *self.value_map.entry(val).or_insert_with(|| VmValueId(val.0))
    }

    pub fn map_block(&mut self, block: crate::ir::BlockId) -> VmBlockId {
        *self.block_map.entry(block).or_insert_with(|| VmBlockId(block.0))
    }

    pub fn lower_module(&mut self, module: &Module) -> VmModule {
        let mut vm_module = VmModule::new(module.name.clone());
        for func in &module.functions {
            vm_module.functions.push(self.lower_function(func));
        }
        vm_module
    }

    pub fn lower_function(&mut self, func: &Function) -> VmFunction {
        let entry_id = self.map_block(func.entry);
        let mut vm_func = VmFunction::new(func.name.clone(), entry_id, func.return_type.clone());

        for (param_id, param_ty) in &func.params {
            let vm_param_id = self.map_value(*param_id);
            vm_func.params.push((vm_param_id, param_ty.clone()));
        }

        for (block_id, block) in &func.blocks {
            let vm_block_id = self.map_block(*block_id);
            let mut vm_block = VmBlock::new(vm_block_id, VmTerminator::Unreachable);
            vm_block.name = block.name.clone();

            for (param_id, param_ty) in &block.params {
                let vm_param_id = self.map_value(*param_id);
                vm_block.params.push((vm_param_id, param_ty.clone()));
            }

            for inst in &block.instructions {
                vm_block.instructions.push(self.lower_instruction(inst));
            }

            vm_block.terminator = self.lower_terminator(&block.terminator);
            vm_func.blocks.insert(vm_block_id, vm_block);
        }

        vm_func
    }

    fn lower_instruction(&mut self, inst: &Instruction) -> VmInstruction {
        match inst {
            Instruction::Pure { dest, val, ty } => VmInstruction::VmPure {
                dest: self.map_value(*dest),
                val: val.clone(),
                ty: ty.clone(),
            },
            Instruction::Read {
                dest,
                domain,
                ok_type,
                err_type,
                latent,
            } => VmInstruction::VmRead {
                dest: self.map_value(*dest),
                domain: domain.clone(),
                ok_type: ok_type.clone(),
                err_type: err_type.clone(),
                latent: latent.clone(),
            },
            Instruction::Infer {
                dest,
                prompt,
                ok_type,
                err_type,
                latent,
            } => VmInstruction::VmInfer {
                dest: self.map_value(*dest),
                prompt: prompt.clone(),
                ok_type: ok_type.clone(),
                err_type: err_type.clone(),
                latent: latent.clone(),
            },
            Instruction::Assign { dest, source, ty } => VmInstruction::VmAssign {
                dest: self.map_value(*dest),
                source: self.map_value(*source),
                ty: ty.clone(),
            },
        }
    }

    fn lower_terminator(&mut self, term: &Terminator) -> VmTerminator {
        match term {
            Terminator::Return(val_opt) => VmTerminator::Return(val_opt.map(|v| self.map_value(v))),
            Terminator::Br { target, args } => VmTerminator::Br {
                target: self.map_block(*target),
                args: args.iter().map(|a| self.map_value(*a)).collect(),
            },
            Terminator::CondBr {
                cond,
                true_target,
                true_args,
                false_target,
                false_args,
            } => VmTerminator::CondBr {
                cond: self.map_value(*cond),
                true_target: self.map_block(*true_target),
                true_args: true_args.iter().map(|a| self.map_value(*a)).collect(),
                false_target: self.map_block(*false_target),
                false_args: false_args.iter().map(|a| self.map_value(*a)).collect(),
            },
            Terminator::MatchResult {
                result_val,
                ok_target,
                ok_arg,
                err_target,
                err_arg,
            } => VmTerminator::SwitchResult {
                result_val: self.map_value(*result_val),
                ok_target: self.map_block(*ok_target),
                ok_arg: self.map_value(*ok_arg),
                err_target: self.map_block(*err_target),
                err_arg: self.map_value(*err_arg),
            },
            Terminator::Unreachable => VmTerminator::Unreachable,
        }
    }
}
