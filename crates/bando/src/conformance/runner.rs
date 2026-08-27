use std::collections::BTreeMap;

use crate::{
    conformance::schema::{ConformanceObservationV0, ConformanceProgramV0},
    lowering::LoweringContext,
    verifier::HighLevelVerifier,
    vm::{
        adapters::{DefaultTestInferAdapter, DefaultTestReadAdapter, RuntimeAdapters},
        interpreter::VmStatus,
        VmInterpreter,
    },
    vm_ir::VmValueId,
    vm_verifier::VmVerifier,
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
            };
        }
    };

    // 5. Build runtime adapters
    let mut read_adapter = DefaultTestReadAdapter::default();
    read_adapter.errors = prog.read_errors.clone();

    let mut infer_adapter = DefaultTestInferAdapter::default();
    infer_adapter.errors = prog.infer_errors.clone();

    let adapters = RuntimeAdapters {
        read: Box::new(read_adapter),
        infer: Box::new(infer_adapter),
    };

    // 6. Map inputs
    let mut vm_inputs = BTreeMap::new();
    for (k, v) in &prog.inputs {
        if k.starts_with('v') {
            if let Ok(id) = k[1..].parse::<u32>() {
                vm_inputs.insert(VmValueId(id), v.clone());
            }
        }
    }

    // 7. Interpret
    let interpreter = VmInterpreter::with_mutations(func, &adapters, prog.mutations.clone());
    let state = interpreter.execute(vm_inputs, 1000);

    let status_str = match state.status {
        VmStatus::Running => "running".to_string(),
        VmStatus::Terminated => "ok".to_string(),
        VmStatus::ProtocolViolation(msg) => format!("protocol_violation: {}", msg),
    };

    let mut sorted_facts: Vec<_> = state.active_facts.into_iter().collect();
    sorted_facts.sort_by(|a, b| (&a.predicate, &a.args).cmp(&(&b.predicate, &b.args)));

    let mut types_map = BTreeMap::new();
    for (k, t) in state.types {
        types_map.insert(k, t.display_name());
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
    }
}
