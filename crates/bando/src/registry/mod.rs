pub mod agent;
pub mod intent;
pub mod internalization;
pub mod operation;
pub mod trust;
pub mod verifier;

use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};

use crate::ir::effects::Effect;

pub use agent::{AgentDescriptor, AgentId};
pub use intent::{IntentId, IntentInvocationDescriptor};
pub use internalization::{ClaimContract, InternalizationPolicyDescriptor, PolicyId};
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
    #[serde(default)]
    pub verifiers: BTreeMap<VerifierId, VerifierDescriptor>,
    #[serde(default)]
    pub operations: BTreeMap<OperationId, OperationDescriptor>,
    #[serde(default)]
    pub agents: BTreeMap<AgentId, AgentDescriptor>,
    #[serde(default)]
    pub intents: BTreeMap<IntentId, IntentInvocationDescriptor>,
    #[serde(default)]
    pub internalization_policies: BTreeMap<PolicyId, InternalizationPolicyDescriptor>,
    #[serde(default)]
    pub trust_policy: TrustPolicy,
    #[serde(default)]
    pub caller_authority: Option<CallerAuthority>,
    #[serde(default)]
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
        self.operations.insert(descriptor.op_id.clone(), descriptor);
    }

    pub fn register_agent(&mut self, descriptor: AgentDescriptor) {
        self.agents.insert(descriptor.agent_id.clone(), descriptor);
    }

    pub fn register_intent(&mut self, descriptor: IntentInvocationDescriptor) {
        self.intents
            .insert(descriptor.intent_id.clone(), descriptor);
    }

    pub fn register_internalization_policy(&mut self, descriptor: InternalizationPolicyDescriptor) {
        self.internalization_policies
            .insert(descriptor.policy_id.clone(), descriptor);
    }
}
