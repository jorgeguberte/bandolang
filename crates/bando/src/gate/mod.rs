use serde::{Deserialize, Serialize};

use crate::{
    ir::values::Value,
    registry::{PolicyRequirement, TrustPolicy, VerifierId},
    world::WorldState,
};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum RequirementResolution {
    Proved,
    Deferred(Vec<DeferredCheck>),
    Refuted,
    Uncovered,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum DeferredCheck {
    CheckSubjectBinding {
        expected_subject: Value,
        attestation_subject: Value,
    },
    CheckTrustPolicy {
        predicate: String,
        issuer: VerifierId,
    },
    CheckStateBaseVersion {
        key: String,
        expected_version: u64,
    },
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct GateWitness {
    pub observed_state_version: Option<u64>,
    pub gate_effects_executed: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum GateError {
    SubjectMismatch,
    UntrustedIssuer(String),
    BaseVersionMismatch,
    GateRejected(String),
}

pub struct GateEngine;

impl GateEngine {
    pub fn resolve_requirements(
        requirements: &[PolicyRequirement],
        args: &[Value],
        evidence: &[Value],
    ) -> RequirementResolution {
        if requirements.is_empty() {
            return RequirementResolution::Proved;
        }

        let mut deferred = Vec::new();

        for req in requirements {
            match req {
                PolicyRequirement::RequiresAttestation { predicate, subject_arg_idx } => {
                    let matching_attestation = evidence.iter().find_map(|v| match v {
                        Value::Attestation { predicate: p, subject, issuer, .. } => {
                            if p == predicate {
                                Some((p.clone(), subject.clone(), issuer.clone()))
                            } else {
                                None
                            }
                        }
                        Value::Ok(inner) => match inner.as_ref() {
                            Value::Attestation { predicate: p, subject, issuer, .. } => {
                                if p == predicate {
                                    Some((p.clone(), subject.clone(), issuer.clone()))
                                } else {
                                    None
                                }
                            }
                            _ => None,
                        },
                        _ => None,
                    });

                    match matching_attestation {
                        Some((p, subject, issuer)) => {
                            let subject_val = args.get(*subject_arg_idx).cloned().unwrap_or(Value::Unit);
                            if subject.as_ref() == &subject_val {
                                deferred.push(DeferredCheck::CheckTrustPolicy {
                                    predicate: p,
                                    issuer: VerifierId(issuer),
                                });
                            } else {
                                deferred.push(DeferredCheck::CheckSubjectBinding {
                                    expected_subject: subject_val,
                                    attestation_subject: *subject,
                                });
                                deferred.push(DeferredCheck::CheckTrustPolicy {
                                    predicate: p,
                                    issuer: VerifierId(issuer),
                                });
                            }
                        }
                        None => return RequirementResolution::Uncovered,
                    }
                }
                PolicyRequirement::RequiresStateBase { key, expected_version } => {
                    deferred.push(DeferredCheck::CheckStateBaseVersion {
                        key: key.clone(),
                        expected_version: *expected_version,
                    });
                }
            }
        }

        if deferred.is_empty() {
            RequirementResolution::Proved
        } else {
            RequirementResolution::Deferred(deferred)
        }
    }

    pub fn evaluate_deferred(
        checks: &[DeferredCheck],
        world: &WorldState,
        trust_policy: &TrustPolicy,
        gate_effects: &[String],
    ) -> Result<GateWitness, GateError> {
        let mut witness_version = None;
        let executed_effects = gate_effects.to_vec();

        for check in checks {
            match check {
                DeferredCheck::CheckSubjectBinding { expected_subject, attestation_subject } => {
                    if expected_subject != attestation_subject {
                        return Err(GateError::SubjectMismatch);
                    }
                }
                DeferredCheck::CheckTrustPolicy { predicate, issuer } => {
                    if !trust_policy.is_trusted(predicate, issuer) {
                        return Err(GateError::UntrustedIssuer(issuer.0.clone()));
                    }
                }
                DeferredCheck::CheckStateBaseVersion { key, expected_version } => {
                    let actual_ver = world.get(key).map(|(_, v)| v).unwrap_or(0);
                    if actual_ver != *expected_version {
                        return Err(GateError::BaseVersionMismatch);
                    }
                    witness_version = Some(actual_ver);
                }
            }
        }

        Ok(GateWitness {
            observed_state_version: witness_version,
            gate_effects_executed: executed_effects,
        })
    }
}
