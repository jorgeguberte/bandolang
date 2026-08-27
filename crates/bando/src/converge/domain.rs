use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

use crate::ir::values::Value;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum SearchStatus {
    Searching,
    Waiting,
    Closing,
    Failed,
    Satisfied,
    Exhausted,
    Cancelled,
}

impl SearchStatus {
    pub fn is_terminal(&self) -> bool {
        matches!(
            self,
            SearchStatus::Failed
                | SearchStatus::Satisfied
                | SearchStatus::Exhausted
                | SearchStatus::Cancelled
        )
    }

    pub fn display_name(&self) -> &'static str {
        match self {
            SearchStatus::Searching => "Searching",
            SearchStatus::Waiting => "Waiting",
            SearchStatus::Closing => "Closing",
            SearchStatus::Failed => "Failed",
            SearchStatus::Satisfied => "Satisfied",
            SearchStatus::Exhausted => "Exhausted",
            SearchStatus::Cancelled => "Cancelled",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum NodeStatus {
    Queued,
    Frontier,
    Expanding,
    Expanded,
    Pruned,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum SatisfactionState {
    Untested,
    Satisfied,
    CheckedNotSatisfied,
    RetryableFailure,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct SearchNode {
    pub node_id: String,
    pub status: NodeStatus,
    pub satisfaction_state: SatisfactionState,
    pub satisfaction_retries: u64,
}

impl SearchNode {
    pub fn new(node_id: impl Into<String>) -> Self {
        Self {
            node_id: node_id.into(),
            status: NodeStatus::Frontier,
            satisfaction_state: SatisfactionState::Untested,
            satisfaction_retries: 0,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct VisitedRecord {
    pub visit_key: String,
    pub node_id: String,
    pub op_id: String,
    pub visit_no: u64,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct DispatchRecord {
    pub node_id: String,
    pub op_id: String,
    pub visit_no: u64,
    pub kind: String, // "Local" | "External"
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ClosingReason {
    pub kind: String, // "PendingSatisfied" | "PendingExhausted" | "PendingCancelled" | "PendingFailure" | "Draining"
    pub error: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct OutboxRecord {
    pub request_id: String,
    pub op_id: String,
    pub payload_digest: String,
    pub dedup_capable: bool,
    pub idempotent: bool,
    pub node_id: Option<String>,
    pub local_only: bool,
    pub reserved_resource: String,
    pub reserved_amount: u64,
    pub is_expansion: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ExecutionReceipt {
    pub request_id: String,
    pub receipt_id: String,
    pub resource: String,
    pub amount: u64,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct InFlightLifecycleState {
    pub handle_id: String,
    pub request_id: String,
    pub state: String, // "Staged" | "InFlight" | "DeliveryUnknown" | "Delivered" | "Settled" | "Applied" | "Closed" | "Aborted" | "ConfirmedNotDelivered"
    pub delivery_unknown: bool,
    pub transport_attempts: u64,
    pub completion: Option<CompletionRecord>,
    pub settlement: Option<SettlementRecord>,
    pub applied: bool,
    pub semantic_disposition: Option<String>, // "Applied" | "DiscardedDueToClosing"
    pub reserved_resource: String,
    pub reserved_amount: u64,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct SpaceOutcome {
    pub successors: Vec<String>,
    pub error: Option<String>,
    pub is_failure: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct SatisfierOutcome {
    pub node_id: String,
    pub op_id: String,
    pub satisfied: bool,
    pub value: Option<Value>,
    pub error: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum SemanticPayload {
    Space(SpaceOutcome),
    Satisfier(SatisfierOutcome),
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct CompletionRecord {
    pub handle_id: String,
    pub receipt_id: String,
    pub digest: String,
    pub outcome: String, // "Success" | "Failure"
    pub semantic_payload: Option<SemanticPayload>,
    pub receipt: Option<ExecutionReceipt>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct SettlementRecord {
    pub handle_id: String,
    pub receipt_id: String,
    pub resource: String,
    pub amount: u64,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ExhaustionReport {
    pub best_partial: Option<Value>,
    pub policy: String,
    pub reason: String,
    pub visited_nodes: Vec<String>,
    pub trace: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PendingAction {
    pub node_id: String,
    pub op_id: String,
    pub kind: String, // "local" | "external"
    pub cost: u64,
    pub is_expansion: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ConvergeTransactionDomain {
    // 1. Lifecycle & graph
    pub frame_status: SearchStatus,
    pub closing_reason: Option<ClosingReason>,
    pub nodes: BTreeMap<String, SearchNode>,
    pub frontier: Vec<String>,
    pub visited: Vec<VisitedRecord>,
    pub dispatches: Vec<DispatchRecord>,
    pub best_partial: Option<Value>,
    pub frontier_mutations_during_closing: u64,

    // 2. Fuel & attempts
    pub step_count: u64,
    pub satisfaction_attempts: u64,
    pub first_emission_flags: BTreeMap<String, bool>,

    // 3. In-flight & outbox
    pub current_in_flight: Option<InFlightLifecycleState>,
    pub outbox: BTreeMap<String, OutboxRecord>,
    pub handles: BTreeMap<String, InFlightLifecycleState>,
    pub completions: BTreeMap<String, CompletionRecord>,
    pub applied_completions: Vec<String>,
    pub settlement_reconciliations: BTreeMap<String, u64>,
    #[serde(default)]
    pub pending_action: Option<PendingAction>,
    #[serde(default)]
    pub pending_stop: Option<String>,
    #[serde(default)]
    pub last_staged_handle: Option<String>,

    // 4. Coordinated accounting
    pub scope_limit: BTreeMap<String, u64>,
    pub scope_committed: BTreeMap<String, u64>,
    pub scope_spent: BTreeMap<String, u64>,
    pub intent_initial_total: BTreeMap<String, u64>,
    pub intent_available: BTreeMap<String, u64>,
    pub intent_reserved: BTreeMap<String, u64>,
    pub intent_spent: BTreeMap<String, u64>,

    // 5. Protocol violations
    pub protocol_violations: Vec<BTreeMap<String, String>>,

    // 6. Satisfaction results & policies
    pub satisfied_value: Option<Value>,
    pub satisfier_error: Option<String>,
    pub on_satisfier_error: String, // "abort" | "retry"
    pub on_step_failure: String,    // "abort" | "prune" | "requeue"
    pub max_satisfaction_attempts: u64,
    pub max_steps: u64,
    pub exhaustion_reason: Option<String>,
}

impl Default for ConvergeTransactionDomain {
    fn default() -> Self {
        Self {
            frame_status: SearchStatus::Searching,
            closing_reason: None,
            nodes: BTreeMap::new(),
            frontier: Vec::new(),
            visited: Vec::new(),
            dispatches: Vec::new(),
            best_partial: None,
            frontier_mutations_during_closing: 0,
            step_count: 0,
            satisfaction_attempts: 0,
            first_emission_flags: BTreeMap::new(),
            current_in_flight: None,
            outbox: BTreeMap::new(),
            handles: BTreeMap::new(),
            completions: BTreeMap::new(),
            applied_completions: Vec::new(),
            settlement_reconciliations: BTreeMap::new(),
            pending_action: None,
            pending_stop: None,
            last_staged_handle: None,
            scope_limit: BTreeMap::new(),
            scope_committed: BTreeMap::new(),
            scope_spent: BTreeMap::new(),
            intent_initial_total: BTreeMap::new(),
            intent_available: BTreeMap::new(),
            intent_reserved: BTreeMap::new(),
            intent_spent: BTreeMap::new(),
            protocol_violations: Vec::new(),
            satisfied_value: None,
            satisfier_error: None,
            on_satisfier_error: "abort".to_string(),
            on_step_failure: "abort".to_string(),
            max_satisfaction_attempts: 10,
            max_steps: 100,
            exhaustion_reason: None,
        }
    }
}
