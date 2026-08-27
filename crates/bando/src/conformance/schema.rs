use std::collections::BTreeMap;
use serde::{Deserialize, Serialize};

use crate::{
    diagnostics::Diagnostic,
    ir::{
        effects::EffectRow,
        facts::{Fact, LatentPostconditions},
        values::Value,
        Module,
    },
    registry::RegistrySnapshot,
    world::WorldState,
};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConformanceProgramV0 {
    pub name: String,
    pub module: Module,
    pub entry_func: String,
    pub inputs: BTreeMap<String, Value>,
    #[serde(default)]
    pub read_errors: BTreeMap<String, String>,
    #[serde(default)]
    pub infer_errors: BTreeMap<String, String>,
    #[serde(default)]
    pub verifier_failures: BTreeMap<String, String>,
    #[serde(default)]
    pub verifier_out_of_envelope: BTreeMap<String, EffectRow>,
    #[serde(default)]
    pub act_scenarios: BTreeMap<String, String>,
    #[serde(default)]
    pub act_custom_writes: BTreeMap<String, Vec<(String, Value)>>,
    #[serde(default)]
    pub toctou_hook_bumps: BTreeMap<String, (String, Value, u64)>,
    #[serde(default)]
    pub initial_world: Option<WorldState>,
    #[serde(default)]
    pub initial_facts: Option<Vec<Fact>>,
    #[serde(default)]
    pub registry: Option<RegistrySnapshot>,
    #[serde(default)]
    pub mutations: crate::lowering::CompilerMutations,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConformanceObservationV0 {
    pub status: String,
    pub return_val: Option<Value>,
    pub effects: Vec<String>,
    pub active_facts: Vec<Fact>,
    pub latent_facts: BTreeMap<String, LatentPostconditions>,
    pub types: BTreeMap<String, String>,
    pub bindings: BTreeMap<String, Value>,
    pub lineage: BTreeMap<String, Vec<String>>,
    pub diagnostics: Vec<Diagnostic>,
    #[serde(default)]
    pub mutation_trace: Vec<(String, Value, u64)>,
    #[serde(default)]
    pub final_world: Option<BTreeMap<String, (Value, u64)>>,
}
