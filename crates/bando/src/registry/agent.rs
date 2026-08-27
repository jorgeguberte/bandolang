use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;

use crate::ir::effects::Effect;

#[derive(Debug, Clone, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
pub struct AgentId(pub String);

impl AgentId {
    pub fn new(id: impl Into<String>) -> Self {
        Self(id.into())
    }
}

impl std::fmt::Display for AgentId {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.0)
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct AgentDescriptor {
    pub agent_id: AgentId,
    pub native_authority: BTreeSet<Effect>,
}

impl AgentDescriptor {
    pub fn new(agent_id: AgentId, native_authority: impl IntoIterator<Item = Effect>) -> Self {
        Self {
            agent_id,
            native_authority: native_authority.into_iter().collect(),
        }
    }
}
