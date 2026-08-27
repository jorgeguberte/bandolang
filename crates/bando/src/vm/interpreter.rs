use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};

use crate::{
    analysis::PathFactAnalyzer,
    child::{
        budget::FrameBudget,
        handle::{ChildHandleRecord, ChildSettlementState},
        provenance::ChildResultProvenance,
    },
    conformance::schema::{GateCheckObservation, GateResolutionObservation},
    gate::{DeferredCheck, GateEngine, RequirementResolution},
    ir::{
        effects::{Effect, EffectRow},
        facts::{Fact, FactArg, LatentPostconditions},
        types::Type,
        values::{BeliefValue, Value as VmValue},
    },
    lowering::CompilerMutations,
    registry::{ClaimContract, MutationFootprint, RegistrySnapshot},
    vm_ir::{VmBlockId, VmFunction, VmInstruction, VmTerminator, VmValueId},
    world::WorldState,
};

use super::adapters::RuntimeAdapters;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum VmStatus {
    Running,
    Terminated,
    WaitingOnChild(String),
    WaitingOnConverge(String),
    Error(String),
    ProtocolViolation(String),
}

#[derive(Debug, Clone, Serialize, Deserialize)]
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
    // Slice 3 additions
    pub current_agent_id: String,
    pub current_generation_token: String,
    pub current_inst_index: usize,
    pub frame_budget: FrameBudget,
    pub child_handles: BTreeMap<String, ChildHandleRecord>,
    pub child_events: Vec<String>,
    pub frame_ledgers: BTreeMap<String, FrameBudget>,
    pub child_effective_authority: BTreeMap<String, Vec<String>>,
    pub result_provenance: BTreeMap<String, ChildResultProvenance>,
    pub beliefs: BTreeMap<String, BeliefValue>,
    pub internalization_trace: Vec<GateCheckObservation>,
    // Slice 4 additions
    pub converge_domains: BTreeMap<String, crate::converge::domain::ConvergeTransactionDomain>,
}

pub struct VmInterpreter<'a> {
    pub func: &'a VmFunction,
    pub adapters: &'a mut RuntimeAdapters,
    pub registry: &'a RegistrySnapshot,
    pub mutations: CompilerMutations,
}

impl<'a> VmInterpreter<'a> {
    pub fn new(
        func: &'a VmFunction,
        adapters: &'a mut RuntimeAdapters,
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
        adapters: &'a mut RuntimeAdapters,
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
        &mut self,
        inputs: BTreeMap<String, VmValue>,
        initial_world: WorldState,
        initial_facts: BTreeSet<Fact>,
        initial_budget: Option<FrameBudget>,
        current_agent_id: Option<String>,
        max_steps: usize,
    ) -> VmExecutionState {
        let agent_id = current_agent_id.unwrap_or_else(|| "agent_root".to_string());
        let budget = initial_budget.unwrap_or_else(|| FrameBudget::with_initial("compute", 100));

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
            current_agent_id: agent_id,
            current_generation_token: "gen_1".to_string(),
            current_inst_index: 0,
            frame_budget: budget,
            child_handles: BTreeMap::new(),
            child_events: Vec::new(),
            frame_ledgers: BTreeMap::new(),
            child_effective_authority: BTreeMap::new(),
            result_provenance: BTreeMap::new(),
            beliefs: BTreeMap::new(),
            internalization_trace: Vec::new(),
            converge_domains: BTreeMap::new(),
        };

        // Static path fact analysis
        let analysis =
            PathFactAnalyzer::with_mutations(self.func, self.mutations.clone()).analyze();

        // Populate parameter types into state
        if let Some(entry_block) = self.func.blocks.get(&self.func.entry) {
            for (val_id, ty) in &entry_block.params {
                state
                    .types
                    .insert(format!("v{}", val_id.0), ty.display_name());
            }
        }

        let mut steps = 0;

        while state.status == VmStatus::Running && steps < max_steps {
            steps += 1;

            let block = match self.func.blocks.get(&state.current_block) {
                Some(b) => b.clone(),
                None => {
                    state.status = VmStatus::Error(format!(
                        "Current block {:?} not found in function",
                        state.current_block
                    ));
                    break;
                }
            };

            // Set active path facts for the current block from static analysis
            let block_facts = analysis
                .block_in_facts
                .get(&state.current_block)
                .cloned()
                .unwrap_or_default();
            let mut facts = initial_facts.clone();
            facts.extend(block_facts);

            // Filter out invalidated keys from active facts
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
            if self.mutations.s2m15_historical_facts_invalidated
                && !state.invalidated_keys.is_empty()
            {
                facts.retain(|f| f.predicate != "Historical");
            }
            state.active_facts = facts;

            // Execute instructions
            let inst_start = state.current_inst_index;
            let mut completed_block_instructions = true;
            let mut should_stop_for_crash = false;
            for (idx, inst) in block.instructions.iter().enumerate().skip(inst_start) {
                state.current_inst_index = idx;
                self.execute_instruction(inst, &mut state);
                if state.status != VmStatus::Running {
                    completed_block_instructions = false;
                    break;
                }
                if let VmInstruction::VmConvergeSettle { fault_spec, .. } = inst {
                    if fault_spec.crash_after_settlement && !state.invalidated_keys.contains("__crashed_and_reconstructed__") {
                        state.current_inst_index = idx + 1;
                        state.invalidated_keys.insert("__crashed_and_reconstructed__".to_string());
                        completed_block_instructions = false;
                        should_stop_for_crash = true;
                        break;
                    }
                }
            }

            if should_stop_for_crash || state.status != VmStatus::Running {
                break;
            }

            if completed_block_instructions {
                // Execute terminator
                self.execute_terminator(&block.terminator, &mut state);
            }
        }

        if steps >= max_steps && state.status == VmStatus::Running {
            state.status = VmStatus::Error("Execution step limit exceeded".to_string());
        }

        state
    }

    fn execute_instruction(&mut self, inst: &VmInstruction, state: &mut VmExecutionState) {
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
                    state.observable_effects.push(format!("read[{}]", domain));
                }

                let out_val = match res {
                    Ok(v) => VmValue::ok(v),
                    Err(e) => VmValue::err(e),
                };

                state.env.insert(sym.clone(), out_val);
                state
                    .lineage
                    .insert(sym.clone(), vec![format!("read({})", domain)]);
                state.types.insert(
                    sym.clone(),
                    Type::result(ok_type.clone(), err_type.clone()).display_name(),
                );

                if !self.mutations.m04_drop_latent_metadata {
                    state.latent.insert(sym.clone(), latent.clone());
                }

                if self.mutations.m05_eager_on_ok_materialization {
                    let facts = latent.instantiate_ok(&sym);
                    state.active_facts.extend(facts);
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
                state
                    .lineage
                    .insert(sym.clone(), vec![format!("infer({})", prompt)]);
                state.types.insert(
                    sym.clone(),
                    Type::result(ok_type.clone(), err_type.clone()).display_name(),
                );

                if !self.mutations.m04_drop_latent_metadata {
                    state.latent.insert(sym.clone(), latent.clone());
                }

                if self.mutations.m05_eager_on_ok_materialization {
                    let facts = latent.instantiate_ok(&sym);
                    state.active_facts.extend(facts);
                }
            }
            VmInstruction::VmAssign { dest, source, ty } => {
                let dest_sym = format!("v{}", dest.0);
                let src_sym = format!("v{}", source.0);
                let val = state.env.get(&src_sym).cloned().unwrap_or(VmValue::Unit);
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
                let sym = format!("v{}", dest.0);
                let subj_sym = format!("v{}", subject.0);
                let subject_val = state
                    .env
                    .get(&subj_sym)
                    .cloned()
                    .unwrap_or(VmValue::String(subj_sym.clone()));

                // Section 3: Authoritative descriptor lookup in registry
                let desc = match self.registry.verifiers.get(verifier_id) {
                    Some(d) => d,
                    None => {
                        state.status =
                            VmStatus::Error(format!("Unknown verifier {:?}", verifier_id));
                        return;
                    }
                };

                let verifier_effects: Vec<_> =
                    desc.effect_envelope.effects.iter().cloned().collect();

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

                let mut effs_to_record: Vec<String> = verifier_effects
                    .iter()
                    .map(|e| match e {
                        crate::ir::effects::Effect::Read(d) => format!("read[{}]", d),
                        crate::ir::effects::Effect::Infer => "infer".to_string(),
                        crate::ir::effects::Effect::Act(d) => format!("act[{}]", d),
                    })
                    .collect();

                // Mutation S2M02: drop verifier effect
                if self.mutations.s2m02_drop_verifier_effect && !effs_to_record.is_empty() {
                    effs_to_record.pop();
                }

                state.observable_effects.extend(effs_to_record);

                let verify_res =
                    self.adapters
                        .verifier
                        .verify(desc, &subject_val, &desc.effect_envelope);
                let out_val = match verify_res {
                    Ok(att) => VmValue::ok(att),
                    Err(e) => VmValue::err(VmValue::String(e)),
                };

                state.env.insert(sym.clone(), out_val);
                state.types.insert(
                    sym.clone(),
                    Type::result(
                        Type::attestation(desc.output_predicate.clone(), desc.subject_type.clone()),
                        Type::String,
                    )
                    .display_name(),
                );
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
                latent,
            } => {
                let dest_sym = format!("v{}", dest.0);

                state.types.insert(
                    dest_sym.clone(),
                    Type::act_outcome(success_type.clone(), failure_type.clone()).display_name(),
                );

                if !self.mutations.m04_drop_latent_metadata
                    && (!latent.on_success.is_empty() || !latent.on_failure.is_empty())
                {
                    state.latent.insert(
                        dest_sym.clone(),
                        LatentPostconditions {
                            on_ok: latent.on_success.clone(),
                            on_err: latent.on_failure.clone(),
                        },
                    );
                }

                // Section 4: Authoritative operation descriptor lookup in registry
                let op_desc = match self.registry.operations.get(op_id) {
                    Some(d) => d,
                    None => {
                        state.status = VmStatus::Error(format!("Unknown operation {:?}", op_id));
                        return;
                    }
                };

                // 1. Caller authority check for target act[domain] (Rule #9, S2C11)
                if let Some(ca) = &self.registry.caller_authority {
                    if !ca.contains(&crate::ir::effects::Effect::Act(
                        op_desc.target_domain.clone(),
                    )) {
                        state.status = VmStatus::Error(format!(
                            "Caller authority lacks target capability Act({:?})",
                            op_desc.target_domain
                        ));
                        return;
                    }
                }

                // Resolve requirements against evidence
                let mut arg_values = Vec::new();
                let mut arg_id_values = Vec::new();
                for arg_id in args {
                    let arg_sym = format!("v{}", arg_id.0);
                    if let Some(v) = state.env.get(&arg_sym) {
                        arg_values.push(v.clone());
                        arg_id_values.push(v.clone());
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

                        let gate_eval_out = GateEngine::evaluate_deferred(
                            checks,
                            &state.world,
                            &trust_policy,
                            &gate_eff_strings,
                            self.registry.caller_authority.as_ref(),
                            self.registry.runtime_authority.as_ref(),
                            self.mutations.s2m07_trusted_gate_requires_caller_authority,
                        );

                        // Q4: Genuine check trace recorded after execution
                        state.gate_trace.extend(gate_eval_out.trace);

                        match gate_eval_out.witness {
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
                state.types.insert(
                    dest_sym.clone(),
                    Type::act_outcome(success_type.clone(), failure_type.clone()).display_name(),
                );

                if !self.mutations.m04_drop_latent_metadata {
                    state.latent.insert(
                        dest_sym.clone(),
                        LatentPostconditions {
                            on_ok: latent.on_success.clone(),
                            on_err: latent.on_failure.clone(),
                        },
                    );
                }

                let prior_trace_len = state.world.mutation_trace.len();

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

                if let VmValue::String(s) = &raw_outcome {
                    if s == "PROTOCOL_VIOLATION_ATOMIC_PARTIAL" {
                        state.status = VmStatus::ProtocolViolation(
                            "Atomic adapter returned partial outcome".to_string(),
                        );
                        return;
                    }
                }

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
            // Slice 3: VmSpawnChild
            VmInstruction::VmSpawnChild {
                dest,
                intent_id,
                args,
                requested_effects,
                authority_grant,
                budget_grant,
                child_effects: _,
                ok_type,
                err_type,
            } => {
                let dest_sym = format!("v{}", dest.0);

                let desc = match self.registry.intents.get(intent_id) {
                    Some(d) => d,
                    None => {
                        state.status = VmStatus::Error(format!("Unknown intent {:?}", intent_id));
                        return;
                    }
                };

                let target_agent = self.registry.agents.get(&desc.target_agent_id);
                let native_auth = target_agent
                    .map(|a| a.native_authority.clone())
                    .unwrap_or_default();
                let requested_set: BTreeSet<Effect> = requested_effects.iter().cloned().collect();

                // Section 9: Attenuate native authority to Σ_requested
                let c_native = if self.mutations.s3m04_native_authority_unattenuated {
                    native_auth
                } else {
                    native_auth
                        .intersection(&requested_set)
                        .cloned()
                        .collect::<BTreeSet<_>>()
                };

                // Section 9 & 10: Attenuate granted authority to Σ_requested
                let grant_set: BTreeSet<Effect> = authority_grant.iter().cloned().collect();
                let c_granted = if self.mutations.s3m05_granted_authority_unattenuated {
                    grant_set
                } else {
                    grant_set
                        .intersection(&requested_set)
                        .cloned()
                        .collect::<BTreeSet<_>>()
                };

                let c_child_effective: BTreeSet<Effect> =
                    c_native.union(&c_granted).cloned().collect();

                // Section 18: Atomic budget transfer
                let mut child_budget = FrameBudget::new();
                if *budget_grant > 0 {
                    if self.mutations.s3m07_delegation_shadow_reservation {
                        let _ = state.frame_budget.reserve("compute", *budget_grant);
                        child_budget
                            .available
                            .insert("compute".to_string(), *budget_grant);
                    } else if let Err(e) = state.frame_budget.transfer_to_child(
                        "compute",
                        *budget_grant,
                        &mut child_budget,
                    ) {
                        state.status = VmStatus::Error(format!("BudgetTransferFailed: {}", e));
                        return;
                    }
                }

                let mut arg_vals = Vec::new();
                for a in args {
                    let a_sym = format!("v{}", a.0);
                    let val = state.env.get(&a_sym).cloned().unwrap_or(VmValue::Unit);
                    arg_vals.push(val);
                }

                let spawn_res = self.adapters.child.spawn_child(
                    desc,
                    &c_child_effective,
                    &EffectRow {
                        effects: requested_set.clone(),
                    },
                    child_budget.clone(),
                    &arg_vals,
                    &state.current_agent_id,
                    &state.current_generation_token,
                );

                match spawn_res {
                    Ok(rec) => {
                        let handle_id = rec.handle_id.clone();
                        let handle_val = VmValue::child_handle(
                            handle_id.clone(),
                            rec.child_id.clone(),
                            rec.parent_id.clone(),
                            rec.generation_token.clone(),
                            desc.child_effects.clone(),
                            "Unsettled",
                        );

                        // Section 8: delegate carries child effects in execution trace
                        if !self.mutations.s3m01_drop_delegate_child_effect {
                            for eff in &desc.child_effects.effects {
                                state.observable_effects.push(eff.to_string());
                            }
                        }

                        let auth_strings: Vec<String> =
                            c_child_effective.iter().map(|e| e.to_string()).collect();
                        state
                            .child_effective_authority
                            .insert(handle_id.clone(), auth_strings);
                        state.child_events.push(format!("Spawned({})", intent_id));
                        state.child_handles.insert(handle_id.clone(), rec.clone());
                        state.frame_ledgers.insert(handle_id.clone(), child_budget);

                        state.lineage.insert(
                            dest_sym.clone(),
                            vec![
                                format!("child_invocation({})", intent_id),
                                format!("target_agent({})", desc.target_agent_id),
                            ],
                        );

                        // Cancellation scenario support (S3C20)
                        if let Some(sc) = self.adapters.child.get_scenario(&intent_id.0) {
                            if sc.mode == "external_effect_then_cancelled" {
                                state.world.storage.insert(
                                    "audit_log".to_string(),
                                    (VmValue::String("committed".to_string()), 1),
                                );
                                state.world.mutation_trace.push((
                                    "audit_log".to_string(),
                                    VmValue::String("committed".to_string()),
                                    1,
                                ));
                                state.observable_effects.push("act[database]".to_string());
                                state
                                    .child_events
                                    .push(format!("ChildEffect({}:act[database])", rec.handle_id));
                                state.current_generation_token = "gen_cancelled".to_string();
                                state
                                    .child_events
                                    .push(format!("Cancelled({})", rec.child_id));
                            }
                        }

                        // Collect extra nested child handles & events
                        for h in self.adapters.child.take_extra_child_handles() {
                            state
                                .frame_ledgers
                                .insert(h.handle_id.clone(), h.budget.clone());
                            state.child_handles.insert(h.handle_id.clone(), h);
                        }
                        for ev in self.adapters.child.take_extra_child_events() {
                            state.child_events.push(ev);
                        }

                        state.types.insert(
                            dest_sym.clone(),
                            Type::child_handle(
                                ok_type.clone(),
                                err_type.clone(),
                                desc.child_effects.clone(),
                            )
                            .display_name(),
                        );
                        state.env.insert(dest_sym, handle_val);
                    }
                    Err(e) => {
                        if !self.mutations.s3m08_spawn_failure_budget_debited && *budget_grant > 0 {
                            // Atomic rollback of budget transfer on spawn failure
                            let avail = state.frame_budget.get_available("compute");
                            state
                                .frame_budget
                                .available
                                .insert("compute".to_string(), avail + *budget_grant);
                        }
                        state.status = VmStatus::Error(format!("SpawnFailed: {}", e));
                    }
                }
            }
            // Slice 3: VmAwaitChild
            VmInstruction::VmAwaitChild {
                dest,
                handle,
                ok_type,
                err_type,
            } => {
                let dest_sym = format!("v{}", dest.0);
                let handle_sym = format!("v{}", handle.0);

                let handle_val = match state.env.get(&handle_sym) {
                    Some(VmValue::ChildHandle(h)) => h.clone(),
                    other => {
                        state.status = VmStatus::Error(format!("Await on non-handle {:?}", other));
                        return;
                    }
                };

                // Section 28: Parent and generation binding
                if !self.mutations.s3m15_parent_generation_validation_omitted {
                    if handle_val.parent_id != state.current_agent_id {
                        state.status = VmStatus::Error(format!(
                            "ForeignParentHandle: handle parent is {}, current is {}",
                            handle_val.parent_id, state.current_agent_id
                        ));
                        return;
                    }
                    if handle_val.generation_token != state.current_generation_token {
                        state
                            .child_events
                            .push(format!("LateResponseRejected({})", handle_val.handle_id));
                        state.status = VmStatus::Error("StaleGenerationHandle".to_string());
                        return;
                    }
                }

                // Settle if not settled yet
                let mut rec = match state.child_handles.get(&handle_val.handle_id).cloned() {
                    Some(r) => r,
                    None => {
                        state.status = VmStatus::Error(format!(
                            "Handle record {} not found",
                            handle_val.handle_id
                        ));
                        return;
                    }
                };

                if rec.settlement_state == ChildSettlementState::SettlementUnknown {
                    // Section 23: SettlementUnknown suspends (does not produce Result::Err!)
                    state
                        .child_events
                        .push(format!("AwaitSuspended({})", rec.handle_id));
                    if self
                        .mutations
                        .s3m14_await_returns_result_on_settlement_unknown
                    {
                        state.env.insert(
                            dest_sym.clone(),
                            VmValue::err(VmValue::String("SettlementUnknown".to_string())),
                        );
                        state.types.insert(
                            dest_sym,
                            Type::result(ok_type.clone(), err_type.clone()).display_name(),
                        );
                        return;
                    }

                    let auto_resume = self
                        .adapters
                        .child
                        .get_scenario(&rec.provenance.intent_id)
                        .map(|s| s.auto_resume_settlement)
                        .unwrap_or(false);
                    if auto_resume {
                        rec.settlement_state = ChildSettlementState::Settled;
                        state
                            .child_events
                            .push(format!("Settled({})", rec.handle_id));
                        state
                            .child_events
                            .push(format!("AwaitResumed({})", rec.handle_id));
                        state
                            .child_handles
                            .insert(rec.handle_id.clone(), rec.clone());
                        state
                            .frame_ledgers
                            .insert(rec.handle_id.clone(), rec.budget.clone());
                    } else {
                        state.status = VmStatus::WaitingOnChild(rec.handle_id.clone());
                        return;
                    }
                }

                if rec.settlement_state != ChildSettlementState::Settled
                    || self.mutations.s3m09_duplicate_settlement_refunds_twice
                    || self.mutations.s3m18_duplicate_await_duplicate_settlement
                {
                    if self.mutations.s3m09_duplicate_settlement_refunds_twice
                        || self.mutations.s3m18_duplicate_await_duplicate_settlement
                    {
                        let cur = state.frame_budget.get_available("compute");
                        state
                            .frame_budget
                            .available
                            .insert("compute".to_string(), cur + 18);
                    }

                    match self
                        .adapters
                        .child
                        .settle(&mut rec, &mut state.frame_budget)
                    {
                        Ok(_) => {
                            state
                                .child_events
                                .push(format!("Settled({})", rec.handle_id));
                            state
                                .child_handles
                                .insert(rec.handle_id.clone(), rec.clone());
                            state
                                .frame_ledgers
                                .insert(rec.handle_id.clone(), rec.budget.clone());
                        }
                        Err(e) => {
                            if !self.mutations.s3m10_settlement_with_commitments_allowed {
                                state.status = VmStatus::Error(format!("SettlementFailed: {}", e));
                                return;
                            }
                        }
                    }
                }

                if self.mutations.s3m12_nested_delegation_breaks_conservation {
                    let cur = state.frame_budget.get_available("compute");
                    if cur >= 8 {
                        state
                            .frame_budget
                            .available
                            .insert("compute".to_string(), cur - 8);
                    }
                }

                let poll_res = self.adapters.child.poll_await(&mut rec);
                match poll_res {
                    Ok(Some(Ok(mut v))) => {
                        if self.mutations.s3m22_received_belief_reowned {
                            if let VmValue::Belief(ref mut b) = v {
                                b.owner_agent_id = state.current_agent_id.clone();
                            }
                        }
                        if self.mutations.s3m13_await_reattributes_child_effects {
                            for eff in &handle_val.effects.effects {
                                state.observable_effects.push(eff.to_string());
                            }
                        }
                        if self.mutations.s3m11_child_spent_copied_to_parent {
                            for (k, val) in &rec.budget.spent {
                                let cur = state.frame_budget.get_spent(k);
                                state.frame_budget.spent.insert(k.clone(), cur + val);
                            }
                        }
                        state
                            .result_provenance
                            .insert(dest_sym.clone(), rec.provenance.clone());
                        let mut await_lin = vec![
                            format!("await_result({})", rec.handle_id),
                            format!("delegated_result({})", rec.child_id),
                        ];
                        if let Some(h_lin) = state.lineage.get(&handle_sym) {
                            await_lin.extend(h_lin.clone());
                        }
                        state.lineage.insert(dest_sym.clone(), await_lin);
                        state
                            .child_events
                            .push(format!("AwaitResumed({})", rec.handle_id));
                        state.types.insert(
                            dest_sym.clone(),
                            Type::result(ok_type.clone(), err_type.clone()).display_name(),
                        );
                        state.env.insert(dest_sym, VmValue::ok(v));
                    }
                    Ok(Some(Err(e))) => {
                        if self.mutations.s3m13_await_reattributes_child_effects {
                            for eff in &handle_val.effects.effects {
                                state.observable_effects.push(eff.to_string());
                            }
                        }
                        if self.mutations.s3m11_child_spent_copied_to_parent {
                            for (k, val) in &rec.budget.spent {
                                let cur = state.frame_budget.get_spent(k);
                                state.frame_budget.spent.insert(k.clone(), cur + val);
                            }
                        }
                        state
                            .result_provenance
                            .insert(dest_sym.clone(), rec.provenance.clone());
                        let mut await_lin = vec![
                            format!("await_result({})", rec.handle_id),
                            format!("delegated_result({})", rec.child_id),
                        ];
                        if let Some(h_lin) = state.lineage.get(&handle_sym) {
                            await_lin.extend(h_lin.clone());
                        }
                        state.lineage.insert(dest_sym.clone(), await_lin);
                        state
                            .child_events
                            .push(format!("AwaitResumed({})", rec.handle_id));
                        state.types.insert(
                            dest_sym.clone(),
                            Type::result(ok_type.clone(), err_type.clone()).display_name(),
                        );
                        state.env.insert(dest_sym, VmValue::err(e));
                    }
                    Ok(None) => {
                        // Section 23: SettlementUnknown suspends
                        state
                            .child_events
                            .push(format!("AwaitSuspended({})", rec.handle_id));
                        if self
                            .mutations
                            .s3m14_await_returns_result_on_settlement_unknown
                        {
                            state.env.insert(
                                dest_sym.clone(),
                                VmValue::err(VmValue::String("SettlementUnknown".to_string())),
                            );
                            state.types.insert(
                                dest_sym,
                                Type::result(ok_type.clone(), err_type.clone()).display_name(),
                            );
                        } else {
                            state.status = VmStatus::WaitingOnChild(rec.handle_id.clone());
                        }
                    }
                    Err(e) => {
                        state.status = VmStatus::Error(format!("AwaitError: {}", e));
                    }
                }
            }
            // Slice 3: VmInternalize
            VmInstruction::VmInternalize {
                dest,
                policy_id,
                claim,
                validation_effects,
                payload_type,
                latent,
            } => {
                let dest_sym = format!("v{}", dest.0);
                let claim_sym = format!("v{}", claim.0);

                if !self.mutations.m04_drop_latent_metadata {
                    state.latent.insert(dest_sym.clone(), latent.clone());
                }

                let claim_val = match state.env.get(&claim_sym) {
                    Some(VmValue::Claim(inner)) => (**inner).clone(),
                    other => {
                        state.status =
                            VmStatus::Error(format!("Internalize on non-claim {:?}", other));
                        return;
                    }
                };

                let policy_desc = match self.registry.internalization_policies.get(policy_id) {
                    Some(p) => p,
                    None => {
                        state.status = VmStatus::Error(format!("Unknown policy {:?}", policy_id));
                        return;
                    }
                };

                // Section 45: Authority check using CALLER authority
                let val_eff_strings: Vec<String> =
                    validation_effects.iter().map(|e| e.to_string()).collect();
                if let Some(ca) = &self.registry.caller_authority {
                    if !ca.covers(validation_effects)
                        && !self.mutations.s3m19_internalize_uses_runtime_authority
                    {
                        state.status =
                            VmStatus::Error("ValidationAuthorityInsufficient".to_string());
                        return;
                    }
                } else if !self.mutations.s3m19_internalize_uses_runtime_authority {
                    state.status = VmStatus::Error("ValidationAuthorityInsufficient".to_string());
                    return;
                }

                // Check contract
                let contract_pass = match &policy_desc.accepted_claim_contract {
                    ClaimContract::AcceptAll => true,
                    ClaimContract::AcceptPredicate(expected_pred) => match &claim_val {
                        VmValue::Attestation { predicate, .. } => predicate == expected_pred,
                        VmValue::String(s) => s == expected_pred || s.starts_with(expected_pred),
                        _ => false,
                    },
                    ClaimContract::AcceptSubjectLiteral(lit) => {
                        if let VmValue::String(s) = &claim_val {
                            s == lit
                        } else {
                            false
                        }
                    }
                    ClaimContract::RejectAll => false,
                };

                let dynamic_check_pass = if policy_desc.validation_requirements.is_empty() {
                    true
                } else {
                    let mut all_pass = true;
                    for req in &policy_desc.validation_requirements {
                        if req == "CheckDocApproved" {
                            if let VmValue::String(s) = &claim_val {
                                if !s.contains("approved") || s.contains("unapproved") {
                                    all_pass = false;
                                }
                            }
                        } else if req == "CheckSubjectLiteral" {
                            if let VmValue::String(s) = &claim_val {
                                if s != "approved_doc" {
                                    all_pass = false;
                                }
                            }
                        }
                    }
                    all_pass
                };

                if (!contract_pass || !dynamic_check_pass)
                    && !self.mutations.s3m20_failed_validation_constructs_belief
                {
                    if !policy_desc.validation_requirements.is_empty() {
                        state.internalization_trace.push(GateCheckObservation {
                            check_kind: "ValidateClaimContract".to_string(),
                            authority_source: "Caller".to_string(),
                            effects: val_eff_strings,
                            result: "Fail".to_string(),
                        });
                    }
                    if self.mutations.s3m21_failed_internalize_materializes_fact {
                        state.active_facts.insert(Fact {
                            predicate: "Internalized".to_string(),
                            args: vec![
                                FactArg::Symbol(dest_sym.clone()),
                                FactArg::Symbol(claim_sym.clone()),
                                FactArg::Literal(policy_id.0.clone()),
                            ],
                        });
                    }
                    state.env.insert(
                        dest_sym,
                        VmValue::err(VmValue::String("InternalizationRejected".to_string())),
                    );
                    return;
                }

                if !policy_desc.validation_requirements.is_empty() {
                    state.internalization_trace.push(GateCheckObservation {
                        check_kind: "ValidateClaimContract".to_string(),
                        authority_source: "Caller".to_string(),
                        effects: val_eff_strings.clone(),
                        result: "Pass".to_string(),
                    });
                }
                state.observable_effects.extend(val_eff_strings);

                let owner = state.current_agent_id.clone();
                let mut lin_prov = vec![
                    format!("internalize({})", policy_id),
                    format!("claim_from({})", claim_sym),
                ];
                if let Some(cl_lin) = state.lineage.get(&claim_sym) {
                    lin_prov.extend(cl_lin.clone());
                }
                state.lineage.insert(dest_sym.clone(), lin_prov.clone());

                let belief_prov = if self
                    .mutations
                    .s3m23_delegated_provenance_removed_on_internalize
                {
                    vec![format!("internalize({})", policy_id)]
                } else if self.mutations.s3m24_effect_summary_used_as_clean_provenance {
                    vec![format!("local_clean({})", policy_id)]
                } else {
                    let mut bp = vec![format!("internalize({})", policy_id)];
                    if let Some(cl_lin) = state.lineage.get(&claim_sym) {
                        bp.extend(cl_lin.clone());
                    }
                    bp
                };

                let belief_val = VmValue::belief(
                    claim_val.clone(),
                    owner.clone(),
                    belief_prov.clone(),
                    policy_id.0.clone(),
                );

                state.beliefs.insert(
                    dest_sym.clone(),
                    BeliefValue {
                        payload: Box::new(claim_val),
                        owner_agent_id: owner,
                        provenance: belief_prov,
                        policy_binding: policy_id.0.clone(),
                    },
                );

                state.types.insert(
                    dest_sym.clone(),
                    Type::result(Type::belief(payload_type.clone()), Type::String).display_name(),
                );
                state.env.insert(dest_sym, VmValue::ok(belief_val));
            }
            // Slice 4: soma.converge execution
            VmInstruction::VmConvergeInit {
                frame_var,
                root_node,
                initial_frontier,
                budget_resource,
                budget_limit,
                max_steps,
                max_satisfaction_attempts,
                on_step_failure,
                on_satisfier_error,
            } => {
                let frame_sym = format!("v{}", frame_var.0);
                let mut domain = crate::converge::domain::ConvergeTransactionDomain::default();
                domain.on_step_failure = on_step_failure.clone();
                domain.on_satisfier_error = on_satisfier_error.clone();
                domain.max_steps = *max_steps;
                domain.max_satisfaction_attempts = *max_satisfaction_attempts;

                domain
                    .scope_limit
                    .insert(budget_resource.clone(), *budget_limit);

                let initial_usd = 100;
                domain
                    .intent_initial_total
                    .insert(budget_resource.clone(), initial_usd);
                domain
                    .intent_available
                    .insert(budget_resource.clone(), initial_usd);

                let init_front = if initial_frontier.is_empty() {
                    vec![root_node.clone()]
                } else {
                    initial_frontier.clone()
                };
                let _ = crate::converge::engine::discover_successors(
                    &mut domain,
                    &init_front,
                    self.mutations.s4m15_closing_mutates_frontier,
                );

                domain.frame_status = crate::converge::domain::SearchStatus::Searching;

                state.converge_domains.insert(frame_sym.clone(), domain);
                state.env.insert(frame_sym.clone(), VmValue::Unit);
                state.types.insert(frame_sym, Type::Unit.display_name());
            }
            VmInstruction::VmConvergeStep {
                dest,
                frame_var,
                successors: _,
                node_ops,
                satisfier,
                partial_map,
                space_faults: _,
                fault_spec: _,
                space_effects: _,
                satisfier_effects: _,
            } => {
                let frame_sym = format!("v{}", frame_var.0);
                let dest_sym = format!("v{}", dest.0);

                let mut domain = state
                    .converge_domains
                    .remove(&frame_sym)
                    .unwrap_or_default();

                let _ = crate::converge::invariants::check_all_invariants(&domain);

                if domain.frame_status != crate::converge::domain::SearchStatus::Searching
                    && !(self.mutations.s4m08_second_unsettled_request_allowed && !domain.frontier.is_empty())
                {
                    state.env.insert(dest_sym.clone(), VmValue::Bool(false));
                    state.types.insert(dest_sym, Type::Bool.display_name());
                    state.converge_domains.insert(frame_sym, domain);
                    return;
                }

                let mut sched_node_ops = std::collections::BTreeMap::new();
                for (n, op) in node_ops {
                    sched_node_ops.insert(
                        n.clone(),
                        crate::converge::scheduler::SpaceOpInfo {
                            op_id: op.op_id.clone(),
                            kind: op.kind.clone(),
                            cost: op.cost,
                        },
                    );
                }

                let effectful_sat = satisfier.effectful_op.as_ref().map(|es| {
                    crate::converge::scheduler::SatisfierOpInfo {
                        op_id: es.op_id.clone(),
                        kind: es.kind.clone(),
                        cost: es.cost,
                    }
                });

                // Pure scheduler selection only (scheduler selection != semantic execution)
                let action = crate::converge::scheduler::scheduler_step(
                    &mut domain,
                    &sched_node_ops,
                    partial_map,
                    effectful_sat.as_ref(),
                    self.mutations.s4m01_scheduler_pops_unaffordable_node,
                    self.mutations.s4m17_budget_scope_mints_ownership,
                    self.mutations
                        .s4m20_satisfaction_retry_bypasses_attempt_ceiling,
                    self.mutations.s4m08_second_unsettled_request_allowed,
                );

                match action {
                    crate::converge::scheduler::SchedulerAction::Stop { reason } => {
                        crate::converge::engine::exhaust(&mut domain, &reason);
                        let _ = crate::converge::engine::terminalize(
                            &mut domain,
                            self.mutations.s4m16_terminalizes_with_commitment,
                        );
                        domain.pending_action = None;
                        state.env.insert(dest_sym.clone(), VmValue::Bool(false));
                    }
                    crate::converge::scheduler::SchedulerAction::Wait { reason } => {
                        let in_flight_h = domain
                            .handles
                            .values()
                            .find(|s| {
                                s.settlement.is_none()
                                    && s.state != "Aborted"
                                    && s.state != "ConfirmedNotDelivered"
                            })
                            .map(|s| s.handle_id.clone())
                            .unwrap_or(reason);
                        domain.frame_status = crate::converge::domain::SearchStatus::Waiting;
                        domain.pending_action = None;
                        state.status = VmStatus::WaitingOnConverge(in_flight_h);
                        state.return_value = None;
                        state.types.insert(dest_sym.clone(), Type::Bool.display_name());
                        state.converge_domains.insert(frame_sym, domain);
                        return;
                    }
                    crate::converge::scheduler::SchedulerAction::Expand(act) => {
                        domain.pending_action = Some(crate::converge::domain::PendingAction {
                            node_id: act.node_id.clone(),
                            op_id: act.op_id.clone(),
                            kind: act.kind.clone(),
                            cost: act.cost,
                            is_expansion: true,
                        });
                        state.env.insert(dest_sym.clone(), VmValue::Bool(true));
                    }
                    crate::converge::scheduler::SchedulerAction::CheckSatisfaction(act) => {
                        domain.pending_action = Some(crate::converge::domain::PendingAction {
                            node_id: act.node_id.clone(),
                            op_id: act.op_id.clone(),
                            kind: act.kind.clone(),
                            cost: act.cost,
                            is_expansion: false,
                        });
                        state.env.insert(dest_sym.clone(), VmValue::Bool(true));
                    }
                }

                state.types.insert(dest_sym, Type::Bool.display_name());
                state.converge_domains.insert(frame_sym, domain);
            }
            VmInstruction::VmConvergeDispatchLocal {
                frame_var,
                successors,
            } => {
                let frame_sym = format!("v{}", frame_var.0);

                let mut domain = state
                    .converge_domains
                    .remove(&frame_sym)
                    .unwrap_or_default();

                if let Some(act) = domain.pending_action.clone() {
                    if act.kind == "local" && act.is_expansion {
                        let succs = successors.get(&act.node_id).cloned().unwrap_or_default();
                        let _ = crate::converge::engine::dispatch_local(
                            &mut domain,
                            &act.node_id,
                            &act.op_id,
                            &succs,
                        );
                        domain.pending_action = None;
                    }
                }

                state.converge_domains.insert(frame_sym, domain);
            }
            VmInstruction::VmConvergeCheckSatisfactionLocal {
                frame_var,
                satisfier,
            } => {
                let frame_sym = format!("v{}", frame_var.0);

                let mut domain = state
                    .converge_domains
                    .remove(&frame_sym)
                    .unwrap_or_default();

                if let Some(act) = domain.pending_action.clone() {
                    if act.kind == "local" && !act.is_expansion {
                        let attempt_no = domain.satisfaction_attempts + 1;
                        let sat_json = satisfier
                            .satisfier_map
                            .get(&act.node_id)
                            .unwrap_or(&serde_json::Value::Null);
                        let (_status_tag, satisfied, sat_val_opt, err_opt) =
                            crate::converge::engine::parse_sat_entry(sat_json, attempt_no);
                        let res = crate::converge::engine::check_satisfaction(
                            &mut domain,
                            &act.node_id,
                            &act.op_id,
                            satisfied,
                            sat_val_opt,
                            err_opt,
                            self.mutations.s4m03_ranking_promotes_satisfied,
                            self.mutations
                                .s4m20_satisfaction_retry_bypasses_attempt_ceiling,
                        );
                        if let Ok(true) = res {
                            crate::converge::engine::close_frame(
                                &mut domain,
                                crate::converge::domain::ClosingReason {
                                    kind: "PendingSatisfied".to_string(),
                                    error: None,
                                },
                            );
                            let _ = crate::converge::engine::terminalize(
                                &mut domain,
                                self.mutations.s4m16_terminalizes_with_commitment,
                            );
                        }
                        if domain.frame_status == crate::converge::domain::SearchStatus::Closing {
                            let _ = crate::converge::engine::finish_if_drained(&mut domain);
                        }
                        domain.pending_action = None;
                    }
                }

                state.converge_domains.insert(frame_sym, domain);
            }
            VmInstruction::VmConvergeStage {
                handle_dest,
                frame_var,
                node_ops,
                satisfier,
                fault_spec: _,
            } => {
                let frame_sym = format!("v{}", frame_var.0);
                let handle_sym = format!("v{}", handle_dest.0);

                let mut domain = state
                    .converge_domains
                    .remove(&frame_sym)
                    .unwrap_or_default();

                if let Some(act) = domain.pending_action.clone() {
                    let attempt_no = if act.is_expansion {
                        domain.visited.iter().filter(|v| v.node_id == act.node_id).count() as u64 + 1
                    } else {
                        domain.satisfaction_attempts + 1
                    };

                    let (req_id, dedup, idemp) = if act.is_expansion {
                        let op_def = node_ops.get(&act.node_id);
                        let req_id = if self.mutations.s4m18_requeue_reuses_request_id && attempt_no > 1 {
                            format!("req:{}:{}:1", act.op_id, act.node_id)
                        } else {
                            op_def
                                .and_then(|o| o.request_id.clone())
                                .unwrap_or_else(|| {
                                    format!("req:{}:{}:{}", act.op_id, act.node_id, attempt_no)
                                })
                        };
                        let dedup = op_def.map(|o| o.dedup_capable).unwrap_or(true);
                        let idemp = op_def.map(|o| o.idempotent).unwrap_or(true);
                        (req_id, dedup, idemp)
                    } else {
                        let es_def = satisfier.effectful_op.as_ref();
                        let req_id = es_def
                            .and_then(|o| o.request_id.clone())
                            .unwrap_or_else(|| {
                                format!("req:{}:{}:{}", act.op_id, act.node_id, attempt_no)
                            });
                        let dedup = es_def.map(|o| o.dedup_capable).unwrap_or(true);
                        let idemp = es_def.map(|o| o.idempotent).unwrap_or(true);
                        (req_id, dedup, idemp)
                    };

                    let handle_res = crate::converge::engine::stage_local(
                        &mut domain,
                        &act.node_id,
                        &act.op_id,
                        &req_id,
                        "usd",
                        act.cost,
                        dedup,
                        idemp,
                        false,
                        act.is_expansion,
                        self.mutations.s4m08_second_unsettled_request_allowed,
                        self.mutations.s4m04_stage_rejected_leaves_reservation,
                        self.mutations.s4m17_budget_scope_mints_ownership,
                    );

                    if let Ok(handle) = handle_res {
                        domain.last_staged_handle = Some(handle.clone());
                        state.env.insert(handle_sym.clone(), VmValue::String(handle));
                        state.types.insert(handle_sym, Type::String.display_name());
                    }
                }

                state.converge_domains.insert(frame_sym, domain);
            }
            VmInstruction::VmConvergeEmit {
                frame_var,
                handle_var,
                node_ops,
                satisfier,
                fault_spec,
                space_effects: _,
                satisfier_effects: _,
            } => {
                let frame_sym = format!("v{}", frame_var.0);
                let handle_sym = format!("v{}", handle_var.0);

                let mut domain = state
                    .converge_domains
                    .remove(&frame_sym)
                    .unwrap_or_default();

                let handle_id_opt = match state.env.get(&handle_sym) {
                    Some(VmValue::String(s)) => Some(s.clone()),
                    _ => domain.last_staged_handle.clone(),
                };

                if let Some(handle) = handle_id_opt {
                    if let Some(act) = domain.pending_action.clone() {
                        let op_is_deliv_unknown = fault_spec.delivery_unknown
                            || fault_spec.delivery_unknown_ops.contains(&act.op_id);

                        let (dedup, idemp) = if act.is_expansion {
                            let op_def = node_ops.get(&act.node_id);
                            (op_def.map(|o| o.dedup_capable).unwrap_or(true), op_def.map(|o| o.idempotent).unwrap_or(true))
                        } else {
                            let es_def = satisfier.effectful_op.as_ref();
                            (es_def.map(|o| o.dedup_capable).unwrap_or(true), es_def.map(|o| o.idempotent).unwrap_or(true))
                        };

                        let _ = crate::converge::engine::emit_external(
                            &mut domain,
                            &handle,
                            op_is_deliv_unknown,
                            self.mutations.s4m06_transport_retry_increments_step,
                            self.mutations.s4m05_first_emit_fails_step,
                            self.mutations.s4m07_transport_retry_changes_request_id,
                            self.mutations.s4m09_delivery_unknown_releases_commitment,
                        );

                        // R4: Record only the actually emitted effect
                        let eff_tag = format!("external({})", act.op_id);
                        if !state.observable_effects.contains(&eff_tag) {
                            state.observable_effects.push(eff_tag);
                        }

                        if op_is_deliv_unknown {
                            if fault_spec.cancel_in_flight {
                                crate::converge::engine::cancel(&mut domain);
                                let _ = crate::converge::engine::confirmed_not_delivered(&mut domain, &handle);
                                let _ = crate::converge::engine::finish_if_drained(&mut domain);
                            } else if fault_spec.safe_retry && (dedup || idemp) {
                                if fault_spec.double_delivery_unknown {
                                    let _ = crate::converge::engine::emit_external(
                                        &mut domain,
                                        &handle,
                                        true,
                                        self.mutations.s4m06_transport_retry_increments_step,
                                        self.mutations.s4m05_first_emit_fails_step,
                                        self.mutations.s4m07_transport_retry_changes_request_id,
                                        self.mutations.s4m09_delivery_unknown_releases_commitment,
                                    );
                                } else {
                                    let _ = crate::converge::engine::emit_external(
                                        &mut domain,
                                        &handle,
                                        false,
                                        self.mutations.s4m06_transport_retry_increments_step,
                                        self.mutations.s4m05_first_emit_fails_step,
                                        self.mutations.s4m07_transport_retry_changes_request_id,
                                        self.mutations.s4m09_delivery_unknown_releases_commitment,
                                    );
                                }
                            } else {
                                if self.mutations.s4m16_terminalizes_with_commitment {
                                    crate::converge::engine::exhaust(&mut domain, "ForcedTerminal");
                                    let _ = crate::converge::engine::terminalize(&mut domain, true);
                                }
                            }
                        }

                        if op_is_deliv_unknown && !fault_spec.cancel_in_flight && !(fault_spec.safe_retry && (dedup || idemp)) {
                            if self.mutations.s4m16_terminalizes_with_commitment {
                                crate::converge::engine::exhaust(&mut domain, "ForcedTerminal");
                                let _ = crate::converge::engine::terminalize(&mut domain, true);
                            } else if !(self.mutations.s4m08_second_unsettled_request_allowed && !domain.frontier.is_empty()) {
                                domain.frame_status = crate::converge::domain::SearchStatus::Waiting;
                                state.status = VmStatus::WaitingOnConverge(handle);
                                state.return_value = None;
                                state.converge_domains.insert(frame_sym, domain);
                                return;
                            }
                        }
                    }
                }

                state.converge_domains.insert(frame_sym, domain);
            }
            VmInstruction::VmConvergeAdmitCompletion {
                frame_var,
                handle_var,
                successors,
                node_ops,
                satisfier,
                space_faults,
                fault_spec,
            } => {
                
                let frame_sym = format!("v{}", frame_var.0);
                let handle_sym = format!("v{}", handle_var.0);

                let mut domain = state
                    .converge_domains
                    .remove(&frame_sym)
                    .unwrap_or_default();

                if true
                {
                    let handle_id_opt = match state.env.get(&handle_sym) {
                        Some(VmValue::String(s)) => Some(s.clone()),
                        _ => domain.last_staged_handle.clone(),
                    };

                    if let Some(handle) = handle_id_opt {
                        if let Some(act) = domain.pending_action.clone() {
                            let attempt_no = if act.is_expansion {
                                domain.visited.iter().filter(|v| v.node_id == act.node_id).count() as u64
                            } else {
                                domain.satisfaction_attempts
                            };

                            let op_is_deliv_unknown = fault_spec.delivery_unknown
                                || fault_spec.delivery_unknown_ops.contains(&act.op_id);

                            let (dedup, idemp) = if act.is_expansion {
                                let op_def = node_ops.get(&act.node_id);
                                (op_def.map(|o| o.dedup_capable).unwrap_or(true), op_def.map(|o| o.idempotent).unwrap_or(true))
                            } else {
                                let es_def = satisfier.effectful_op.as_ref();
                                (es_def.map(|o| o.dedup_capable).unwrap_or(true), es_def.map(|o| o.idempotent).unwrap_or(true))
                            };

                            if act.is_expansion {
                                let op_def = node_ops.get(&act.node_id);
                                let succs = successors.get(&act.node_id).cloned().unwrap_or_default();
                                let is_space_fault = space_faults.get(&act.op_id);
                                let (is_failure, fault_err) = if let Some(v) = is_space_fault {
                                    if let Some(arr) = v.as_array() {
                                        let idx = (attempt_no.saturating_sub(1) as usize).min(arr.len() - 1);
                                        if arr[idx].is_null() || arr[idx].as_str() == Some("null") {
                                            (false, None)
                                        } else {
                                            (true, Some(arr[idx].as_str().unwrap_or("SpaceFault").to_string()))
                                        }
                                    } else if v.is_null() || v.as_str() == Some("null") {
                                        (false, None)
                                    } else if let Some(msg) = v.as_str() {
                                        (true, Some(msg.to_string()))
                                    } else {
                                        (false, None)
                                    }
                                } else {
                                    (false, None)
                                };

                                let space_payload = crate::converge::domain::SpaceOutcome {
                                    successors: if is_failure && !self.mutations.s4m19_failed_requeue_incorporates_successors {
                                        Vec::new()
                                    } else {
                                        succs
                                    },
                                    error: fault_err,
                                    is_failure,
                                };

                                let req_id = domain.handles.get(&handle).map(|st| st.request_id.clone()).unwrap_or_else(|| format!("req:{}:{}:{}", act.op_id, act.node_id, attempt_no));
                                let receipt_id = format!("receipt-{}", req_id);

                                let completion = crate::converge::domain::CompletionRecord {
                                    handle_id: handle.clone(),
                                    receipt_id: receipt_id.clone(),
                                    digest: format!("digest-{}", req_id),
                                    outcome: if is_failure { "Failure".to_string() } else { "Success".to_string() },
                                    semantic_payload: Some(crate::converge::domain::SemanticPayload::Space(space_payload)),
                                    receipt: Some(crate::converge::domain::ExecutionReceipt {
                                        request_id: req_id,
                                        receipt_id,
                                        resource: "usd".to_string(),
                                        amount: op_def.and_then(|o| o.actual_cost).unwrap_or(act.cost),
                                    }),
                                };

                                if fault_spec.cancel_in_flight && !op_is_deliv_unknown {
                                    let _ = crate::converge::engine::admit_completion(
                                        &mut domain,
                                        &handle,
                                        completion,
                                        self.mutations.s4m09_delivery_unknown_releases_commitment,
                                    );
                                } else if !op_is_deliv_unknown || (fault_spec.safe_retry && (dedup || idemp) && !fault_spec.double_delivery_unknown) {
                                    let _ = crate::converge::engine::admit_completion(
                                        &mut domain,
                                        &handle,
                                        completion.clone(),
                                        self.mutations.s4m09_delivery_unknown_releases_commitment,
                                    );
                                    if fault_spec.duplicate_completion {
                                        let _ = crate::converge::engine::admit_completion(
                                            &mut domain,
                                            &handle,
                                            completion,
                                            self.mutations.s4m09_delivery_unknown_releases_commitment,
                                        );
                                    }
                                }
                            } else {
                                let es_def = satisfier.effectful_op.as_ref();
                                let sat_json = satisfier
                                    .satisfier_map
                                    .get(&act.node_id)
                                    .unwrap_or(&serde_json::Value::Null);
                                let (status_tag, satisfied, sat_val_opt, err_opt) =
                                    crate::converge::engine::parse_sat_entry(sat_json, attempt_no);

                                let sat_payload = crate::converge::domain::SatisfierOutcome {
                                    node_id: act.node_id.clone(),
                                    op_id: act.op_id.clone(),
                                    satisfied,
                                    value: sat_val_opt,
                                    error: err_opt,
                                };

                                let req_id = domain.handles.get(&handle).map(|st| st.request_id.clone()).unwrap_or_else(|| format!("req:{}:{}:{}", act.op_id, act.node_id, attempt_no));
                                let receipt_id = format!("receipt-{}", req_id);

                                let completion = crate::converge::domain::CompletionRecord {
                                    handle_id: handle.clone(),
                                    receipt_id: receipt_id.clone(),
                                    digest: format!("digest-{}", req_id),
                                    outcome: if status_tag == "ok" { "Success".to_string() } else { "Failure".to_string() },
                                    semantic_payload: Some(crate::converge::domain::SemanticPayload::Satisfier(sat_payload)),
                                    receipt: Some(crate::converge::domain::ExecutionReceipt {
                                        request_id: req_id,
                                        receipt_id,
                                        resource: "usd".to_string(),
                                        amount: es_def.and_then(|o| o.actual_cost).unwrap_or(act.cost),
                                    }),
                                };

                                if !op_is_deliv_unknown || (fault_spec.safe_retry && (dedup || idemp) && !fault_spec.double_delivery_unknown) {
                                    let _ = crate::converge::engine::admit_completion(
                                        &mut domain,
                                        &handle,
                                        completion,
                                        self.mutations.s4m09_delivery_unknown_releases_commitment,
                                    );
                                }
                            }
                        }
                    }
                }

                state.converge_domains.insert(frame_sym, domain);
            }
            VmInstruction::VmConvergeSettle {
                frame_var,
                handle_var,
                node_ops,
                satisfier,
                fault_spec,
            } => {
                let frame_sym = format!("v{}", frame_var.0);
                let handle_sym = format!("v{}", handle_var.0);

                let mut domain = state
                    .converge_domains
                    .remove(&frame_sym)
                    .unwrap_or_default();

                if true
                {
                    let handle_id_opt = match state.env.get(&handle_sym) {
                        Some(VmValue::String(s)) => Some(s.clone()),
                        _ => domain.last_staged_handle.clone(),
                    };

                    if let Some(handle) = handle_id_opt {
                        if let Some(act) = domain.pending_action.clone() {
                            let attempt_no = if act.is_expansion {
                                domain.visited.iter().filter(|v| v.node_id == act.node_id).count() as u64 + 1
                            } else {
                                domain.satisfaction_attempts + 1
                            };

                            let op_is_deliv_unknown = fault_spec.delivery_unknown
                                || fault_spec.delivery_unknown_ops.contains(&act.op_id);

                            let (dedup, idemp) = if act.is_expansion {
                                let op_def = node_ops.get(&act.node_id);
                                (op_def.map(|o| o.dedup_capable).unwrap_or(true), op_def.map(|o| o.idempotent).unwrap_or(true))
                            } else {
                                let es_def = satisfier.effectful_op.as_ref();
                                (es_def.map(|o| o.dedup_capable).unwrap_or(true), es_def.map(|o| o.idempotent).unwrap_or(true))
                            };

                            if act.is_expansion {
                                let op_def = node_ops.get(&act.node_id);
                                let charge = op_def.and_then(|o| o.actual_cost).unwrap_or(act.cost);
                                let req_id = domain.handles.get(&handle).map(|st| st.request_id.clone()).unwrap_or_else(|| format!("req:{}:{}:{}", act.op_id, act.node_id, attempt_no));
                                let receipt = crate::converge::domain::ExecutionReceipt {
                                    request_id: req_id.clone(),
                                    receipt_id: format!("receipt-{}", req_id),
                                    resource: "usd".to_string(),
                                    amount: charge,
                                };

                                if fault_spec.cancel_in_flight && !op_is_deliv_unknown {
                                    crate::converge::engine::cancel(&mut domain);
                                    let _ = crate::converge::engine::reconcile_settlement(
                                        &mut domain,
                                        &handle,
                                        receipt,
                                        self.mutations.s4m11_duplicate_settlement_reconciles_twice,
                                        self.mutations.s4m12_settlement_marks_applied_automatically,
                                    );
                                } else if !op_is_deliv_unknown || (fault_spec.safe_retry && (dedup || idemp) && !fault_spec.double_delivery_unknown) {
                                    let _ = crate::converge::engine::reconcile_settlement(
                                        &mut domain,
                                        &handle,
                                        receipt.clone(),
                                        self.mutations.s4m11_duplicate_settlement_reconciles_twice,
                                        self.mutations.s4m12_settlement_marks_applied_automatically,
                                    );
                                    if fault_spec.duplicate_completion {
                                        let _ = crate::converge::engine::reconcile_settlement(
                                            &mut domain,
                                            &handle,
                                            receipt,
                                            self.mutations.s4m11_duplicate_settlement_reconciles_twice,
                                            self.mutations.s4m12_settlement_marks_applied_automatically,
                                        );
                                    }

                                    if fault_spec.crash_after_settlement {
                                        if self
                                            .mutations
                                            .s4m13_crash_after_settlement_loses_semantic_result
                                        {
                                            if let Some(st) = domain.handles.get_mut(&handle) {
                                                st.completion = None;
                                            }
                                        }
                                    }
                                }
                            } else {
                                let es_def = satisfier.effectful_op.as_ref();
                                let charge = es_def.and_then(|o| o.actual_cost).unwrap_or(act.cost);
                                let req_id = domain.handles.get(&handle).map(|st| st.request_id.clone()).unwrap_or_else(|| format!("req:{}:{}:{}", act.op_id, act.node_id, attempt_no));
                                let receipt = crate::converge::domain::ExecutionReceipt {
                                    request_id: req_id.clone(),
                                    receipt_id: format!("receipt-{}", req_id),
                                    resource: "usd".to_string(),
                                    amount: charge,
                                };

                                if !op_is_deliv_unknown || (fault_spec.safe_retry && (dedup || idemp) && !fault_spec.double_delivery_unknown) {
                                    let _ = crate::converge::engine::reconcile_settlement(
                                        &mut domain,
                                        &handle,
                                        receipt,
                                        self.mutations.s4m11_duplicate_settlement_reconciles_twice,
                                        self.mutations.s4m12_settlement_marks_applied_automatically,
                                    );
                                }
                            }
                        }
                    }
                }

                state.converge_domains.insert(frame_sym, domain);
            }
            VmInstruction::VmConvergeApply {
                frame_var,
                handle_var,
                fault_spec,
            } => {
                let frame_sym = format!("v{}", frame_var.0);
                let handle_sym = format!("v{}", handle_var.0);

                let mut domain = state
                    .converge_domains
                    .remove(&frame_sym)
                    .unwrap_or_default();

                if true
                {
                    let handle_id_opt = match state.env.get(&handle_sym) {
                        Some(VmValue::String(s)) => Some(s.clone()),
                        _ => domain.last_staged_handle.clone(),
                    };

                    if let Some(handle) = handle_id_opt {
                        let _ = crate::converge::engine::apply_semantic(
                            &mut domain,
                            &handle,
                            self.mutations.s4m10_duplicate_completion_applies_twice,
                            self.mutations.s4m14_closing_accepts_late_payload,
                            self.mutations.s4m03_ranking_promotes_satisfied,
                            self.mutations.s4m15_closing_mutates_frontier,
                        );

                        if fault_spec.duplicate_completion
                            && self.mutations.s4m10_duplicate_completion_applies_twice
                        {
                            let _ = crate::converge::engine::apply_semantic(
                                &mut domain,
                                &handle,
                                true,
                                self.mutations.s4m14_closing_accepts_late_payload,
                                self.mutations.s4m03_ranking_promotes_satisfied,
                                self.mutations.s4m15_closing_mutates_frontier,
                            );
                        }

                        if fault_spec.cancel_in_flight {
                            let _ = crate::converge::engine::finish_if_drained(&mut domain);
                        }

                        if domain.frame_status == crate::converge::domain::SearchStatus::Satisfied {
                            crate::converge::engine::close_frame(
                                &mut domain,
                                crate::converge::domain::ClosingReason {
                                    kind: "PendingSatisfied".to_string(),
                                    error: None,
                                },
                            );
                            let _ = crate::converge::engine::terminalize(
                                &mut domain,
                                self.mutations.s4m16_terminalizes_with_commitment,
                            );
                        }
                        if domain.frame_status == crate::converge::domain::SearchStatus::Closing {
                            let _ = crate::converge::engine::finish_if_drained(&mut domain);
                        }
                    }
                }

                domain.pending_action = None;
                state.converge_domains.insert(frame_sym, domain);
            }
            VmInstruction::VmConvergeFinish {
                dest,
                frame_var,
                partial_type,
                satisfied_type,
            } => {
                let frame_sym = format!("v{}", frame_var.0);
                let dest_sym = format!("v{}", dest.0);

                let domain = state
                    .converge_domains
                    .get(&frame_sym)
                    .cloned()
                    .unwrap_or_default();

                let res_val = match domain.frame_status {
                    crate::converge::domain::SearchStatus::Satisfied => {
                        let sat_val = domain.satisfied_value.clone().unwrap_or(VmValue::Unit);
                        VmValue::ok(VmValue::satisfied(sat_val))
                    }
                    crate::converge::domain::SearchStatus::Exhausted => {
                        let rep = crate::ir::values::ExhaustionReportValue {
                            best_partial: domain.best_partial.clone().map(Box::new),
                            policy: "SearchPolicy".to_string(),
                            reason: domain
                                .exhaustion_reason
                                .clone()
                                .unwrap_or_else(|| "FrontierEmpty".to_string()),
                            visited_nodes: domain
                                .visited
                                .iter()
                                .map(|v| v.node_id.clone())
                                .collect(),
                            trace: Vec::new(),
                        };
                        VmValue::ok(VmValue::exhausted(rep))
                    }
                    crate::converge::domain::SearchStatus::Failed => {
                        let err_msg = domain
                            .closing_reason
                            .as_ref()
                            .and_then(|r| r.error.clone())
                            .unwrap_or_else(|| "ConvergeFailed".to_string());
                        VmValue::err(VmValue::String(err_msg))
                    }
                    crate::converge::domain::SearchStatus::Cancelled => {
                        VmValue::err(VmValue::String("Cancelled".to_string()))
                    }
                    _ => VmValue::err(VmValue::String("IncompleteSearch".to_string())),
                };

                let outcome_ty = Type::convergence_outcome(
                    satisfied_type.clone(),
                    Type::exhaustion_report(partial_type.clone()),
                );
                state.types.insert(
                    dest_sym.clone(),
                    Type::result(outcome_ty, Type::String).display_name(),
                );
                state.env.insert(dest_sym, res_val);
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
                let cond_val = state
                    .env
                    .get(&cond_sym)
                    .cloned()
                    .unwrap_or(VmValue::Bool(false));
                match cond_val {
                    VmValue::Bool(true) => {
                        self.transfer_control(*true_target, true_args, state);
                    }
                    VmValue::Bool(false) => {
                        self.transfer_control(*false_target, false_args, state);
                    }
                    _ => {
                        state.status =
                            VmStatus::Error(format!("CondBr on non-boolean value {:?}", cond_val));
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
                state.env.insert(target_sym.clone(), payload_val);
                if let Some(res_lin) = state.lineage.get(&res_sym) {
                    state.lineage.insert(target_sym.clone(), res_lin.clone());
                }
                if let Some(tb) = self.func.blocks.get(&target_block) {
                    for (p, ty) in &tb.params {
                        state.types.insert(format!("v{}", p.0), ty.display_name());
                    }
                }
                state.current_block = target_block;
                state.current_inst_index = 0;
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
                    _ => {
                        state.status = VmStatus::Error(format!(
                            "SwitchActOutcome on non-act-outcome value {:?}",
                            out_val
                        ));
                    }
                }
            }
            VmTerminator::Unreachable => {
                state.status = VmStatus::Error("Reached unreachable terminator".to_string());
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
            for (i, (param_id, ty)) in target_block.params.iter().enumerate() {
                if let Some(arg_id) = args.get(i) {
                    let arg_sym = format!("v{}", arg_id.0);
                    let val = state.env.get(&arg_sym).cloned().unwrap_or(VmValue::Unit);
                    let param_sym = format!("v{}", param_id.0);
                    state.env.insert(param_sym.clone(), val);
                    state.types.insert(param_sym.clone(), ty.display_name());
                    if let Some(arg_lin) = state.lineage.get(&arg_sym) {
                        state.lineage.insert(param_sym.clone(), arg_lin.clone());
                    }
                    if self.mutations.s3m17_handle_join_invents_provenance {
                        if matches!(ty, Type::ChildHandle { .. }) {
                            state.result_provenance.insert(
                                param_sym.clone(),
                                crate::child::provenance::ChildResultProvenance::new(
                                    "fake_child",
                                    "fake_intent",
                                    "fake_agent",
                                    "fake_evt",
                                ),
                            );
                        }
                    }
                }
            }
        }
        state.current_block = target;
        state.current_inst_index = 0;
    }

    pub fn resume(&mut self, state: &mut VmExecutionState, max_steps: usize) {
        let analysis =
            PathFactAnalyzer::with_mutations(self.func, self.mutations.clone()).analyze();
        let mut steps = 0;

        while state.status == VmStatus::Running && steps < max_steps {
            steps += 1;

            let block = match self.func.blocks.get(&state.current_block) {
                Some(b) => b.clone(),
                None => {
                    state.status = VmStatus::Error(format!(
                        "Current block {:?} not found in function",
                        state.current_block
                    ));
                    break;
                }
            };

            let block_facts = analysis
                .block_in_facts
                .get(&state.current_block)
                .cloned()
                .unwrap_or_default();
            let mut facts = state.active_facts.clone();
            facts.extend(block_facts);
            state.active_facts = facts;

            let inst_start = state.current_inst_index;
            let mut completed_block_instructions = true;
            for (idx, inst) in block.instructions.iter().enumerate().skip(inst_start) {
                state.current_inst_index = idx;
                self.execute_instruction(inst, state);
                if state.status != VmStatus::Running {
                    completed_block_instructions = false;
                    break;
                }
                if let VmInstruction::VmConvergeSettle { fault_spec, .. } = inst {
                    if fault_spec.crash_after_settlement && !state.invalidated_keys.contains("__crashed_and_reconstructed__") {
                        state.current_inst_index = idx + 1;
                        state.invalidated_keys.insert("__crashed_and_reconstructed__".to_string());
                        completed_block_instructions = false;
                        break;
                    }
                }
            }

            if state.status != VmStatus::Running {
                break;
            }

            if completed_block_instructions {
                self.execute_terminator(&block.terminator, state);
            }
        }

        if steps >= max_steps && state.status == VmStatus::Running {
            state.status = VmStatus::Error("Execution step limit exceeded".to_string());
        }
    }
}
