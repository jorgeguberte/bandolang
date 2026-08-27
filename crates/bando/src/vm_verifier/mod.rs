use std::collections::{BTreeMap, BTreeSet};

use crate::{
    analysis::DominanceTree,
    diagnostics::{Diagnostic, DiagnosticCode},
    ir::types::Type,
    vm_ir::{VmBlockId, VmFunction, VmInstruction, VmModule, VmTerminator, VmValueId},
};

pub struct VmVerifier<'a> {
    func: &'a VmFunction,
    diagnostics: Vec<Diagnostic>,
    all_defined_values: BTreeMap<VmValueId, Type>,
    block_definitions: BTreeMap<VmBlockId, Vec<VmValueId>>,
}

impl<'a> VmVerifier<'a> {
    pub fn new(func: &'a VmFunction) -> Self {
        Self {
            func,
            diagnostics: Vec::new(),
            all_defined_values: BTreeMap::new(),
            block_definitions: BTreeMap::new(),
        }
    }

    pub fn verify_module(module: &VmModule) -> Result<(), Vec<Diagnostic>> {
        let mut all_diags = Vec::new();
        for func in &module.functions {
            let mut v = VmVerifier::new(func);
            if let Err(mut diags) = v.verify() {
                all_diags.append(&mut diags);
            }
        }
        if all_diags.is_empty() {
            Ok(())
        } else {
            Err(all_diags)
        }
    }

    pub fn verify(&mut self) -> Result<(), Vec<Diagnostic>> {
        // 1. Check duplicate definitions for function params
        for (param_id, param_type) in &self.func.params {
            self.register_def(*param_id, param_type.clone());
        }

        // 2. Validate entry block existence
        if !self.func.blocks.contains_key(&self.func.entry) {
            self.diagnostics.push(Diagnostic::error(
                DiagnosticCode::CfgBadTarget,
                format!("VM Entry block {:?} does not exist in function", self.func.entry),
            ));
        }

        // 3. Register definitions across all blocks
        for (block_id, block) in &self.func.blocks {
            let mut block_defs = Vec::new();
            for (param_id, param_type) in &block.params {
                self.register_def(*param_id, param_type.clone());
                block_defs.push(*param_id);
            }

            for inst in &block.instructions {
                let dest = inst.dest();
                let ty = match inst {
                    VmInstruction::VmPure { ty, .. } => ty.clone(),
                    VmInstruction::VmRead { ok_type, err_type, .. } => Type::result(ok_type.clone(), err_type.clone()),
                    VmInstruction::VmInfer { ok_type, err_type, .. } => Type::result(ok_type.clone(), err_type.clone()),
                    VmInstruction::VmAssign { ty, .. } => ty.clone(),
                };
                self.register_def(dest, ty);
                block_defs.push(dest);
            }

            self.block_definitions.insert(*block_id, block_defs);
        }

        // 4. Compute dominance tree (R3)
        let block_ids: Vec<VmBlockId> = self.func.blocks.keys().copied().collect();
        let dom_tree = DominanceTree::compute(self.func.entry, &block_ids, |b| self.find_predecessors(b));

        // 5. Verify instructions & terminators with SSA dominance / visibility
        for (block_id, block) in &self.func.blocks {
            let mut visible_values = BTreeSet::new();

            // Function params are visible
            for (p_id, _) in &self.func.params {
                visible_values.insert(*p_id);
            }

            // Definitions from strictly dominating blocks are visible
            if let Some(doms) = dom_tree.dominators.get(block_id) {
                for &dom_block in doms {
                    if dom_block != *block_id {
                        if let Some(defs) = self.block_definitions.get(&dom_block) {
                            for d in defs {
                                visible_values.insert(*d);
                            }
                        }
                    }
                }
            }

            // Block params are visible
            for (p_id, _) in &block.params {
                visible_values.insert(*p_id);
            }

            // Verify instructions
            for inst in &block.instructions {
                self.verify_instruction(inst, &visible_values);
                visible_values.insert(inst.dest());
            }

            // Verify terminator
            self.verify_terminator(&block.terminator, *block_id, &visible_values);
        }

        if self.diagnostics.is_empty() {
            Ok(())
        } else {
            Err(self.diagnostics.clone())
        }
    }

    fn find_predecessors(&self, target: VmBlockId) -> Vec<VmBlockId> {
        let mut preds = Vec::new();
        for (b_id, b) in &self.func.blocks {
            match &b.terminator {
                VmTerminator::Br { target: t, .. } => {
                    if t == &target {
                        preds.push(*b_id);
                    }
                }
                VmTerminator::CondBr { true_target, false_target, .. } => {
                    if true_target == &target || false_target == &target {
                        preds.push(*b_id);
                    }
                }
                VmTerminator::SwitchResult { ok_target, err_target, .. } => {
                    if ok_target == &target || err_target == &target {
                        preds.push(*b_id);
                    }
                }
                _ => {}
            }
        }
        preds
    }

    fn register_def(&mut self, val_id: VmValueId, ty: Type) {
        if self.all_defined_values.contains_key(&val_id) {
            self.diagnostics.push(Diagnostic::error(
                DiagnosticCode::SsaDuplicateDef,
                format!("Duplicate VM SSA definition of value {:?}", val_id),
            ));
        } else {
            self.all_defined_values.insert(val_id, ty);
        }
    }

    fn check_visible(&mut self, val_id: VmValueId, visible: &BTreeSet<VmValueId>) -> Option<Type> {
        if !visible.contains(&val_id) {
            self.diagnostics.push(Diagnostic::error(
                DiagnosticCode::SsaUseBeforeDef,
                format!("Use of VM SSA value {:?} outside its dominating scope", val_id),
            ));
            return None;
        }
        self.all_defined_values.get(&val_id).cloned()
    }

    fn verify_instruction(&mut self, inst: &VmInstruction, visible: &BTreeSet<VmValueId>) {
        // R2: Verify required_effects against declared_effects
        for eff in inst.required_effects() {
            if !self.func.declared_effects.contains(&eff) {
                self.diagnostics.push(Diagnostic::error(
                    DiagnosticCode::EffectUndeclared,
                    format!("VM Instruction requires effect {:?} not declared in function effects {:?}", eff, self.func.declared_effects),
                ));
            }
        }

        match inst {
            VmInstruction::VmPure { .. } | VmInstruction::VmRead { .. } | VmInstruction::VmInfer { .. } => {}
            VmInstruction::VmAssign { source, ty, .. } => {
                if let Some(src_ty) = self.check_visible(*source, visible) {
                    if &src_ty != ty {
                        self.diagnostics.push(Diagnostic::error(
                            DiagnosticCode::TypeMismatch,
                            format!("VM Assign type mismatch: source is {:?}, dest is {:?}", src_ty, ty),
                        ));
                    }
                }
            }
        }
    }

    fn verify_terminator(&mut self, term: &VmTerminator, _current_block: VmBlockId, visible: &BTreeSet<VmValueId>) {
        match term {
            VmTerminator::Return(val_opt) => {
                if let Some(val_id) = val_opt {
                    if let Some(val_ty) = self.check_visible(*val_id, visible) {
                        if val_ty != self.func.return_type {
                            self.diagnostics.push(Diagnostic::error(
                                DiagnosticCode::TypeMismatch,
                                format!("VM Return type mismatch: function returns {:?}, got {:?}", self.func.return_type, val_ty),
                            ));
                        }
                    }
                } else if self.func.return_type != Type::Unit {
                    self.diagnostics.push(Diagnostic::error(
                        DiagnosticCode::TypeMismatch,
                        format!("VM Return without value in function expecting {:?}", self.func.return_type),
                    ));
                }
            }
            VmTerminator::Br { target, args } => {
                self.verify_branch_target(*target, args, visible);
            }
            VmTerminator::CondBr {
                cond,
                true_target,
                true_args,
                false_target,
                false_args,
            } => {
                if let Some(cond_ty) = self.check_visible(*cond, visible) {
                    if cond_ty != Type::Bool {
                        self.diagnostics.push(Diagnostic::error(
                            DiagnosticCode::TypeMismatch,
                            format!("VM CondBr condition must be bool, got {:?}", cond_ty),
                        ));
                    }
                }
                self.verify_branch_target(*true_target, true_args, visible);
                self.verify_branch_target(*false_target, false_args, visible);
            }
            VmTerminator::SwitchResult {
                result_val,
                ok_target,
                ok_arg,
                err_target,
                err_arg,
            } => {
                if let Some(res_ty) = self.check_visible(*result_val, visible) {
                    match res_ty {
                        Type::Result { ok, err } => {
                            self.verify_match_branch(*ok_target, *ok_arg, &ok);
                            self.verify_match_branch(*err_target, *err_arg, &err);
                        }
                        other => {
                            self.diagnostics.push(Diagnostic::error(
                                DiagnosticCode::TypeMismatch,
                                format!("VM SwitchResult expects Result<T,E>, got {:?}", other),
                            ));
                        }
                    }
                }
            }
            VmTerminator::Unreachable => {}
        }
    }

    fn verify_branch_target(&mut self, target: VmBlockId, args: &[VmValueId], visible: &BTreeSet<VmValueId>) {
        let block = if let Some(b) = self.func.blocks.get(&target) {
            b
        } else {
            self.diagnostics.push(Diagnostic::error(
                DiagnosticCode::CfgBadTarget,
                format!("VM Branch target block {:?} not found", target),
            ));
            return;
        };

        if block.params.len() != args.len() {
            self.diagnostics.push(Diagnostic::error(
                DiagnosticCode::BlockArgArity,
                format!("VM Block {:?} expects {} arguments, got {}", target, block.params.len(), args.len()),
            ));
            return;
        }

        let expected_types: Vec<_> = block.params.iter().map(|(_, t)| t.clone()).collect();
        for (i, (arg_id, expected_ty)) in args.iter().zip(expected_types.iter()).enumerate() {
            if let Some(arg_ty) = self.check_visible(*arg_id, visible) {
                if &arg_ty != expected_ty {
                    self.diagnostics.push(Diagnostic::error(
                        DiagnosticCode::BlockArgType,
                        format!("VM Block {:?} arg {} type mismatch: expected {:?}, got {:?}", target, i, expected_ty, arg_ty),
                    ));
                }
            }
        }
    }

    fn verify_match_branch(&mut self, target: VmBlockId, arg_id: VmValueId, expected_ty: &Type) {
        let block = if let Some(b) = self.func.blocks.get(&target) {
            b
        } else {
            self.diagnostics.push(Diagnostic::error(
                DiagnosticCode::CfgBadTarget,
                format!("VM SwitchResult target block {:?} not found", target),
            ));
            return;
        };

        if block.params.len() != 1 {
            self.diagnostics.push(Diagnostic::error(
                DiagnosticCode::BlockArgArity,
                format!("VM Switch target block {:?} must take exactly 1 argument, takes {}", target, block.params.len()),
            ));
            return;
        }

        let (param_id, param_ty) = &block.params[0];
        if param_id != &arg_id {
            self.diagnostics.push(Diagnostic::error(
                DiagnosticCode::SsaUseBeforeDef,
                format!("VM Switch target block {:?} parameter {:?} does not match branch arg {:?}", target, param_id, arg_id),
            ));
        }
        if param_ty != expected_ty {
            self.diagnostics.push(Diagnostic::error(
                DiagnosticCode::ResultPayloadType,
                format!("VM Switch target block {:?} payload type mismatch: expected {:?}, got {:?}", target, expected_ty, param_ty),
            ));
        }
    }
}
