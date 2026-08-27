pub mod operation;
pub mod trust;
pub mod verifier;

use std::collections::BTreeMap;
use serde::{Deserialize, Serialize};

pub use operation::{AtomicityGuarantee, MutationFootprint, OperationDescriptor, OperationId, PolicyRequirement};
pub use trust::TrustPolicy;
pub use verifier::{VerifierDescriptor, VerifierId};

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct RegistrySnapshot {
    pub verifiers: BTreeMap<VerifierId, VerifierDescriptor>,
    pub operations: BTreeMap<OperationId, OperationDescriptor>,
    pub trust_policy: TrustPolicy,
}

impl RegistrySnapshot {
    pub fn new() -> Self {
        Self {
            verifiers: BTreeMap::new(),
            operations: BTreeMap::new(),
            trust_policy: TrustPolicy::new(),
        }
    }

    pub fn register_verifier(&mut self, descriptor: VerifierDescriptor) {
        self.verifiers.insert(descriptor.verifier_id.clone(), descriptor);
    }

    pub fn register_operation(&mut self, descriptor: OperationDescriptor) {
        self.operations.insert(descriptor.op_id.clone(), descriptor);
    }
}
