use serde::{Deserialize, Serialize};

use crate::ir::{effects::EffectRow, types::Type};

#[derive(Debug, Clone, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
pub struct VerifierId(pub String);

impl VerifierId {
    pub fn new(name: impl Into<String>) -> Self {
        Self(name.into())
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct VerifierDescriptor {
    pub verifier_id: VerifierId,
    pub version: String,
    pub effect_envelope: EffectRow,
    pub output_predicate: String,
    pub subject_type: Type,
}

impl VerifierDescriptor {
    pub fn new(
        verifier_id: VerifierId,
        version: impl Into<String>,
        effect_envelope: EffectRow,
        output_predicate: impl Into<String>,
        subject_type: Type,
    ) -> Self {
        Self {
            verifier_id,
            version: version.into(),
            effect_envelope,
            output_predicate: output_predicate.into(),
            subject_type,
        }
    }
}
