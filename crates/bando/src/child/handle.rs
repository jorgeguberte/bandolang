use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

use super::provenance::ChildResultProvenance;
use crate::ir::{effects::EffectRow, values::Value as VmValue};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
pub enum ChildSettlementState {
    Unsettled,
    SettlementUnknown,
    Settled,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ChildHandleRecord {
    pub handle_id: String,
    pub child_id: String,
    pub parent_id: String,
    pub generation_token: String,
    pub effects: EffectRow,
    pub settlement_state: ChildSettlementState,
    pub result: Option<Result<VmValue, VmValue>>,
    pub unspent_budget: BTreeMap<String, u64>,
    pub budget: super::budget::FrameBudget,
    pub provenance: ChildResultProvenance,
    pub active_children: usize,
    pub outstanding_commitments: u64,
    pub is_cancelled: bool,
}

impl ChildHandleRecord {
    pub fn new(
        handle_id: impl Into<String>,
        child_id: impl Into<String>,
        parent_id: impl Into<String>,
        generation_token: impl Into<String>,
        effects: EffectRow,
        provenance: ChildResultProvenance,
    ) -> Self {
        Self {
            handle_id: handle_id.into(),
            child_id: child_id.into(),
            parent_id: parent_id.into(),
            generation_token: generation_token.into(),
            effects,
            settlement_state: ChildSettlementState::Unsettled,
            result: None,
            unspent_budget: BTreeMap::new(),
            budget: super::budget::FrameBudget::new(),
            provenance,
            active_children: 0,
            outstanding_commitments: 0,
            is_cancelled: false,
        }
    }
}
