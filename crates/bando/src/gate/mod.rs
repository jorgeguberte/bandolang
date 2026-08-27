use serde::{Deserialize, Serialize};

use crate::{
    conformance::schema::GateCheckObservation,
    ir::{effects::Effect, values::Value},
    registry::{
        AuthoritySource, CallerAuthority, PolicyRequirement, TrustPolicy, TrustedRuntimeAuthority,
        VerifierId,
    },
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

impl DeferredCheck {
    pub fn required_effects(&self) -> Vec<Effect> {
        match self {
            DeferredCheck::CheckSubjectBinding { .. } => Vec::new(),
            DeferredCheck::CheckTrustPolicy { .. } => vec![Effect::Read("trust_store".to_string())],
            DeferredCheck::CheckStateBaseVersion { .. } => {
                vec![Effect::Read("state_base".to_string())]
            }
        }
    }

    pub fn authority_source(&self) -> AuthoritySource {
        match self {
            DeferredCheck::CheckSubjectBinding { .. } => AuthoritySource::Caller,
            DeferredCheck::CheckTrustPolicy { .. } => AuthoritySource::TrustedRuntime,
            DeferredCheck::CheckStateBaseVersion { .. } => AuthoritySource::TrustedRuntime,
        }
    }
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
    AuthorityInsufficient(String),
    GateRejected(String),
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct GateEvaluationOutput {
    pub witness: Result<GateWitness, GateError>,
    pub trace: Vec<GateCheckObservation>,
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
                PolicyRequirement::RequiresStaticProof {
                    predicate,
                    subject_arg_idx,
                } => {
                    let matching_evidence = evidence.iter().find_map(|v| match v {
                        Value::Attestation {
                            predicate: p,
                            subject,
                            ..
                        } => {
                            if p == predicate {
                                Some(subject.clone())
                            } else {
                                None
                            }
                        }
                        Value::Ok(inner) => match inner.as_ref() {
                            Value::Attestation {
                                predicate: p,
                                subject,
                                ..
                            } => {
                                if p == predicate {
                                    Some(subject.clone())
                                } else {
                                    None
                                }
                            }
                            _ => None,
                        },
                        _ => None,
                    });

                    match matching_evidence {
                        Some(subject) => {
                            let subject_val =
                                args.get(*subject_arg_idx).cloned().unwrap_or(Value::Unit);
                            if subject.as_ref() == &subject_val {
                                // Statically proved!
                                continue;
                            } else {
                                // Statically refuted by contradictory subject
                                return RequirementResolution::Refuted;
                            }
                        }
                        None => return RequirementResolution::Uncovered,
                    }
                }
                PolicyRequirement::RequiresAttestation {
                    predicate,
                    subject_arg_idx,
                } => {
                    let matching_attestation = evidence.iter().find_map(|v| match v {
                        Value::Attestation {
                            predicate: p,
                            subject,
                            issuer,
                            ..
                        } => {
                            if p == predicate {
                                Some((p.clone(), subject.clone(), issuer.clone()))
                            } else {
                                None
                            }
                        }
                        Value::Ok(inner) => match inner.as_ref() {
                            Value::Attestation {
                                predicate: p,
                                subject,
                                issuer,
                                ..
                            } => {
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
                            let subject_val =
                                args.get(*subject_arg_idx).cloned().unwrap_or(Value::Unit);
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
                PolicyRequirement::RequiresStateBase {
                    key,
                    expected_version,
                } => {
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
        caller_authority: Option<&CallerAuthority>,
        runtime_authority: Option<&TrustedRuntimeAuthority>,
        require_caller_authority_for_all: bool,
    ) -> GateEvaluationOutput {
        let mut witness_version = None;
        let executed_effects = gate_effects.to_vec();
        let mut trace = Vec::new();

        for check in checks {
            let required_effects = check.required_effects();
            let source = check.authority_source();

            let check_name = match check {
                DeferredCheck::CheckSubjectBinding { .. } => "CheckSubjectBinding",
                DeferredCheck::CheckTrustPolicy { .. } => "CheckTrustPolicy",
                DeferredCheck::CheckStateBaseVersion { .. } => "CheckStateBaseVersion",
            };
            let auth_name = match source {
                AuthoritySource::Caller => "Caller",
                AuthoritySource::TrustedRuntime => "TrustedRuntime",
            };
            let eff_strings: Vec<String> = required_effects.iter().map(|e| e.to_string()).collect();

            // Authority check (Rule #10, Rule #17)
            match source {
                AuthoritySource::Caller => {
                    if let Some(ca) = caller_authority {
                        if !ca.covers(&required_effects) {
                            trace.push(GateCheckObservation {
                                check_kind: check_name.to_string(),
                                authority_source: auth_name.to_string(),
                                effects: eff_strings,
                                result: "Fail".to_string(),
                            });
                            return GateEvaluationOutput {
                                witness: Err(GateError::AuthorityInsufficient(
                                    "Caller lacks authority for check".to_string(),
                                )),
                                trace,
                            };
                        }
                    } else {
                        trace.push(GateCheckObservation {
                            check_kind: check_name.to_string(),
                            authority_source: auth_name.to_string(),
                            effects: eff_strings,
                            result: "Fail".to_string(),
                        });
                        return GateEvaluationOutput {
                            witness: Err(GateError::AuthorityInsufficient(
                                "Caller authority absent".to_string(),
                            )),
                            trace,
                        };
                    }
                }
                AuthoritySource::TrustedRuntime => {
                    if require_caller_authority_for_all {
                        // S2M07 mutation: falsely requires caller authority for trusted gate check!
                        if let Some(ca) = caller_authority {
                            if !ca.covers(&required_effects) {
                                trace.push(GateCheckObservation {
                                    check_kind: check_name.to_string(),
                                    authority_source: auth_name.to_string(),
                                    effects: eff_strings,
                                    result: "Fail".to_string(),
                                });
                                return GateEvaluationOutput {
                                    witness: Err(GateError::AuthorityInsufficient(
                                        "S2M07: Caller lacks authority for trusted check"
                                            .to_string(),
                                    )),
                                    trace,
                                };
                            }
                        } else {
                            trace.push(GateCheckObservation {
                                check_kind: check_name.to_string(),
                                authority_source: auth_name.to_string(),
                                effects: eff_strings,
                                result: "Fail".to_string(),
                            });
                            return GateEvaluationOutput {
                                witness: Err(GateError::AuthorityInsufficient(
                                    "Caller authority absent for S2M07 check".to_string(),
                                )),
                                trace,
                            };
                        }
                    } else {
                        // Baseline: trusted runtime authority covers the check
                        if let Some(ra) = runtime_authority {
                            if !ra.covers(&required_effects) {
                                trace.push(GateCheckObservation {
                                    check_kind: check_name.to_string(),
                                    authority_source: auth_name.to_string(),
                                    effects: eff_strings,
                                    result: "Fail".to_string(),
                                });
                                return GateEvaluationOutput {
                                    witness: Err(GateError::AuthorityInsufficient(
                                        "Runtime lacks authority for check".to_string(),
                                    )),
                                    trace,
                                };
                            }
                        } else {
                            trace.push(GateCheckObservation {
                                check_kind: check_name.to_string(),
                                authority_source: auth_name.to_string(),
                                effects: eff_strings,
                                result: "Fail".to_string(),
                            });
                            return GateEvaluationOutput {
                                witness: Err(GateError::AuthorityInsufficient(
                                    "Runtime authority absent".to_string(),
                                )),
                                trace,
                            };
                        }
                    }
                }
            }

            match check {
                DeferredCheck::CheckSubjectBinding {
                    expected_subject,
                    attestation_subject,
                } => {
                    if expected_subject != attestation_subject {
                        trace.push(GateCheckObservation {
                            check_kind: check_name.to_string(),
                            authority_source: auth_name.to_string(),
                            effects: eff_strings,
                            result: "Fail".to_string(),
                        });
                        return GateEvaluationOutput {
                            witness: Err(GateError::SubjectMismatch),
                            trace,
                        };
                    }
                }
                DeferredCheck::CheckTrustPolicy { predicate, issuer } => {
                    if !trust_policy.is_trusted(predicate, issuer) {
                        trace.push(GateCheckObservation {
                            check_kind: check_name.to_string(),
                            authority_source: auth_name.to_string(),
                            effects: eff_strings,
                            result: "Fail".to_string(),
                        });
                        return GateEvaluationOutput {
                            witness: Err(GateError::UntrustedIssuer(issuer.0.clone())),
                            trace,
                        };
                    }
                }
                DeferredCheck::CheckStateBaseVersion {
                    key,
                    expected_version,
                } => {
                    let actual_ver = world.get(key).map(|(_, v)| v).unwrap_or(0);
                    if actual_ver != *expected_version {
                        trace.push(GateCheckObservation {
                            check_kind: check_name.to_string(),
                            authority_source: auth_name.to_string(),
                            effects: eff_strings,
                            result: "Fail".to_string(),
                        });
                        return GateEvaluationOutput {
                            witness: Err(GateError::BaseVersionMismatch),
                            trace,
                        };
                    }
                    witness_version = Some(actual_ver);
                }
            }

            trace.push(GateCheckObservation {
                check_kind: check_name.to_string(),
                authority_source: auth_name.to_string(),
                effects: eff_strings,
                result: "Pass".to_string(),
            });
        }

        GateEvaluationOutput {
            witness: Ok(GateWitness {
                observed_state_version: witness_version,
                gate_effects_executed: executed_effects,
            }),
            trace,
        }
    }
}
