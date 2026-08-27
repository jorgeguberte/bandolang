use crate::ir::effects::EffectRow;
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
    Attestation {
        predicate: String,
        subject_ty: Box<Type>,
    },
    ActOutcome {
        success: Box<Type>,
        failure: Box<Type>,
    },
    PartialReport,
    ChildHandle {
        ok: Box<Type>,
        err: Box<Type>,
        effects: EffectRow,
    },
    Claim(Box<Type>),
    Belief(Box<Type>),
}

impl Type {
    pub fn result(ok: Type, err: Type) -> Self {
        Type::Result {
            ok: Box::new(ok),
            err: Box::new(err),
        }
    }

    pub fn attestation(predicate: impl Into<String>, subject_ty: Type) -> Self {
        Type::Attestation {
            predicate: predicate.into(),
            subject_ty: Box::new(subject_ty),
        }
    }

    pub fn act_outcome(success: Type, failure: Type) -> Self {
        Type::ActOutcome {
            success: Box::new(success),
            failure: Box::new(failure),
        }
    }

    pub fn child_handle(ok: Type, err: Type, effects: EffectRow) -> Self {
        Type::ChildHandle {
            ok: Box::new(ok),
            err: Box::new(err),
            effects,
        }
    }

    pub fn claim(payload: Type) -> Self {
        Type::Claim(Box::new(payload))
    }

    pub fn belief(payload: Type) -> Self {
        Type::Belief(Box::new(payload))
    }

    pub fn display_name(&self) -> String {
        match self {
            Type::Unit => "unit".to_string(),
            Type::Bool => "bool".to_string(),
            Type::I64 => "i64".to_string(),
            Type::String => "string".to_string(),
            Type::Result { ok, err } => {
                format!("Result<{}, {}>", ok.display_name(), err.display_name())
            }
            Type::Attestation {
                predicate,
                subject_ty,
            } => format!("Attestation<{}, {}>", predicate, subject_ty.display_name()),
            Type::ActOutcome { success, failure } => format!(
                "ActOutcome<{}, {}>",
                success.display_name(),
                failure.display_name()
            ),
            Type::PartialReport => "PartialReport".to_string(),
            Type::ChildHandle { ok, err, effects } => {
                let eff_str: Vec<_> = effects.effects.iter().map(|e| e.to_string()).collect();
                format!(
                    "ChildHandle<{}, {}, {{{}}}>",
                    ok.display_name(),
                    err.display_name(),
                    eff_str.join(", ")
                )
            }
            Type::Claim(payload) => format!("Claim<{}>", payload.display_name()),
            Type::Belief(payload) => format!("Belief<{}>", payload.display_name()),
        }
    }
}
