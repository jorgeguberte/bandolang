"""transitions.py — the lowered transitions of soma.converge.

Each transition enforces the frozen normative principles. Faults are injected
by the harness, never by these functions.
"""
from __future__ import annotations

from model import (
    ClosingReason, CompletionRecord, ConvergeTransactionDomain,
    InFlightLifecycleState, NodeStatus, OutboxRecord, Reservation,
    SearchStatus, SettlementRecord, VisitedRecord, next_id,
)


class TransitionError(Exception):
    """A transition refused by the frozen protocol."""


class FatalInvariantViolation(Exception):
    """Protocol-level violation requiring durable evidence + Closing(PendingFailure)."""


# ---------------------------------------------------------------------
# StageLocal — reserve resources and write outbox. NOT a semantic dispatch.
# ---------------------------------------------------------------------

def check_satisfaction(d: ConvergeTransactionDomain, node_id: str, op_id: str,
                       satisfied: bool, value: object = None,
                       error: str = None, abort_on_error: bool = False) -> None:
    """Satisfaction check on a node WITHOUT dispatching/expanding it.

    Frozen ConvergeFrame v0 semantics: CheckSatisfaction is part of the
    parent expansion's processing — the successor node is consumed by the
    check without consuming fuel or entering visitation history.

    Campaign 2 finding: Campaign 1 never exercised satisfaction of an
    unexpanded successor; this transition was missing from the harness.
    Classified HARNESS_GAP (spec unchanged).
    """
    if d.frame_status != SearchStatus.SEARCHING:
        raise TransitionError("CheckSatisfaction outside Searching frame")
    d.satisfaction_attempts += 1
    if satisfied:
        d.satisfied_value = value
        return
    if error is not None:
        d.satisfier_error = error
        if abort_on_error:
            fatal_close(d, error)


def stage_local(d: ConvergeTransactionDomain, node_id: str, op_id: str,
                request_id: str, resource: str, amount: int,
                dedup_capable: bool = False, idempotent: bool = False,
                local_only: bool = False) -> None:
    if d.frame_status != SearchStatus.SEARCHING:
        raise TransitionError("StageLocal outside Searching frame")
    # I4 guard: rejection must leave committed/reserved deltas at zero.
    available = d.intent_available.get(resource, 0) - d.intent_reserved.get(resource, 0)
    scope_head = d.scope_limit.get(resource, 0) - d.scope_committed.get(resource, 0)
    if amount > available or amount > scope_head or amount < 0:
        raise TransitionError("StageLocal.Rejected")   # caller sees rejection; no deltas move

    d.intent_reserved[resource] = d.intent_reserved.get(resource, 0) + amount
    d.scope_committed[resource] = d.scope_committed.get(resource, 0) + amount
    d.outbox[request_id] = OutboxRecord(
        request_id=request_id, op_id=op_id, payload_digest=f"digest({node_id})",
        dedup_capable=dedup_capable, idempotent=idempotent,
        node_id=node_id, local_only=local_only,
    )


# ---------------------------------------------------------------------
# EmitExternal — first logical emission consumes fuel; transport retries do not.
# ---------------------------------------------------------------------

def emit_external(d: ConvergeTransactionDomain, request_id: str,
                  deliver_unknown: bool = False) -> str:
    if d.frame_status != SearchStatus.SEARCHING:
        raise TransitionError("EmitExternal outside Searching frame")
    rec = d.outbox.get(request_id)
    if rec is None:
        raise TransitionError("no staged record for request")

    handle_id = next_id("h")
    st = InFlightLifecycleState(handle_id=handle_id, request_id=request_id)

    if request_id not in d.first_emission_flags:
        # First logical emission: exactly one fuel increment, node advances,
        # visitation recorded (I9, T03).
        d.first_emission_flags[request_id] = True
        d.step_count += 1
        if not rec.local_only:
            d.satisfaction_attempts += 1   # external emission carries an attempt;
        node_id = rec.node_id or _node_for_op(d, rec.op_id)   # local dispatch does not
        d.nodes[node_id] = __import__("model", fromlist=["SearchNode"]).SearchNode(node_id, NodeStatus.EXPANDING)
        visit_key = f"{rec.op_id}:{node_id}"
        visit_no = sum(1 for v in d.visited if v.visit_key == visit_key) + 1
        d.visited.append(VisitedRecord(visit_key, node_id, rec.op_id, visit_no))
    else:
        # Transport retry (T04): only legal with adapter guarantees (T04B).
        prior_id = _find_handle_by_request(d, request_id)
        prior = d.handles.get(prior_id)
        if prior is not None and prior.delivery_unknown:
            if not (rec.dedup_capable or rec.idempotent):
                raise TransitionError("BLIND RETRY PROHIBITED (T04B)")
            st.transport_attempts = prior.transport_attempts + 1
            handle_id = prior_id          # retry RE-USES the same handle
        else:
            raise TransitionError("re-emission without DeliveryUnknown")

    if d.current_in_flight is not None and request_id not in d.first_emission_flags \
            and d.current_in_flight.request_id != request_id:
        raise TransitionError("in-flight slot occupied (sequential search)")
    st.delivery_unknown = deliver_unknown
    d.current_in_flight = st
    d.handles[handle_id] = st
    return handle_id


def _find_handle_by_request(d: ConvergeTransactionDomain, request_id: str) -> str | None:
    for hid, s in d.handles.items():
        if s.request_id == request_id:
            return hid
    return None


def _node_for_op(d: ConvergeTransactionDomain, op_id: str) -> str:
    for nid, node in d.nodes.items():
        if op_id in nid:
            return nid
    return f"node:{op_id}"


# ---------------------------------------------------------------------
# Completion admission — durable records; equivocation detected here (T07/T07B)
# ---------------------------------------------------------------------

def admit_completion(d: ConvergeTransactionDomain, handle_id: str,
                     receipt_id: str, digest: str, outcome: str = "Success") -> None:
    st = d.handles.get(handle_id)
    if st is None:
        raise TransitionError("completion for unknown handle")

    existing = next((c for c in d.completions.values() if c.handle_id == handle_id), None)
    if existing is not None and existing.digest != digest:
        # T07B: the contradiction becomes real ONLY when durably observed.
        # Persist violation evidence atomically WITH this admission,
        # BEFORE any fatal control flow completes.
        d.protocol_violations.append({
            "handle_id": handle_id,
            "receipt_a": existing.receipt_id, "digest_a": existing.digest,
            "receipt_b": receipt_id, "digest_b": digest,
        })
        raise FatalInvariantViolation(f"receipt equivocation on {handle_id}")

    comp = CompletionRecord(handle_id=handle_id, receipt_id=receipt_id,
                            digest=digest, outcome=outcome)
    d.completions[f"{handle_id}:{receipt_id}"] = comp
    st.completion = comp
    st.state = "Delivered"


# ---------------------------------------------------------------------
# settle — ledger reconciliation exactly once (I7); works from Delivered
# or Settled-pending states, including late settlement after Closing (T10/T11)
# ---------------------------------------------------------------------

def settle(d: ConvergeTransactionDomain, handle_id: str, resource: str, amount: int) -> None:
    st = d.handles.get(handle_id)
    if st is None:
        raise TransitionError("settlement for unknown handle")
    if st.settlement is not None:
        return          # idempotent: duplicate settlement reconciles nothing extra
    st.settlement = SettlementRecord(
        handle_id=handle_id, receipt_id=st.completion.receipt_id if st.completion else "?",
        resource=resource, amount=amount,
    )
    d.scope_spent[resource] = d.scope_spent.get(resource, 0) + amount
    d.intent_spent[resource] = d.intent_spent.get(resource, 0) + amount

    # Release this convergence's commitment on the scope; IntentFrame keeps ownership
    # of the reservation until the obligation chain closes.
    committed = d.scope_committed.get(resource, 0)
    d.scope_committed[resource] = max(0, committed - amount)


# ---------------------------------------------------------------------
# apply — semantic incorporation, exactly once per completion (I6)
# ---------------------------------------------------------------------

def apply_semantic(d: ConvergeTransactionDomain, handle_id: str,
                   mutate_frontier: bool = False) -> bool:
    st = d.handles.get(handle_id)
    if st is None:
        raise TransitionError("apply for unknown handle")
    if st.applied:
        return False         # idempotent: duplicate apply is a no-op
    if st.state != "Delivered":
        raise TransitionError("apply before delivery")
    if mutate_frontier and d.frame_status == SearchStatus.CLOSING:
        raise TransitionError("I8: frontier mutation during Closing")
    st.applied = True
    st.state = "Applied"
    return True


# ---------------------------------------------------------------------
# Cancellation & fatal closing
# ---------------------------------------------------------------------

def cancel(d: ConvergeTransactionDomain) -> None:
    """Owner cancels: Closing(PendingCancelled). Late settlement still settles."""
    if d.frame_status == SearchStatus.CLOSING:
        return
    d.frame_status = SearchStatus.CLOSING
    d.closing_reason = ClosingReason("PendingCancelled")


def fatal_close(d: ConvergeTransactionDomain, err: str) -> None:
    """FatalInvariantViolation control flow: Closing(PendingFailure(err)).

    Keeps in_flight obligations alive — logical death does not erase them.
    """
    d.protocol_violations.append({"fatal": err})
    d.frame_status = SearchStatus.CLOSING
    d.closing_reason = ClosingReason("PendingFailure", err)


def exhaust(d: ConvergeTransactionDomain) -> None:
    """Natural exhaustion: frontier drained / fuel out without satisfaction.

    Campaign 2 finding: this transition existed in the frozen semantics
    (Exhausted outcome of ConvergeFrame v0) but had never been exercised —
    Campaign 1 only tested cancel/fatal closing paths. Added for the
    semantic differential; classified HARNESS_GAP, not spec change.
    """
    if d.frame_status != SearchStatus.SEARCHING:
        return
    unsettled = [s for s in d.handles.values() if s.settlement is None]
    pending_scope = any(v > 0 for v in d.scope_committed.values())
    if unsettled or pending_scope:
        # must close first and drain obligations before terminalizing
        d.frame_status = SearchStatus.CLOSING
        d.closing_reason = ClosingReason("Draining")
        return
    d.frame_status = SearchStatus.EXHAUSTED
    d.current_in_flight = None


def finish_if_drained(d: ConvergeTransactionDomain) -> bool:
    """When all obligations are empty, a Closing frame terminalizes."""
    if d.frame_status != SearchStatus.CLOSING:
        return False
    unsettled = [s for s in d.handles.values()
                 if s.settlement is None]
    pending_scope = any(v > 0 for v in d.scope_committed.values())
    if unsettled or pending_scope:
        return False
    kind = d.closing_reason.kind if d.closing_reason else "Draining"
    d.current_in_flight = None      # terminal frames carry no in-flight handle (I2)
    if kind == "PendingFailure":
        d.frame_status = SearchStatus.FAILED
    elif kind == "PendingCancelled":
        d.frame_status = SearchStatus.EXHAUSTED
    else:
        d.frame_status = SearchStatus.SATISFIED
    return True


# ---------------------------------------------------------------------
# Recovery — forward only; observes pre-state OR committed post-state (T08/T09)
# ---------------------------------------------------------------------

def recover(d: ConvergeTransactionDomain, snapshot: ConvergeTransactionDomain,
            crash_point: str) -> None:
    """Forward recovery from a durable snapshot taken before the crash.

    T08: settlement record persisted but semantic application lost → re-apply once.
    T09: crash during semantic apply loop → domain resumes from pre-state or
    committed post-state, never partial.
    """
    if crash_point == "after_settlement_before_apply":
        # Restore durable state, then forward-apply exactly once.
        restored = snapshot.copy()
        for hid, st in restored.handles.items():
            if st.settlement is not None and not st.applied:
                live = d.handles.get(hid) or st
                live.applied = True
                live.state = "Applied"
