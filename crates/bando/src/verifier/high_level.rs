use std::collections::{BTreeMap, BTreeSet};

use crate::{
    analysis::DominanceTree,
    conformance::schema::GateResolutionObservation,
    diagnostics::{Diagnostic, DiagnosticCode},
    ir::{
        effects::{Effect, EffectRow},
        ops::{Instruction, Region, RegionTerminator, Terminator},
        types::Type,
        BlockId, Function, Module, ValueId,
    },
    registry::{AgentId, ClaimContract, IntentId, RegistrySnapshot},
};

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ValueOrigin {
    Literal(String),
    VerifySubject {
        predicate: String,
        subject_val_id: ValueId,
        subject_literal: Option<String>,
    },
    DelegatedHandle {
        intent_id: IntentId,
        target_agent_id: AgentId,
    },
    Other(ValueId),
}

pub struct HighLevelVerifier<'a> {
    pub func: &'a Function,
    pub registry: Option<&'a RegistrySnapshot>,
    pub diagnostics: Vec<Diagnostic>,
    pub all_defined_values: BTreeMap<ValueId, Type>,
    pub value_origins: BTreeMap<ValueId, ValueOrigin>,
    pub static_gate_resolutions: Vec<GateResolutionObservation>,
}

impl<'a> HighLevelVerifier<'a> {
    pub fn new(func: &'a Function) -> Self {
        Self {
            func,
            registry: None,
            diagnostics: Vec::new(),
            all_defined_values: BTreeMap::new(),
            value_origins: BTreeMap::new(),
            static_gate_resolutions: Vec::new(),
        }
    }

    pub fn with_registry(func: &'a Function, registry: &'a RegistrySnapshot) -> Self {
        Self {
            func,
            registry: Some(registry),
            diagnostics: Vec::new(),
            all_defined_values: BTreeMap::new(),
            value_origins: BTreeMap::new(),
            static_gate_resolutions: Vec::new(),
        }
    }

    pub fn verify_module(module: &Module) -> Result<(), Vec<Diagnostic>> {
        let mut all_diags = Vec::new();
        for func in &module.functions {
            let mut v = HighLevelVerifier::new(func);
            v.verify();
            all_diags.extend(v.diagnostics);
        }
        if all_diags.is_empty() {
            Ok(())
        } else {
            Err(all_diags)
        }
    }

    pub fn verify_module_with_registry(
        module: &Module,
        registry: &RegistrySnapshot,
    ) -> Result<Vec<GateResolutionObservation>, (Vec<Diagnostic>, Vec<GateResolutionObservation>)>
    {
        let mut all_diags = Vec::new();
        let mut all_resolutions = Vec::new();
        for func in &module.functions {
            let mut v = HighLevelVerifier::with_registry(func, registry);
            v.verify();
            all_diags.extend(v.diagnostics);
            all_resolutions.extend(v.static_gate_resolutions);
        }
        if all_diags.is_empty() {
            Ok(all_resolutions)
        } else {
            Err((all_diags, all_resolutions))
        }
    }

    pub fn verify(&mut self) {
        // Collect function parameter definitions
        for (param_id, param_ty) in &self.func.params {
            self.all_defined_values.insert(*param_id, param_ty.clone());
            self.value_origins
                .insert(*param_id, ValueOrigin::Other(*param_id));
        }

        // Collect block parameter definitions
        for (b_id, block) in &self.func.blocks {
            if b_id != &self.func.entry {
                for (p_id, p_ty) in &block.params {
                    self.all_defined_values.insert(*p_id, p_ty.clone());
                    self.value_origins.insert(*p_id, ValueOrigin::Other(*p_id));
                }
            }
        }

        // Collect all instruction defs
        for block in self.func.blocks.values() {
            for inst in &block.instructions {
                let (dest, ty) = self.instruction_def_type(inst);
                if let Some(existing) = self.all_defined_values.insert(dest, ty.clone()) {
                    self.diagnostics.push(Diagnostic::error(
                        DiagnosticCode::SsaDuplicateDef,
                        format!(
                            "SSA value {:?} defined multiple times with types {:?} and {:?}",
                            dest, existing, ty
                        ),
                    ));
                }
            }
        }

        // Build dominance tree
        let dom_tree = self.compute_dominance_tree();

        for (b_id, block) in &self.func.blocks {
            let mut visible = BTreeSet::new();
            for (param_id, _) in &self.func.params {
                visible.insert(*param_id);
            }
            for (&other_id, other_block) in &self.func.blocks {
                if other_id != *b_id && dom_tree.dominates(other_id, *b_id) {
                    for (p_id, _) in &other_block.params {
                        visible.insert(*p_id);
                    }
                    for inst in &other_block.instructions {
                        let (dest, _) = self.instruction_def_type(inst);
                        visible.insert(dest);
                    }
                }
            }
            self.verify_block(block, &visible);
        }
    }

    fn compute_dominance_tree(&self) -> DominanceTree<BlockId> {
        let block_ids: Vec<BlockId> = self.func.blocks.keys().copied().collect();
        DominanceTree::compute(self.func.entry, &block_ids, |b| self.get_predecessors(b))
    }

    fn get_predecessors(&self, target: BlockId) -> Vec<BlockId> {
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
                Terminator::MatchResult {
                    ok_body, err_body, ..
                } => {
                    if let RegionTerminator::Br { target: ok_t, .. } = &ok_body.terminator {
                        if ok_t == &target {
                            preds.push(*b_id);
                        }
                    }
                    if let RegionTerminator::Br { target: err_t, .. } = &err_body.terminator {
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
                    if let RegionTerminator::Br { target: t, .. } = &success_body.terminator {
                        if t == &target {
                            preds.push(*b_id);
                        }
                    }
                    if let RegionTerminator::Br { target: t, .. } = &failure_body.terminator {
                        if t == &target {
                            preds.push(*b_id);
                        }
                    }
                    if let RegionTerminator::Br { target: t, .. } = &partial_body.terminator {
                        if t == &target {
                            preds.push(*b_id);
                        }
                    }
                    if let RegionTerminator::Br { target: t, .. } = &unknown_body.terminator {
                        if t == &target {
                            preds.push(*b_id);
                        }
                    }
                }
                _ => {}
            }
        }
        preds
    }

    fn verify_block(&mut self, block: &crate::ir::Block, visible: &BTreeSet<ValueId>) {
        let mut block_visible = visible.clone();
        for (p_id, _) in &block.params {
            block_visible.insert(*p_id);
        }
        for inst in &block.instructions {
            self.verify_instruction(inst, &block_visible);
            let (dest, _) = self.instruction_def_type(inst);
            block_visible.insert(dest);
        }
        self.verify_terminator(&block.terminator, block.id, &block_visible);
    }

    fn instruction_def_type(&self, inst: &Instruction) -> (ValueId, Type) {
        match inst {
            Instruction::Pure { dest, ty, .. } => (*dest, ty.clone()),
            Instruction::Read {
                dest,
                ok_type,
                err_type,
                ..
            } => (*dest, Type::result(ok_type.clone(), err_type.clone())),
            Instruction::Infer {
                dest,
                ok_type,
                err_type,
                ..
            } => (*dest, Type::result(ok_type.clone(), err_type.clone())),
            Instruction::Assign { dest, ty, .. } => (*dest, ty.clone()),
            Instruction::Verify {
                dest,
                verifier_id,
                output_predicate,
                subject_type,
                ..
            } => {
                if let Some(reg) = self.registry {
                    if let Some(desc) = reg.verifiers.get(verifier_id) {
                        let att_ty = Type::attestation(
                            desc.output_predicate.clone(),
                            desc.subject_type.clone(),
                        );
                        return (*dest, Type::result(att_ty, Type::String));
                    }
                }
                let att_ty = Type::attestation(output_predicate.clone(), subject_type.clone());
                (*dest, Type::result(att_ty, Type::String))
            }
            Instruction::Act {
                dest,
                success_type,
                failure_type,
                ..
            } => (
                *dest,
                Type::act_outcome(success_type.clone(), failure_type.clone()),
            ),
            Instruction::Delegate {
                dest, intent_id, ..
            } => {
                if let Some(reg) = self.registry {
                    if let Some(desc) = reg.intents.get(intent_id) {
                        return (
                            *dest,
                            Type::child_handle(
                                desc.output_type.clone(),
                                desc.error_type.clone(),
                                desc.child_effects.clone(),
                            ),
                        );
                    }
                }
                (
                    *dest,
                    Type::child_handle(Type::String, Type::String, EffectRow::empty()),
                )
            }
            Instruction::Await { dest, handle } => {
                if let Some(Type::ChildHandle { ok, err, .. }) = self.all_defined_values.get(handle)
                {
                    (*dest, Type::result((**ok).clone(), (**err).clone()))
                } else {
                    (*dest, Type::result(Type::String, Type::String))
                }
            }
            Instruction::Internalize { dest, claim, .. } => {
                if let Some(Type::Claim(payload)) = self.all_defined_values.get(claim) {
                    (
                        *dest,
                        Type::result(Type::belief((**payload).clone()), Type::String),
                    )
                } else {
                    (
                        *dest,
                        Type::result(Type::belief(Type::String), Type::String),
                    )
                }
            }
        }
    }

    fn check_visible(&mut self, val_id: ValueId, visible: &BTreeSet<ValueId>) -> Option<Type> {
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
        // Track value origins
        match inst {
            Instruction::Pure { dest, val, .. } => {
                if let crate::ir::values::Value::String(s) = val {
                    self.value_origins
                        .insert(*dest, ValueOrigin::Literal(s.clone()));
                } else {
                    self.value_origins.insert(*dest, ValueOrigin::Other(*dest));
                }
            }
            Instruction::Verify {
                dest,
                verifier_id,
                subject,
                ..
            } => {
                let subj_lit =
                    if let Some(ValueOrigin::Literal(s)) = self.value_origins.get(subject) {
                        Some(s.clone())
                    } else {
                        None
                    };
                let pred = if let Some(reg) = self.registry {
                    if let Some(desc) = reg.verifiers.get(verifier_id) {
                        desc.output_predicate.clone()
                    } else {
                        "UnknownPredicate".to_string()
                    }
                } else {
                    "UnknownPredicate".to_string()
                };
                self.value_origins.insert(
                    *dest,
                    ValueOrigin::VerifySubject {
                        predicate: pred,
                        subject_val_id: *subject,
                        subject_literal: subj_lit,
                    },
                );
            }
            _ => {}
        }

        // Q1 & Q2: Check required effects and fail-closed authorities
        let required_effects = match inst {
            Instruction::Verify {
                verifier_id,
                verifier_effects,
                subject,
                ..
            } => {
                if let Some(reg) = self.registry {
                    if let Some(desc) = reg.verifiers.get(verifier_id) {
                        if let Some(subj_ty) = self.check_visible(*subject, visible) {
                            if subj_ty != desc.subject_type {
                                self.diagnostics.push(Diagnostic::error(
                                    DiagnosticCode::TypeMismatch,
                                    format!(
                                        "Verify subject type mismatch: expected {:?}, got {:?}",
                                        desc.subject_type, subj_ty
                                    ),
                                ));
                            }
                        }

                        let effs: Vec<_> = desc.effect_envelope.effects.iter().cloned().collect();

                        // 1. Semantic row must contain verifier effects (Rule #1, Q2)
                        for eff in &effs {
                            if !self.func.declared_effects.contains(eff) {
                                self.diagnostics.push(Diagnostic::error(
                                    DiagnosticCode::EffectUndeclared,
                                    format!("Verifier requires effect {:?} not declared in function effects", eff),
                                ));
                            }
                        }

                        // 2. Caller authority check (Q2, fail-closed)
                        if let Some(ca) = &reg.caller_authority {
                            if !ca.covers(&effs) {
                                self.diagnostics.push(Diagnostic::error(
                                    DiagnosticCode::AuthorityInsufficient,
                                    format!(
                                        "Caller authority insufficient for verifier {:?}",
                                        verifier_id
                                    ),
                                ));
                            }
                        } else {
                            self.diagnostics.push(Diagnostic::error(
                                DiagnosticCode::AuthorityInsufficient,
                                format!("Caller authority absent for verifier {:?}", verifier_id),
                            ));
                        }

                        effs
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
            Instruction::Act {
                op_id,
                target_domain,
                gate_effects,
                args,
                evidence,
                ..
            } => {
                for a in args {
                    self.check_visible(*a, visible);
                }
                for e in evidence {
                    self.check_visible(*e, visible);
                }

                if let Some(reg) = self.registry {
                    if let Some(op_desc) = reg.operations.get(op_id) {
                        let act_eff = Effect::Act(op_desc.target_domain.clone());

                        // 1. Caller authority must contain act[target_domain] (Q2, fail-closed)
                        if let Some(ca) = &reg.caller_authority {
                            if !ca.contains(&act_eff) {
                                self.diagnostics.push(Diagnostic::error(
                                    DiagnosticCode::AuthorityInsufficient,
                                    format!(
                                        "Caller authority lacks target capability {:?}",
                                        act_eff
                                    ),
                                ));
                            }
                        } else {
                            self.diagnostics.push(Diagnostic::error(
                                DiagnosticCode::AuthorityInsufficient,
                                format!("Caller authority absent for operation {:?}", op_id),
                            ));
                        }

                        // 2. Compute gate effects from requirements
                        let mut gate_effs = Vec::new();
                        for req in &op_desc.requirements {
                            gate_effs.extend(req.required_gate_effects());
                        }

                        // 3. Runtime authority must cover all gate check effects (Q2, fail-closed)
                        for g_eff in &gate_effs {
                            if let Some(ra) = &reg.runtime_authority {
                                if !ra.contains(g_eff) {
                                    self.diagnostics.push(Diagnostic::error(
                                        DiagnosticCode::AuthorityInsufficient,
                                        format!(
                                            "Runtime authority lacks gate capability {:?}",
                                            g_eff
                                        ),
                                    ));
                                }
                            } else {
                                self.diagnostics.push(Diagnostic::error(
                                    DiagnosticCode::AuthorityInsufficient,
                                    format!("Runtime authority absent for gate check {:?}", g_eff),
                                ));
                            }
                        }

                        let mut full_act_effs = vec![act_eff];
                        full_act_effs.extend(gate_effs);

                        // 4. Function declared effects MUST contain all semantic effects Σ_act (Q2)
                        for eff in &full_act_effs {
                            if !self.func.declared_effects.contains(eff) {
                                self.diagnostics.push(Diagnostic::error(
                                    DiagnosticCode::EffectUndeclared,
                                    format!("Operation requires effect {:?} not declared in function effects", eff),
                                ));
                            }
                        }

                        // 5. Enforce declared envelope (Rule #11, S2C13)
                        for eff in &full_act_effs {
                            if !op_desc.declared_envelope.contains(eff) {
                                self.diagnostics.push(Diagnostic::error(
                                    DiagnosticCode::EnvelopeExceeded,
                                    format!("Σ_act effect {:?} exceeds operation declared envelope {:?}", eff, op_desc.declared_envelope),
                                ));
                            }
                        }

                        // 6. Static requirement resolution over SSA subject identity (Q3)
                        for req in &op_desc.requirements {
                            match req {
                                crate::registry::PolicyRequirement::RequiresStaticProof {
                                    predicate,
                                    subject_arg_idx,
                                } => {
                                    let mut matching_ev = None;
                                    for e in evidence {
                                        if let Some(origin) = self.value_origins.get(e) {
                                            if let ValueOrigin::VerifySubject {
                                                predicate: p,
                                                subject_val_id,
                                                subject_literal,
                                            } = origin
                                            {
                                                if p == predicate {
                                                    matching_ev = Some((
                                                        *subject_val_id,
                                                        subject_literal.clone(),
                                                    ));
                                                    break;
                                                }
                                            }
                                        }
                                    }

                                    match matching_ev {
                                        Some((sub_val_id, sub_lit)) => {
                                            let arg_val_id = args.get(*subject_arg_idx).cloned();
                                            let arg_lit = arg_val_id.and_then(|id| {
                                                if let Some(ValueOrigin::Literal(s)) =
                                                    self.value_origins.get(&id)
                                                {
                                                    Some(s.clone())
                                                } else {
                                                    None
                                                }
                                            });

                                            if arg_val_id == Some(sub_val_id) {
                                                // Statically Proved by identical SSA ValueId!
                                                self.static_gate_resolutions.push(
                                                    GateResolutionObservation {
                                                        op_id: op_id.0.clone(),
                                                        resolution: "Proved".to_string(),
                                                    },
                                                );
                                            } else if sub_lit.is_some() && arg_lit.is_some() {
                                                if sub_lit == arg_lit {
                                                    // Statically Proved by identical compile-time literal!
                                                    self.static_gate_resolutions.push(
                                                        GateResolutionObservation {
                                                            op_id: op_id.0.clone(),
                                                            resolution: "Proved".to_string(),
                                                        },
                                                    );
                                                } else {
                                                    // Statically Refuted by distinct compile-time literal! (Q3, S2C09)
                                                    self.static_gate_resolutions.push(
                                                        GateResolutionObservation {
                                                            op_id: op_id.0.clone(),
                                                            resolution: "Refuted".to_string(),
                                                        },
                                                    );
                                                    self.diagnostics.push(Diagnostic::error(
                                                        DiagnosticCode::RefutedRequirement,
                                                        format!("Requirement statically refuted for operation {:?}: expected subject literal {:?}, got {:?}", op_id, arg_lit, sub_lit),
                                                    ));
                                                }
                                            } else {
                                                // Deferred dynamic check
                                                self.static_gate_resolutions.push(
                                                    GateResolutionObservation {
                                                        op_id: op_id.0.clone(),
                                                        resolution: "Deferred".to_string(),
                                                    },
                                                );
                                            }
                                        }
                                        None => {
                                            self.static_gate_resolutions.push(
                                                GateResolutionObservation {
                                                    op_id: op_id.0.clone(),
                                                    resolution: "Uncovered".to_string(),
                                                },
                                            );
                                            self.diagnostics.push(Diagnostic::error(
                                                DiagnosticCode::UncoveredRequirement,
                                                format!("Static proof requirement for predicate '{}' uncovered for operation {:?}", predicate, op_id),
                                            ));
                                        }
                                    }
                                }
                                crate::registry::PolicyRequirement::RequiresAttestation {
                                    predicate,
                                    ..
                                } => {
                                    let mut matching_ev = false;
                                    for e in evidence {
                                        if let Some(origin) = self.value_origins.get(e) {
                                            if let ValueOrigin::VerifySubject {
                                                predicate: p, ..
                                            } = origin
                                            {
                                                if p == predicate {
                                                    matching_ev = true;
                                                    break;
                                                }
                                            }
                                        }
                                    }

                                    if matching_ev {
                                        self.static_gate_resolutions.push(
                                            GateResolutionObservation {
                                                op_id: op_id.0.clone(),
                                                resolution: "Deferred".to_string(),
                                            },
                                        );
                                    } else {
                                        self.static_gate_resolutions.push(
                                            GateResolutionObservation {
                                                op_id: op_id.0.clone(),
                                                resolution: "Uncovered".to_string(),
                                            },
                                        );
                                        self.diagnostics.push(Diagnostic::error(
                                            DiagnosticCode::UncoveredRequirement,
                                            format!("Attestation requirement for predicate '{}' uncovered for operation {:?}", predicate, op_id),
                                        ));
                                    }
                                }
                                crate::registry::PolicyRequirement::RequiresStateBase {
                                    ..
                                } => {
                                    self.static_gate_resolutions
                                        .push(GateResolutionObservation {
                                            op_id: op_id.0.clone(),
                                            resolution: "Deferred".to_string(),
                                        });
                                }
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
                    effs.extend(gate_effects.clone());
                    effs
                }
            }
            // Slice 3: Delegate
            Instruction::Delegate {
                intent_id,
                args,
                requested_effects,
                authority_grant,
                ..
            } => {
                for a in args {
                    self.check_visible(*a, visible);
                }

                if let Some(reg) = self.registry {
                    if let Some(desc) = reg.intents.get(intent_id) {
                        // 1. Input type match
                        if args.len() != desc.input_types.len() {
                            self.diagnostics.push(Diagnostic::error(
                                DiagnosticCode::DelegateInputTypeMismatch,
                                format!(
                                    "Delegate argument count mismatch: expected {}, got {}",
                                    desc.input_types.len(),
                                    args.len()
                                ),
                            ));
                        } else {
                            for (i, a_id) in args.iter().enumerate() {
                                if let Some(arg_ty) = self.check_visible(*a_id, visible) {
                                    if arg_ty != desc.input_types[i] {
                                        self.diagnostics.push(Diagnostic::error(
                                            DiagnosticCode::DelegateInputTypeMismatch,
                                            format!("Delegate argument {} type mismatch: expected {:?}, got {:?}", i, desc.input_types[i], arg_ty),
                                        ));
                                    }
                                }
                            }
                        }

                        // 2. Ceiling checks: Σ_child ⊆ Σ_requested ⊆ Σ_exported
                        let req_row = EffectRow {
                            effects: requested_effects.iter().cloned().collect(),
                        };

                        if !desc.child_effects.is_subset(&req_row) {
                            self.diagnostics.push(Diagnostic::error(
                                DiagnosticCode::InvocationCeilingBelowChild,
                                format!("Invocation ceiling {:?} is below child effect requirement {:?}", req_row, desc.child_effects),
                            ));
                        }

                        if !req_row.is_subset(&desc.exported_envelope) {
                            self.diagnostics.push(Diagnostic::error(
                                DiagnosticCode::InvocationCeilingAboveExported,
                                format!(
                                    "Invocation ceiling {:?} exceeds exported envelope {:?}",
                                    req_row, desc.exported_envelope
                                ),
                            ));
                        }

                        // 3. Grant checks: grant ⊆ CallerAuthority && grant ⊆ Σ_requested
                        if let Some(ca) = &reg.caller_authority {
                            for g in authority_grant {
                                if !ca.contains(g) {
                                    self.diagnostics.push(Diagnostic::error(
                                        DiagnosticCode::GrantExceedsCallerAuthority,
                                        format!(
                                            "Authority grant {:?} exceeds caller authority {:?}",
                                            g, ca
                                        ),
                                    ));
                                }
                                if !req_row.contains(g) {
                                    self.diagnostics.push(Diagnostic::error(
                                        DiagnosticCode::GrantExceedsRequestedCeiling,
                                        format!("Authority grant {:?} exceeds requested invocation ceiling {:?}", g, req_row),
                                    ));
                                }
                            }
                        } else {
                            self.diagnostics.push(Diagnostic::error(
                                DiagnosticCode::AuthorityInsufficient,
                                "Caller authority absent for delegate",
                            ));
                        }

                        // 4. Function declared effects must contain child effects (Section 8)
                        for eff in &desc.child_effects.effects {
                            if !self.func.declared_effects.contains(eff) {
                                self.diagnostics.push(Diagnostic::error(
                                    DiagnosticCode::EffectUndeclared,
                                    format!("Delegate child effect {:?} not declared in function effects", eff),
                                ));
                            }
                        }

                        desc.child_effects.effects.iter().cloned().collect()
                    } else {
                        self.diagnostics.push(Diagnostic::error(
                            DiagnosticCode::UnknownIntent,
                            format!("IntentId {:?} not found in trusted registry", intent_id),
                        ));
                        return;
                    }
                } else {
                    requested_effects.clone()
                }
            }
            // Slice 3: Await
            Instruction::Await { handle, .. } => {
                if let Some(ty) = self.check_visible(*handle, visible) {
                    if !matches!(ty, Type::ChildHandle { .. }) {
                        self.diagnostics.push(Diagnostic::error(
                            DiagnosticCode::AwaitNonChildHandle,
                            format!("Await expects ChildHandle type, got {:?}", ty),
                        ));
                    }
                }
                Vec::new()
            }
            // Slice 3: Internalize
            Instruction::Internalize {
                policy_id, claim, ..
            } => {
                if let Some(ty) = self.check_visible(*claim, visible) {
                    if !matches!(ty, Type::Claim { .. }) {
                        self.diagnostics.push(Diagnostic::error(
                            DiagnosticCode::InternalizeNonClaim,
                            format!("Internalize expects Claim type, got {:?}", ty),
                        ));
                    }
                }

                if let Some(reg) = self.registry {
                    if let Some(policy_desc) = reg.internalization_policies.get(policy_id) {
                        if matches!(
                            policy_desc.accepted_claim_contract,
                            ClaimContract::RejectAll
                        ) {
                            self.diagnostics.push(Diagnostic::error(
                                DiagnosticCode::RefutedRequirement,
                                format!("Claim rejected by internalization policy {:?}", policy_id),
                            ));
                        }

                        let val_effs: Vec<_> = policy_desc
                            .validation_effect_envelope
                            .effects
                            .iter()
                            .cloned()
                            .collect();

                        // 1. Function declared effects must contain validation effects
                        for eff in &val_effs {
                            if !self.func.declared_effects.contains(eff) {
                                self.diagnostics.push(Diagnostic::error(
                                    DiagnosticCode::EffectUndeclared,
                                    format!("Internalize validation effect {:?} not declared in function effects", eff),
                                ));
                            }
                        }

                        // 2. Section 45: Caller authority must cover validation effects
                        if let Some(ca) = &reg.caller_authority {
                            if !ca.covers(&val_effs) {
                                self.diagnostics.push(Diagnostic::error(
                                    DiagnosticCode::ValidationAuthorityInsufficient,
                                    format!("Caller authority insufficient for internalization validation {:?}", val_effs),
                                ));
                            }
                        } else {
                            self.diagnostics.push(Diagnostic::error(
                                DiagnosticCode::ValidationAuthorityInsufficient,
                                "Caller authority absent for internalization validation",
                            ));
                        }

                        val_effs
                    } else {
                        self.diagnostics.push(Diagnostic::error(
                            DiagnosticCode::UnknownInternalizationPolicy,
                            format!("PolicyId {:?} not found in trusted registry", policy_id),
                        ));
                        return;
                    }
                } else {
                    Vec::new()
                }
            }
            Instruction::Read { domain, .. } => vec![Effect::Read(domain.clone())],
            Instruction::Infer { .. } => vec![Effect::Infer],
            Instruction::Pure { .. } => Vec::new(),
            Instruction::Assign { source, .. } => {
                self.check_visible(*source, visible);
                Vec::new()
            }
        };

        // Rule #1 & #9: check that required effects are declared in function signature
        for eff in &required_effects {
            if !self.func.declared_effects.contains(eff) {
                self.diagnostics.push(Diagnostic::error(
                    DiagnosticCode::EffectUndeclared,
                    format!(
                        "Instruction requires effect {:?} not declared in function signature",
                        eff
                    ),
                ));
            }
        }
    }

    fn verify_terminator(
        &mut self,
        term: &Terminator,
        block_id: BlockId,
        visible: &BTreeSet<ValueId>,
    ) {
        match term {
            Terminator::Return(val_opt) => {
                let ret_ty = if let Some(val_id) = val_opt {
                    self.check_visible(*val_id, visible).unwrap_or(Type::String)
                } else {
                    Type::String
                };
                if ret_ty != self.func.return_type {
                    self.diagnostics.push(Diagnostic::error(
                        DiagnosticCode::TypeMismatch,
                        format!(
                            "Return type mismatch in block {:?}: expected {:?}, got {:?}",
                            block_id, self.func.return_type, ret_ty
                        ),
                    ));
                }
            }
            Terminator::Br { target, args } => {
                self.verify_branch_target(*target, args, block_id, visible);
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
                            format!(
                                "CondBr condition {:?} must have type Bool, got {:?}",
                                cond, cond_ty
                            ),
                        ));
                    }
                }
                self.verify_branch_target(*true_target, true_args, block_id, visible);
                self.verify_branch_target(*false_target, false_args, block_id, visible);
            }
            Terminator::MatchResult {
                result_val,
                ok_arg,
                ok_body,
                err_arg,
                err_body,
            } => {
                let (ok_ty, err_ty) = match self.check_visible(*result_val, visible) {
                    Some(Type::Result { ok, err }) => (*ok, *err),
                    Some(other) => {
                        self.diagnostics.push(Diagnostic::error(
                            DiagnosticCode::TypeMismatch,
                            format!("MatchResult on non-result type {:?}", other),
                        ));
                        (Type::String, Type::String)
                    }
                    None => (Type::String, Type::String),
                };

                self.verify_region(ok_body, *ok_arg, &ok_ty, block_id, visible);
                self.verify_region(err_body, *err_arg, &err_ty, block_id, visible);
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
                let (succ_ty, fail_ty) = match self.check_visible(*outcome_val, visible) {
                    Some(Type::ActOutcome { success, failure }) => (*success, *failure),
                    Some(other) => {
                        self.diagnostics.push(Diagnostic::error(
                            DiagnosticCode::TypeMismatch,
                            format!("MatchActOutcome on non-act-outcome type {:?}", other),
                        ));
                        (Type::String, Type::String)
                    }
                    None => (Type::String, Type::String),
                };

                self.verify_region(success_body, *success_arg, &succ_ty, block_id, visible);
                self.verify_region(failure_body, *failure_arg, &fail_ty, block_id, visible);
                self.verify_region(
                    partial_body,
                    *partial_arg,
                    &Type::PartialReport,
                    block_id,
                    visible,
                );
                self.verify_region(unknown_body, *unknown_arg, &Type::String, block_id, visible);
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
            let (dest, _) = self.instruction_def_type(inst);
            region_visible.insert(dest);
        }

        match &region.terminator {
            RegionTerminator::Return(val_opt) => {
                let ret_ty = if let Some(val_id) = val_opt {
                    self.check_visible(*val_id, &region_visible)
                        .unwrap_or(Type::String)
                } else {
                    Type::String
                };
                if ret_ty != self.func.return_type {
                    self.diagnostics.push(Diagnostic::error(
                        DiagnosticCode::TypeMismatch,
                        format!(
                            "Region return type mismatch: expected {:?}, got {:?}",
                            self.func.return_type, ret_ty
                        ),
                    ));
                }
            }
            RegionTerminator::Br { target, args } => {
                self.verify_branch_target(*target, args, _parent_block, &region_visible);
            }
            RegionTerminator::Unreachable => {}
        }
    }

    fn verify_branch_target(
        &mut self,
        target: BlockId,
        args: &[ValueId],
        source_block: BlockId,
        visible: &BTreeSet<ValueId>,
    ) {
        let target_block = match self.func.blocks.get(&target) {
            Some(b) => b,
            None => {
                self.diagnostics.push(Diagnostic::error(
                    DiagnosticCode::CfgBadTarget,
                    format!(
                        "Branch from block {:?} to non-existent target block {:?}",
                        source_block, target
                    ),
                ));
                return;
            }
        };

        if target_block.params.len() != args.len() {
            self.diagnostics.push(Diagnostic::error(
                DiagnosticCode::BlockArgArity,
                format!(
                    "Block {:?} expects {} arguments, but branch provided {}",
                    target,
                    target_block.params.len(),
                    args.len()
                ),
            ));
            return;
        }

        for (i, (param_id, expected_ty)) in target_block.params.iter().enumerate() {
            let arg_id = args[i];
            if let Some(arg_ty) = self.check_visible(arg_id, visible) {
                // Section 32 & 34: Handle Joins in CFG
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
                                format!("Handle join type mismatch: expected ok={:?}, err={:?}, got ok={:?}, err={:?}", exp_ok, exp_err, arg_ok, arg_err),
                            ));
                        } else if !arg_effs.is_subset(exp_effs) {
                            self.diagnostics.push(Diagnostic::error(
                                DiagnosticCode::IncompatibleHandleJoin,
                                format!("Handle join effect loss: incoming effects {:?} not covered by merged handle effects {:?}", arg_effs, exp_effs),
                            ));
                        }
                    } else {
                        self.diagnostics.push(Diagnostic::error(
                            DiagnosticCode::BlockArgType,
                            format!(
                                "Block {:?} parameter {} ({:?}) expects type {:?}, got {:?}",
                                target, i, param_id, expected_ty, arg_ty
                            ),
                        ));
                    }
                } else if &arg_ty != expected_ty {
                    self.diagnostics.push(Diagnostic::error(
                        DiagnosticCode::BlockArgType,
                        format!(
                            "Block {:?} parameter {} ({:?}) expects type {:?}, got {:?}",
                            target, i, param_id, expected_ty, arg_ty
                        ),
                    ));
                }
            }
        }
    }
}
