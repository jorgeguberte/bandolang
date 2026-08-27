use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(tag = "kind", content = "payload")]
pub enum Type {
    Unit,
    Bool,
    I64,
    String,
    Result {
        ok: Box<Type>,
        err: Box<Type>,
    },
}

impl Type {
    pub fn result(ok: Type, err: Type) -> Self {
        Type::Result {
            ok: Box::new(ok),
            err: Box::new(err),
        }
    }

    pub fn display_name(&self) -> String {
        match self {
            Type::Unit => "unit".to_string(),
            Type::Bool => "bool".to_string(),
            Type::I64 => "i64".to_string(),
            Type::String => "string".to_string(),
            Type::Result { ok, err } => format!("Result<{}, {}>", ok.display_name(), err.display_name()),
        }
    }
}
