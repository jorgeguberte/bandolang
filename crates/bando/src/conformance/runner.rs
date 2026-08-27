use std::collections::{BTreeMap, BTreeSet};

use crate::{
    child::{
        budget::FrameBudget, executor::DefaultTestChildExecutor, handle::ChildSettlementState,
    },
    conformance::schema::{
        BeliefObservation, ChildHandleObservation, ChildResultProvenanceObservation,
        ConformanceObservationV0, ConformanceProgramV0, FrameBudgetObservation,
    },
    lowering::LoweringContext,
    registry::RegistrySnapshot,
    verifier::HighLevelVerifier,
    vm::{
        adapters::{
            DefaultTestActAdapter, DefaultTestInferAdapter, DefaultTestReadAdapter,
            DefaultTestVerifierAdapter, RuntimeAdapters,
        },
        interpreter::VmStatus,
        VmInterpreter,
    },
    vm_verifier::VmVerifier,
    world::WorldState,
};

pub fn run_conformance(prog: &ConformanceProgramV0) -> ConformanceObservationV0 {
    let registry = prog.registry.clone().unwrap_or_else(RegistrySnapshot::new);

    // 1. High-level verifier (with trusted registry binding, P1, Q2, Q3, Q4)
    if let Err((diags, gate_resolutions)) =
        HighLevelVerifier::verify_module_with_registry_and_mutations(
            &prog.module,
            &registry,
            &prog.mutations,
        )
    {
        return ConformanceObservationV0 {
            status: "verifier_error".to_string(),
            return_val: None,
            effects: Vec::new(),
            active_facts: Vec::new(),
            latent_facts: BTreeMap::new(),
            types: BTreeMap::new(),
            bindings: BTreeMap::new(),
            lineage: BTreeMap::new(),
            diagnostics: diags,
            mutation_trace: Vec::new(),
            final_world: None,
            gate_resolutions,
            gate_trace: Vec::new(),
            child_handles: BTreeMap::new(),
            child_events: Vec::new(),
            frame_ledgers: BTreeMap::new(),
            child_effective_authority: BTreeMap::new(),
            result_provenance: BTreeMap::new(),
            beliefs: BTreeMap::new(),
            internalization_trace: Vec::new(),
        };
    }

    // 2. Lowering (with trusted registry binding, Q1)
    let mut lowering = LoweringContext::with_registry(registry.clone(), prog.mutations.clone());
    let vm_module = lowering.lower_module(&prog.module);

    // 3. VM Verifier
    if let Err(diags) = VmVerifier::verify_module(&vm_module) {
        return ConformanceObservationV0 {
            status: "vm_verifier_error".to_string(),
            return_val: None,
            effects: Vec::new(),
            active_facts: Vec::new(),
            latent_facts: BTreeMap::new(),
            types: BTreeMap::new(),
            bindings: BTreeMap::new(),
            lineage: BTreeMap::new(),
            diagnostics: diags,
            mutation_trace: Vec::new(),
            final_world: None,
            gate_resolutions: Vec::new(),
            gate_trace: Vec::new(),
            child_handles: BTreeMap::new(),
            child_events: Vec::new(),
            frame_ledgers: BTreeMap::new(),
            child_effective_authority: BTreeMap::new(),
            result_provenance: BTreeMap::new(),
            beliefs: BTreeMap::new(),
            internalization_trace: Vec::new(),
        };
    }

    // 4. Find entry function
    let func = match vm_module
        .functions
        .iter()
        .find(|f| f.name == prog.entry_func)
    {
        Some(f) => f,
        None => {
            return ConformanceObservationV0 {
                status: "entry_func_not_found".to_string(),
                return_val: None,
                effects: Vec::new(),
                active_facts: Vec::new(),
                latent_facts: BTreeMap::new(),
                types: BTreeMap::new(),
                bindings: BTreeMap::new(),
                lineage: BTreeMap::new(),
                diagnostics: Vec::new(),
                mutation_trace: Vec::new(),
                final_world: None,
                gate_resolutions: Vec::new(),
                gate_trace: Vec::new(),
                child_handles: BTreeMap::new(),
                child_events: Vec::new(),
                frame_ledgers: BTreeMap::new(),
                child_effective_authority: BTreeMap::new(),
                result_provenance: BTreeMap::new(),
                beliefs: BTreeMap::new(),
                internalization_trace: Vec::new(),
            };
        }
    };

    // 5. Build runtime adapters (including Slice 2 & Slice 3 adapters)
    let mut read_adapter = DefaultTestReadAdapter::default();
    read_adapter.errors = prog.read_errors.clone();

    let mut infer_adapter = DefaultTestInferAdapter::default();
    infer_adapter.errors = prog.infer_errors.clone();

    let mut verifier_adapter = DefaultTestVerifierAdapter::default();
    verifier_adapter.failures = prog.verifier_failures.clone();
    verifier_adapter.out_of_envelope_attempts = prog.verifier_out_of_envelope.clone();

    let mut act_adapter = DefaultTestActAdapter::default();
    act_adapter.scenarios = prog.act_scenarios.clone();
    act_adapter.custom_writes = prog.act_custom_writes.clone();
    act_adapter.toctou_hook_bumps = prog.toctou_hook_bumps.clone();

    let mut child_adapter = DefaultTestChildExecutor::default();
    child_adapter.scenarios = prog.child_scenarios.clone();

    let mut adapters = RuntimeAdapters {
        read: Box::new(read_adapter),
        infer: Box::new(infer_adapter),
        verifier: Box::new(verifier_adapter),
        act: Box::new(act_adapter),
        child: Box::new(child_adapter),
    };

    // 6. Map inputs
    let mut vm_inputs = BTreeMap::new();
    for (k, v) in &prog.inputs {
        vm_inputs.insert(k.clone(), v.clone());
    }

    // 7. Interpret with WorldState and RegistrySnapshot
    let initial_world = prog.initial_world.clone().unwrap_or_else(WorldState::new);
    let initial_facts: BTreeSet<_> = prog
        .initial_facts
        .clone()
        .unwrap_or_default()
        .into_iter()
        .collect();
    let registry = prog.registry.clone().unwrap_or_else(RegistrySnapshot::new);

    let initial_budget = prog.initial_budget.as_ref().map(|b| {
        let mut fb = FrameBudget::new();
        fb.available = b.clone();
        fb
    });

    let mut interpreter =
        VmInterpreter::with_mutations(func, &mut adapters, &registry, prog.mutations.clone());
    let state = interpreter.execute(
        vm_inputs,
        initial_world,
        initial_facts,
        initial_budget,
        prog.current_agent_id.clone(),
        1000,
    );

    let status_str = match state.status {
        VmStatus::Running => "running".to_string(),
        VmStatus::Terminated => "ok".to_string(),
        VmStatus::WaitingOnChild(h) => format!("waiting_on_child({})", h),
        VmStatus::Error(msg) => format!("error: {}", msg),
        VmStatus::ProtocolViolation(msg) => format!("protocol_violation: {}", msg),
    };

    let mut sorted_facts: Vec<_> = state.active_facts.into_iter().collect();
    sorted_facts.sort_by(|a, b| (&a.predicate, &a.args).cmp(&(&b.predicate, &b.args)));

    let mut types_map = BTreeMap::new();
    for (k, t) in state.types {
        types_map.insert(k, t);
    }

    let mut child_handles_obs = BTreeMap::new();
    for (h_id, h_rec) in state.child_handles {
        let st_str = match h_rec.settlement_state {
            ChildSettlementState::Unsettled => "Unsettled",
            ChildSettlementState::SettlementUnknown => "SettlementUnknown",
            ChildSettlementState::Settled => "Settled",
        };
        child_handles_obs.insert(
            h_id,
            ChildHandleObservation {
                handle_id: h_rec.handle_id,
                child_id: h_rec.child_id,
                parent_id: h_rec.parent_id,
                generation_token: h_rec.generation_token,
                effects: h_rec
                    .effects
                    .effects
                    .iter()
                    .map(|e| e.to_string())
                    .collect(),
                settlement_state: st_str.to_string(),
            },
        );
    }

    let mut frame_ledgers_obs = BTreeMap::new();
    let root_avail: BTreeMap<_, _> = state
        .frame_budget
        .available
        .into_iter()
        .filter(|(_, v)| *v > 0)
        .collect();
    let root_res: BTreeMap<_, _> = state
        .frame_budget
        .reserved
        .into_iter()
        .filter(|(_, v)| *v > 0)
        .collect();
    let root_sp: BTreeMap<_, _> = state
        .frame_budget
        .spent
        .into_iter()
        .filter(|(_, v)| *v > 0)
        .collect();
    frame_ledgers_obs.insert(
        "root".to_string(),
        FrameBudgetObservation {
            available: root_avail,
            reserved: root_res,
            spent: root_sp,
        },
    );
    for (f_id, f_b) in state.frame_ledgers {
        let avail: BTreeMap<_, _> = f_b.available.into_iter().filter(|(_, v)| *v > 0).collect();
        let res: BTreeMap<_, _> = f_b.reserved.into_iter().filter(|(_, v)| *v > 0).collect();
        let sp: BTreeMap<_, _> = f_b.spent.into_iter().filter(|(_, v)| *v > 0).collect();
        frame_ledgers_obs.insert(
            f_id,
            FrameBudgetObservation {
                available: avail,
                reserved: res,
                spent: sp,
            },
        );
    }

    let mut result_prov_obs = BTreeMap::new();
    for (dest, prov) in state.result_provenance {
        result_prov_obs.insert(
            dest,
            ChildResultProvenanceObservation {
                child_id: prov.child_id,
                intent_id: prov.intent_id,
                target_agent_id: prov.target_agent_id,
                result_event_id: prov.result_event_id,
                is_opaque: prov.is_opaque,
                underlying_refs: prov.underlying_refs,
            },
        );
    }

    let mut beliefs_obs = BTreeMap::new();
    for (dest, b) in state.beliefs {
        beliefs_obs.insert(
            dest,
            BeliefObservation {
                payload: *b.payload,
                owner_agent_id: b.owner_agent_id,
                provenance: b.provenance,
                policy_binding: b.policy_binding,
            },
        );
    }

    ConformanceObservationV0 {
        status: status_str,
        return_val: state.return_value,
        effects: state.observable_effects,
        active_facts: sorted_facts,
        latent_facts: state.latent,
        types: types_map,
        bindings: state.env,
        lineage: state.lineage,
        diagnostics: Vec::new(),
        mutation_trace: state.world.mutation_trace,
        final_world: Some(state.world.storage),
        gate_resolutions: state.gate_resolutions,
        gate_trace: state.gate_trace,
        child_handles: child_handles_obs,
        child_events: state.child_events,
        frame_ledgers: frame_ledgers_obs,
        child_effective_authority: state.child_effective_authority,
        result_provenance: result_prov_obs,
        beliefs: beliefs_obs,
        internalization_trace: state.internalization_trace,
    }
}
