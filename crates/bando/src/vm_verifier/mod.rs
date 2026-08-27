use std::collections::{BTreeMap, BTreeSet};

use crate::{
    analysis::DominanceTree,
    diagnostics::{Diagnostic, DiagnosticCode},
    ir::{effects::EffectRow, types::Type},
    lowering::CompilerMutations,
    vm_ir::{VmBlockId, VmFunction, VmInstruction, VmModule, VmTerminator, VmValueId},
};

pub struct VmVerifier<'a> {
    func: &'a VmFunction,
    diagnostics: Vec<Diagnostic>,
    all_defined_values: BTreeMap<VmValueId, Type>,
    block_definitions: BTreeMap<VmBlockId, Vec<VmValueId>>,
    mutations: Option<CompilerMutations>,
}

impl<'a> VmVerifier<'a> {
    pub fn new(func: &'a VmFunction) -> Self {
        Self {
            func,
            diagnostics: Vec::new(),
            all_defined_values: BTreeMap::new(),
            block_definitions: BTreeMap::new(),
            mutations: None,
        }
    }

    pub fn with_mutations(func: &'a VmFunction, mutations: CompilerMutations) -> Self {
        Self {
            func,
            diagnostics: Vec::new(),
            all_defined_values: BTreeMap::new(),
            block_definitions: BTreeMap::new(),
            mutations: Some(mutations),
        }
    }

    pub fn verify_module(module: &VmModule) -> Result<(), Vec<Diagnostic>> {
        Self::verify_module_with_mutations(module, &CompilerMutations::default())
    }

    pub fn verify_module_with_mutations(
        module: &VmModule,
        mutations: &CompilerMutations,
    ) -> Result<(), Vec<Diagnostic>> {
        let mut all_diags = Vec::new();
        for func in &module.functions {
            let mut v = VmVerifier::with_mutations(func, mutations.clone());
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
                format!(
                    "VM Entry block {:?} does not exist in function",
                    self.func.entry
                ),
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
                if let Some(dest) = inst.dest() {
                    let ty = match inst {
                        VmInstruction::VmPure { ty, .. } => ty.clone(),
                        VmInstruction::VmRead {
                            ok_type, err_type, ..
                        } => Type::result(ok_type.clone(), err_type.clone()),
                        VmInstruction::VmInfer {
                            ok_type, err_type, ..
                        } => Type::result(ok_type.clone(), err_type.clone()),
                        VmInstruction::VmAssign { ty, .. } => ty.clone(),
                        VmInstruction::VmVerify {
                            output_predicate,
                            subject_type,
                            ..
                        } => {
                            let att_ty =
                                Type::attestation(output_predicate.clone(), subject_type.clone());
                            Type::result(att_ty, Type::String)
                        }
                        VmInstruction::VmAct {
                            success_type,
                            failure_type,
                            ..
                        } => Type::act_outcome(success_type.clone(), failure_type.clone()),
                        VmInstruction::VmSpawnChild {
                            ok_type,
                            err_type,
                            child_effects,
                            ..
                        } => Type::child_handle(
                            ok_type.clone(),
                            err_type.clone(),
                            EffectRow {
                                effects: child_effects.iter().cloned().collect(),
                            },
                        ),
                        VmInstruction::VmAwaitChild {
                            ok_type, err_type, ..
                        } => Type::result(ok_type.clone(), err_type.clone()),
                        VmInstruction::VmInternalize { payload_type, .. } => {
                            Type::result(Type::belief(payload_type.clone()), Type::String)
                        }
                        VmInstruction::VmConvergeInit { .. } => Type::Unit,
                        VmInstruction::VmConvergeStep { .. } => Type::Bool,
                        VmInstruction::VmConvergeStage { .. } => Type::String,
                        VmInstruction::VmConvergeFinish {
                            partial_type,
                            satisfied_type,
                            ..
                        } => {
                            let outcome_ty = Type::convergence_outcome(
                                satisfied_type.clone(),
                                Type::exhaustion_report(partial_type.clone()),
                            );
                            Type::result(outcome_ty, Type::String)
                        }
                        _ => Type::Unit,
                    };
                    self.register_def(dest, ty);
                    block_defs.push(dest);
                }
            }

            self.block_definitions.insert(*block_id, block_defs);
        }

        // 4. Compute dominance tree (R3)
        let block_ids: Vec<VmBlockId> = self.func.blocks.keys().copied().collect();
        let dom_tree =
            DominanceTree::compute(self.func.entry, &block_ids, |b| self.find_predecessors(b));

        // 5. Verify instructions & terminators with SSA dominance / visibility
        for (block_id, block) in &self.func.blocks {
            let mut visible_values = BTreeSet::new();

            for (p_id, _) in &self.func.params {
                visible_values.insert(*p_id);
            }

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

            for (p_id, _) in &block.params {
                visible_values.insert(*p_id);
            }

            for inst in &block.instructions {
                self.verify_instruction(inst, &visible_values);
                if let Some(dest) = inst.dest() {
                    visible_values.insert(dest);
                }
            }

            self.verify_terminator(&block.terminator, *block_id, &visible_values);
        }

        self.verify_handle_joins();

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
                VmTerminator::CondBr {
                    true_target,
                    false_target,
                    ..
                } => {
                    if true_target == &target || false_target == &target {
                        preds.push(*b_id);
                    }
                }
                VmTerminator::SwitchResult {
                    ok_target,
                    err_target,
                    ..
                } => {
                    if ok_target == &target || err_target == &target {
                        preds.push(*b_id);
                    }
                }
                VmTerminator::SwitchActOutcome {
                    success_target,
                    failure_target,
                    partial_target,
                    unknown_target,
                    ..
                } => {
                    if success_target == &target
                        || failure_target == &target
                        || partial_target == &target
                        || unknown_target == &target
                    {
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
                format!(
                    "Use of VM SSA value {:?} outside its dominating scope",
                    val_id
                ),
            ));
            return None;
        }
        self.all_defined_values.get(&val_id).cloned()
    }

    fn verify_instruction(&mut self, inst: &VmInstruction, visible: &BTreeSet<VmValueId>) {
        for eff in inst.required_effects() {
            if !self.func.declared_effects.contains(&eff) {
                self.diagnostics.push(Diagnostic::error(
                    DiagnosticCode::EffectUndeclared,
                    format!(
                        "VM Instruction requires effect {:?} not declared in function effects {:?}",
                        eff, self.func.declared_effects
                    ),
                ));
            }
        }

        match inst {
            VmInstruction::VmPure { .. }
            | VmInstruction::VmRead { .. }
            | VmInstruction::VmInfer { .. } => {}
            VmInstruction::VmAssign { source, ty, .. } => {
                if let Some(src_ty) = self.check_visible(*source, visible) {
                    if &src_ty != ty {
                        self.diagnostics.push(Diagnostic::error(
                            DiagnosticCode::TypeMismatch,
                            format!(
                                "VM Assign type mismatch: source is {:?}, dest is {:?}",
                                src_ty, ty
                            ),
                        ));
                    }
                }
            }
            VmInstruction::VmVerify {
                subject,
                subject_type,
                ..
            } => {
                if let Some(sub_ty) = self.check_visible(*subject, visible) {
                    if &sub_ty != subject_type {
                        self.diagnostics.push(Diagnostic::error(
                            DiagnosticCode::TypeMismatch,
                            format!(
                                "VM Verify subject type mismatch: expected {:?}, got {:?}",
                                subject_type, sub_ty
                            ),
                        ));
                    }
                }
            }
            VmInstruction::VmAct { args, evidence, .. } => {
                for arg in args {
                    self.check_visible(*arg, visible);
                }
                for ev in evidence {
                    self.check_visible(*ev, visible);
                }
            }
            VmInstruction::VmSpawnChild { args, .. } => {
                for arg in args {
                    self.check_visible(*arg, visible);
                }
            }
            VmInstruction::VmAwaitChild { handle, .. } => {
                self.check_visible(*handle, visible);
            }
            VmInstruction::VmInternalize { claim, .. } => {
                self.check_visible(*claim, visible);
            }
            VmInstruction::VmConvergeInit { .. } => {}
            VmInstruction::VmConvergeStep { frame_var, .. } => {
                self.check_visible(*frame_var, visible);
            }
            VmInstruction::VmConvergeDispatchLocal { frame_var, .. } => {
                self.check_visible(*frame_var, visible);
            }
            VmInstruction::VmConvergeCheckSatisfactionLocal { frame_var, .. } => {
                self.check_visible(*frame_var, visible);
            }
            VmInstruction::VmConvergeStage { frame_var, .. } => {
                self.check_visible(*frame_var, visible);
            }
            VmInstruction::VmConvergeEmit {
                frame_var,
                handle_var,
                ..
            } => {
                self.check_visible(*frame_var, visible);
                self.check_visible(*handle_var, visible);
            }
            VmInstruction::VmConvergeAdmitCompletion {
                frame_var,
                handle_var,
                ..
            } => {
                self.check_visible(*frame_var, visible);
                self.check_visible(*handle_var, visible);
            }
            VmInstruction::VmConvergeSettle {
                frame_var,
                handle_var,
                ..
            } => {
                self.check_visible(*frame_var, visible);
                self.check_visible(*handle_var, visible);
            }
            VmInstruction::VmConvergeApply {
                frame_var,
                handle_var,
                ..
            } => {
                self.check_visible(*frame_var, visible);
                self.check_visible(*handle_var, visible);
            }
            VmInstruction::VmConvergeFinish { frame_var, .. } => {
                self.check_visible(*frame_var, visible);
            }
        }
    }

    fn verify_terminator(
        &mut self,
        term: &VmTerminator,
        _current_block: VmBlockId,
        visible: &BTreeSet<VmValueId>,
    ) {
        match term {
            VmTerminator::Return(val_opt) => {
                if let Some(val_id) = val_opt {
                    if let Some(val_ty) = self.check_visible(*val_id, visible) {
                        if val_ty != self.func.return_type {
                            self.diagnostics.push(Diagnostic::error(
                                DiagnosticCode::TypeMismatch,
                                format!(
                                    "VM Return type mismatch: function returns {:?}, got {:?}",
                                    self.func.return_type, val_ty
                                ),
                            ));
                        }
                    }
                } else if self.func.return_type != Type::Unit {
                    self.diagnostics.push(Diagnostic::error(
                        DiagnosticCode::TypeMismatch,
                        format!(
                            "VM Return without value in function expecting {:?}",
                            self.func.return_type
                        ),
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
            VmTerminator::SwitchActOutcome {
                outcome_val,
                success_target,
                success_arg,
                failure_target,
                failure_arg,
                partial_target,
                partial_arg,
                unknown_target,
                unknown_arg,
            } => {
                if let Some(res_ty) = self.check_visible(*outcome_val, visible) {
                    match res_ty {
                        Type::ActOutcome { success, failure } => {
                            self.verify_match_branch(*success_target, *success_arg, &success);
                            self.verify_match_branch(*failure_target, *failure_arg, &failure);
                            self.verify_match_branch(
                                *partial_target,
                                *partial_arg,
                                &Type::PartialReport,
                            );
                            self.verify_match_branch(*unknown_target, *unknown_arg, &Type::String);
                        }
                        other => {
                            self.diagnostics.push(Diagnostic::error(
                                DiagnosticCode::TypeMismatch,
                                format!(
                                    "VM SwitchActOutcome expects ActOutcome<T,E>, got {:?}",
                                    other
                                ),
                            ));
                        }
                    }
                }
            }
            VmTerminator::Unreachable => {}
        }
    }

    fn verify_branch_target(
        &mut self,
        target: VmBlockId,
        args: &[VmValueId],
        visible: &BTreeSet<VmValueId>,
    ) {
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
                format!(
                    "VM Block {:?} expects {} arguments, got {}",
                    target,
                    block.params.len(),
                    args.len()
                ),
            ));
            return;
        }

        let expected_types: Vec<_> = block.params.iter().map(|(_, t)| t.clone()).collect();
        for (i, (arg_id, expected_ty)) in args.iter().zip(expected_types.iter()).enumerate() {
            if let Some(arg_ty) = self.check_visible(*arg_id, visible) {
                if let Type::ChildHandle {
                    ok: exp_ok,
                    err: exp_err,
                    effects: exp_effs,
                } = expected_ty
                {
                    if let Type::ChildHandle {
                        ok: arg_ok,
                        err: arg_err,
                        effects: arg_effs,
                    } = &arg_ty
                    {
                        if exp_ok != arg_ok || exp_err != arg_err {
                            self.diagnostics.push(Diagnostic::error(
                                DiagnosticCode::IncompatibleHandleJoin,
                                format!("VM Handle join type mismatch: expected ok={:?}, err={:?}, got ok={:?}, err={:?}", exp_ok, exp_err, arg_ok, arg_err),
                            ));
                        } else if !arg_effs.is_subset(exp_effs) {
                            let allow_drop = self
                                .mutations
                                .as_ref()
                                .map(|m| m.s3m16_handle_join_drops_effect)
                                .unwrap_or(false);
                            if !allow_drop {
                                self.diagnostics.push(Diagnostic::error(
                                    DiagnosticCode::IncompatibleHandleJoin,
                                    format!("VM Handle join effect loss: incoming effects {:?} not covered by merged handle effects {:?}", arg_effs, exp_effs),
                                ));
                            }
                        }
                    } else {
                        self.diagnostics.push(Diagnostic::error(
                            DiagnosticCode::BlockArgType,
                            format!(
                                "VM Block {:?} arg {} type mismatch: expected {:?}, got {:?}",
                                target, i, expected_ty, arg_ty
                            ),
                        ));
                    }
                } else if &arg_ty != expected_ty {
                    self.diagnostics.push(Diagnostic::error(
                        DiagnosticCode::BlockArgType,
                        format!(
                            "VM Block {:?} arg {} type mismatch: expected {:?}, got {:?}",
                            target, i, expected_ty, arg_ty
                        ),
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
                format!("VM Match branch target block {:?} not found", target),
            ));
            return;
        };

        if block.params.len() != 1 {
            self.diagnostics.push(Diagnostic::error(
                DiagnosticCode::BlockArgArity,
                format!(
                    "VM Match target block {:?} must take exactly 1 argument, takes {}",
                    target,
                    block.params.len()
                ),
            ));
            return;
        }

        let (param_id, param_ty) = &block.params[0];
        if param_id != &arg_id {
            self.diagnostics.push(Diagnostic::error(
                DiagnosticCode::SsaUseBeforeDef,
                format!(
                    "VM Match target block {:?} parameter {:?} does not match branch arg {:?}",
                    target, param_id, arg_id
                ),
            ));
        }
        if param_ty != expected_ty {
            self.diagnostics.push(Diagnostic::error(
                DiagnosticCode::ResultPayloadType,
                format!(
                    "VM Match target block {:?} payload type mismatch: expected {:?}, got {:?}",
                    target, expected_ty, param_ty
                ),
            ));
        }
    }

    fn verify_handle_joins(&mut self) {
        let mut incoming_jumps: BTreeMap<VmBlockId, Vec<(VmBlockId, Vec<VmValueId>)>> =
            BTreeMap::new();
        for (b_id, block) in &self.func.blocks {
            match &block.terminator {
                VmTerminator::Br { target, args } => {
                    incoming_jumps
                        .entry(*target)
                        .or_default()
                        .push((*b_id, args.clone()));
                }
                VmTerminator::CondBr {
                    true_target,
                    true_args,
                    false_target,
                    false_args,
                    ..
                } => {
                    incoming_jumps
                        .entry(*true_target)
                        .or_default()
                        .push((*b_id, true_args.clone()));
                    incoming_jumps
                        .entry(*false_target)
                        .or_default()
                        .push((*b_id, false_args.clone()));
                }
                VmTerminator::SwitchResult {
                    ok_target,
                    ok_arg,
                    err_target,
                    err_arg,
                    ..
                } => {
                    incoming_jumps
                        .entry(*ok_target)
                        .or_default()
                        .push((*b_id, vec![*ok_arg]));
                    incoming_jumps
                        .entry(*err_target)
                        .or_default()
                        .push((*b_id, vec![*err_arg]));
                }
                VmTerminator::SwitchActOutcome {
                    success_target,
                    success_arg,
                    failure_target,
                    failure_arg,
                    partial_target,
                    partial_arg,
                    unknown_target,
                    unknown_arg,
                    ..
                } => {
                    incoming_jumps
                        .entry(*success_target)
                        .or_default()
                        .push((*b_id, vec![*success_arg]));
                    incoming_jumps
                        .entry(*failure_target)
                        .or_default()
                        .push((*b_id, vec![*failure_arg]));
                    incoming_jumps
                        .entry(*partial_target)
                        .or_default()
                        .push((*b_id, vec![*partial_arg]));
                    incoming_jumps
                        .entry(*unknown_target)
                        .or_default()
                        .push((*b_id, vec![*unknown_arg]));
                }
                VmTerminator::Return(_) | VmTerminator::Unreachable => {}
            }
        }

        for (target_id, target_block) in &self.func.blocks {
            if target_id == &self.func.entry {
                continue;
            }
            let jumps = match incoming_jumps.get(target_id) {
                Some(j) => j,
                None => continue,
            };

            for (param_idx, (param_id, expected_ty)) in target_block.params.iter().enumerate() {
                if let Type::ChildHandle {
                    ok: exp_ok,
                    err: exp_err,
                    effects: exp_effs,
                } = expected_ty
                {
                    let mut incoming_handle_effects = Vec::new();
                    for (_pred_id, args) in jumps {
                        if param_idx < args.len() {
                            let arg_id = args[param_idx];
                            if let Some(arg_ty) = self.all_defined_values.get(&arg_id) {
                                if let Type::ChildHandle {
                                    ok: in_ok,
                                    err: in_err,
                                    effects: in_effs,
                                } = arg_ty
                                {
                                    if in_ok != exp_ok || in_err != exp_err {
                                        self.diagnostics.push(Diagnostic::error(
                                            DiagnosticCode::IncompatibleHandleJoin,
                                            format!(
                                                "VM Handle join type mismatch: expected ok={:?}, err={:?}, got ok={:?}, err={:?}",
                                                exp_ok, exp_err, in_ok, in_err
                                            ),
                                        ));
                                    }
                                    incoming_handle_effects.push(in_effs.clone());
                                }
                            }
                        }
                    }

                    let mut union_effects = EffectRow::empty();
                    for in_eff in &incoming_handle_effects {
                        for e in &in_eff.effects {
                            union_effects = union_effects.with(e.clone());
                        }
                    }

                    let allow_drop = self
                        .mutations
                        .as_ref()
                        .map(|m| m.s3m16_handle_join_drops_effect)
                        .unwrap_or(false);
                    if !allow_drop && exp_effs != &union_effects {
                        self.diagnostics.push(Diagnostic::error(
                            DiagnosticCode::IncompatibleHandleJoin,
                            format!(
                                "VM Exact handle join effect violation on Block {:?} param {:?}: expected exact union {:?}, got {:?}",
                                target_id, param_id, union_effects, exp_effs
                            ),
                        ));
                    }
                }
            }
        }
    }
}
