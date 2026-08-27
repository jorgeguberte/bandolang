use std::collections::{BTreeMap, BTreeSet};
use serde::{Deserialize, Serialize};

use crate::{
    analysis::PathFactAnalyzer,
    conformance::schema::{GateCheckObservation, GateResolutionObservation},
    gate::{DeferredCheck, GateEngine, RequirementResolution},
    ir::{
        effects::Effect,
        facts::{Fact, FactArg, LatentPostconditions},
        types::Type,
        values::Value as VmValue,
    },
    lowering::CompilerMutations,
    registry::{MutationFootprint, RegistrySnapshot},
    vm_ir::{VmBlockId, VmFunction, VmInstruction, VmTerminator, VmValueId},
    world::WorldState,
};

use super::adapters::RuntimeAdapters;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum VmStatus {
    Running,
    Terminated,
    Error(String),
    ProtocolViolation(String),
}

#[derive(Debug, Clone)]
pub struct VmExecutionState {
    pub current_block: VmBlockId,
    pub env: BTreeMap<String, VmValue>,
    pub types: BTreeMap<String, String>,
    pub latent: BTreeMap<String, LatentPostconditions>,
    pub observable_effects: Vec<String>,
    pub lineage: BTreeMap<String, Vec<String>>,
    pub active_facts: BTreeSet<Fact>,
    pub status: VmStatus,
    pub return_value: Option<VmValue>,
    pub world: WorldState,
    pub invalidated_keys: BTreeSet<String>,
    pub gate_resolutions: Vec<GateResolutionObservation>,
    pub gate_trace: Vec<GateCheckObservation>,
}

pub struct VmInterpreter<'a> {
    pub func: &'a VmFunction,
    pub adapters: &'a RuntimeAdapters,
    pub registry: &'a RegistrySnapshot,
    pub mutations: CompilerMutations,
}

impl<'a> VmInterpreter<'a> {
    pub fn new(
        func: &'a VmFunction,
        adapters: &'a RuntimeAdapters,
        registry: &'a RegistrySnapshot,
    ) -> Self {
        Self {
            func,
            adapters,
            registry,
            mutations: CompilerMutations::default(),
        }
    }

    pub fn with_mutations(
        func: &'a VmFunction,
        adapters: &'a RuntimeAdapters,
        registry: &'a RegistrySnapshot,
        mutations: CompilerMutations,
    ) -> Self {
        Self {
            func,
            adapters,
            registry,
            mutations,
        }
    }

    pub fn execute(
        &self,
        inputs: BTreeMap<String, VmValue>,
        initial_world: WorldState,
        initial_facts: BTreeSet<Fact>,
        max_steps: usize,
    ) -> VmExecutionState {
        let mut state = VmExecutionState {
            current_block: self.func.entry,
            env: inputs.clone(),
            types: BTreeMap::new(),
            latent: BTreeMap::new(),
            observable_effects: Vec::new(),
            lineage: BTreeMap::new(),
            active_facts: initial_facts.clone(),
            status: VmStatus::Running,
            return_value: None,
            world: initial_world,
            invalidated_keys: BTreeSet::new(),
            gate_resolutions: Vec::new(),
            gate_trace: Vec::new(),
        };

        // Static path fact analysis
        let analysis = PathFactAnalyzer::with_mutations(self.func, self.mutations.clone()).analyze();

        // Populate parameter types into state
        if let Some(entry_block) = self.func.blocks.get(&self.func.entry) {
            for (val_id, ty) in &entry_block.params {
                state.types.insert(format!("v{}", val_id.0), ty.display_name());
            }
        }

        let mut steps = 0;

        while state.status == VmStatus::Running {
            if steps >= max_steps {
                state.status = VmStatus::Error("Maximum execution steps exceeded".to_string());
                break;
            }
            steps += 1;

            let block = match self.func.blocks.get(&state.current_block) {
                Some(b) => b,
                None => {
                    state.status = VmStatus::Error(format!(
                        "Block {:?} not found during execution",
                        state.current_block
                    ));
                    break;
                }
            };

            // Active path facts for current block
            let block_facts = analysis
                .block_in_facts
                .get(&state.current_block)
                .cloned()
                .unwrap_or_default();
            let mut facts = initial_facts.clone();
            facts.extend(block_facts);

            if !self.mutations.s2m14_current_facts_not_invalidated {
                facts.retain(|f| {
                    if f.predicate == "CurrentState" {
                        if let Some(FactArg::Literal(k)) = f.args.first() {
                            return !state.invalidated_keys.contains(k);
                        }
                    }
                    true
                });
            }
            if self.mutations.s2m15_historical_facts_invalidated && !state.invalidated_keys.is_empty() {
                facts.retain(|f| f.predicate != "Historical");
            }
            state.active_facts = facts;

            // Execute instructions in block
            for inst in &block.instructions {
                self.execute_instruction(inst, &mut state);
                if state.status != VmStatus::Running {
                    break;
                }
            }

            if state.status != VmStatus::Running {
                break;
            }

            // Execute terminator
            self.execute_terminator(&block.terminator, &mut state);
        }

        state
    }

    fn execute_instruction(&self, inst: &VmInstruction, state: &mut VmExecutionState) {
        match inst {
            VmInstruction::VmPure { dest, val, ty } => {
                let sym = format!("v{}", dest.0);
                state.env.insert(sym.clone(), val.clone());
                state.types.insert(sym, ty.display_name());
            }
            VmInstruction::VmRead {
                dest,
                domain,
                ok_type,
                err_type,
                latent,
            } => {
                let sym = format!("v{}", dest.0);
                let res = self.adapters.read.read(domain);

                // Mutation M07: drop read effect
                if !self.mutations.m07_drop_read_effect {
                    state
                        .observable_effects
                        .push(format!("read[{}]", domain));
                }

                let out_val = match res {
                    Ok(v) => VmValue::ok(v),
                    Err(e) => VmValue::err(e),
                };

                state.env.insert(sym.clone(), out_val);
                state.lineage.insert(sym.clone(), vec![format!("read({})", domain)]);
                state.types.insert(
                    sym.clone(),
                    Type::result(ok_type.clone(), err_type.clone()).display_name(),
                );

                // Mutation M04: drop latent postcondition
                if !self.mutations.m04_drop_latent_metadata {
                    state.latent.insert(sym, latent.clone());
                }

                // Mutation M05: eager instantiation of on_ok
                if self.mutations.m05_eager_on_ok_materialization {
                    for f in latent.instantiate_ok(&format!("v{}", dest.0)) {
                        state.active_facts.insert(f);
                    }
                }
            }
            VmInstruction::VmInfer {
                dest,
                prompt,
                ok_type,
                err_type,
                latent,
            } => {
                let sym = format!("v{}", dest.0);
                let res = self.adapters.infer.infer(prompt);

                // Mutation M08: drop infer effect
                if !self.mutations.m08_drop_infer_effect {
                    state.observable_effects.push("infer".to_string());
                }

                let out_val = match res {
                    Ok(v) => VmValue::ok(v),
                    Err(e) => VmValue::err(e),
                };

                state.env.insert(sym.clone(), out_val);
                state.lineage.insert(sym.clone(), vec![format!("infer({})", prompt)]);
                state.types.insert(
                    sym.clone(),
                    Type::result(ok_type.clone(), err_type.clone()).display_name(),
                );

                if !self.mutations.m04_drop_latent_metadata {
                    state.latent.insert(sym, latent.clone());
                }
            }
            VmInstruction::VmAssign { dest, source, ty } => {
                let src_sym = if self.mutations.m09_stale_source_value_id {
                    format!("v{}", dest.0) // Corrupted source
                } else {
                    format!("v{}", source.0)
                };
                let val = state.env.get(&src_sym).cloned().unwrap_or(VmValue::Unit);
                let dest_sym = format!("v{}", dest.0);
                state.env.insert(dest_sym.clone(), val);
                state.types.insert(dest_sym, ty.display_name());
            }
            VmInstruction::VmVerify {
                dest,
                verifier_id,
                subject,
                output_predicate: _,
                subject_type: _,
                verifier_effects: _,
            } => {
                let dest_sym = format!("v{}", dest.0);
                let sub_sym = format!("v{}", subject.0);
                let subject_val = state.env.get(&sub_sym).cloned().unwrap_or(VmValue::Unit);

                let desc = match self.registry.verifiers.get(verifier_id) {
                    Some(d) => d,
                    None => {
                        state.status = VmStatus::Error(format!(
                            "Unknown verifier {:?} in trusted registry",
                            verifier_id
                        ));
                        return;
                    }
                };

                let verifier_effects: Vec<_> = desc.effect_envelope.effects.iter().cloned().collect();

                // Caller authority check for Verify (Rule #5, S2C04)
                if let Some(ca) = &self.registry.caller_authority {
                    if !ca.covers(&verifier_effects) {
                        state.status = VmStatus::Error(format!(
                            "Caller authority insufficient for verifier {:?}",
                            verifier_id
                        ));
                        return;
                    }
                }

                // S2M02: drop verifier effect from execution
                if !self.mutations.s2m02_drop_verifier_effect {
                    for eff in &verifier_effects {
                        match eff {
                            crate::ir::effects::Effect::Read(d) => {
                                state.observable_effects.push(format!("read[{}]", d))
                            }
                            crate::ir::effects::Effect::Infer => {
                                state.observable_effects.push("infer".to_string())
                            }
                            crate::ir::effects::Effect::Act(d) => {
                                state.observable_effects.push(format!("act[{}]", d))
                            }
                        }
                    }
                }

                let verify_res = self
                    .adapters
                    .verifier
                    .verify(desc, &subject_val, &desc.effect_envelope);
                let out_val = match verify_res {
                    Ok(att) => VmValue::ok(att),
                    Err(e) => VmValue::err(VmValue::String(e)),
                };

                let ret_ty = Type::result(
                    Type::attestation(desc.output_predicate.clone(), desc.subject_type.clone()),
                    Type::String,
                );

                state.env.insert(dest_sym.clone(), out_val);
                state.types.insert(dest_sym, ret_ty.display_name());
            }
            VmInstruction::VmAct {
                dest,
                op_id,
                target_domain: _,
                success_type,
                failure_type,
                args,
                evidence,
                gate_effects: _,
                latent: _,
            } => {
                let dest_sym = format!("v{}", dest.0);
                let ret_ty = Type::act_outcome(success_type.clone(), failure_type.clone());
                state.types.insert(dest_sym.clone(), ret_ty.display_name());

                // Look up operation descriptor (Fail-closed, P1)
                let op_desc = match self.registry.operations.get(op_id) {
                    Some(d) => d.clone(),
                    None => {
                        state.status = VmStatus::Error(format!(
                            "Unknown operation {:?} in trusted registry",
                            op_id
                        ));
                        return;
                    }
                };

                // Caller authority check for target domain (Rule #9, S2C11)
                if let Some(ca) = &self.registry.caller_authority {
                    let target_eff = Effect::Act(op_desc.target_domain.clone());
                    if !ca.contains(&target_eff) {
                        state.status = VmStatus::Error(format!(
                            "Caller authority lacks target capability {:?}",
                            target_eff
                        ));
                        return;
                    }
                }

                // 1. Resolve requirements against args and evidence
                let mut arg_values = Vec::new();
                for arg_id in args {
                    let arg_sym = format!("v{}", arg_id.0);
                    if let Some(v) = state.env.get(&arg_sym) {
                        arg_values.push(v.clone());
                    }
                }

                let mut ev_values = Vec::new();
                for ev_id in evidence {
                    let ev_sym = format!("v{}", ev_id.0);
                    if let Some(v) = state.env.get(&ev_sym) {
                        ev_values.push(v.clone());
                    }
                }

                let resolution = if self.mutations.s2m04_deferred_treated_as_proved {
                    RequirementResolution::Proved
                } else {
                    GateEngine::resolve_requirements(&op_desc.requirements, &arg_values, &ev_values)
                };

                let res_name = match &resolution {
                    RequirementResolution::Proved => "Proved",
                    RequirementResolution::Deferred(_) => "Deferred",
                    RequirementResolution::Refuted => "Refuted",
                    RequirementResolution::Uncovered => "Uncovered",
                };
                state.gate_resolutions.push(GateResolutionObservation {
                    op_id: op_id.0.clone(),
                    resolution: res_name.to_string(),
                });

                // 2. Evaluate gate checks
                let mut gate_passed = true;
                let mut witness_version = None;
                let mut gate_eff_strings = Vec::new();

                match &resolution {
                    RequirementResolution::Proved => {
                        // No dynamic checks required
                    }
                    RequirementResolution::Deferred(checks) => {
                        for check in checks {
                            let check_name = match check {
                                DeferredCheck::CheckSubjectBinding { .. } => "CheckSubjectBinding",
                                DeferredCheck::CheckTrustPolicy { .. } => "CheckTrustPolicy",
                                DeferredCheck::CheckStateBaseVersion { .. } => "CheckStateBaseVersion",
                            };
                            let auth_name = match check.authority_source() {
                                crate::registry::AuthoritySource::Caller => "Caller",
                                crate::registry::AuthoritySource::TrustedRuntime => "TrustedRuntime",
                            };
                            let check_effs: Vec<String> = check.required_effects().iter().map(|e| e.to_string()).collect();

                            for eff in check.required_effects() {
                                match eff {
                                    crate::ir::effects::Effect::Read(d) => {
                                        gate_eff_strings.push(format!("read[{}]", d))
                                    }
                                    crate::ir::effects::Effect::Infer => {
                                        gate_eff_strings.push("infer".to_string())
                                    }
                                    crate::ir::effects::Effect::Act(d) => {
                                        gate_eff_strings.push(format!("act[{}]", d))
                                    }
                                }
                            }

                            state.gate_trace.push(GateCheckObservation {
                                check_kind: check_name.to_string(),
                                authority_source: auth_name.to_string(),
                                effects: check_effs,
                                result: "Pass".to_string(),
                            });
                        }

                        // Record gate check effects in observable trace (Rule #15)
                        if !self.mutations.s2m06_gate_effect_omitted_from_act {
                            state.observable_effects.extend(gate_eff_strings.clone());
                        }

                        let mut trust_policy = self.registry.trust_policy.clone();
                        if self.mutations.s2m03_trust_arbitrary_issuer
                            || self.mutations.s2m16_untrusted_attestation_accepted
                        {
                            // Flawed trust policy accepting all issuers
                            trust_policy.trusted_issuers.clear();
                            for check in checks {
                                if let DeferredCheck::CheckTrustPolicy { predicate, issuer } = check
                                {
                                    trust_policy.trust_verifier(predicate.clone(), issuer.clone());
                                }
                            }
                        }

                        let gate_eval = GateEngine::evaluate_deferred(
                            checks,
                            &state.world,
                            &trust_policy,
                            &gate_eff_strings,
                            self.registry.caller_authority.as_ref(),
                            self.registry.runtime_authority.as_ref(),
                            self.mutations.s2m07_trusted_gate_requires_caller_authority,
                        );

                        match gate_eval {
                            Ok(w) => {
                                witness_version =
                                    if self.mutations.s2m08_toctou_revalidation_omitted {
                                        None
                                    } else {
                                        w.observed_state_version
                                    };
                            }
                            Err(_) => {
                                gate_passed = false;
                            }
                        }
                    }
                    RequirementResolution::Refuted | RequirementResolution::Uncovered => {
                        gate_passed = false;
                    }
                }

                if !gate_passed && !self.mutations.s2m05_gate_rejection_still_invokes_target {
                    // Rule #15: Gate rejected -> zero target mutation, gate effects remain observable
                    state.env.insert(
                        dest_sym,
                        VmValue::act_failure(VmValue::String("GateRejected".to_string())),
                    );
                    return;
                }

                // 3. Execute target act
                state
                    .observable_effects
                    .push(format!("act[{}]", op_desc.target_domain));

                let prior_trace_len = state.world.mutation_trace.len();

                let mut arg_id_values = Vec::new();
                for arg_id in args {
                    let arg_sym = format!("v{}", arg_id.0);
                    let val = state.env.get(&arg_sym).cloned().unwrap_or(VmValue::Unit);
                    arg_id_values.push(val);
                }

                let footprint = if self.mutations.s2m09_footprint_enforcement_disabled {
                    MutationFootprint::Unknown(op_desc.target_domain.clone())
                } else {
                    op_desc.declared_footprint.clone()
                };

                let mut raw_outcome = self.adapters.act.execute_act(
                    op_id,
                    &arg_id_values,
                    &footprint,
                    &mut state.world,
                    op_desc.atomicity,
                    witness_version,
                );

                if self.mutations.s2m10_partial_collapsed_to_failure {
                    if let VmValue::ActPartial(rep) = raw_outcome {
                        raw_outcome = VmValue::act_failure(VmValue::String(format!(
                            "CoercedPartial({})",
                            rep.op_id
                        )));
                    }
                }
                if self.mutations.s2m11_unknown_collapsed_to_failure {
                    if let VmValue::DeliveryUnknown(r) | VmValue::SettlementUnknown(r) = raw_outcome
                    {
                        raw_outcome =
                            VmValue::act_failure(VmValue::String(format!("CoercedUnknown({})", r)));
                    }
                }

                // 4. Invalidate facts intersecting mutation footprint (Rule #20)
                if state.world.mutation_trace.len() > prior_trace_len {
                    for (k, _, _) in &state.world.mutation_trace[prior_trace_len..] {
                        state.invalidated_keys.insert(k.clone());
                    }
                }

                state.env.insert(dest_sym, raw_outcome);
            }
        }
    }

    fn execute_terminator(&self, term: &VmTerminator, state: &mut VmExecutionState) {
        match term {
            VmTerminator::Return(val_opt) => {
                state.status = VmStatus::Terminated;
                if let Some(val_id) = val_opt {
                    let sym = format!("v{}", val_id.0);
                    state.return_value = state.env.get(&sym).cloned();
                } else {
                    state.return_value = Some(VmValue::Unit);
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
                let cond_val = state.env.get(&cond_sym).cloned().unwrap_or(VmValue::Bool(false));
                match cond_val {
                    VmValue::Bool(true) => {
                        self.transfer_control(*true_target, true_args, state);
                    }
                    VmValue::Bool(false) => {
                        self.transfer_control(*false_target, false_args, state);
                    }
                    _ => {
                        state.status = VmStatus::Error(format!(
                            "CondBr on non-boolean value {:?}",
                            cond_val
                        ));
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
                let res_val = state.env.get(&res_sym).cloned().unwrap_or(VmValue::Unit);

                let (target_block, target_arg, payload_val) = match res_val {
                    VmValue::Ok(inner) => {
                        // Mutation M02: swap ok and err targets
                        if self.mutations.m02_swap_ok_err_targets {
                            (*err_target, *err_arg, *inner)
                        } else {
                            (*ok_target, *ok_arg, *inner)
                        }
                    }
                    VmValue::Err(inner) => {
                        // Mutation M01: drop err edge -> protocol violation / error
                        if self.mutations.m01_drop_err_edge {
                            state.status = VmStatus::ProtocolViolation(
                                "M01: Error branch unreachable".to_string(),
                            );
                            return;
                        }
                        if self.mutations.m02_swap_ok_err_targets {
                            (*ok_target, *ok_arg, *inner)
                        } else {
                            (*err_target, *err_arg, *inner)
                        }
                    }
                    _ => {
                        state.status = VmStatus::Error(format!(
                            "SwitchResult on non-result value {:?}",
                            res_val
                        ));
                        return;
                    }
                };

                let target_sym = format!("v{}", target_arg.0);
                state.env.insert(target_sym, payload_val);
                if let Some(tb) = self.func.blocks.get(&target_block) {
                    for (p, ty) in &tb.params {
                        state.types.insert(format!("v{}", p.0), ty.display_name());
                    }
                }
                state.current_block = target_block;
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
                let out_sym = format!("v{}", outcome_val.0);
                let out_val = state.env.get(&out_sym).cloned().unwrap_or(VmValue::Unit);

                match out_val {
                    VmValue::ActSuccess(inner) => {
                        let sym = format!("v{}", success_arg.0);
                        state.env.insert(sym, *inner);
                        if let Some(tb) = self.func.blocks.get(success_target) {
                            for (p, ty) in &tb.params {
                                state.types.insert(format!("v{}", p.0), ty.display_name());
                            }
                        }
                        state.current_block = *success_target;
                    }
                    VmValue::ActFailure(inner) => {
                        let sym = format!("v{}", failure_arg.0);
                        state.env.insert(sym, *inner);
                        if let Some(tb) = self.func.blocks.get(failure_target) {
                            for (p, ty) in &tb.params {
                                state.types.insert(format!("v{}", p.0), ty.display_name());
                            }
                        }
                        state.current_block = *failure_target;
                    }
                    VmValue::ActPartial(report) => {
                        let sym = format!("v{}", partial_arg.0);
                        state.env.insert(sym, VmValue::ActPartial(report));
                        if let Some(tb) = self.func.blocks.get(partial_target) {
                            for (p, ty) in &tb.params {
                                state.types.insert(format!("v{}", p.0), ty.display_name());
                            }
                        }
                        state.current_block = *partial_target;
                    }
                    VmValue::DeliveryUnknown(reason) => {
                        let sym = format!("v{}", unknown_arg.0);
                        state.env.insert(sym, VmValue::String(reason));
                        if let Some(tb) = self.func.blocks.get(unknown_target) {
                            for (p, ty) in &tb.params {
                                state.types.insert(format!("v{}", p.0), ty.display_name());
                            }
                        }
                        state.current_block = *unknown_target;
                    }
                    VmValue::SettlementUnknown(reason) => {
                        let sym = format!("v{}", unknown_arg.0);
                        state.env.insert(sym, VmValue::String(reason));
                        if let Some(tb) = self.func.blocks.get(unknown_target) {
                            for (p, ty) in &tb.params {
                                state.types.insert(format!("v{}", p.0), ty.display_name());
                            }
                        }
                        state.current_block = *unknown_target;
                    }
                    VmValue::String(ref s) if s == "PROTOCOL_VIOLATION_ATOMIC_PARTIAL" => {
                        state.status = VmStatus::ProtocolViolation(
                            "Atomic adapter returned partial outcome".to_string(),
                        );
                    }
                    _ => {
                        state.status = VmStatus::Error(format!(
                            "SwitchActOutcome on non-outcome value {:?}",
                            out_val
                        ));
                    }
                }
            }
            VmTerminator::Unreachable => {
                state.status = VmStatus::Error("Reached Unreachable terminator".to_string());
            }
        }
    }

    fn transfer_control(
        &self,
        target: VmBlockId,
        args: &[VmValueId],
        state: &mut VmExecutionState,
    ) {
        if let Some(target_block) = self.func.blocks.get(&target) {
            for (i, (param_id, _)) in target_block.params.iter().enumerate() {
                if let Some(arg_id) = args.get(i) {
                    let arg_sym = format!("v{}", arg_id.0);
                    let val = state.env.get(&arg_sym).cloned().unwrap_or(VmValue::Unit);
                    let param_sym = format!("v{}", param_id.0);
                    state.env.insert(param_sym, val);
                }
            }
        }
        state.current_block = target;
    }
}
