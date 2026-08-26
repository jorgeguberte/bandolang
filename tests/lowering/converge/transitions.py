"""transitions.py — the lowered transitions of soma.converge.

Each transition enforces the frozen normative principles. Faults are injected
by the harness, never by these functions.
"""
from dataclasses import replace
from typing import Any

from model import (
    ClosingReason, CompletionRecord, Continue, ConvergeTransactionDomain,
    DispatchRecord, InFlightLifecycleState, NodeStatus, OutboxRecord,
    Reservation, SchedulerAction, SearchNode, SearchStatus, SettlementRecord,
    Stop, VisitedRecord, Wait, next_id,
)


class TransitionError(Exception):
    """A transition refused by the frozen protocol."""


class FatalInvariantViolation(Exception):
    """Protocol-level violation requiring durable evidence + Closing(PendingFailure)."""


# ---------------------------------------------------------------------
# StageLocal — reserve resources and write outbox. NOT a semantic dispatch.
# ---------------------------------------------------------------------

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
    d.nodes[node_id] = SearchNode(node_id, NodeStatus.EXPANDING)
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


def classify_runnable(d: ConvergeTransactionDomain, op_cost: int, resource: str = "usd") -> bool:
    """R20: Check whether an operation ceiling can be afforded under current headroom."""
    available = d.intent_available.get(resource, 0)
    scope_head = d.scope_limit.get(resource, 0) - d.scope_spent.get(resource, 0) - d.scope_committed.get(resource, 0)
    return (op_cost <= available and op_cost <= scope_head)


def scheduler_step(d: ConvergeTransactionDomain, prog: Any) -> SchedulerAction:
    """R25: Machine-owned scheduling decisions. Driver never writes/pops frontier."""
    if d.step_count >= prog.max_steps:
        return Stop("FuelExhausted")
    if not d.frontier:
        return Stop("FrontierEmpty")

    for n in d.frontier:
        op = prog.node_ops.get(n)
        if op is None:
            from scenarios import OpDef
            op = OpDef(op_id=f"op:{n}")
        cost = op.cost if op.kind == "external" else 0
        if classify_runnable(d, cost, "usd"):
            return Continue(node=n, op_id=op.op_id, kind=op.kind)

    return Stop("BudgetDepleted")


def check_satisfaction(d: ConvergeTransactionDomain, node_id: str, op_id: str,
                       satisfied: bool, value: object = None,
                       error: str = None, abort_on_error: bool = False) -> None:
    """CheckSatisfaction on a node WITHOUT dispatching/expanding it.

    Frozen ConvergeFrame v0 semantics: CheckSatisfaction evaluates whether
    a candidate in the frontier or current expansion satisfies the goal.
    It does NOT consume fuel and does NOT record visitation.

    R1 (audit): the ONLY place satisfaction_attempts increments.
    R3 (audit): Ok(Some(T)) performs the normative Satisfied transition itself.
    """
    if d.frame_status != SearchStatus.SEARCHING:
        raise TransitionError("CheckSatisfaction outside Searching frame")
    d.satisfaction_attempts += 1
    if satisfied:
        d.satisfied_value = value
        d.frame_status = SearchStatus.SATISFIED      # R3: normative transition
        d.current_in_flight = None                   # search consumed its request
        return
    if error is not None:
        d.satisfier_error = error
        if abort_on_error:
            fatal_close(d, error)


def stage_local(d: ConvergeTransactionDomain, node_id: str, op_id: str,
                request_id: str, resource: str, amount: int,
                dedup_capable: bool = False, idempotent: bool = False,
                local_only: bool = False, is_expansion: bool = True) -> str:
    if d.frame_status != SearchStatus.SEARCHING:
        raise TransitionError("StageLocal outside Searching frame")

    # Sequential in-flight: cannot stage a new request if an unsettled handle exists
    unsettled = [s for s in d.handles.values() if s.settlement is None and s.state != "Aborted"]
    if unsettled:
        raise TransitionError("sequential in-flight: previous request still unsettled (I1/R7)")

    # I4 guard: rejection must leave committed/reserved deltas at zero.
    # R12/R15: headroom accounts for both committed AND spent in BudgetScope
    available = d.intent_available.get(resource, 0)
    scope_head = d.scope_limit.get(resource, 0) - d.scope_spent.get(resource, 0) - d.scope_committed.get(resource, 0)
    if amount > available or amount > scope_head or amount < 0:
        raise TransitionError("StageLocal.Rejected")   # caller sees rejection; no deltas move

    d.intent_available[resource] = available - amount
    d.intent_reserved[resource] = d.intent_reserved.get(resource, 0) + amount
    d.scope_committed[resource] = d.scope_committed.get(resource, 0) + amount
    d.outbox[request_id] = OutboxRecord(
        request_id=request_id, op_id=op_id, payload_digest=f"digest({node_id})",
        dedup_capable=dedup_capable, idempotent=idempotent,
        node_id=node_id, local_only=local_only,
        reserved_resource=resource, reserved_amount=amount,
        is_expansion=is_expansion,
    )

    # R15: StageLocal creates stable InFlightHandle atomically with reservation and outbox
    handle_id = next_id("h")
    st = InFlightLifecycleState(
        handle_id=handle_id, request_id=request_id, state="Staged",
        reserved_resource=resource, reserved_amount=amount,
    )
    d.handles[handle_id] = st
    d.current_in_flight = st
    return handle_id


# ---------------------------------------------------------------------
# EmitExternal — first logical emission consumes fuel; transport retries do not.
# ---------------------------------------------------------------------

def emit_external(d: ConvergeTransactionDomain, request_or_handle_id: str,
                  deliver_unknown: bool = False) -> str:
    if d.frame_status != SearchStatus.SEARCHING:
        raise TransitionError("EmitExternal outside Searching frame")

    # Find the handle by handle_id or request_id
    st = d.handles.get(request_or_handle_id)
    if st is None:
        hid = _find_handle_by_request(d, request_or_handle_id)
        if hid:
            st = d.handles.get(hid)

    request_id = st.request_id if st else request_or_handle_id
    rec = d.outbox.get(request_id)
    if rec is None:
        raise TransitionError("no staged record for request")

    if st is None:
        handle_id = next_id("h")
        st = InFlightLifecycleState(
            handle_id=handle_id, request_id=request_id,
            reserved_resource=rec.reserved_resource, reserved_amount=rec.reserved_amount,
        )
        d.handles[handle_id] = st
    else:
        handle_id = st.handle_id

    if request_id not in d.first_emission_flags:
        d.first_emission_flags[request_id] = True
        st.state = "InFlight"
        if rec.is_expansion:
            # First logical emission of a space expansion: consumes step fuel,
            # advances node to EXPANDING, records visitation (I9, T03).
            d.step_count += 1
            node_id = rec.node_id or _node_for_op(d, rec.op_id)
            d.nodes[node_id] = SearchNode(node_id, NodeStatus.EXPANDING)
            visit_key = f"{rec.op_id}:{node_id}"
            visit_no = sum(1 for v in d.visited if v.visit_key == visit_key) + 1
            d.visited.append(VisitedRecord(visit_key, node_id, rec.op_id, visit_no))
            # R29: bind VisitedRecord to explicit DispatchRecord for external expansion
            d.dispatches.append(DispatchRecord(node_id, rec.op_id, visit_no, "External"))
            if node_id in d.frontier:
                d.frontier.remove(node_id)
        else:
            # R26: Effectful CheckSatisfaction commit point -> satisfaction_attempts increments here
            d.satisfaction_attempts += 1
    else:
        # Transport retry (T04): only legal with adapter guarantees (T04B).
        if st is not None and st.delivery_unknown:
            if not (rec.dedup_capable or rec.idempotent):
                raise TransitionError("BLIND RETRY PROHIBITED (T04B)")
            st.transport_attempts += 1
        else:
            raise TransitionError("re-emission without DeliveryUnknown")

    st.delivery_unknown = deliver_unknown
    d.current_in_flight = st
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
    if existing is not None:
        if existing.digest != digest:
            # T07B: contradictory digest on same handle -> fatal equivocation
            fatal_close(d, f"receipt equivocation on {handle_id}")
            raise FatalInvariantViolation(f"receipt equivocation on {handle_id}")
        else:
            # Idempotent duplicate delivery of identical completion
            return

    if st.state not in ("InFlight", "DeliveryUnknown"):
        raise TransitionError(f"completion admitted in invalid state '{st.state}' — must be InFlight or DeliveryUnknown")

    comp = CompletionRecord(handle_id=handle_id, receipt_id=receipt_id,
                            digest=digest, outcome=outcome)
    d.completions[f"{handle_id}:{receipt_id}"] = comp
    st.completion = comp
    st.state = "Delivered"


# ---------------------------------------------------------------------
# settle — ledger reconciliation exactly once (I7); works from Delivered
# ---------------------------------------------------------------------

def settle(d: ConvergeTransactionDomain, handle_id: str, resource: str, amount: int) -> None:
    st = d.handles.get(handle_id)
    if st is None:
        raise TransitionError("settlement for unknown handle")
    if st.settlement is not None:
        return          # idempotent: duplicate settlement reconciles nothing extra

    if st.state != "Delivered":
        raise TransitionError(f"settle called in invalid state '{st.state}' — must be Delivered")

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
# apply — semantic incorporation, exactly once per completion (I6, R27)
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
    if mutate_frontier and d.frame_status in (SearchStatus.CLOSING, SearchStatus.CANCELLED,
                                              SearchStatus.FAILED, SearchStatus.EXHAUSTED):
        raise TransitionError("I8: frontier mutation during Closing")
    st.applied = True
    st.state = "Applied"
    c_id = f"{handle_id}:{st.completion.receipt_id}" if st.completion else handle_id
    d.applied_completions.append(c_id)
    return True


def apply_space_completion(d: ConvergeTransactionDomain, handle_id: str,
                           succs: list[str]) -> bool:
    """R27: Atomic space completion incorporation.

    Atomically applies handle AND adds discovered successors to frontier.
    Handle is never Applied without its successors being discovered.
    """
    st = d.handles.get(handle_id)
    if st is None:
        raise TransitionError("apply for unknown handle")
    if st.applied:
        return False
    if st.state != "Settled":
        raise TransitionError(f"apply_space_completion called in invalid state '{st.state}' — must be Settled")

    # Discover successors into frontier & nodes
    discover_successors(d, succs)

    st.applied = True
    st.state = "Applied"
    c_id = f"{handle_id}:{st.completion.receipt_id}" if st.completion else handle_id
    d.applied_completions.append(c_id)
    return True


def apply_satisfier_completion(d: ConvergeTransactionDomain, handle_id: str,
                               node_id: str, op_id: str, satisfied: bool,
                               value: object = None, error: str = None,
                               abort_on_error: bool = False) -> bool:
    """R27: Atomic satisfier completion incorporation.

    Atomically applies satisfier handle AND registers satisfaction outcome.
    """
    st = d.handles.get(handle_id)
    if st is None:
        raise TransitionError("apply for unknown handle")
    if st.applied:
        return False
    if st.state != "Settled":
        raise TransitionError(f"apply_satisfier_completion called in invalid state '{st.state}' — must be Settled")

    if satisfied:
        d.satisfied_value = value
        d.frame_status = SearchStatus.SATISFIED
        d.current_in_flight = None
    elif error is not None:
        d.satisfier_error = error
        if abort_on_error:
            fatal_close(d, error)

    st.applied = True
    st.state = "Applied"
    c_id = f"{handle_id}:{st.completion.receipt_id}" if st.completion else handle_id
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


def exhaust(d: ConvergeTransactionDomain) -> None:
    """Natural exhaustion: frontier drained / fuel out without satisfaction."""
    if d.frame_status != SearchStatus.SEARCHING:
        return
    unsettled = [s for s in d.handles.values() if s.settlement is None]
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
                 if s.settlement is None and s.state != "Aborted"]
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
# Recovery — forward only; observes pre-state OR committed post-state (T08/T09)
# ---------------------------------------------------------------------

def recover(d: ConvergeTransactionDomain, snapshot: ConvergeTransactionDomain,
            crash_point: str) -> None:
    """Forward recovery from a durable snapshot taken before the crash.

    T08: settlement record persisted but semantic application lost → re-apply once.
    T09: crash during semantic apply loop → domain resumes from pre-state snapshot
    or committed post-state, never partial (transactional atomicity).
    """
    if crash_point == "after_settlement_before_apply":
        # Restore durable state, then forward-apply exactly once.
        restored = snapshot.copy()
        for hid, st in restored.handles.items():
            if st.settlement is not None and not st.applied:
                live = d.handles.get(hid) or st
                live.applied = True
                live.state = "Applied"
    elif crash_point == "mid_apply_loop":
        # R22: Transactional atomicity — if crash happened mid-apply,
        # reset uncommitted partial RAM state back to pre-state durable snapshot
        d.nodes.clear()
        d.nodes.update({k: replace(v) for k, v in snapshot.nodes.items()})
        d.frontier.clear()
        d.frontier.extend(snapshot.frontier)
        for hid, st in snapshot.handles.items():
            if hid in d.handles:
                d.handles[hid].applied = st.applied
                d.handles[hid].state = st.state
