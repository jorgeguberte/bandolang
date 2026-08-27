use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
pub struct ValueId(pub u32);

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
pub struct BlockId(pub u32);

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
pub struct OpId(pub u32);

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "kind", content = "payload")]
pub enum Value {
    Unit,
    Bool(bool),
    I64(i64),
    String(String),
    Ok(Box<Value>),
    Err(Box<Value>),
}

impl Value {
    pub fn ok(val: Value) -> Self {
        Value::Ok(Box::new(val))
    }

    pub fn err(val: Value) -> Self {
        Value::Err(Box::new(val))
    }
}
