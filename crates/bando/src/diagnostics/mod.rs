use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum DiagnosticCode {
    SsaDuplicateDef,
    SsaUseBeforeDef,
    BlockArgArity,
    BlockArgType,
    ResultPayloadType,
    EffectUndeclared,
    CfgBadTarget,
    EagerLatentMaterialization,
    StalePredecessorSymbol,
    InvalidTerminator,
    TypeMismatch,
    UnreachableCode,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Diagnostic {
    pub code: DiagnosticCode,
    pub message: String,
    pub location: Option<String>,
    pub notes: Vec<String>,
}

impl Diagnostic {
    pub fn error(code: DiagnosticCode, message: impl Into<String>) -> Self {
        Self {
            code,
            message: message.into(),
            location: None,
            notes: Vec::new(),
        }
    }

    pub fn with_note(mut self, note: impl Into<String>) -> Self {
        self.notes.push(note.into());
        self
    }
}
