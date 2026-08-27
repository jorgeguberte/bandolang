pub mod operation;
pub mod trust;
pub mod verifier;

use std::collections::{BTreeMap, BTreeSet};
use serde::{Deserialize, Serialize};

use crate::ir::effects::Effect;

pub use operation::{
    AtomicityGuarantee, MutationFootprint, OperationDescriptor, OperationId, PolicyRequirement,
};
pub use trust::TrustPolicy;
pub use verifier::{VerifierDescriptor, VerifierId};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum AuthoritySource {
    Caller,
    TrustedRuntime,
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct CallerAuthority {
    pub effects: BTreeSet<Effect>,
}

impl CallerAuthority {
    pub fn contains(&self, effect: &Effect) -> bool {
        self.effects.contains(effect)
    }

    pub fn covers(&self, effects: &[Effect]) -> bool {
        effects.iter().all(|e| self.contains(e))
    }
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct TrustedRuntimeAuthority {
    pub effects: BTreeSet<Effect>,
}

impl TrustedRuntimeAuthority {
    pub fn contains(&self, effect: &Effect) -> bool {
        self.effects.contains(effect)
    }

    pub fn covers(&self, effects: &[Effect]) -> bool {
        effects.iter().all(|e| self.contains(e))
    }
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct RegistrySnapshot {
    pub verifiers: BTreeMap<VerifierId, VerifierDescriptor>,
    pub operations: BTreeMap<OperationId, OperationDescriptor>,
    pub trust_policy: TrustPolicy,
    pub caller_authority: Option<CallerAuthority>,
    pub runtime_authority: Option<TrustedRuntimeAuthority>,
}

impl RegistrySnapshot {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn register_verifier(&mut self, descriptor: VerifierDescriptor) {
        self.verifiers
            .insert(descriptor.verifier_id.clone(), descriptor);
    }

    pub fn register_operation(&mut self, descriptor: OperationDescriptor) {
        self.operations
            .insert(descriptor.op_id.clone(), descriptor);
    }
}
