use serde::{Deserialize, Serialize};

use crate::ir::effects::EffectRow;

#[derive(Debug, Clone, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
pub struct PolicyId(pub String);

impl PolicyId {
    pub fn new(id: impl Into<String>) -> Self {
        Self(id.into())
    }
}

impl std::fmt::Display for PolicyId {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.0)
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum ClaimContract {
    AcceptAll,
    AcceptPredicate(String),
    AcceptSubjectLiteral(String),
    RejectAll,
}

impl Default for ClaimContract {
    fn default() -> Self {
        ClaimContract::AcceptAll
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct InternalizationPolicyDescriptor {
    pub policy_id: PolicyId,
    pub accepted_claim_contract: ClaimContract,
    #[serde(default)]
    pub validation_requirements: Vec<String>,
    #[serde(default)]
    pub validation_effect_envelope: EffectRow,
}

impl InternalizationPolicyDescriptor {
    pub fn new(
        policy_id: PolicyId,
        accepted_claim_contract: ClaimContract,
        validation_requirements: Vec<String>,
        validation_effect_envelope: EffectRow,
    ) -> Self {
        Self {
            policy_id,
            accepted_claim_contract,
            validation_requirements,
            validation_effect_envelope,
        }
    }
}
