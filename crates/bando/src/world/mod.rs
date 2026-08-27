use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

use crate::{ir::values::Value, registry::MutationFootprint};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum WorldError {
    FootprintViolation(String),
    ToctouViolation {
        key: String,
        expected: u64,
        actual: u64,
    },
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct WorldState {
    pub storage: BTreeMap<String, (Value, u64)>,
    pub mutation_trace: Vec<(String, Value, u64)>,
}

impl WorldState {
    pub fn new() -> Self {
        Self {
            storage: BTreeMap::new(),
            mutation_trace: Vec::new(),
        }
    }

    pub fn set_initial(&mut self, key: impl Into<String>, val: Value, version: u64) {
        self.storage.insert(key.into(), (val, version));
    }

    pub fn get(&self, key: &str) -> Option<(&Value, u64)> {
        self.storage.get(key).map(|(v, ver)| (v, *ver))
    }

    pub fn commit_writes(
        &mut self,
        footprint: &MutationFootprint,
        target_domain: &str,
        writes: &[(String, Value)],
        witness_version: Option<u64>,
    ) -> Result<(), WorldError> {
        // 1. Footprint enforcement (Rule #18)
        for (key, _) in writes {
            if !footprint.contains_write(target_domain, key) {
                return Err(WorldError::FootprintViolation(key.clone()));
            }
        }

        // 2. TOCTOU state base version check (Rule #14)
        if let Some(expected_ver) = witness_version {
            for (key, _) in writes {
                if let Some((_, actual_ver)) = self.storage.get(key) {
                    if *actual_ver != expected_ver {
                        return Err(WorldError::ToctouViolation {
                            key: key.clone(),
                            expected: expected_ver,
                            actual: *actual_ver,
                        });
                    }
                }
            }
        }

        // 3. Apply writes atomically
        for (key, val) in writes {
            let next_ver = self.storage.get(key).map(|(_, ver)| ver + 1).unwrap_or(1);
            self.storage.insert(key.clone(), (val.clone(), next_ver));
            self.mutation_trace
                .push((key.clone(), val.clone(), next_ver));
        }

        Ok(())
    }
}
