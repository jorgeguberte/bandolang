use std::collections::{BTreeMap, BTreeSet};

use crate::{
    conformance::schema::{ConformanceObservationV0, ConformanceProgramV0},
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
    vm_ir::VmFunction,
    vm_verifier::VmVerifier,
    world::WorldState,
};

pub fn run_conformance(prog: &ConformanceProgramV0) -> ConformanceObservationV0 {
    // 1. High-level verifier
    if let Err(diags) = HighLevelVerifier::verify_module(&prog.module) {
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
        };
    }

    // 2. Lowering (with mutation configuration if any)
    let mut lowering = LoweringContext::with_mutations(prog.mutations.clone());
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
        };
    }

    // 4. Find entry function
    let func = match vm_module.functions.iter().find(|f| f.name == prog.entry_func) {
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
            };
        }
    };

    // 5. Build runtime adapters (including Slice 2 adapters)
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

    let adapters = RuntimeAdapters {
        read: Box::new(read_adapter),
        infer: Box::new(infer_adapter),
        verifier: Box::new(verifier_adapter),
        act: Box::new(act_adapter),
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

    let interpreter = VmInterpreter::with_mutations(
        func,
        &adapters,
        &registry,
        prog.mutations.clone(),
    );
    let state = interpreter.execute(vm_inputs, initial_world, initial_facts, 1000);

    let status_str = match state.status {
        VmStatus::Running => "running".to_string(),
        VmStatus::Terminated => "ok".to_string(),
        VmStatus::Error(msg) => format!("error: {}", msg),
        VmStatus::ProtocolViolation(msg) => format!("protocol_violation: {}", msg),
    };

    let mut sorted_facts: Vec<_> = state.active_facts.into_iter().collect();
    sorted_facts.sort_by(|a, b| (&a.predicate, &a.args).cmp(&(&b.predicate, &b.args)));

    let mut types_map = BTreeMap::new();
    for (k, t) in state.types {
        types_map.insert(k, t);
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
    }
}
