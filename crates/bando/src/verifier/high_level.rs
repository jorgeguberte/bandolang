use std::collections::{BTreeMap, BTreeSet};

use crate::{
    analysis::DominanceTree,
    diagnostics::{Diagnostic, DiagnosticCode},
    ir::{
        ops::{Instruction, Region, RegionTerminator, Terminator},
        types::Type,
        values::{BlockId, ValueId},
        Function, Module,
    },
};

pub struct HighLevelVerifier<'a> {
    func: &'a Function,
    diagnostics: Vec<Diagnostic>,
    all_defined_values: BTreeMap<ValueId, Type>,
    block_definitions: BTreeMap<BlockId, Vec<ValueId>>,
}

impl<'a> HighLevelVerifier<'a> {
    pub fn new(func: &'a Function) -> Self {
        Self {
            func,
            diagnostics: Vec::new(),
            all_defined_values: BTreeMap::new(),
            block_definitions: BTreeMap::new(),
        }
    }

    pub fn verify_module(module: &Module) -> Result<(), Vec<Diagnostic>> {
        let mut all_diags = Vec::new();
        for func in &module.functions {
            let mut v = HighLevelVerifier::new(func);
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
                format!("Entry block {:?} does not exist in function", self.func.entry),
            ));
        }

        // 3. First pass: Collect all definitions across blocks and regions with exact types (S1)
        // Note: Region-local definitions are registered globally for uniqueness and type tracking,
        // but are NOT added to block_definitions[parent_block], preserving lexical region isolation.
        for (block_id, block) in &self.func.blocks {
            let mut block_defs = Vec::new();
            for (param_id, param_type) in &block.params {
                self.register_def(*param_id, param_type.clone());
                block_defs.push(*param_id);
            }

            for inst in &block.instructions {
                let dest = inst.dest();
                let ty = self.infer_instruction_type(inst);
                self.register_def(dest, ty);
                block_defs.push(dest);
            }

            if let Terminator::MatchResult {
                result_val,
                ok_arg,
                ok_body,
                err_arg,
                err_body,
            } = &block.terminator
            {
                let (ok_ty, err_ty) = match self.all_defined_values.get(result_val) {
                    Some(Type::Result { ok, err }) => (*ok.clone(), *err.clone()),
                    _ => (Type::String, Type::String),
                };

                // Register region arguments with their actual types (S1)
                self.register_def(*ok_arg, ok_ty);
                for inst in &ok_body.instructions {
                    let dest = inst.dest();
                    let ty = self.infer_instruction_type(inst);
                    self.register_def(dest, ty);
                }

                self.register_def(*err_arg, err_ty);
                for inst in &err_body.instructions {
                    let dest = inst.dest();
                    let ty = self.infer_instruction_type(inst);
                    self.register_def(dest, ty);
                }
            }

            self.block_definitions.insert(*block_id, block_defs);
        }

        // 4. Compute dominance tree over blocks (R3)
        let block_ids: Vec<BlockId> = self.func.blocks.keys().copied().collect();
        let dom_tree = DominanceTree::compute(self.func.entry, &block_ids, |b| self.find_predecessors(b));

        // 5. Verify instructions & terminators with SSA dominance / lexical visibility (S1 & R3)
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

            // Verify instructions in block
            for inst in &block.instructions {
                self.verify_instruction(inst, &visible_values);
                visible_values.insert(inst.dest());
            }

            // Verify terminator
            self.verify_terminator(&block.terminator, *block_id, &mut visible_values);
        }

        if self.diagnostics.is_empty() {
            Ok(())
        } else {
            Err(self.diagnostics.clone())
        }
    }

    fn infer_instruction_type(&self, inst: &Instruction) -> Type {
        match inst {
            Instruction::Pure { ty, .. } => ty.clone(),
            Instruction::Read { ok_type, err_type, .. } => Type::result(ok_type.clone(), err_type.clone()),
            Instruction::Infer { ok_type, err_type, .. } => Type::result(ok_type.clone(), err_type.clone()),
            Instruction::Assign { ty, .. } => ty.clone(),
        }
    }

    fn find_predecessors(&self, target: BlockId) -> Vec<BlockId> {
        let mut preds = Vec::new();
        for (b_id, b) in &self.func.blocks {
            match &b.terminator {
                Terminator::Br { target: t, .. } => {
                    if t == &target {
                        preds.push(*b_id);
                    }
                }
                Terminator::CondBr {
                    true_target,
                    false_target,
                    ..
                } => {
                    if true_target == &target || false_target == &target {
                        preds.push(*b_id);
                    }
                }
                _ => {}
            }
        }
        preds
    }

    fn register_def(&mut self, val_id: ValueId, ty: Type) {
        if self.all_defined_values.contains_key(&val_id) {
            self.diagnostics.push(Diagnostic::error(
                DiagnosticCode::SsaDuplicateDef,
                format!("Duplicate SSA definition of value {:?}", val_id),
            ));
        } else {
            self.all_defined_values.insert(val_id, ty);
        }
    }

    fn check_visible(&mut self, val_id: ValueId, visible: &BTreeSet<ValueId>) -> Option<Type> {
        if !visible.contains(&val_id) {
            self.diagnostics.push(Diagnostic::error(
                DiagnosticCode::SsaUseBeforeDef,
                format!("Use of SSA value {:?} outside its dominating/lexical scope", val_id),
            ));
            return None;
        }
        self.all_defined_values.get(&val_id).cloned()
    }

    fn verify_instruction(&mut self, inst: &Instruction, visible: &BTreeSet<ValueId>) {
        for eff in inst.required_effects() {
            if !self.func.declared_effects.contains(&eff) {
                self.diagnostics.push(Diagnostic::error(
                    DiagnosticCode::EffectUndeclared,
                    format!("Instruction requires effect {:?} not declared in function effects", eff),
                ));
            }
        }

        match inst {
            Instruction::Pure { .. } | Instruction::Read { .. } | Instruction::Infer { .. } => {}
            Instruction::Assign { source, ty, .. } => {
                if let Some(src_ty) = self.check_visible(*source, visible) {
                    if &src_ty != ty {
                        self.diagnostics.push(Diagnostic::error(
                            DiagnosticCode::TypeMismatch,
                            format!("Assign type mismatch: source is {:?}, dest is {:?}", src_ty, ty),
                        ));
                    }
                }
            }
        }
    }

    fn verify_terminator(&mut self, term: &Terminator, current_block: BlockId, visible: &mut BTreeSet<ValueId>) {
        match term {
            Terminator::Return(val_opt) => {
                if let Some(val_id) = val_opt {
                    if let Some(val_ty) = self.check_visible(*val_id, visible) {
                        if val_ty != self.func.return_type {
                            self.diagnostics.push(Diagnostic::error(
                                DiagnosticCode::TypeMismatch,
                                format!("Return type mismatch: function returns {:?}, got {:?}", self.func.return_type, val_ty),
                            ));
                        }
                    }
                } else if self.func.return_type != Type::Unit {
                    self.diagnostics.push(Diagnostic::error(
                        DiagnosticCode::TypeMismatch,
                        format!("Return without value in function expecting {:?}", self.func.return_type),
                    ));
                }
            }
            Terminator::Br { target, args } => {
                self.verify_branch_target(*target, args, visible);
            }
            Terminator::CondBr {
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
                            format!("CondBr condition must be bool, got {:?}", cond_ty),
                        ));
                    }
                }
                self.verify_branch_target(*true_target, true_args, visible);
                self.verify_branch_target(*false_target, false_args, visible);
            }
            Terminator::MatchResult {
                result_val,
                ok_arg,
                ok_body,
                err_arg,
                err_body,
            } => {
                if let Some(res_ty) = self.check_visible(*result_val, visible) {
                    match res_ty {
                        Type::Result { ok, err } => {
                            self.verify_region(ok_body, *ok_arg, &ok, current_block, visible);
                            self.verify_region(err_body, *err_arg, &err, current_block, visible);
                        }
                        other => {
                            self.diagnostics.push(Diagnostic::error(
                                DiagnosticCode::TypeMismatch,
                                format!("MatchResult expects Result<T,E>, got {:?}", other),
                            ));
                        }
                    }
                }
            }
            Terminator::Unreachable => {}
        }
    }

    fn verify_region(
        &mut self,
        region: &Region,
        arg_id: ValueId,
        _expected_arg_ty: &Type,
        _parent_block: BlockId,
        parent_visible: &BTreeSet<ValueId>,
    ) {
        // S1: Region-local scope starts with parent visible values + region argument
        let mut region_visible = parent_visible.clone();
        region_visible.insert(arg_id);

        for inst in &region.instructions {
            self.verify_instruction(inst, &region_visible);
            region_visible.insert(inst.dest());
        }

        match &region.terminator {
            RegionTerminator::Return(val_opt) => {
                if let Some(val_id) = val_opt {
                    if let Some(val_ty) = self.check_visible(*val_id, &region_visible) {
                        if val_ty != self.func.return_type {
                            self.diagnostics.push(Diagnostic::error(
                                DiagnosticCode::TypeMismatch,
                                format!("Region Return type mismatch: expected {:?}, got {:?}", self.func.return_type, val_ty),
                            ));
                        }
                    }
                }
            }
            RegionTerminator::Br { target, args } => {
                self.verify_branch_target(*target, args, &region_visible);
            }
            RegionTerminator::Unreachable => {}
        }
    }

    fn verify_branch_target(&mut self, target: BlockId, args: &[ValueId], visible: &BTreeSet<ValueId>) {
        let block = if let Some(b) = self.func.blocks.get(&target) {
            b
        } else {
            self.diagnostics.push(Diagnostic::error(
                DiagnosticCode::CfgBadTarget,
                format!("Branch target block {:?} not found", target),
            ));
            return;
        };

        if block.params.len() != args.len() {
            self.diagnostics.push(Diagnostic::error(
                DiagnosticCode::BlockArgArity,
                format!("Block {:?} expects {} arguments, got {}", target, block.params.len(), args.len()),
            ));
            return;
        }

        let expected_types: Vec<_> = block.params.iter().map(|(_, t)| t.clone()).collect();
        for (i, (arg_id, expected_ty)) in args.iter().zip(expected_types.iter()).enumerate() {
            if let Some(arg_ty) = self.check_visible(*arg_id, visible) {
                if &arg_ty != expected_ty {
                    self.diagnostics.push(Diagnostic::error(
                        DiagnosticCode::BlockArgType,
                        format!("Block {:?} arg {} type mismatch: expected {:?}, got {:?}", target, i, expected_ty, arg_ty),
                    ));
                }
            }
        }
    }
}
