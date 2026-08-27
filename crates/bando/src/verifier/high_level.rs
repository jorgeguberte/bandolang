use std::collections::{BTreeMap, BTreeSet};

use crate::{
    analysis::DominanceTree,
    diagnostics::{Diagnostic, DiagnosticCode},
    ir::{
        effects::Effect,
        ops::{Instruction, Region, RegionTerminator, Terminator},
        types::Type,
        values::{BlockId, ValueId},
        Function, Module,
    },
    registry::RegistrySnapshot,
};

pub struct HighLevelVerifier<'a> {
    pub func: &'a Function,
    pub registry: Option<&'a RegistrySnapshot>,
    pub all_defined_values: BTreeMap<ValueId, Type>,
    pub diagnostics: Vec<Diagnostic>,
}

impl<'a> HighLevelVerifier<'a> {
    pub fn new(func: &'a Function) -> Self {
        Self {
            func,
            registry: None,
            all_defined_values: BTreeMap::new(),
            diagnostics: Vec::new(),
        }
    }

    pub fn with_registry(func: &'a Function, registry: &'a RegistrySnapshot) -> Self {
        Self {
            func,
            registry: Some(registry),
            all_defined_values: BTreeMap::new(),
            diagnostics: Vec::new(),
        }
    }

    pub fn verify_module(module: &'a Module) -> Result<(), Vec<Diagnostic>> {
        let mut all_diags = Vec::new();
        for func in &module.functions {
            let mut verifier = HighLevelVerifier::new(func);
            verifier.verify();
            all_diags.extend(verifier.diagnostics);
        }
        if all_diags.is_empty() {
            Ok(())
        } else {
            Err(all_diags)
        }
    }

    pub fn verify_module_with_registry(
        module: &'a Module,
        registry: &'a RegistrySnapshot,
    ) -> Result<(), Vec<Diagnostic>> {
        let mut all_diags = Vec::new();
        for func in &module.functions {
            let mut verifier = HighLevelVerifier::with_registry(func, registry);
            verifier.verify();
            all_diags.extend(verifier.diagnostics);
        }
        if all_diags.is_empty() {
            Ok(())
        } else {
            Err(all_diags)
        }
    }

    pub fn verify(&mut self) {
        // 1. Check entry block exists
        if !self.func.blocks.contains_key(&self.func.entry) {
            self.diagnostics.push(Diagnostic::error(
                DiagnosticCode::CfgBadTarget,
                format!(
                    "Entry block {:?} does not exist in function",
                    self.func.entry
                ),
            ));
        }

        // 2. Collect and verify all definitions (R3 SSA single-def)
        for (param_id, ty) in &self.func.params {
            self.register_def(*param_id, ty.clone());
        }

        for (block_id, block) in &self.func.blocks {
            if block_id != &self.func.entry {
                for (param_id, ty) in &block.params {
                    self.register_def(*param_id, ty.clone());
                }
            }

            for inst in &block.instructions {
                let dest = inst.dest();
                let ty = self.infer_instruction_type(inst);
                self.register_def(dest, ty);
            }

            // Register definitions in region arguments for MatchResult / MatchActOutcome
            match &block.terminator {
                Terminator::MatchResult {
                    result_val,
                    ok_arg,
                    ok_body: _,
                    err_arg,
                    err_body: _,
                } => {
                    let (ok_ty, err_ty) = match self.all_defined_values.get(result_val) {
                        Some(Type::Result { ok, err }) => (*ok.clone(), *err.clone()),
                        _ => (Type::String, Type::String),
                    };
                    self.register_def(*ok_arg, ok_ty);
                    self.register_def(*err_arg, err_ty);
                }
                Terminator::MatchActOutcome {
                    outcome_val,
                    success_arg,
                    success_body: _,
                    failure_arg,
                    failure_body: _,
                    partial_arg,
                    partial_body: _,
                    unknown_arg,
                    unknown_body: _,
                } => {
                    let (succ_ty, fail_ty) = match self.all_defined_values.get(outcome_val) {
                        Some(Type::ActOutcome { success, failure }) => {
                            (*success.clone(), *failure.clone())
                        }
                        _ => (Type::String, Type::String),
                    };

                    self.register_def(*success_arg, succ_ty);
                    self.register_def(*failure_arg, fail_ty);
                    self.register_def(*partial_arg, Type::PartialReport);
                    self.register_def(*unknown_arg, Type::String);
                }
                _ => {}
            }
        }

        // 3. Compute dominance tree over blocks (R3)
        let block_ids: Vec<BlockId> = self.func.blocks.keys().copied().collect();
        let dom_tree =
            DominanceTree::compute(self.func.entry, &block_ids, |b| self.find_predecessors(b));

        // 4. Verify instructions & terminators with SSA dominance / lexical visibility
        for (block_id, block) in &self.func.blocks {
            let mut visible_in_block = BTreeSet::new();

            // All definitions from strictly dominating blocks are visible
            for other_id in &block_ids {
                if dom_tree.dominates(*other_id, *block_id) {
                    if let Some(other_block) = self.func.blocks.get(other_id) {
                        for (p, _) in &other_block.params {
                            visible_in_block.insert(*p);
                        }
                        for inst in &other_block.instructions {
                            visible_in_block.insert(inst.dest());
                        }
                    }
                }
            }

            // Function params always visible
            for (p, _) in &self.func.params {
                visible_in_block.insert(*p);
            }

            // Current block params visible
            for (p, _) in &block.params {
                visible_in_block.insert(*p);
            }

            // Verify instructions in block
            for inst in &block.instructions {
                self.verify_instruction(inst, &visible_in_block);
                visible_in_block.insert(inst.dest());
            }

            // Verify terminator
            self.verify_terminator(&block.terminator, *block_id, &mut visible_in_block);
        }
    }

    fn register_def(&mut self, val_id: ValueId, ty: Type) {
        if self.all_defined_values.insert(val_id, ty).is_some() {
            self.diagnostics.push(Diagnostic::error(
                DiagnosticCode::SsaDuplicateDef,
                format!("Duplicate definition of SSA value {:?}", val_id),
            ));
        }
    }

    fn infer_instruction_type(&self, inst: &Instruction) -> Type {
        match inst {
            Instruction::Pure { ty, .. } => ty.clone(),
            Instruction::Read {
                ok_type, err_type, ..
            } => Type::result(ok_type.clone(), err_type.clone()),
            Instruction::Infer {
                ok_type, err_type, ..
            } => Type::result(ok_type.clone(), err_type.clone()),
            Instruction::Assign { ty, .. } => ty.clone(),
            Instruction::Verify {
                verifier_id,
                output_predicate,
                subject_type,
                ..
            } => {
                if let Some(reg) = self.registry {
                    if let Some(desc) = reg.verifiers.get(verifier_id) {
                        let att_ty =
                            Type::attestation(desc.output_predicate.clone(), desc.subject_type.clone());
                        return Type::result(att_ty, Type::String);
                    }
                }
                let att_ty =
                    Type::attestation(output_predicate.clone(), subject_type.clone());
                Type::result(att_ty, Type::String)
            }
            Instruction::Act {
                op_id,
                success_type,
                failure_type,
                ..
            } => {
                if let Some(reg) = self.registry {
                    if let Some(_desc) = reg.operations.get(op_id) {
                        return Type::act_outcome(success_type.clone(), failure_type.clone());
                    }
                }
                Type::act_outcome(success_type.clone(), failure_type.clone())
            }
        }
    }

    fn check_visible(
        &mut self,
        val_id: ValueId,
        visible: &BTreeSet<ValueId>,
    ) -> Option<Type> {
        if !visible.contains(&val_id) {
            self.diagnostics.push(Diagnostic::error(
                DiagnosticCode::SsaUseBeforeDef,
                format!(
                    "Use of SSA value {:?} outside its dominating/lexical scope",
                    val_id
                ),
            ));
            return None;
        }
        self.all_defined_values.get(&val_id).cloned()
    }

    fn verify_instruction(&mut self, inst: &Instruction, visible: &BTreeSet<ValueId>) {
        // Rule #1 & #9: check required effects
        let required_effects = match inst {
            Instruction::Verify { verifier_id, verifier_effects, .. } => {
                if let Some(reg) = self.registry {
                    if let Some(desc) = reg.verifiers.get(verifier_id) {
                        desc.effect_envelope.effects.iter().cloned().collect()
                    } else {
                        self.diagnostics.push(Diagnostic::error(
                            DiagnosticCode::UnknownVerifier,
                            format!("VerifierId {:?} not found in trusted registry", verifier_id),
                        ));
                        return;
                    }
                } else {
                    verifier_effects.clone()
                }
            }
            Instruction::Act { op_id, target_domain, gate_effects, args, evidence, .. } => {
                if let Some(reg) = self.registry {
                    if let Some(op_desc) = reg.operations.get(op_id) {
                        // 1. Caller authority must contain act[target_domain]
                        let act_eff = Effect::Act(op_desc.target_domain.clone());
                        if !self.func.declared_effects.contains(&act_eff) {
                            self.diagnostics.push(Diagnostic::error(
                                DiagnosticCode::EffectUndeclared,
                                format!("Caller lacks target capability {:?}", act_eff),
                            ));
                        }

                        // 2. Compute gate effects from requirements
                        let mut gate_effs = Vec::new();
                        for req in &op_desc.requirements {
                            gate_effs.extend(req.required_gate_effects());
                        }

                        let mut full_act_effs = vec![act_eff];
                        full_act_effs.extend(gate_effs);

                        // 3. Enforce declared envelope (Rule #11, S2C13)
                        for eff in &full_act_effs {
                            if !op_desc.declared_envelope.contains(eff) {
                                self.diagnostics.push(Diagnostic::error(
                                    DiagnosticCode::EnvelopeExceeded,
                                    format!("Σ_act effect {:?} exceeds operation declared envelope {:?}", eff, op_desc.declared_envelope),
                                ));
                            }
                        }

                        // 4. Static requirement resolution over evidence types (P3, S2C09, S2C10)
                        for req in &op_desc.requirements {
                            match req {
                                crate::registry::PolicyRequirement::RequiresStaticProof { predicate, subject_arg_idx } => {
                                    let matching = evidence.iter().find_map(|e| {
                                        let ty = self.all_defined_values.get(e)?;
                                        match ty {
                                            Type::Attestation { predicate: p, subject_ty } => {
                                                if p == predicate { Some(subject_ty.clone()) } else { None }
                                            }
                                            Type::Result { ok, .. } => match ok.as_ref() {
                                                Type::Attestation { predicate: p, subject_ty } => {
                                                    if p == predicate { Some(subject_ty.clone()) } else { None }
                                                }
                                                _ => None,
                                            },
                                            _ => None,
                                        }
                                    });

                                    match matching {
                                        Some(subj_ty) => {
                                            let arg_val_id = args.get(*subject_arg_idx);
                                            let expected_ty = arg_val_id.and_then(|id| self.all_defined_values.get(id));
                                            if expected_ty == Some(&subj_ty) {
                                                // Proved!
                                            } else {
                                                self.diagnostics.push(Diagnostic::error(
                                                    DiagnosticCode::RefutedRequirement,
                                                    format!("Requirement statically refuted for operation {:?}", op_id),
                                                ));
                                            }
                                        }
                                        None => {
                                            self.diagnostics.push(Diagnostic::error(
                                                DiagnosticCode::UncoveredRequirement,
                                                format!("Requirement uncovered for operation {:?}", op_id),
                                            ));
                                        }
                                    }
                                }
                                crate::registry::PolicyRequirement::RequiresAttestation { predicate, subject_arg_idx } => {
                                    let matching = evidence.iter().find_map(|e| {
                                        let ty = self.all_defined_values.get(e)?;
                                        match ty {
                                            Type::Attestation { predicate: p, subject_ty } => {
                                                if p == predicate { Some(subject_ty.clone()) } else { None }
                                            }
                                            Type::Result { ok, .. } => match ok.as_ref() {
                                                Type::Attestation { predicate: p, subject_ty } => {
                                                    if p == predicate { Some(subject_ty.clone()) } else { None }
                                                }
                                                _ => None,
                                            },
                                            _ => None,
                                        }
                                    });

                                    match matching {
                                        Some(subj_ty) => {
                                            let arg_val_id = args.get(*subject_arg_idx);
                                            let expected_ty = arg_val_id.and_then(|id| self.all_defined_values.get(id));
                                            if expected_ty != Some(&subj_ty) {
                                                self.diagnostics.push(Diagnostic::error(
                                                    DiagnosticCode::RefutedRequirement,
                                                    format!("Requirement statically refuted for operation {:?}", op_id),
                                                ));
                                            }
                                        }
                                        None => {
                                            self.diagnostics.push(Diagnostic::error(
                                                DiagnosticCode::UncoveredRequirement,
                                                format!("Requirement uncovered for operation {:?}", op_id),
                                            ));
                                        }
                                    }
                                }
                                crate::registry::PolicyRequirement::RequiresStateBase { .. } => {}
                            }
                        }

                        full_act_effs
                    } else {
                        self.diagnostics.push(Diagnostic::error(
                            DiagnosticCode::UnknownOperation,
                            format!("OperationId {:?} not found in trusted registry", op_id),
                        ));
                        return;
                    }
                } else {
                    let mut effs = vec![Effect::Act(target_domain.clone())];
                    effs.extend(gate_effects.iter().cloned());
                    effs
                }
            }
            _ => inst.required_effects(),
        };

        for eff in &required_effects {
            // Act gate effects may come from trusted runtime authority; caller only needs act[D]
            if let Effect::Act(_) = eff {
                if !self.func.declared_effects.contains(eff) {
                    self.diagnostics.push(Diagnostic::error(
                        DiagnosticCode::EffectUndeclared,
                        format!(
                            "Instruction requires effect {:?} not declared in function effects {:?}",
                            eff, self.func.declared_effects
                        ),
                    ));
                }
            } else if !matches!(inst, Instruction::Act { .. }) {
                if !self.func.declared_effects.contains(eff) {
                    self.diagnostics.push(Diagnostic::error(
                        DiagnosticCode::EffectUndeclared,
                        format!(
                            "Instruction requires effect {:?} not declared in function effects {:?}",
                            eff, self.func.declared_effects
                        ),
                    ));
                }
            }
        }

        match inst {
            Instruction::Pure { .. } | Instruction::Read { .. } | Instruction::Infer { .. } => {}
            Instruction::Assign { source, ty, .. } => {
                if let Some(src_ty) = self.check_visible(*source, visible) {
                    if &src_ty != ty {
                        self.diagnostics.push(Diagnostic::error(
                            DiagnosticCode::TypeMismatch,
                            format!(
                                "Assign type mismatch: source is {:?}, dest is {:?}",
                                src_ty, ty
                            ),
                        ));
                    }
                }
            }
            Instruction::Verify {
                subject,
                subject_type,
                verifier_id,
                ..
            } => {
                let expected_subject_type = if let Some(reg) = self.registry {
                    if let Some(desc) = reg.verifiers.get(verifier_id) {
                        &desc.subject_type
                    } else {
                        subject_type
                    }
                } else {
                    subject_type
                };

                if let Some(sub_ty) = self.check_visible(*subject, visible) {
                    if &sub_ty != expected_subject_type {
                        self.diagnostics.push(Diagnostic::error(
                            DiagnosticCode::TypeMismatch,
                            format!(
                                "Verify subject type mismatch: expected {:?}, got {:?}",
                                expected_subject_type, sub_ty
                            ),
                        ));
                    }
                }
            }
            Instruction::Act { args, evidence, .. } => {
                for a in args {
                    self.check_visible(*a, visible);
                }
                for e in evidence {
                    self.check_visible(*e, visible);
                }
            }
        }
    }

    fn verify_terminator(
        &mut self,
        term: &Terminator,
        current_block: BlockId,
        visible: &mut BTreeSet<ValueId>,
    ) {
        match term {
            Terminator::Return(val_opt) => {
                if let Some(val_id) = val_opt {
                    if let Some(val_ty) = self.check_visible(*val_id, visible) {
                        if val_ty != self.func.return_type {
                            self.diagnostics.push(Diagnostic::error(
                                DiagnosticCode::TypeMismatch,
                                format!(
                                    "Return type mismatch: function returns {:?}, got {:?}",
                                    self.func.return_type, val_ty
                                ),
                            ));
                        }
                    }
                } else if self.func.return_type != Type::Unit {
                    self.diagnostics.push(Diagnostic::error(
                        DiagnosticCode::TypeMismatch,
                        format!(
                            "Return without value in function expecting {:?}",
                            self.func.return_type
                        ),
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
                            format!("CondBr condition must be Bool, got {:?}", cond_ty),
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
            Terminator::MatchActOutcome {
                outcome_val,
                success_arg,
                success_body,
                failure_arg,
                failure_body,
                partial_arg,
                partial_body,
                unknown_arg,
                unknown_body,
            } => {
                if let Some(res_ty) = self.check_visible(*outcome_val, visible) {
                    match res_ty {
                        Type::ActOutcome { success, failure } => {
                            self.verify_region(
                                success_body,
                                *success_arg,
                                &success,
                                current_block,
                                visible,
                            );
                            self.verify_region(
                                failure_body,
                                *failure_arg,
                                &failure,
                                current_block,
                                visible,
                            );
                            self.verify_region(
                                partial_body,
                                *partial_arg,
                                &Type::PartialReport,
                                current_block,
                                visible,
                            );
                            self.verify_region(
                                unknown_body,
                                *unknown_arg,
                                &Type::String,
                                current_block,
                                visible,
                            );
                        }
                        other => {
                            self.diagnostics.push(Diagnostic::error(
                                DiagnosticCode::TypeMismatch,
                                format!("MatchActOutcome expects ActOutcome<T,E>, got {:?}", other),
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
        param_arg: ValueId,
        _param_ty: &Type,
        _parent_block: BlockId,
        visible: &BTreeSet<ValueId>,
    ) {
        let mut region_visible = visible.clone();
        region_visible.insert(param_arg);

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
                                format!(
                                    "Region Return type mismatch: expected {:?}, got {:?}",
                                    self.func.return_type, val_ty
                                ),
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

    fn verify_branch_target(
        &mut self,
        target: BlockId,
        args: &[ValueId],
        visible: &BTreeSet<ValueId>,
    ) {
        let block = if let Some(b) = self.func.blocks.get(&target) {
            b
        } else {
            self.diagnostics.push(Diagnostic::error(
                DiagnosticCode::CfgBadTarget,
                format!("Branch target block {:?} does not exist", target),
            ));
            return;
        };

        if block.params.len() != args.len() {
            self.diagnostics.push(Diagnostic::error(
                DiagnosticCode::BlockArgArity,
                format!(
                    "Block {:?} expects {} arguments, got {}",
                    target,
                    block.params.len(),
                    args.len()
                ),
            ));
            return;
        }

        for (i, (arg_id, (_, expected_ty))) in args.iter().zip(&block.params).enumerate() {
            if let Some(arg_ty) = self.check_visible(*arg_id, visible) {
                if &arg_ty != expected_ty {
                    self.diagnostics.push(Diagnostic::error(
                        DiagnosticCode::BlockArgType,
                        format!(
                            "Block {:?} arg {} type mismatch: expected {:?}, got {:?}",
                            target, i, expected_ty, arg_ty
                        ),
                    ));
                }
            }
        }
    }

    fn find_predecessors(&self, target: BlockId) -> Vec<BlockId> {
        let mut preds = Vec::new();
        for (b_id, b) in &self.func.blocks {
            match &b.terminator {
                Terminator::Br {
                    target: t,
                    args: _,
                } => {
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
                Terminator::MatchResult {
                    ok_body,
                    err_body,
                    ..
                } => {
                    if let RegionTerminator::Br {
                        target: ok_t,
                        args: _,
                    } = &ok_body.terminator
                    {
                        if ok_t == &target {
                            preds.push(*b_id);
                        }
                    }
                    if let RegionTerminator::Br {
                        target: err_t,
                        args: _,
                    } = &err_body.terminator
                    {
                        if err_t == &target {
                            preds.push(*b_id);
                        }
                    }
                }
                Terminator::MatchActOutcome {
                    success_body,
                    failure_body,
                    partial_body,
                    unknown_body,
                    ..
                } => {
                    if let RegionTerminator::Br {
                        target: t,
                        args: _,
                    } = &success_body.terminator
                    {
                        if t == &target {
                            preds.push(*b_id);
                        }
                    }
                    if let RegionTerminator::Br {
                        target: t,
                        args: _,
                    } = &failure_body.terminator
                    {
                        if t == &target {
                            preds.push(*b_id);
                        }
                    }
                    if let RegionTerminator::Br {
                        target: t,
                        args: _,
                    } = &partial_body.terminator
                    {
                        if t == &target {
                            preds.push(*b_id);
                        }
                    }
                    if let RegionTerminator::Br {
                        target: t,
                        args: _,
                    } = &unknown_body.terminator
                    {
                        if t == &target {
                            preds.push(*b_id);
                        }
                    }
                }
                Terminator::Return(_) | Terminator::Unreachable => {}
            }
        }
        preds
    }
}
