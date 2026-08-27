use std::collections::BTreeMap;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
pub enum FactArg {
    Symbol(String),
    Literal(String),
}

#[derive(Debug, Clone, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
pub struct Fact {
    pub predicate: String,
    pub args: Vec<FactArg>,
}

impl Fact {
    pub fn new(predicate: impl Into<String>, args: Vec<FactArg>) -> Self {
        Self {
            predicate: predicate.into(),
            args,
        }
    }

    pub fn rename(&self, mapping: &BTreeMap<String, String>) -> Self {
        let new_args = self
            .args
            .iter()
            .map(|arg| match arg {
                FactArg::Symbol(sym) => {
                    if let Some(new_sym) = mapping.get(sym) {
                        FactArg::Symbol(new_sym.clone())
                    } else {
                        FactArg::Symbol(sym.clone())
                    }
                }
                FactArg::Literal(lit) => FactArg::Literal(lit.clone()),
            })
            .collect();
        Self {
            predicate: self.predicate.clone(),
            args: new_args,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
pub struct FactTemplate {
    pub predicate: String,
    pub args: Vec<FactArg>,
}

impl FactTemplate {
    pub fn instantiate(&self, binding: &BTreeMap<String, String>) -> Fact {
        let args = self
            .args
            .iter()
            .map(|arg| match arg {
                FactArg::Symbol(formal) => {
                    if let Some(actual) = binding.get(formal) {
                        FactArg::Symbol(actual.clone())
                    } else {
                        FactArg::Symbol(formal.clone())
                    }
                }
                FactArg::Literal(lit) => FactArg::Literal(lit.clone()),
            })
            .collect();
        Fact {
            predicate: self.predicate.clone(),
            args,
        }
    }
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct LatentPostconditions {
    pub on_ok: Vec<FactTemplate>,
    pub on_err: Vec<FactTemplate>,
}

impl LatentPostconditions {
    pub fn empty() -> Self {
        Self::default()
    }

    pub fn instantiate_ok(&self, bound_var: &str) -> Vec<Fact> {
        let mut binding = BTreeMap::new();
        binding.insert("$value".to_string(), bound_var.to_string());
        self.on_ok.iter().map(|tmpl| tmpl.instantiate(&binding)).collect()
    }

    pub fn instantiate_err(&self, bound_var: &str) -> Vec<Fact> {
        let mut binding = BTreeMap::new();
        binding.insert("$error".to_string(), bound_var.to_string());
        self.on_err.iter().map(|tmpl| tmpl.instantiate(&binding)).collect()
    }
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct ActLatentPostconditions {
    pub on_success: Vec<FactTemplate>,
    pub on_failure: Vec<FactTemplate>,
    pub on_partial: Vec<FactTemplate>,
}

impl ActLatentPostconditions {
    pub fn instantiate_success(&self, bound_var: &str) -> Vec<Fact> {
        let mut binding = BTreeMap::new();
        binding.insert("$value".to_string(), bound_var.to_string());
        self.on_success.iter().map(|tmpl| tmpl.instantiate(&binding)).collect()
    }

    pub fn instantiate_failure(&self, bound_var: &str) -> Vec<Fact> {
        let mut binding = BTreeMap::new();
        binding.insert("$error".to_string(), bound_var.to_string());
        self.on_failure.iter().map(|tmpl| tmpl.instantiate(&binding)).collect()
    }

    pub fn instantiate_partial(&self, bound_var: &str) -> Vec<Fact> {
        let mut binding = BTreeMap::new();
        binding.insert("$report".to_string(), bound_var.to_string());
        self.on_partial.iter().map(|tmpl| tmpl.instantiate(&binding)).collect()
    }
}
