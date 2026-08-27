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
    // Slice 3 additions
    pub current_agent_id: String,
    pub frame_budget: FrameBudget,
    pub child_handles: BTreeMap<String, ChildHandleRecord>,
    pub child_events: Vec<String>,
    pub frame_ledgers: BTreeMap<String, FrameBudget>,
    pub child_effective_authority: BTreeMap<String, Vec<String>>,
    pub result_provenance: BTreeMap<String, ChildResultProvenance>,
    pub beliefs: BTreeMap<String, BeliefValue>,
    pub internalization_trace: Vec<GateCheckObservation>,
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
            frame_budget: budget,
            child_handles: BTreeMap::new(),
            child_events: Vec::new(),
            frame_ledgers: BTreeMap::new(),
            child_effective_authority: BTreeMap::new(),
            result_provenance: BTreeMap::new(),
            beliefs: BTreeMap::new(),
            internalization_trace: Vec::new(),
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
                    "gen_1",
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
                        state.child_handles.insert(handle_id.clone(), rec);
                        state.frame_ledgers.insert(handle_id.clone(), child_budget);

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
                    if handle_val.generation_token == "stale" {
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
                            dest_sym,
                            VmValue::err(VmValue::String("SettlementUnknown".to_string())),
                        );
                    } else {
                        state.status = VmStatus::WaitingOnChild(rec.handle_id.clone());
                    }
                    return;
                }

                if rec.settlement_state != ChildSettlementState::Settled {
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
                        state
                            .result_provenance
                            .insert(dest_sym.clone(), rec.provenance.clone());
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
                        state
                            .result_provenance
                            .insert(dest_sym.clone(), rec.provenance.clone());
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
                                dest_sym,
                                VmValue::err(VmValue::String("SettlementUnknown".to_string())),
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
            } => {
                let dest_sym = format!("v{}", dest.0);
                let claim_sym = format!("v{}", claim.0);

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
                    ClaimContract::AcceptPredicate(_) => true,
                    ClaimContract::AcceptSubjectLiteral(lit) => {
                        if let VmValue::String(s) = &claim_val {
                            s == lit
                        } else {
                            false
                        }
                    }
                    ClaimContract::RejectAll => false,
                };

                if !contract_pass && !self.mutations.s3m20_failed_validation_constructs_belief {
                    state.internalization_trace.push(GateCheckObservation {
                        check_kind: "ValidateClaimContract".to_string(),
                        authority_source: "Caller".to_string(),
                        effects: val_eff_strings,
                        result: "Fail".to_string(),
                    });
                    state.env.insert(
                        dest_sym,
                        VmValue::err(VmValue::String("InternalizationRejected".to_string())),
                    );
                    return;
                }

                state.internalization_trace.push(GateCheckObservation {
                    check_kind: "ValidateClaimContract".to_string(),
                    authority_source: "Caller".to_string(),
                    effects: val_eff_strings.clone(),
                    result: "Pass".to_string(),
                });
                state.observable_effects.extend(val_eff_strings);

                let owner = state.current_agent_id.clone();
                let prov = vec![
                    format!("claim_from({})", claim_sym),
                    format!("internalize({})", policy_id),
                ];
                let belief_val =
                    VmValue::belief(claim_val.clone(), owner.clone(), prov, policy_id.0.clone());

                state.beliefs.insert(
                    dest_sym.clone(),
                    BeliefValue {
                        payload: Box::new(claim_val),
                        owner_agent_id: owner,
                        provenance: vec![format!("internalize({})", policy_id)],
                        policy_binding: policy_id.0.clone(),
                    },
                );

                state.types.insert(
                    dest_sym.clone(),
                    Type::result(Type::belief(payload_type.clone()), Type::String).display_name(),
                );
                state.env.insert(dest_sym, VmValue::ok(belief_val));
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
                    state.types.insert(param_sym, ty.display_name());
                }
            }
        }
        state.current_block = target;
    }
}
