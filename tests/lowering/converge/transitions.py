"""transitions.py — transition functions of the converge lowering state machine.

Every transition takes domain d, validates pre-state, mutates d, and returns.
All state mutations belong HERE. Harness instrumentation is recorded
by the harness, never by these functions.
"""
from __future__ import annotations

import json
from dataclasses import replace
from typing import Any, Optional

from model import (
    ClosingReason, CompletionRecord, Continue, ConvergeTransactionDomain,
    DispatchRecord, ExecutionReceipt, InFlightLifecycleState, NodeStatus, OutboxRecord,
    Reservation, SatisfactionState, SatisfierOutcome, SchedulerAction, SearchNode, SearchStatus,
    SettlementRecord, SpaceOutcome, Stop, VisitedRecord, Wait, next_id,
)


class TransitionError(Exception):
    """A transition refused by the frozen protocol."""
    pass


class FatalInvariantViolation(Exception):
    """Protocol-level violation requiring durable evidence + Closing(PendingFailure)."""
    pass


def _active_in_flight_for_op(d: ConvergeTransactionDomain, op_id: str) -> bool:
    for rec in d.outbox.values():
        if rec.op_id == op_id:
            st = d.handles.get(rec.request_id)
            if st and st.state in ("InFlight", "DeliveryUnknown"):
                return True
    return False


# ---------------------------------------------------------------------
# DISPATCH_LOCAL — real local/pure expansion (R19).
# Consumes step fuel, records visited, expands frontier.
# NEVER creates InFlightHandle, outbox, completion, settlement, or spend.
# ---------------------------------------------------------------------

def dispatch_local(d: ConvergeTransactionDomain, node_id: str, op_id: str,
                   succs: list[str]) -> None:
    if d.frame_status != SearchStatus.SEARCHING:
        raise TransitionError("dispatch_local outside Searching frame")

    unsettled = [s for s in d.handles.values() if s.settlement is None and s.state != "Aborted"]
    if unsettled:
        raise TransitionError("sequential in-flight: previous request still unsettled (I1/R7)")

    d.step_count += 1
    existing_node = d.nodes.get(node_id)
    sat_state = existing_node.satisfaction_state if existing_node else SatisfactionState.UNTESTED
    sat_retries = existing_node.satisfaction_retries if existing_node else 0
    d.nodes[node_id] = SearchNode(node_id, NodeStatus.EXPANDING, sat_state, sat_retries)
    visit_key = f"{op_id}:{node_id}"
    visit_no = sum(1 for v in d.visited if v.visit_key == visit_key) + 1
    d.visited.append(VisitedRecord(visit_key, node_id, op_id, visit_no))
    # R29: bind VisitedRecord to explicit DispatchRecord for local expansion
    d.dispatches.append(DispatchRecord(node_id, op_id, visit_no, "Local"))

    if node_id in d.frontier:
        d.frontier.remove(node_id)

    discover_successors(d, succs)


def discover_successors(d: ConvergeTransactionDomain, succs: list[str]) -> None:
    """R23: all frontier additions go through this modeled operation."""
    if d.frame_status in (SearchStatus.CLOSING, SearchStatus.CANCELLED,
                          SearchStatus.FAILED, SearchStatus.EXHAUSTED):
        d.frontier_mutations_during_closing += 1
        raise TransitionError("I8: frontier mutation during Closing")
    for s in succs:
        if s not in d.nodes:
            d.nodes[s] = SearchNode(s, NodeStatus.FRONTIER)
            d.frontier.append(s)


def classify_runnable(d: ConvergeTransactionDomain, cost: int, resource: str = "usd") -> bool:
    """Check budget affordability. External ops require cost <= available headroom."""
    if cost == 0:
        return True
    spent = d.scope_spent.get(resource, 0)
    committed = d.scope_committed.get(resource, 0)
    limit = d.scope_limit.get(resource, 0)
    avail_scope = limit - spent - committed
    avail_intent = d.intent_available.get(resource, 0)
    return avail_scope >= cost and avail_intent >= cost


def scheduler_step(d: ConvergeTransactionDomain, prog: Any) -> SchedulerAction:
    """R25/R31: Machine-owned scheduling decisions.
    Checks unsettled in-flight handles first -> returns Wait(reason).
    Checks fuel/frontier/budget -> returns Continue(...) or Stop(reason).
    """
    unsettled = [s for s in d.handles.values() if s.settlement is None and s.state != "Aborted"]
    if unsettled:
        d.frame_status = SearchStatus.WAITING
        return Wait(reason=f"InFlight({unsettled[0].handle_id})")

    if d.step_count >= prog.max_steps:
        return Stop("FuelExhausted")
    if not d.frontier:
        return Stop("FrontierEmpty")

    for n in d.frontier:
        op = prog.node_ops.get(n, None) if hasattr(prog, "node_ops") else None
        cost = op.cost if op and op.kind == "external" else 0
        if classify_runnable(d, cost, "usd"):
            return Continue(n, op.op_id if op else f"op:{n}", op.kind if op else "local")

    return Stop("BudgetDepleted")


def stage_local(d: ConvergeTransactionDomain, node_id: str, op_id: str,
                request_id: str, resource: str, amount: int,
                dedup_capable: bool = False, idempotent: bool = False,
                local_only: bool = False, is_expansion: bool = True) -> str:
    """R17: stage_local creates InFlightHandle atomically with outbox record."""
    # R43: reject request_id reuse before any reservation/mutation
    if request_id in d.outbox:
        raise TransitionError(f"RequestIdAlreadyUsed: cannot stage new request with historical request_id '{request_id}'")

    unsettled = [s for s in d.handles.values() if s.settlement is None and s.state != "Aborted"]
    if unsettled:
        raise TransitionError("sequential in-flight: previous request still unsettled (I1/R7)")

    if d.frame_status != SearchStatus.SEARCHING:
        raise TransitionError("StageLocal outside Searching frame")

    if amount < 0:
        raise TransitionError("negative amount")

    avail = d.intent_available.get(resource, 0)
    if avail < amount:
        raise TransitionError(f"insufficient available intent: {avail} < {amount}")

    spent = d.scope_spent.get(resource, 0)
    committed = d.scope_committed.get(resource, 0)
    limit = d.scope_limit.get(resource, 0)
    if spent + committed + amount > limit:
        raise TransitionError("budget limit exceeded")

    d.intent_available[resource] = avail - amount
    d.intent_reserved[resource] = d.intent_reserved.get(resource, 0) + amount
    d.scope_committed[resource] = committed + amount

    handle_id = next_id("h")
    digest = f"payload:{op_id}"
    rec = OutboxRecord(
        request_id=request_id, op_id=op_id, payload_digest=digest,
        dedup_capable=dedup_capable, idempotent=idempotent,
        node_id=node_id, local_only=local_only,
        reserved_resource=resource, reserved_amount=amount,
        is_expansion=is_expansion,
    )
    d.outbox[request_id] = rec

    st = InFlightLifecycleState(
        handle_id=handle_id, request_id=request_id, state="Staged",
        reserved_resource=resource, reserved_amount=amount,
    )
    d.handles[handle_id] = st
    return handle_id


# ---------------------------------------------------------------------
# EMIT_EXTERNAL — the boundary transition that performs logical dispatch
# ---------------------------------------------------------------------

def emit_external(d: ConvergeTransactionDomain, request_or_handle_id: str,
                  deliver_unknown: bool = False) -> str:
    if d.frame_status not in (SearchStatus.SEARCHING, SearchStatus.WAITING):
        raise TransitionError("EmitExternal outside Searching/Waiting frame")

    st = d.handles.get(request_or_handle_id)
    if st is None:
        st = next((s for s in d.handles.values() if s.request_id == request_or_handle_id), None)
    if st is None:
        raise TransitionError("unknown request/handle")

    request_id = st.request_id
    handle_id = st.handle_id
    rec = d.outbox.get(request_id)
    if rec is None:
        raise TransitionError("outbox record missing")

    is_first = request_id not in d.first_emission_flags
    if is_first:
        d.first_emission_flags[request_id] = True

        if rec.is_expansion:
            d.step_count += 1
            node_id = rec.node_id or _node_for_op(d, rec.op_id)
            existing_node = d.nodes.get(node_id)
            sat_state = existing_node.satisfaction_state if existing_node else SatisfactionState.UNTESTED
            sat_retries = existing_node.satisfaction_retries if existing_node else 0
            d.nodes[node_id] = SearchNode(node_id, NodeStatus.EXPANDING, sat_state, sat_retries)
            visit_key = f"{rec.op_id}:{node_id}"
            visit_no = sum(1 for v in d.visited if v.visit_key == visit_key) + 1
            d.visited.append(VisitedRecord(visit_key, node_id, rec.op_id, visit_no))
            d.dispatches.append(DispatchRecord(node_id, rec.op_id, visit_no, "External"))

            if node_id in d.frontier:
                d.frontier.remove(node_id)
        else:
            d.satisfaction_attempts += 1

        st.state = "DeliveryUnknown" if deliver_unknown else "InFlight"
    else:
        if not (rec.dedup_capable or rec.idempotent):
            raise TransitionError("BLIND RETRY: unsafe retry without adapter dedup/idempotence guarantee")
        if not st.delivery_unknown and st.state != "DeliveryUnknown":
            raise TransitionError("retry of non-DeliveryUnknown request")
        st.transport_attempts += 1
        st.state = "DeliveryUnknown" if deliver_unknown else "InFlight"

    st.delivery_unknown = deliver_unknown
    d.current_in_flight = st
    d.frame_status = SearchStatus.WAITING
    return handle_id


def _find_handle_by_request(d: ConvergeTransactionDomain, request_id: str) -> str | None:
    for hid, s in d.handles.items():
        if s.request_id == request_id:
            return hid
    return None


def _node_for_op(d: ConvergeTransactionDomain, op_id: str) -> str:
    for nid, node in d.nodes.items():
        if node.status in (NodeStatus.FRONTIER, NodeStatus.EXPANDING):
            return nid
    return f"node:{op_id}"


# ---------------------------------------------------------------------
# Completion admission — durable records; equivocation detected here (T07/T07B/R46/R56/R57/R62)
# ---------------------------------------------------------------------

def canonical_digest(receipt_id: str, outcome: str = "Success",
                     semantic_payload: Optional[SpaceOutcome | SatisfierOutcome] = None,
                     receipt: Optional[ExecutionReceipt] = None) -> str:
    """R46/R50/R56/R57/R62: Injective canonical JSON digest binding receipt_id, outcome, payload, and receipt."""
    if isinstance(semantic_payload, SpaceOutcome):
        p_obj = ["Space", list(semantic_payload.successors), semantic_payload.error, semantic_payload.is_failure]
    elif isinstance(semantic_payload, SatisfierOutcome):
        p_obj = ["Satisfier", semantic_payload.node_id, semantic_payload.op_id,
                 semantic_payload.satisfied, semantic_payload.value, semantic_payload.error]
    else:
        p_obj = None

    rcpt_obj = [receipt.request_id, receipt.receipt_id, receipt.resource, receipt.amount] if receipt is not None else None
    canon_structure = ["v1", receipt_id, outcome, p_obj, rcpt_obj]
    return "digest:" + json.dumps(canon_structure, sort_keys=True, separators=(',', ':'))


def admit_completion(d: ConvergeTransactionDomain, handle_id: str,
                     receipt_id: str, digest: Optional[str] = None, outcome: str = "Success",
                     semantic_payload: Optional[SpaceOutcome | SatisfierOutcome] = None,
                     receipt: Optional[ExecutionReceipt] = None) -> None:
    st = d.handles.get(handle_id)
    if st is None:
        raise TransitionError("completion for unknown handle")

    if outcome == "Failure" and semantic_payload is not None and not getattr(semantic_payload, "is_failure", False):
        raise TransitionError("Failure outcome cannot carry success semantic payload (R37)")

    # R62: ExecutionReceipt is mandatory for external completions and must match request_id and receipt_id
    if receipt is not None:
        if receipt.request_id != st.request_id:
            raise TransitionError(f"ReceiptRequestIdMismatch: receipt.request_id '{receipt.request_id}' != handle.request_id '{st.request_id}' (R62)")
        if receipt.receipt_id != receipt_id:
            raise TransitionError(f"ReceiptIdMismatch: receipt.receipt_id '{receipt.receipt_id}' != completion.receipt_id '{receipt_id}' (R62)")

    expected_digest = canonical_digest(receipt_id, outcome, semantic_payload, receipt)
    if digest is not None and digest != expected_digest:
        # R46/R56: digest must bind outcome, semantic_payload, and receipt
        raise TransitionError(f"DigestPayloadMismatch: digest '{digest}' does not bind payload (expected '{expected_digest}') (R46/R56)")
    digest = expected_digest

    existing = next((c for c in d.completions.values() if c.handle_id == handle_id), None)
    if existing is not None:
        # R37/R46/R56/R62: Equivocation check binds receipt_id, digest, outcome, semantic_payload, AND receipt
        if (existing.receipt_id != receipt_id or
            existing.digest != digest or
            existing.semantic_payload != semantic_payload or
            existing.receipt != receipt or
            existing.outcome != outcome):
            fatal_close(d, f"receipt equivocation on {handle_id}")
            raise FatalInvariantViolation(f"receipt equivocation on {handle_id}")
        else:
            # Idempotent duplicate delivery of identical completion
            return

    if st.state not in ("InFlight", "DeliveryUnknown"):
        raise TransitionError(f"completion admitted in invalid state '{st.state}' — must be InFlight or DeliveryUnknown")

    comp = CompletionRecord(handle_id=handle_id, receipt_id=receipt_id,
                            digest=digest, outcome=outcome,
                            semantic_payload=semantic_payload,
                            receipt=receipt)
    d.completions[f"{handle_id}:{receipt_id}"] = comp
    st.completion = comp
    st.state = "Delivered"


# ---------------------------------------------------------------------
# settle — ledger reconciliation exactly once (I7/R57/R62); works from Delivered
# ---------------------------------------------------------------------

def settle(d: ConvergeTransactionDomain, handle_id: str,
           resource: Optional[str] = None, amount: Optional[int] = None) -> None:
    """R57/R62: Settle handle. Resource and amount are authoritatively derived from st.completion.receipt."""
    st = d.handles.get(handle_id)
    if st is None:
        raise TransitionError("settlement for unknown handle")
    if st.settlement is not None:
        return          # idempotent: duplicate settlement reconciles nothing extra

    if st.state != "Delivered":
        raise TransitionError(f"settle called in invalid state '{st.state}' — must be Delivered")

    if st.completion is not None and st.completion.receipt is not None:
        rec_res = st.completion.receipt.resource
        rec_amount = st.completion.receipt.amount
        if amount is not None and amount != rec_amount:
            raise TransitionError(f"SettlementAmountMismatch: caller amount {amount} != durable receipt amount {rec_amount} (R57)")
        if resource is not None and resource != rec_res:
            raise TransitionError(f"SettlementResourceMismatch: caller resource {resource} != durable receipt resource {rec_res} (R57)")
        resource = rec_res
        amount = rec_amount
    else:
        resource = resource or st.reserved_resource or "usd"
        amount = amount if amount is not None else st.reserved_amount

    ceiling = st.reserved_amount
    ceiling_res = st.reserved_resource or resource

    # R16 (audit): receipt adversarial bounds checks
    if amount < 0:
        raise TransitionError("negative settlement charge")
    if st.reserved_amount == 0 and amount > 0:
        raise TransitionError("ChargeOnZeroReservation: cannot settle positive charge on zero reservation")
    if amount > ceiling:
        fatal_close(d, f"SettlementExceedsCeiling: charge {amount} > ceiling {ceiling}")
        raise FatalInvariantViolation(f"SettlementExceedsCeiling: charge {amount} exceeds reserved ceiling {ceiling}")
    if resource != ceiling_res:
        fatal_close(d, f"SettlementResourceMismatch: resource {resource} != reserved {ceiling_res}")
        raise FatalInvariantViolation(f"SettlementResourceMismatch: resource {resource} != reserved {ceiling_res}")

    st.settlement = SettlementRecord(
        handle_id=handle_id, receipt_id=st.completion.receipt_id if st.completion else "?",
        resource=resource, amount=amount,
    )
    st.state = "Settled"
    # R40: independent reconciliation count per handle
    d.settlement_reconciliations[handle_id] = d.settlement_reconciliations.get(handle_id, 0) + 1

    # IntentFrame reconciliation:
    # reserved -= R; spent += C; available += (R - C) [unspent refund]
    d.intent_reserved[ceiling_res] = max(0, d.intent_reserved.get(ceiling_res, 0) - ceiling)
    d.intent_spent[resource] = d.intent_spent.get(resource, 0) + amount
    d.intent_available[ceiling_res] = d.intent_available.get(ceiling_res, 0) + max(0, ceiling - amount)

    # BudgetScope reconciliation:
    # committed -= R; spent += C
    committed = d.scope_committed.get(ceiling_res, 0)
    d.scope_committed[ceiling_res] = max(0, committed - ceiling)
    d.scope_spent[resource] = d.scope_spent.get(resource, 0) + amount


# ---------------------------------------------------------------------
# ConfirmedNotDelivered transition (R65)
# ---------------------------------------------------------------------

def confirmed_not_delivered(d: ConvergeTransactionDomain, handle_id: str) -> None:
    """R65: Transport layer confirms request was not delivered.
    Releases all reservations and commitments with 0 spend; returns frame to Searching/Closing."""
    st = d.handles.get(handle_id)
    if st is None:
        raise TransitionError("unknown handle")
    if st.state not in ("InFlight", "DeliveryUnknown"):
        raise TransitionError(f"confirmed_not_delivered called in invalid state '{st.state}'")

    ceiling = st.reserved_amount
    ceiling_res = st.reserved_resource or "usd"

    d.intent_reserved[ceiling_res] = max(0, d.intent_reserved.get(ceiling_res, 0) - ceiling)
    d.intent_available[ceiling_res] = d.intent_available.get(ceiling_res, 0) + ceiling
    d.scope_committed[ceiling_res] = max(0, d.scope_committed.get(ceiling_res, 0) - ceiling)

    st.state = "ConfirmedNotDelivered"
    if d.current_in_flight == st:
        d.current_in_flight = None

    if d.frame_status == SearchStatus.WAITING:
        d.frame_status = SearchStatus.SEARCHING


# ---------------------------------------------------------------------
# apply — semantic incorporation, exactly once per completion (I6, R27, R38, R45, R58, R61, R64)
# ---------------------------------------------------------------------

def apply_semantic(d: ConvergeTransactionDomain, handle_id: str,
                   mutate_frontier: bool = False) -> bool:
    st = d.handles.get(handle_id)
    if st is None:
        raise TransitionError("apply for unknown handle")
    if st.applied:
        return False         # idempotent: duplicate apply is a no-op
    if st.state != "Settled":
        raise TransitionError(f"apply_semantic called in invalid state '{st.state}' — must be Settled")
    if st.completion is not None and st.completion.semantic_payload is not None:
        # R38: refuse generic apply on handles with typed SpaceOutcome/SatisfierOutcome
        raise TransitionError("generic apply_semantic refused on handle with typed SpaceOutcome/SatisfierOutcome — use apply_space_completion or apply_satisfier_completion")
    if mutate_frontier and d.frame_status in (SearchStatus.CLOSING, SearchStatus.CANCELLED,
                                              SearchStatus.FAILED, SearchStatus.EXHAUSTED):
        raise TransitionError("I8: frontier mutation during Closing")
    st.applied = True
    st.semantic_disposition = "Applied"
    st.state = "Applied"
    c_id = f"{handle_id}:{st.completion.receipt_id}" if st.completion else handle_id
    d.applied_completions.append(c_id)
    if d.frame_status == SearchStatus.WAITING:
        d.frame_status = SearchStatus.SEARCHING
    return True


def apply_space_completion(d: ConvergeTransactionDomain, handle_id: str) -> bool:
    """R27/R45/R58/R64: Atomic space completion incorporation.
    R58: If frame is Closing or Terminal, semantic payload is safely discarded without mutating frontier.
    R64: Handles typed StepFailure outcomes with on_step_failure policy.
    """
    st = d.handles.get(handle_id)
    if st is None:
        raise TransitionError("apply for unknown handle")
    if st.applied or st.semantic_disposition is not None:
        return False
    if st.state != "Settled":
        raise TransitionError(f"apply_space_completion called in invalid state '{st.state}' — must be Settled")
    if st.completion is None or not isinstance(st.completion.semantic_payload, SpaceOutcome):
        raise TransitionError("apply_space_completion called on handle without durable SpaceOutcome")

    if d.frame_status in (SearchStatus.CLOSING, SearchStatus.FAILED, SearchStatus.CANCELLED, SearchStatus.EXHAUSTED):
        # R58: Semantic payload discarded during Closing/Terminal — accounting settled, search not advanced
        st.semantic_disposition = "DiscardedDueToClosing"
        st.state = "Closed"
        return True

    payload = st.completion.semantic_payload
    if payload.is_failure:
        # R64: Space StepFailure
        st.semantic_disposition = "StepFailure"
        st.applied = True
        st.state = "Applied"
        c_id = f"{handle_id}:{st.completion.receipt_id}"
        d.applied_completions.append(c_id)
        if d.on_step_failure == "abort":
            fatal_close(d, payload.error or "StepFailure")
        elif d.frame_status == SearchStatus.WAITING:
            d.frame_status = SearchStatus.SEARCHING
        return True

    # Discover successors into frontier & nodes from durable payload
    discover_successors(d, payload.successors)

    st.applied = True
    st.semantic_disposition = "Applied"
    st.state = "Applied"
    c_id = f"{handle_id}:{st.completion.receipt_id}"
    d.applied_completions.append(c_id)
    if d.frame_status == SearchStatus.WAITING:
        d.frame_status = SearchStatus.SEARCHING
    return True


def apply_satisfier_completion(d: ConvergeTransactionDomain, handle_id: str) -> bool:
    """R27/R45/R52/R58/R61: Atomic satisfier completion incorporation.
    R58: If frame is Closing, late satisfaction is safely discarded and never overrides Closing reason.
    R61: Updates node satisfaction_state machine-side (CheckedNotSatisfied, RetryableFailure, Satisfied).
    """
    st = d.handles.get(handle_id)
    if st is None:
        raise TransitionError("apply for unknown handle")
    if st.applied or st.semantic_disposition is not None:
        return False
    if st.state != "Settled":
        raise TransitionError(f"apply_satisfier_completion called in invalid state '{st.state}' — must be Settled")
    if st.completion is None or not isinstance(st.completion.semantic_payload, SatisfierOutcome):
        raise TransitionError("apply_satisfier_completion called on handle without durable SatisfierOutcome")

    if d.frame_status in (SearchStatus.CLOSING, SearchStatus.FAILED, SearchStatus.CANCELLED, SearchStatus.EXHAUSTED):
        # R58: Late satisfaction discarded during Closing
        st.semantic_disposition = "DiscardedDueToClosing"
        st.state = "Closed"
        return True

    so = st.completion.semantic_payload
    node_id = so.node_id
    existing_node = d.nodes.get(node_id)
    cur_status = existing_node.status if existing_node else NodeStatus.FRONTIER

    if so.satisfied:
        d.nodes[node_id] = SearchNode(node_id, cur_status, SatisfactionState.SATISFIED)
        d.satisfied_value = so.value
        d.frame_status = SearchStatus.SATISFIED
        d.current_in_flight = None
    elif so.error is not None:
        retries = (existing_node.satisfaction_retries + 1) if existing_node else 1
        d.nodes[node_id] = SearchNode(node_id, cur_status, SatisfactionState.RETRYABLE_FAILURE, retries)
        d.satisfier_error = so.error
        if d.on_satisfier_error == "abort":
            fatal_close(d, so.error)
        elif d.frame_status == SearchStatus.WAITING:
            d.frame_status = SearchStatus.SEARCHING
    else:
        retries = existing_node.satisfaction_retries if existing_node else 0
        d.nodes[node_id] = SearchNode(node_id, cur_status, SatisfactionState.CHECKED_NOT_SATISFIED, retries)
        if d.frame_status == SearchStatus.WAITING:
            d.frame_status = SearchStatus.SEARCHING

    st.applied = True
    st.semantic_disposition = "Applied"
    st.state = "Applied"
    c_id = f"{handle_id}:{st.completion.receipt_id}"
    d.applied_completions.append(c_id)
    return True


# ---------------------------------------------------------------------
# Cancellation & fatal closing
# ---------------------------------------------------------------------

def cancel(d: ConvergeTransactionDomain) -> None:
    """Owner cancels: Closing(PendingCancelled). Late settlement still settles.
    R15: Any staged but un-emitted handles are aborted and their reservations released."""
    if d.frame_status == SearchStatus.CLOSING:
        return
    d.frame_status = SearchStatus.CLOSING
    d.closing_reason = ClosingReason("PendingCancelled")

    # Release any staged but not yet emitted handle reservations
    for hid, st in list(d.handles.items()):
        if st.state == "Staged":
            st.state = "Aborted"
            R = st.reserved_amount
            res = st.reserved_resource
            d.intent_reserved[res] = max(0, d.intent_reserved.get(res, 0) - R)
            d.intent_available[res] = d.intent_available.get(res, 0) + R
            d.scope_committed[res] = max(0, d.scope_committed.get(res, 0) - R)
            if d.current_in_flight == st:
                d.current_in_flight = None


def fatal_close(d: ConvergeTransactionDomain, err: str) -> None:
    """FatalInvariantViolation control flow: Closing(PendingFailure(err)).

    Keeps in_flight obligations alive — logical death does not erase them.
    """
    d.protocol_violations.append({"fatal": err})
    d.frame_status = SearchStatus.CLOSING
    d.closing_reason = ClosingReason("PendingFailure", err)


def exhaust(d: ConvergeTransactionDomain, reason: str = "FrontierEmpty") -> None:
    """Natural exhaustion: frontier drained / fuel out without satisfaction (R34)."""
    d.exhaustion_reason = reason
    if d.frame_status not in (SearchStatus.SEARCHING, SearchStatus.WAITING):
        return
    unsettled = [s for s in d.handles.values() if s.settlement is None and s.state != "ConfirmedNotDelivered"]
    pending_scope = any(v > 0 for v in d.scope_committed.values())
    if unsettled or pending_scope:
        # R13: must close as PendingExhausted and drain obligations before terminalizing
        d.frame_status = SearchStatus.CLOSING
        d.closing_reason = ClosingReason("PendingExhausted")
        return
    d.frame_status = SearchStatus.EXHAUSTED
    d.current_in_flight = None


def finish_if_drained(d: ConvergeTransactionDomain) -> bool:
    """When all obligations are empty, a Closing frame terminalizes."""
    if d.frame_status != SearchStatus.CLOSING:
        return False
    unsettled = [s for s in d.handles.values()
                 if s.settlement is None and s.state not in ("Aborted", "ConfirmedNotDelivered")]
    pending_scope = any(v > 0 for v in d.scope_committed.values())
    if unsettled or pending_scope:
        return False
    kind = d.closing_reason.kind if d.closing_reason else "Draining"
    d.current_in_flight = None      # terminal frames carry no in-flight handle (I2)
    if kind == "PendingFailure":
        d.frame_status = SearchStatus.FAILED
    elif kind == "PendingCancelled":
        d.frame_status = SearchStatus.CANCELLED   # R2: cancellation ≠ exhaustion
    elif kind == "PendingExhausted":
        d.frame_status = SearchStatus.EXHAUSTED   # R13: PendingExhausted -> Exhausted, NEVER Satisfied
    elif kind == "PendingSatisfied":
        d.frame_status = SearchStatus.SATISFIED
    else:
        d.frame_status = SearchStatus.EXHAUSTED
    return True


# ---------------------------------------------------------------------
# Recovery — forward only; observes pre-state OR committed post-state (T08/T09/R32/R53)
# ---------------------------------------------------------------------

def recover(d: ConvergeTransactionDomain, snapshot: ConvergeTransactionDomain,
            crash_point: str) -> None:
    """Forward recovery from a durable snapshot taken before the crash (R32/R45/R53).
    R53: Redrives exclusively on the restored snapshot domain, then authoritatively updates d.
    """
    if crash_point == "after_settlement_before_apply":
        # Restore durable state, then redrive on restored domain exclusively (R53)
        restored = snapshot.copy()
        for hid, st in list(restored.handles.items()):
            if st.settlement is not None and not st.applied and st.completion is not None:
                payload = st.completion.semantic_payload
                if isinstance(payload, SpaceOutcome):
                    apply_space_completion(restored, hid)
                elif isinstance(payload, SatisfierOutcome):
                    apply_satisfier_completion(restored, hid)
                else:
                    apply_semantic(restored, hid)
        # Authoritatively update d to match restored committed state
        d.__dict__.clear()
        d.__dict__.update(restored.__dict__)
    elif crash_point == "mid_apply_loop":
        # R22: Transactional atomicity — reset uncommitted partial RAM state back to pre-state snapshot
        d.__dict__.clear()
        d.__dict__.update(snapshot.copy().__dict__)


def check_satisfaction(d: ConvergeTransactionDomain, node_id: str, op_id: str,
                       satisfied: bool, value: object = None, error: str = None,
                       abort_on_error: bool = True) -> bool:
    """Check satisfaction for local satisfiers (R61)."""
    if d.frame_status not in (SearchStatus.SEARCHING, SearchStatus.WAITING):
        return False
    d.satisfaction_attempts += 1
    existing_node = d.nodes.get(node_id)
    cur_status = existing_node.status if existing_node else NodeStatus.FRONTIER

    if satisfied:
        d.nodes[node_id] = SearchNode(node_id, cur_status, SatisfactionState.SATISFIED)
        d.satisfied_value = value
        d.frame_status = SearchStatus.SATISFIED
        d.current_in_flight = None
        return True
    elif error is not None:
        retries = (existing_node.satisfaction_retries + 1) if existing_node else 1
        d.nodes[node_id] = SearchNode(node_id, cur_status, SatisfactionState.RETRYABLE_FAILURE, retries)
        d.satisfier_error = error
        if abort_on_error:
            fatal_close(d, error)
        return False
    else:
        retries = existing_node.satisfaction_retries if existing_node else 0
        d.nodes[node_id] = SearchNode(node_id, cur_status, SatisfactionState.CHECKED_NOT_SATISFIED, retries)
        return False
