use crate::ir::effects::EffectRow;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
pub struct ValueId(pub u32);

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
pub struct BlockId(pub u32);

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
pub struct OpId(pub u32);

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PartialEffectReport {
    pub op_id: String,
    pub confirmed_applied: Vec<String>,
    pub confirmed_not_applied: Vec<String>,
    pub receipt_id: String,
    pub error: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ChildHandleValue {
    pub handle_id: String,
    pub child_id: String,
    pub parent_id: String,
    pub generation_token: String,
    pub effects: EffectRow,
    pub settlement_state: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct BeliefValue {
    pub payload: Box<Value>,
    pub owner_agent_id: String,
    pub provenance: Vec<String>,
    pub policy_binding: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "kind", content = "payload")]
pub enum Value {
    Unit,
    Bool(bool),
    I64(i64),
    String(String),
    Ok(Box<Value>),
    Err(Box<Value>),
    Attestation {
        predicate: String,
        subject: Box<Value>,
        issuer: String,
        verifier_build: String,
        token: String,
    },
    ActSuccess(Box<Value>),
    ActFailure(Box<Value>),
    ActPartial(PartialEffectReport),
    DeliveryUnknown(String),
    SettlementUnknown(String),
    ChildHandle(ChildHandleValue),
    Claim(Box<Value>),
    Belief(BeliefValue),
    ConvergenceOutcome(ConvergenceOutcomeValue),
    ExhaustionReport(ExhaustionReportValue),
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ExhaustionReportValue {
    pub best_partial: Option<Box<Value>>,
    pub policy: String,
    pub reason: String,
    pub visited_nodes: Vec<String>,
    pub trace: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "kind", content = "payload")]
pub enum ConvergenceOutcomeValue {
    Satisfied(Box<Value>),
    Exhausted(ExhaustionReportValue),
}

impl Value {
    pub fn ok(val: Value) -> Self {
        Value::Ok(Box::new(val))
    }

    pub fn err(val: Value) -> Self {
        Value::Err(Box::new(val))
    }

    pub fn act_success(val: Value) -> Self {
        Value::ActSuccess(Box::new(val))
    }

    pub fn act_failure(val: Value) -> Self {
        Value::ActFailure(Box::new(val))
    }

    pub fn attestation(
        predicate: impl Into<String>,
        subject: Value,
        issuer: impl Into<String>,
        verifier_build: impl Into<String>,
        token: impl Into<String>,
    ) -> Self {
        Value::Attestation {
            predicate: predicate.into(),
            subject: Box::new(subject),
            issuer: issuer.into(),
            verifier_build: verifier_build.into(),
            token: token.into(),
        }
    }

    pub fn child_handle(
        handle_id: impl Into<String>,
        child_id: impl Into<String>,
        parent_id: impl Into<String>,
        generation_token: impl Into<String>,
        effects: EffectRow,
        settlement_state: impl Into<String>,
    ) -> Self {
        Value::ChildHandle(ChildHandleValue {
            handle_id: handle_id.into(),
            child_id: child_id.into(),
            parent_id: parent_id.into(),
            generation_token: generation_token.into(),
            effects,
            settlement_state: settlement_state.into(),
        })
    }

    pub fn claim(payload: Value) -> Self {
        Value::Claim(Box::new(payload))
    }

    pub fn belief(
        payload: Value,
        owner_agent_id: impl Into<String>,
        provenance: Vec<String>,
        policy_binding: impl Into<String>,
    ) -> Self {
        Value::Belief(BeliefValue {
            payload: Box::new(payload),
            owner_agent_id: owner_agent_id.into(),
            provenance,
            policy_binding: policy_binding.into(),
        })
    }

    pub fn satisfied(payload: Value) -> Self {
        Value::ConvergenceOutcome(ConvergenceOutcomeValue::Satisfied(Box::new(payload)))
    }

    pub fn exhausted(report: ExhaustionReportValue) -> Self {
        Value::ConvergenceOutcome(ConvergenceOutcomeValue::Exhausted(report))
    }
}
