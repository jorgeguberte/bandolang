"""test_scenarios.py — Campaign 1: the 13 adversarial scenarios T01–T11.

Genealogy preserved: T04 split into A/B, T07B and T11 added from cross-review.
Every step runs under the Harness, which checks all invariants after each
transition. A scenario passes only if every expected property holds.

Run: python test_scenarios.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from model import (
    CompletionRecord, ConvergeTransactionDomain, SearchNode, SearchStatus,
    SettlementRecord,
)
from harness import CrashInjected, Harness
from invariants import InvariantViolation
import transitions as tx

PASS, FAIL = 0, 0


def scenario(name: str):
    print(f"\n--- {name}")
    def deco(fn):
        global PASS, FAIL
        try:
            fn()
            print(f"  \u2713 PASS {name}")
            PASS += 1
        except (AssertionError, InvariantViolation) as e:
            print(f"  \u2717 FAIL {name}: {e}")
            FAIL += 1
        return fn
    return deco


def new_domain() -> tuple[ConvergeTransactionDomain, Harness]:
    d = ConvergeTransactionDomain()
    d.scope_limit["usd"] = 100
    d.intent_initial_total["usd"] = 100
    d.intent_available["usd"] = 100
    return d, Harness(d)


def assert_true(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


# =====================================================================

@scenario("T01_STAGE_REJECT")
def t01():
    d, h = new_domain()
    try:
        h.step("stage(reject)", tx.stage_local, "n1", "op1", "r1", "usd", 999)
        raise AssertionError("oversized stage was accepted")
    except tx.TransitionError:
        pass
    assert_true(d.step_count == 0, "fuel changed on rejection")
    assert_true(len(d.visited) == 0, "visited recorded on rejection")
    assert_true(not d.handles, "handle allocated on rejection")
    assert_true(all(v == 0 for v in d.scope_committed.values()), "commitment persisted")
    assert_true(len(h.bk.reservations_created_by_cf) == 0, "phantom reservation in bookkeeping on rejection")


@scenario("T02_CANCEL_AFTER_STAGE_BEFORE_EMIT")
def t02():
    d, h = new_domain()
    h.step("stage", tx.stage_local, "n1", "op1", "r1", "usd", 10)
    h.step("cancel", tx.cancel)
    assert_true(d.frame_status == SearchStatus.CLOSING, "not closing after cancel")
    # Outbox aborted: emit after cancel must refuse
    try:
        h.step("emit-after-cancel", tx.emit_external, "r1")
        raise AssertionError("emit allowed after cancel")
    except tx.TransitionError:
        pass
    assert_true(d.step_count == 0, "steps counted despite cancel-before-emit")
    # Lowered cancel automatically releases staged reservation and clears in-flight:
    assert_true(d.intent_available["usd"] == 100, f"available not refunded on cancel: {d.intent_available}")
    assert_true(d.intent_reserved.get("usd", 0) == 0, "reserved not cleared on cancel")
    assert_true(d.scope_committed.get("usd", 0) == 0, "scope commitment not cleared on cancel")
    h.step("drain", tx.finish_if_drained)
    assert_true(d.frame_status == SearchStatus.CANCELLED,
                f"R2: cancelled frame must terminalize Cancelled, got {d.frame_status}")


@scenario("T03_FIRST_EMIT")
def t03():
    d, h = new_domain()
    h.step("stage", tx.stage_local, "node:opX", "opX", "r1", "usd", 10)
    before_steps = d.step_count
    handle = h.step("first-emit", tx.emit_external, "r1")
    assert_true(d.step_count == before_steps + 1, "fuel not incremented exactly once")
    assert_true(any(nd.status == "Expanding" for nd in d.nodes.values()), "node not Expanding")
    assert_true(len(d.visited) == 1, "visit not recorded")


@scenario("T04A_TRANSPORT_RETRY_SAFE")
def t04a():
    d, h = new_domain()
    h.step("stage(dedup)", tx.stage_local, "node:opY", "opY", "r1", "usd", 10,
           dedup_capable=True)
    handle = h.step("emit-unknown", tx.emit_external, "r1", deliver_unknown=True)
    steps_before = d.step_count
    visited_before = len(d.visited)
    # DeliveryUnknown with dedup-capable adapter → retry same request_id
    h.step("retry-safe", tx.emit_external, "r1")
    assert_true(d.step_count == steps_before, "fuel debited on transport retry")
    assert_true(len(d.visited) == visited_before, "visited re-recorded on retry")
    assert_true(sum(s.transport_attempts for s in d.handles.values()) > len(d.handles),
                "transport attempt counter not tracked separately")


@scenario("T04B_TRANSPORT_RETRY_UNSAFE")
def t04b():
    d, h = new_domain()
    h.step("stage(no-dedup)", tx.stage_local, "node:opZ", "opZ", "r2", "usd", 10,
           dedup_capable=False, idempotent=False)
    handle = h.step("emit-unknown", tx.emit_external, "r2", deliver_unknown=True)
    try:
        h.step("blind-retry", tx.emit_external, "r2")
        raise AssertionError("blind retry was permitted without guarantees")
    except tx.TransitionError as e:
        assert_true("BLIND RETRY" in str(e), f"wrong refusal: {e}")
    st = d.handles[handle]
    assert_true(st.delivery_unknown and st.settlement is None,
                "commitment not preserved while waiting")


@scenario("T05_DELIVERY_UNKNOWN_RETAINS_COMMITMENT")
def t05():
    d, h = new_domain()
    h.step("stage", tx.stage_local, "node:op5", "op5", "r5", "usd", 20)
    handle = h.step("emit-unknown", tx.emit_external, "r5", deliver_unknown=True)
    assert_true(d.scope_committed["usd"] == 20, "commitment released on DeliveryUnknown")


@scenario("T06_DUPLICATE_COMPLETION")
def t06():
    d, h = new_domain()
    h.step("stage", tx.stage_local, "node:op6", "op6", "r6", "usd", 15)
    handle = h.step("emit", tx.emit_external, "r6")
    h.step("deliver", tx.admit_completion, handle, "rcpt-1", "digest-A")
    ledger_before = dict(d.scope_spent)
    h.step("settle", tx.settle, handle, "usd", 15)
    after_once = dict(d.scope_spent)
    h.step("duplicate-settle", tx.settle, handle, "usd", 15)   # duplicate delivery
    assert_true(after_once == d.scope_spent, "ledger mutated twice for one completion")
    h.step("apply", tx.apply_semantic, handle)
    graph_state = dict(d.nodes)
    h.step("apply-again", tx.apply_semantic, handle)
    assert_true(graph_state == d.nodes, "graph transitioned twice")


@scenario("T07_RECEIPT_EQUIVOCATION")
def t07():
    d, h = new_domain()
    h.step("stage", tx.stage_local, "node:op7", "op7", "r7", "usd", 5)
    handle = h.step("emit", tx.emit_external, "r7")
    h.step("deliver-A", tx.admit_completion, handle, "rcpt-A", "digest-X")
    try:
        h.step("deliver-B-conflict", tx.admit_completion, handle, "rcpt-B", "digest-Y")
        raise AssertionError("equivocating receipt accepted without violation")
    except tx.FatalInvariantViolation:
        pass
    # Durable evidence of the conflict exists NOW (T07B precondition)
    assert_true(len(d.protocol_violations) > 0, "no durable violation evidence")


@scenario("T07B_EQUIVOCATION_CRASH")
def t07b():
    """R22: Crash after durable conflict commit, before fatal control flow completes.
    Recovery MUST reconstruct from durable state: conflict and obligations survive."""
    d, h = new_domain()
    h.step("stage", tx.stage_local, "node:op8", "op8", "r8", "usd", 5)
    handle = h.step("emit", tx.emit_external, "r8")
    h.step("deliver-A", tx.admit_completion, handle, "rcpt-A", "digest-X")

    # Conflict arrives on receipt B: admitted + persisted violation + fatal_close raised
    try:
        h.step("deliver-B", tx.admit_completion, handle, "rcpt-B", "digest-Y")
    except tx.FatalInvariantViolation:
        pass

    # Take durable post-conflict crash snapshot
    durable_crash_snapshot = h.snapshot()

    # Simulate fresh process recovery from durable storage:
    d_recovered = durable_crash_snapshot.copy()
    h_rec = Harness(d_recovered)

    assert_true(len(d_recovered.protocol_violations) > 0,
                "conflict evidence lost across crash -- contradiction did not survive")
    assert_true(d_recovered.closing_reason.kind == "PendingFailure",
                "recovery not in PendingFailure")
    assert_true(d_recovered.handles[handle].settlement is None,
                "unsettled obligation lost across crash")
    assert_true(d_recovered.intent_reserved["usd"] == 5,
                "reserved commitment lost across crash")

    # Late settlement on recovered domain reconciles ledger exactly once:
    h_rec.step("late-settle", tx.settle, handle, "usd", 5)
    h_rec.step("drain", tx.finish_if_drained)
    assert_true(d_recovered.frame_status == SearchStatus.FAILED,
                f"expected Failed after drain, got {d_recovered.frame_status}")


@scenario("T08_CRASH_AFTER_SETTLEMENT")
def t08():
    d, h = new_domain()
    h.step("stage", tx.stage_local, "node:op9", "op9", "r9", "usd", 25)
    handle = h.step("emit", tx.emit_external, "r9")
    h.step("deliver", tx.admit_completion, handle, "rcpt-8", "digest-8")
    h.step("settle", tx.settle, handle, "usd", 25)
    snapshot = h.snapshot()   # durable: settlement record persisted
    try:
        h.inject_crash("after_settlement_before_apply")
        raise AssertionError("crash injection failed to fire")
    except CrashInjected:
        pass
    # forward recovery: settlement survives, application happens exactly once
    st = d.handles[handle]
    assert_true(st.settlement is not None, "settlement record lost in recovery")
    from transitions import recover
    recover(d, snapshot, "after_settlement_before_apply")
    assert_true(st.applied and st.state == "Applied", "recovery did not forward-apply")
    # applying again is still a no-op (exactly-once)
    h.step("apply-idempotent", tx.apply_semantic, handle)


@scenario("T09_CRASH_DURING_SEMANTIC_APPLY")
def t09():
    """R22: Crash mid-apply loop resets uncommitted partial RAM state back to durable pre-state."""
    d, h = new_domain()
    h.step("stage", tx.stage_local, "node:op10", "op10", "r10", "usd", 30)
    handle = h.step("emit", tx.emit_external, "r10")
    h.step("deliver", tx.admit_completion, handle, "rcpt-9", "digest-9")
    h.step("settle", tx.settle, handle, "usd", 30)
    pre_state = h.snapshot()

    # Simulate partial uncommitted apply mutation in RAM
    d.nodes["partial_node"] = SearchNode("partial_node", "Partial")
    d.frontier.append("partial_node")

    # Recover resets uncommitted partial state
    from transitions import recover
    recover(d, pre_state, "mid_apply_loop")

    assert_true("partial_node" not in d.nodes, "partial node leaked after recovery")
    assert_true(list(d.frontier) == list(pre_state.frontier), "frontier corrupted after recovery")
    assert_true(not d.handles[handle].applied, "applied flag incorrectly set before committed apply")

    # Now apply cleanly to commit
    h.step("apply-clean", tx.apply_semantic, handle)
    assert_true(d.handles[handle].applied and d.handles[handle].state == "Applied", "clean apply failed")


@scenario("T10_CANCEL_WHILE_IN_FLIGHT")
def t10():
    d, h = new_domain()
    h.step("stage", tx.stage_local, "node:op11", "op11", "r11", "usd", 40)
    handle = h.step("emit", tx.emit_external, "r11")
    h.step("deliver", tx.admit_completion, handle, "rcpt-10", "digest-10")
    h.step("cancel", tx.cancel)
    assert_true(d.frame_status == SearchStatus.CLOSING, "not Closing after cancel")
    frontier_before = list(d.frontier)
    # late settlement STILL processes in the ledger
    h.step("late-settle", tx.settle, handle, "usd", 40)
    assert_true(d.scope_spent["usd"] == 40, "late settlement not reconciled")
    # payload discarded without frontier advance: an apply attempt that would
    # mutate the frontier is REFUSED during Closing (I8 guard fires)
    try:
        h.step("apply-frontier-mutation-refused", tx.apply_semantic, handle, mutate_frontier=True)
        raise AssertionError("frontier mutation allowed during Closing")
    except tx.TransitionError as e:
        assert_true("I8" in str(e), f"wrong refusal: {e}")
    h.step("drain", tx.finish_if_drained)
    assert_true(d.frame_status == SearchStatus.CANCELLED,
                f"R2: cancelled frame must terminalize Cancelled, got {d.frame_status}")


@scenario("T11_LATE_SETTLEMENT_AFTER_FATAL_CLOSING")
def t11():
    d, h = new_domain()
    h.step("stage", tx.stage_local, "node:op12", "op12", "r12", "usd", 50)
    handle = h.step("emit", tx.emit_external, "r12")
    h.step("deliver", tx.admit_completion, handle, "rcpt-11", "digest-11")
    # fatal failure occurs with in-flight obligation H
    h.step("fatal-close", tx.fatal_close, "FatalInvariantViolation")
    reason = d.closing_reason
    assert_true(reason.kind == "PendingFailure" and reason.error == "FatalInvariantViolation",
                f"bad closing reason: {reason}")
    frontier_before = list(d.frontier)
    # later, a valid settlement for H arrives → reconcile exactly once
    h.step("late-settle", tx.settle, handle, "usd", 50)
    h.step("duplicate-late-settle", tx.settle, handle, "usd", 50)
    assert_true(d.scope_spent["usd"] == 50, "settlement reconciled more than once")
    assert_true(d.intent_spent["usd"] == 50, "intent ledger reconciliation wrong")
    # semantic payload discarded; frontier unchanged
    assert_true(list(d.frontier) == frontier_before, "frontier mutated during fatal closing")
    h.step("drain", tx.finish_if_drained)
    assert_true(d.frame_status == SearchStatus.FAILED,
                f"expected Failed(err), got {d.frame_status}")


@scenario("T12_SEQUENTIAL_IN_FLIGHT_REGRESSION")
def t12():
    """R7/R11/R15: staging a new request while a previous request is unsettled MUST fail."""
    d, h = new_domain()
    h.step("stage-1", tx.stage_local, "n1", "op1", "r1", "usd", 10)
    h1 = h.step("emit-1", tx.emit_external, "r1")
    try:
        h.step("stage-2-before-settle", tx.stage_local, "n2", "op2", "r2", "usd", 10)
        raise AssertionError("second request staged while first request unsettled")
    except tx.TransitionError as e:
        assert_true("sequential in-flight" in str(e), f"wrong refusal message: {e}")
    # Settle r1 -> now r2 can be staged and emitted
    h.step("deliver-1", tx.admit_completion, h1, "rc1", "d1")
    h.step("settle-1", tx.settle, h1, "usd", 10)
    h2 = h.step("stage-2-after-settle", tx.stage_local, "n2", "op2", "r2", "usd", 10)
    h.step("emit-2-after-settle", tx.emit_external, "r2")
    assert_true(d.current_in_flight.request_id == "r2", "r2 not admitted after settlement")


@scenario("T13_EXHAUST_WHILE_COMMITMENT_PENDING")
def t13():
    """R13: search exhausts while commitment is pending -> Closing(PendingExhausted) -> drains to Exhausted (never Satisfied)."""
    d, h = new_domain()
    h.step("stage", tx.stage_local, "node:op13", "op13", "r13", "usd", 20)
    handle = h.step("emit", tx.emit_external, "r13")
    h.step("deliver", tx.admit_completion, handle, "rcpt-13", "digest-13")
    # Frontier runs dry or fuel exhausted while commitment is pending:
    h.step("exhaust-pending", tx.exhaust)
    assert_true(d.frame_status == SearchStatus.CLOSING, f"expected Closing, got {d.frame_status}")
    assert_true(d.closing_reason.kind == "PendingExhausted", f"expected PendingExhausted, got {d.closing_reason.kind}")
    # Late settlement arrives:
    h.step("late-settle", tx.settle, handle, "usd", 20)
    # Drain obligations:
    h.step("drain", tx.finish_if_drained)
    assert_true(d.frame_status == SearchStatus.EXHAUSTED, f"expected Exhausted, got {d.frame_status}")


@scenario("T14_SETTLEMENT_EXCEEDS_CEILING")
def t14():
    """R16: settlement charge exceeding ceiling or charging on zero reservation must be refused."""
    d, h = new_domain()
    h.step("stage-10", tx.stage_local, "n14", "op14", "r14", "usd", 10)
    handle = h.step("emit", tx.emit_external, "r14")
    h.step("deliver", tx.admit_completion, handle, "rcpt-14", "digest-14")
    # Charge 15 on ceiling 10 -> raises FatalInvariantViolation
    try:
        h.step("settle-exceeds", tx.settle, handle, "usd", 15)
        raise AssertionError("settlement exceeding ceiling was permitted")
    except tx.FatalInvariantViolation:
        pass
    assert_true(len(d.protocol_violations) > 0, "no protocol violation recorded for settlement exceeding ceiling")

    # Second case: zero reservation cannot settle positive charge
    d2, h2 = new_domain()
    h2.step("stage-0", tx.stage_local, "n14b", "op14b", "r14b", "usd", 0)
    handle2 = h2.step("emit-0", tx.emit_external, "r14b")
    h2.step("deliver-0", tx.admit_completion, handle2, "rcpt-14b", "digest-14b")
    try:
        h2.step("settle-positive-on-zero", tx.settle, handle2, "usd", 5)
        raise AssertionError("settling positive charge on zero reservation was permitted")
    except tx.TransitionError as e:
        assert_true("ChargeOnZeroReservation" in str(e), f"wrong refusal: {e}")


# =====================================================================
print("\n" + "=" * 70)
print(f"CAMPAIGN 1 RESULT: {PASS} scenarios passed, {FAIL} failed (16 total)")
if FAIL:
    sys.exit(1)
print("Phase D lowering survived every adversarial scenario under full invariant checking.")
