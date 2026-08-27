use serde::{Deserialize, Serialize};

use super::agent::AgentId;
use crate::ir::{effects::EffectRow, types::Type};

#[derive(Debug, Clone, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
pub struct IntentId(pub String);

impl IntentId {
    pub fn new(id: impl Into<String>) -> Self {
        Self(id.into())
    }
}

impl std::fmt::Display for IntentId {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.0)
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IntentInvocationDescriptor {
    pub intent_id: IntentId,
    pub target_agent_id: AgentId,
    pub input_types: Vec<Type>,
    pub output_type: Type,
    pub error_type: Type,
    pub child_effects: EffectRow,
    pub exported_envelope: EffectRow,
    pub declared_envelope: EffectRow,
    #[serde(default = "default_authority_policy")]
    pub authority_policy: String,
}

fn default_authority_policy() -> String {
    "AllowGrant".to_string()
}

impl IntentInvocationDescriptor {
    pub fn new(
        intent_id: IntentId,
        target_agent_id: AgentId,
        input_types: Vec<Type>,
        output_type: Type,
        error_type: Type,
        child_effects: EffectRow,
        exported_envelope: EffectRow,
        declared_envelope: EffectRow,
    ) -> Self {
        Self {
            intent_id,
            target_agent_id,
            input_types,
            output_type,
            error_type,
            child_effects,
            exported_envelope,
            declared_envelope,
            authority_policy: default_authority_policy(),
        }
    }
}
