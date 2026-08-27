use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

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

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct GateResolutionObservation {
    pub op_id: String,
    pub resolution: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct GateCheckObservation {
    pub check_kind: String,
    pub authority_source: String,
    pub effects: Vec<String>,
    pub result: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ChildHandleObservation {
    pub handle_id: String,
    pub child_id: String,
    pub parent_id: String,
    pub generation_token: String,
    pub effects: Vec<String>,
    pub settlement_state: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct FrameBudgetObservation {
    pub available: BTreeMap<String, u64>,
    pub reserved: BTreeMap<String, u64>,
    pub spent: BTreeMap<String, u64>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ChildResultProvenanceObservation {
    pub child_id: String,
    pub intent_id: String,
    pub target_agent_id: String,
    pub result_event_id: String,
    pub is_opaque: bool,
    #[serde(default)]
    pub underlying_refs: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct BeliefObservation {
    pub payload: Value,
    pub owner_agent_id: String,
    pub provenance: Vec<String>,
    pub policy_binding: String,
}

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
    pub initial_budget: Option<BTreeMap<String, u64>>,
    #[serde(default)]
    pub current_agent_id: Option<String>,
    #[serde(default)]
    pub child_scenarios: BTreeMap<String, crate::child::ChildScenarioConfig>,
    #[serde(default)]
    pub simulate_suspension_and_resume: bool,
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
    #[serde(default)]
    pub gate_resolutions: Vec<GateResolutionObservation>,
    #[serde(default)]
    pub gate_trace: Vec<GateCheckObservation>,
    // Slice 3 observables (14-20)
    #[serde(default)]
    pub child_handles: BTreeMap<String, ChildHandleObservation>,
    #[serde(default)]
    pub child_events: Vec<String>,
    #[serde(default)]
    pub frame_ledgers: BTreeMap<String, FrameBudgetObservation>,
    #[serde(default)]
    pub child_effective_authority: BTreeMap<String, Vec<String>>,
    #[serde(default)]
    pub result_provenance: BTreeMap<String, ChildResultProvenanceObservation>,
    #[serde(default)]
    pub beliefs: BTreeMap<String, BeliefObservation>,
    #[serde(default)]
    pub internalization_trace: Vec<GateCheckObservation>,
}
