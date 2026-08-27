use super::{
    ops::{Instruction, Terminator},
    types::Type,
    values::{BlockId, ValueId},
};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Block {
    pub id: BlockId,
    pub name: Option<String>,
    pub params: Vec<(ValueId, Type)>,
    pub instructions: Vec<Instruction>,
    pub terminator: Terminator,
}

impl Block {
    pub fn new(id: BlockId, terminator: Terminator) -> Self {
        Self {
            id,
            name: None,
            params: Vec::new(),
            instructions: Vec::new(),
            terminator,
        }
    }
}
