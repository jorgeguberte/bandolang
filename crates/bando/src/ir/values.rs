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
}
