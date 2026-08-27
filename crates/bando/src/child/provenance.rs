use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ChildResultProvenance {
    pub child_id: String,
    pub intent_id: String,
    pub target_agent_id: String,
    pub result_event_id: String,
    pub is_opaque: bool,
    #[serde(default)]
    pub underlying_refs: Vec<String>,
}

impl ChildResultProvenance {
    pub fn new(
        child_id: impl Into<String>,
        intent_id: impl Into<String>,
        target_agent_id: impl Into<String>,
        result_event_id: impl Into<String>,
    ) -> Self {
        Self {
            child_id: child_id.into(),
            intent_id: intent_id.into(),
            target_agent_id: target_agent_id.into(),
            result_event_id: result_event_id.into(),
            is_opaque: false,
            underlying_refs: Vec::new(),
        }
    }

    pub fn opaque(child_id: impl Into<String>, intent_id: impl Into<String>) -> Self {
        Self {
            child_id: child_id.into(),
            intent_id: intent_id.into(),
            target_agent_id: "opaque_agent".to_string(),
            result_event_id: "evt_opaque".to_string(),
            is_opaque: true,
            underlying_refs: Vec::new(),
        }
    }
}
