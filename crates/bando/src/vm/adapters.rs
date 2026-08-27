use crate::{
    child::{ChildExecutor, DefaultTestChildExecutor},
    ir::{
        effects::EffectRow,
        values::{PartialEffectReport, Value as VmValue},
    },
    registry::{AtomicityGuarantee, MutationFootprint, OperationId, VerifierDescriptor},
    world::WorldState,
};
use std::collections::BTreeMap;

pub trait ReadAdapter: Send + Sync {
    fn read(&self, domain: &str) -> Result<VmValue, VmValue>;
}

pub trait InferAdapter: Send + Sync {
    fn infer(&self, prompt: &str) -> Result<VmValue, VmValue>;
}

pub trait VerifierAdapter: Send + Sync {
    fn verify(
        &self,
        descriptor: &VerifierDescriptor,
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
        descriptor: &VerifierDescriptor,
        subject: &VmValue,
        effect_envelope: &EffectRow,
    ) -> Result<VmValue, String> {
        // Check for simulated out of envelope attempt (Rule #4, S2M01)
        if let Some(attempted) = self.out_of_envelope_attempts.get(&descriptor.verifier_id.0) {
            if !attempted.is_subset(effect_envelope) {
                return Err(format!(
                    "ConfinementViolation: verifier {:?} attempted effects {:?} exceeding envelope {:?}",
                    descriptor.verifier_id, attempted, effect_envelope
                ));
            }
        }

        if let Some(err) = self.failures.get(&descriptor.verifier_id.0) {
            Err(err.clone())
        } else {
            // Emits valid Attestation bound to trusted descriptor
            Ok(VmValue::attestation(
                descriptor.output_predicate.clone(),
                subject.clone(),
                descriptor.verifier_id.0.clone(),
                descriptor.version.clone(),
                "tok_valid",
            ))
        }
    }
}

#[derive(Default)]
pub struct DefaultTestActAdapter {
    pub scenarios: BTreeMap<String, String>,
    pub custom_writes: BTreeMap<String, Vec<(String, VmValue)>>,
    pub toctou_hook_bumps: BTreeMap<String, (String, VmValue, u64)>,
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
        // TOCTOU deterministic hook: mutates state version before commit
        if let Some((key, val, new_ver)) = self.toctou_hook_bumps.get(&op_id.0) {
            world.storage.insert(key.clone(), (val.clone(), *new_ver));
        }

        let scenario = self
            .scenarios
            .get(&op_id.0)
            .map(|s| s.as_str())
            .unwrap_or("success");

        match scenario {
            "clean_failure" => VmValue::act_failure(VmValue::String("action_failed".to_string())),
            "partial_legitimate" => {
                let writes = self
                    .custom_writes
                    .get(&op_id.0)
                    .cloned()
                    .unwrap_or_else(|| {
                        vec![(
                            "workspace/part1".to_string(),
                            VmValue::String("val1".to_string()),
                        )]
                    });
                let _ = world.commit_writes(footprint, "workspace", &writes, witness_version);
                VmValue::ActPartial(PartialEffectReport {
                    op_id: op_id.0.clone(),
                    confirmed_applied: vec!["workspace/part1".to_string()],
                    confirmed_not_applied: vec!["workspace/part2".to_string()],
                    receipt_id: "rcpt_part_123".to_string(),
                    error: Some("partial_interruption".to_string()),
                })
            }
            "atomic_yielding_partial" => {
                if atomicity == AtomicityGuarantee::Atomic {
                    // Protocol violation (Rule #24, S2M13)
                    VmValue::String("PROTOCOL_VIOLATION_ATOMIC_PARTIAL".to_string())
                } else {
                    VmValue::ActPartial(PartialEffectReport {
                        op_id: op_id.0.clone(),
                        confirmed_applied: vec!["workspace/part1".to_string()],
                        confirmed_not_applied: vec![],
                        receipt_id: "rcpt_part_legit".to_string(),
                        error: None,
                    })
                }
            }
            "delivery_unknown" => VmValue::DeliveryUnknown("transport_timeout".to_string()),
            "settlement_unknown" => VmValue::SettlementUnknown("ledger_unreachable".to_string()),
            "out_of_footprint_attempt" => {
                // Tries to write to an unauthorized key outside footprint
                let writes = vec![(
                    "forbidden_zone/secret".to_string(),
                    VmValue::String("evil".to_string()),
                )];
                match world.commit_writes(footprint, "workspace", &writes, witness_version) {
                    Ok(_) => {
                        VmValue::act_success(VmValue::String("unauthorized_success".to_string()))
                    }
                    Err(crate::world::WorldError::FootprintViolation(_)) => {
                        VmValue::act_failure(VmValue::String("FootprintViolation".to_string()))
                    }
                    Err(_) => VmValue::act_failure(VmValue::String("WorldError".to_string())),
                }
            }
            _ => {
                // Success path
                let writes = self
                    .custom_writes
                    .get(&op_id.0)
                    .cloned()
                    .unwrap_or_else(|| {
                        vec![(
                            "workspace/doc1".to_string(),
                            VmValue::String("updated_data".to_string()),
                        )]
                    });
                match world.commit_writes(footprint, "workspace", &writes, witness_version) {
                    Ok(_) => VmValue::act_success(VmValue::String("act_success_ok".to_string())),
                    Err(crate::world::WorldError::ToctouViolation { .. }) => {
                        VmValue::act_failure(VmValue::String("GateRejected".to_string()))
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
    pub child: Box<dyn ChildExecutor>,
}

impl Default for RuntimeAdapters {
    fn default() -> Self {
        Self {
            read: Box::new(DefaultTestReadAdapter::default()),
            infer: Box::new(DefaultTestInferAdapter::default()),
            verifier: Box::new(DefaultTestVerifierAdapter::default()),
            act: Box::new(DefaultTestActAdapter::default()),
            child: Box::new(DefaultTestChildExecutor::default()),
        }
    }
}
