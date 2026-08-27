use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

use super::{
    block::Block,
    effects::EffectRow,
    types::Type,
    values::{BlockId, ValueId},
};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Function {
    pub name: String,
    pub params: Vec<(ValueId, Type)>,
    pub return_type: Type,
    pub declared_effects: EffectRow,
    pub entry: BlockId,
    pub blocks: BTreeMap<BlockId, Block>,
}

impl Function {
    pub fn new(name: impl Into<String>, entry: BlockId, return_type: Type) -> Self {
        Self {
            name: name.into(),
            params: Vec::new(),
            return_type,
            declared_effects: EffectRow::empty(),
            entry,
            blocks: BTreeMap::new(),
        }
    }
}
