use std::collections::BTreeMap;
use serde::{Deserialize, Serialize};

use crate::{
    diagnostics::Diagnostic,
    ir::{
        facts::{Fact, LatentPostconditions},
        values::Value,
        Module,
    },
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
}
