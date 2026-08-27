use std::collections::BTreeMap;

use crate::{
    diagnostics::{Diagnostic, DiagnosticCode},
    ir::{
        ops::{Instruction, Terminator},
        types::Type,
        values::{BlockId, ValueId},
        Function, Module,
    },
};

pub struct HighLevelVerifier<'a> {
    func: &'a Function,
    diagnostics: Vec<Diagnostic>,
    defined_values: BTreeMap<ValueId, Type>,
}

impl<'a> HighLevelVerifier<'a> {
    pub fn new(func: &'a Function) -> Self {
        Self {
            func,
            diagnostics: Vec::new(),
            defined_values: BTreeMap::new(),
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
        // 1. Register function parameters
        for (param_id, param_type) in &self.func.params {
            self.define_value(*param_id, param_type.clone());
        }

        // 2. Validate entry block existence
        if !self.func.blocks.contains_key(&self.func.entry) {
            self.diagnostics.push(Diagnostic::error(
                DiagnosticCode::CfgBadTarget,
                format!("Entry block {:?} does not exist in function", self.func.entry),
            ));
        }

        // 3. Register block parameters across all blocks first
        for (block_id, block) in &self.func.blocks {
            for (param_id, param_type) in &block.params {
                self.define_value(*param_id, param_type.clone());
            }

            // Verify instructions
            for inst in &block.instructions {
                self.verify_instruction(inst);
            }

            // Verify terminator
            self.verify_terminator(&block.terminator, *block_id);
        }

        if self.diagnostics.is_empty() {
            Ok(())
        } else {
            Err(self.diagnostics.clone())
        }
    }

    fn define_value(&mut self, val_id: ValueId, ty: Type) {
        if self.defined_values.contains_key(&val_id) {
            self.diagnostics.push(Diagnostic::error(
                DiagnosticCode::SsaDuplicateDef,
                format!("Duplicate SSA definition of value {:?}", val_id),
            ));
        } else {
            self.defined_values.insert(val_id, ty);
        }
    }

    fn get_type(&self, val_id: ValueId) -> Option<Type> {
        self.defined_values.get(&val_id).cloned()
    }

    fn require_defined(&mut self, val_id: ValueId) -> Option<Type> {
        if let Some(ty) = self.get_type(val_id) {
            Some(ty)
        } else {
            self.diagnostics.push(Diagnostic::error(
                DiagnosticCode::SsaUseBeforeDef,
                format!("Use of undefined or uninitialized SSA value {:?}", val_id),
            ));
            None
        }
    }

    fn verify_instruction(&mut self, inst: &Instruction) {
        // Check effect declarations
        for eff in inst.required_effects() {
            if !self.func.declared_effects.contains(&eff) {
                self.diagnostics.push(Diagnostic::error(
                    DiagnosticCode::EffectUndeclared,
                    format!("Instruction requires effect {:?} not declared in function effects", eff),
                ));
            }
        }

        match inst {
            Instruction::Pure { dest, ty, .. } => {
                self.define_value(*dest, ty.clone());
            }
            Instruction::Read {
                dest,
                ok_type,
                err_type,
                ..
            } => {
                let res_ty = Type::result(ok_type.clone(), err_type.clone());
                self.define_value(*dest, res_ty);
            }
            Instruction::Infer {
                dest,
                prompt: _,
                ok_type,
                err_type,
                latent: _,
            } => {
                let res_ty = Type::result(ok_type.clone(), err_type.clone());
                self.define_value(*dest, res_ty);
            }
            Instruction::Assign { dest, source, ty } => {
                if let Some(src_ty) = self.require_defined(*source) {
                    if &src_ty != ty {
                        self.diagnostics.push(Diagnostic::error(
                            DiagnosticCode::TypeMismatch,
                            format!("Assign type mismatch: source is {:?}, dest is {:?}", src_ty, ty),
                        ));
                    }
                }
                self.define_value(*dest, ty.clone());
            }
        }
    }

    fn verify_terminator(&mut self, term: &Terminator, _current_block: BlockId) {
        match term {
            Terminator::Return(val_opt) => {
                if let Some(val_id) = val_opt {
                    if let Some(val_ty) = self.require_defined(*val_id) {
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
                self.verify_branch_target(*target, args);
            }
            Terminator::CondBr {
                cond,
                true_target,
                true_args,
                false_target,
                false_args,
            } => {
                if let Some(cond_ty) = self.require_defined(*cond) {
                    if cond_ty != Type::Bool {
                        self.diagnostics.push(Diagnostic::error(
                            DiagnosticCode::TypeMismatch,
                            format!("CondBr condition must be bool, got {:?}", cond_ty),
                        ));
                    }
                }
                self.verify_branch_target(*true_target, true_args);
                self.verify_branch_target(*false_target, false_args);
            }
            Terminator::MatchResult {
                result_val,
                ok_target,
                ok_arg,
                err_target,
                err_arg,
            } => {
                if let Some(res_ty) = self.require_defined(*result_val) {
                    match res_ty {
                        Type::Result { ok, err } => {
                            let ok_t = *ok;
                            let err_t = *err;
                            self.verify_match_branch(*ok_target, *ok_arg, &ok_t, DiagnosticCode::ResultPayloadType);
                            self.verify_match_branch(*err_target, *err_arg, &err_t, DiagnosticCode::ResultPayloadType);
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

    fn verify_branch_target(&mut self, target: BlockId, args: &[ValueId]) {
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
            if let Some(arg_ty) = self.require_defined(*arg_id) {
                if &arg_ty != expected_ty {
                    self.diagnostics.push(Diagnostic::error(
                        DiagnosticCode::BlockArgType,
                        format!("Block {:?} arg {} type mismatch: expected {:?}, got {:?}", target, i, expected_ty, arg_ty),
                    ));
                }
            }
        }
    }

    fn verify_match_branch(&mut self, target: BlockId, arg_id: ValueId, expected_ty: &Type, diag_code: DiagnosticCode) {
        let block = if let Some(b) = self.func.blocks.get(&target) {
            b
        } else {
            self.diagnostics.push(Diagnostic::error(
                DiagnosticCode::CfgBadTarget,
                format!("MatchResult target block {:?} not found", target),
            ));
            return;
        };

        if block.params.len() != 1 {
            self.diagnostics.push(Diagnostic::error(
                DiagnosticCode::BlockArgArity,
                format!("Match target block {:?} must take exactly 1 argument, takes {}", target, block.params.len()),
            ));
            return;
        }

        let (param_id, param_ty) = &block.params[0];
        if param_id != &arg_id {
            self.diagnostics.push(Diagnostic::error(
                DiagnosticCode::SsaUseBeforeDef,
                format!("Match target block {:?} parameter {:?} does not match branch arg {:?}", target, param_id, arg_id),
            ));
        }
        if param_ty != expected_ty {
            self.diagnostics.push(Diagnostic::error(
                diag_code,
                format!("Match target block {:?} payload type mismatch: expected {:?}, got {:?}", target, expected_ty, param_ty),
            ));
        }
    }
}
