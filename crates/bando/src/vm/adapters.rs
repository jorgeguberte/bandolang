use std::collections::BTreeMap;
use crate::{
    ir::{
        effects::EffectRow,
        values::{PartialEffectReport, Value as VmValue},
    },
    registry::{AtomicityGuarantee, MutationFootprint, OperationId, VerifierId},
    world::WorldState,
};

pub trait ReadAdapter: Send + Sync {
    fn read(&self, domain: &str) -> Result<VmValue, VmValue>;
}

pub trait InferAdapter: Send + Sync {
    fn infer(&self, prompt: &str) -> Result<VmValue, VmValue>;
}

pub trait VerifierAdapter: Send + Sync {
    fn verify(
        &self,
        verifier_id: &VerifierId,
        subject: &VmValue,
        effect_envelope: &EffectRow,
    ) -> Result<VmValue, String>;
}

pub trait ActAdapter: Send + Sync {
    fn execute_act(
        &self,
        op_id: &OperationId,
        args: &[VmValue],
        footprint: &MutationFootprint,
        world: &mut WorldState,
        atomicity: AtomicityGuarantee,
        witness_version: Option<u64>,
    ) -> VmValue;
}

#[derive(Default)]
pub struct DefaultTestReadAdapter {
    pub errors: BTreeMap<String, String>,
}

impl ReadAdapter for DefaultTestReadAdapter {
    fn read(&self, domain: &str) -> Result<VmValue, VmValue> {
        if let Some(err) = self.errors.get(domain) {
            Err(VmValue::String(err.clone()))
        } else {
            Ok(VmValue::String(format!("data_of({})", domain)))
        }
    }
}

#[derive(Default)]
pub struct DefaultTestInferAdapter {
    pub errors: BTreeMap<String, String>,
}

impl InferAdapter for DefaultTestInferAdapter {
    fn infer(&self, prompt: &str) -> Result<VmValue, VmValue> {
        if let Some(err) = self.errors.get(prompt) {
            Err(VmValue::String(err.clone()))
        } else {
            Ok(VmValue::String(format!("infer_of({})", prompt)))
        }
    }
}

#[derive(Default)]
pub struct DefaultTestVerifierAdapter {
    pub failures: BTreeMap<String, String>,
    pub out_of_envelope_attempts: BTreeMap<String, EffectRow>,
}

impl VerifierAdapter for DefaultTestVerifierAdapter {
    fn verify(
        &self,
        verifier_id: &VerifierId,
        subject: &VmValue,
        effect_envelope: &EffectRow,
    ) -> Result<VmValue, String> {
        // Check for simulated out of envelope attempt (Rule #4, S2M01)
        if let Some(attempted) = self.out_of_envelope_attempts.get(&verifier_id.0) {
            if !attempted.is_subset(effect_envelope) {
                return Err(format!(
                    "ConfinementViolation: verifier {:?} attempted effects {:?} exceeding envelope {:?}",
                    verifier_id, attempted, effect_envelope
                ));
            }
        }

        if let Some(err) = self.failures.get(&verifier_id.0) {
            Err(err.clone())
        } else {
            // Emits valid Attestation
            Ok(VmValue::attestation(
                "PassesAudit",
                subject.clone(),
                verifier_id.0.clone(),
                "v1.0.0",
                "tok_valid",
            ))
        }
    }
}

#[derive(Default)]
pub struct DefaultTestActAdapter {
    pub scenarios: BTreeMap<String, String>,
    pub custom_writes: BTreeMap<String, Vec<(String, VmValue)>>,
}

impl ActAdapter for DefaultTestActAdapter {
    fn execute_act(
        &self,
        op_id: &OperationId,
        _args: &[VmValue],
        footprint: &MutationFootprint,
        world: &mut WorldState,
        atomicity: AtomicityGuarantee,
        witness_version: Option<u64>,
    ) -> VmValue {
        let scenario = self.scenarios.get(&op_id.0).map(|s| s.as_str()).unwrap_or("success");

        match scenario {
            "clean_failure" => VmValue::act_failure(VmValue::String("action_failed".to_string())),
            "partial_legitimate" => {
                let writes = self.custom_writes.get(&op_id.0).cloned().unwrap_or_else(|| {
                    vec![("workspace/part1".to_string(), VmValue::String("val1".to_string()))]
                });
                let _ = world.commit_writes(footprint, "workspace", &writes, witness_version);
                VmValue::ActPartial(PartialEffectReport {
                    op_id: op_id.0.clone(),
                    confirmed_applied: vec!["workspace/part1".to_string()],
                    confirmed_not_applied: vec!["workspace/part2".to_string()],
                    receipt_id: "rcpt_part_1".to_string(),
                    error: Some("network_drop".to_string()),
                })
            }
            "atomic_yielding_partial" => {
                if atomicity == AtomicityGuarantee::Atomic {
                    // Rule #24: Atomic adapter yielding partial => ProtocolViolation!
                    VmValue::String("PROTOCOL_VIOLATION_ATOMIC_PARTIAL".to_string())
                } else {
                    VmValue::ActPartial(PartialEffectReport {
                        op_id: op_id.0.clone(),
                        confirmed_applied: vec!["workspace/part1".to_string()],
                        confirmed_not_applied: vec![],
                        receipt_id: "rcpt_part".to_string(),
                        error: None,
                    })
                }
            }
            "delivery_unknown" => VmValue::DeliveryUnknown("transport_timeout".to_string()),
            "settlement_unknown" => VmValue::SettlementUnknown("ledger_unreachable".to_string()),
            "out_of_footprint_attempt" => {
                // Tries to write to an unauthorized key outside footprint
                let writes = vec![("forbidden_zone/secret".to_string(), VmValue::String("evil".to_string()))];
                match world.commit_writes(footprint, "workspace", &writes, witness_version) {
                    Ok(_) => VmValue::act_success(VmValue::String("unauthorized_success".to_string())),
                    Err(crate::world::WorldError::FootprintViolation(_)) => {
                        VmValue::act_failure(VmValue::String("FootprintViolation".to_string()))
                    }
                    Err(_) => VmValue::act_failure(VmValue::String("CommitError".to_string())),
                }
            }
            _ => {
                // Success path
                let writes = self.custom_writes.get(&op_id.0).cloned().unwrap_or_else(|| {
                    vec![("workspace/doc1".to_string(), VmValue::String("updated_data".to_string()))]
                });
                match world.commit_writes(footprint, "workspace", &writes, witness_version) {
                    Ok(_) => VmValue::act_success(VmValue::String("act_success_ok".to_string())),
                    Err(crate::world::WorldError::ToctouViolation { .. }) => {
                        VmValue::act_failure(VmValue::String("ToctouViolation".to_string()))
                    }
                    Err(crate::world::WorldError::FootprintViolation(_)) => {
                        VmValue::act_failure(VmValue::String("FootprintViolation".to_string()))
                    }
                }
            }
        }
    }
}

pub struct RuntimeAdapters {
    pub read: Box<dyn ReadAdapter>,
    pub infer: Box<dyn InferAdapter>,
    pub verifier: Box<dyn VerifierAdapter>,
    pub act: Box<dyn ActAdapter>,
}

impl Default for RuntimeAdapters {
    fn default() -> Self {
        Self {
            read: Box::new(DefaultTestReadAdapter::default()),
            infer: Box::new(DefaultTestInferAdapter::default()),
            verifier: Box::new(DefaultTestVerifierAdapter::default()),
            act: Box::new(DefaultTestActAdapter::default()),
        }
    }
}
