use std::collections::BTreeSet;
use serde::{Deserialize, Serialize};

use crate::ir::effects::EffectRow;

#[derive(Debug, Clone, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
pub struct OperationId(pub String);

impl OperationId {
    pub fn new(name: impl Into<String>) -> Self {
        Self(name.into())
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
            MutationFootprint::Exact(set) => set.contains(key),
            MutationFootprint::Prefix(pfx) => key.starts_with(pfx),
            MutationFootprint::DomainWide(dom) => dom == target_domain,
            MutationFootprint::Unknown(dom) => dom == target_domain,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum PolicyRequirement {
    RequiresAttestation {
        predicate: String,
        subject_arg_idx: usize,
    },
    RequiresStateBase {
        key: String,
        expected_version: u64,
    },
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
