"""model.py — strict state model of the soma.converge lowering.

NON-NORMATIVE decisions (frozen by the campaign plan):
- best_partial is Opaque | None: present, never asserted, never ranked,
  never updated. Open Question #8 of Kernel v0 remains OPEN.
- Reservation attribution to a ConvergeFrame lives OUTSIDE the model
  (Harness.bookkeeping.reservations_created_by_cf) — test observability only.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field, replace
from typing import Any, Optional

_ids = itertools.count(1)


def next_id(prefix: str) -> str:
    return f"{prefix}-{next(_ids)}"


# ---------------------------------------------------------------------
# Statuses and lifecycle states
# ---------------------------------------------------------------------

class SearchStatus:
    SEARCHING = "Searching"
    CLOSING = "Closing"
    FAILED = "Failed"
    SATISFIED = "Satisfied"
    EXHAUSTED = "Exhausted"


TERMINAL = {SearchStatus.FAILED, SearchStatus.SATISFIED, SearchStatus.EXHAUSTED}


class NodeStatus:
    FRONTIER = "Frontier"
    EXPANDING = "Expanding"


@dataclass(frozen=True)
class ClosingReason:
    kind: str          # "PendingCancelled" | "PendingFailure" | "Draining"
    error: Optional[str] = None


# ---------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------

@dataclass(frozen=True)
class SearchNode:
    node_id: str
    status: str


@dataclass(frozen=True)
class VisitedRecord:
    """Historical visitation record — visited is NOT a dedup set (I9)."""
    visit_key: str
    node_id: str
    op_id: str
    visit_no: int


@dataclass(frozen=True)
class OutboxRecord:
    request_id: str
    op_id: str
    payload_digest: str
    dedup_capable: bool       # adapter guarantee: request_id dedup
    idempotent: bool          # adapter guarantee: operation idempotency
    node_id: Optional[str] = None   # explicit node identity (differential parity)
    local_only: bool = False        # DISPATCH_LOCAL semantics: no observable Σ


@dataclass
class InFlightLifecycleState:
    handle_id: str
    request_id: str
    state: str = "InFlight"   # InFlight -> Delivered -> Settled -> Applied | Closed
    delivery_unknown: bool = False
    transport_attempts: int = 1   # semantic attempt == 1; retries add here only
    completion: Optional["CompletionRecord"] = None
    settlement: Optional["SettlementRecord"] = None
    applied: bool = False


@dataclass(frozen=True)
class CompletionRecord:
    """Durable record of a completion delivered for a handle."""
    handle_id: str
    receipt_id: str
    digest: str
    outcome: str              # "Success" | "Failure"


@dataclass(frozen=True)
class SettlementRecord:
    handle_id: str
    receipt_id: str
    resource: str
    amount: int               # positive spend reconciled exactly once (I7)


@dataclass(frozen=True)
class Reservation:
    """IntentFrame-owned reservation. Attribution metadata is harness-only."""
    reservation_id: str
    resource: str
    amount: int


# ---------------------------------------------------------------------
# The transaction domain (strict model, per frozen Candidate v2.3)
# ---------------------------------------------------------------------

@dataclass
class ConvergeTransactionDomain:
    # 1. Lifecycle & graph
    frame_status: str = SearchStatus.SEARCHING
    closing_reason: Optional[ClosingReason] = None
    nodes: dict[str, SearchNode] = field(default_factory=dict)
    frontier: list[str] = field(default_factory=list)
    visited: list[VisitedRecord] = field(default_factory=list)   # history, not dedup
    best_partial: Optional[Any] = None        # OPAQUE — never touched by transitions

    # 2. Fuel & attempts
    step_count: int = 0
    satisfaction_attempts: int = 0
    first_emission_flags: dict[str, bool] = field(default_factory=dict)

    # 3. In-flight (sequencial) & outbox
    current_in_flight: Optional[InFlightLifecycleState] = None
    outbox: dict[str, OutboxRecord] = field(default_factory=dict)
    handles: dict[str, InFlightLifecycleState] = field(default_factory=dict)
    completions: dict[str, CompletionRecord] = field(default_factory=dict)

    # 4. Coordinated accounting
    scope_limit: dict[str, int] = field(default_factory=dict)
    scope_committed: dict[str, int] = field(default_factory=dict)
    scope_spent: dict[str, int] = field(default_factory=dict)
    intent_available: dict[str, int] = field(default_factory=dict)
    intent_reserved: dict[str, int] = field(default_factory=dict)   # owned by IntentFrame
    intent_spent: dict[str, int] = field(default_factory=dict)

    # Durable protocol-violation evidence (T07B): written atomically
    # with admission of the second receipt, before any fatal control flow.
    protocol_violations: list[dict] = field(default_factory=list)

    # Satisfaction result carried by check_satisfaction (differential parity)
    satisfied_value: object = None
    satisfier_error: str = None

    def copy(self) -> "ConvergeTransactionDomain":
        """Snapshot for crash/rollback-of-local-state semantics in tests."""
        h = {k: InFlightCopy.of(v) if isinstance(v, InFlightLifecycleState) else v
             for k, v in self.handles.items()}
        cur = InFlightCopy.of(self.current_in_flight) if self.current_in_flight else None
        return ConvergeTransactionDomain(
            frame_status=self.frame_status,
            closing_reason=self.closing_reason,
            nodes=dict(self.nodes),
            frontier=list(self.frontier),
            visited=list(self.visited),
            best_partial=self.best_partial,
            step_count=self.step_count,
            satisfaction_attempts=self.satisfaction_attempts,
            first_emission_flags=dict(self.first_emission_flags),
            current_in_flight=cur,
            outbox=dict(self.outbox),
            handles=h,
            completions=dict(self.completions),
            scope_limit=dict(self.scope_limit),
            scope_committed=dict(self.scope_committed),
            scope_spent=dict(self.scope_spent),
            intent_available=dict(self.intent_available),
            intent_reserved=dict(self.intent_reserved),
            intent_spent=dict(self.intent_spent),
            protocol_violations=[dict(v) for v in self.protocol_violations],
        )


class InFlightCopy:
    @staticmethod
    def of(s: InFlightLifecycleState) -> InFlightLifecycleState:
        c = InFlightLifecycleState(
            handle_id=s.handle_id, request_id=s.request_id, state=s.state,
            delivery_unknown=s.delivery_unknown, transport_attempts=s.transport_attempts,
        )
        c.completion = s.completion
        c.settlement = s.settlement
        c.applied = s.applied
        return c


# ---------------------------------------------------------------------
# Harness-only bookkeeping — NEVER consulted by transitions
# ---------------------------------------------------------------------

@dataclass
class HarnessBookkeeping:
    reservations_created_by_cf: set[str] = field(default_factory=set)
