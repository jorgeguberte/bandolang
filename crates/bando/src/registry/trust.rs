use std::collections::{BTreeMap, BTreeSet};
use serde::{Deserialize, Serialize};

use super::verifier::VerifierId;

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct TrustPolicy {
    pub trusted_issuers: BTreeMap<String, BTreeSet<VerifierId>>,
}

impl TrustPolicy {
    pub fn new() -> Self {
        Self {
            trusted_issuers: BTreeMap::new(),
        }
    }

    pub fn trust_verifier(&mut self, predicate: impl Into<String>, verifier: VerifierId) {
        self.trusted_issuers
            .entry(predicate.into())
            .or_default()
            .insert(verifier);
    }

    pub fn is_trusted(&self, predicate: &str, verifier: &VerifierId) -> bool {
        if let Some(set) = self.trusted_issuers.get(predicate) {
            set.contains(verifier)
        } else {
            false
        }
    }
}
