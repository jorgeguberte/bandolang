use std::collections::BTreeSet;
use serde::{Deserialize, Serialize};

use crate::ir::effects::EffectRow;

#[derive(Debug, Clone, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
pub struct OperationId(pub String);

impl OperationId {
    pub fn new(id: impl Into<String>) -> Self {
        Self(id.into())
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum AtomicityGuarantee {
    Atomic,
    MayPartiallyComplete,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum MutationFootprint {
    Exact(BTreeSet<String>),
    Prefix(String),
    DomainWide(String),
    Unknown(String),
}

impl MutationFootprint {
    pub fn contains_write(&self, target_domain: &str, key: &str) -> bool {
        match self {
            MutationFootprint::Exact(keys) => keys.contains(key),
            MutationFootprint::Prefix(prefix) => key.starts_with(prefix),
            MutationFootprint::DomainWide(domain) => domain == target_domain,
            MutationFootprint::Unknown(domain) => domain == target_domain,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum PolicyRequirement {
    RequiresAttestation {
        predicate: String,
        subject_arg_idx: usize,
    },
    RequiresStateBase {
        key: String,
        expected_version: u64,
    },
    RequiresStaticProof {
        predicate: String,
        subject_arg_idx: usize,
    },
}

impl PolicyRequirement {
    pub fn required_gate_effects(&self) -> Vec<crate::ir::effects::Effect> {
        match self {
            PolicyRequirement::RequiresAttestation { .. } => {
                vec![crate::ir::effects::Effect::Read("trust_store".to_string())]
            }
            PolicyRequirement::RequiresStateBase { key: _, .. } => {
                vec![crate::ir::effects::Effect::Read("state_base".to_string())]
            }
            PolicyRequirement::RequiresStaticProof { .. } => Vec::new(),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct OperationDescriptor {
    pub op_id: OperationId,
    pub target_domain: String,
    pub declared_envelope: EffectRow,
    pub declared_footprint: MutationFootprint,
    pub atomicity: AtomicityGuarantee,
    pub requirements: Vec<PolicyRequirement>,
}

impl OperationDescriptor {
    pub fn new(
        op_id: OperationId,
        target_domain: impl Into<String>,
        declared_envelope: EffectRow,
        declared_footprint: MutationFootprint,
        atomicity: AtomicityGuarantee,
        requirements: Vec<PolicyRequirement>,
    ) -> Self {
        Self {
            op_id,
            target_domain: target_domain.into(),
            declared_envelope,
            declared_footprint,
            atomicity,
            requirements,
        }
    }
}
