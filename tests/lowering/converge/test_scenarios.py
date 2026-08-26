"""test_scenarios.py — Lowered safety and crash recovery scenarios for Campaign 1.

Every scenario builds a ConvergeTransactionDomain, steps through transitions,
asserts invariants after each step, and proves crash/recovery bounds.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from harness import CrashInjected, Harness
from invariants import assert_clean
from model import (
    CompletionRecord, ConvergeTransactionDomain, ExecutionReceipt, InFlightLifecycleState,
    NodeStatus, SatisfactionState, SatisfierOutcome, SearchNode, SearchStatus, SpaceOutcome,
)
import transitions as tx

PASS = 0
FAIL = 0
SCENARIOS = []


def scenario(name: str):
    def deco(fn):
        SCENARIOS.append(name)
        print(f"\n--- {name}")
        global PASS, FAIL
        try:
            fn()
            print(f"  \u2713 PASS {name}")
            PASS += 1
        except Exception as e:
            print(f"  \u2717 FAIL {name}: {e}")
            FAIL += 1
        return fn
    return deco


def new_domain() -> tuple[ConvergeTransactionDomain, Harness]:
    d = ConvergeTransactionDomain()
    d.scope_limit["usd"] = 100
    d.intent_initial_total["usd"] = 100
    d.intent_available["usd"] = 100
    h = Harness(d)
    return d, h


def assert_true(cond: bool, msg: str):
    if not cond:
        raise AssertionError(msg)


@scenario("T01_STAGE_REJECT")
def t01():
    d, h = new_domain()
    # Attempt to reserve 150 when limit is 100 → must be rejected
    try:
        h.step("stage-too-much", tx.stage_local, "node:op1", "op1", "r1", "usd", 150)
        raise AssertionError("should have rejected: limit exceeded")
    except tx.TransitionError:
        pass
    assert_true(d.scope_committed.get("usd", 0) == 0, "committed mutated on reject")
    assert_true(d.intent_available["usd"] == 100, "intent available mutated on reject")


@scenario("T02_CANCEL_AFTER_STAGE_BEFORE_EMIT")
def t02():
    d, h = new_domain()
    h.step("stage", tx.stage_local, "node:op2", "op2", "r2", "usd", 30)
    assert_true(d.intent_reserved["usd"] == 30, "reserved not updated")
    assert_true(d.intent_available["usd"] == 70, "available not decremented")
    # Cancel while handle is Staged (not yet emitted)
    h.step("cancel", tx.cancel)
    # Reservation must be released
    assert_true(d.intent_reserved["usd"] == 0, "reserved not rolled back on cancel")
    assert_true(d.intent_available["usd"] == 100, "available not restored on cancel")
    assert_true(d.scope_committed["usd"] == 0, "committed not rolled back on cancel")
    h.step("drain", tx.finish_if_drained)
    assert_true(d.frame_status == SearchStatus.CANCELLED, "not Cancelled after drain")


@scenario("T03_FIRST_EMIT")
def t03():
    d, h = new_domain()
    h.step("stage", tx.stage_local, "node:op3", "op3", "r3", "usd", 20)
    handle = h.step("emit", tx.emit_external, "r3")
    assert_true(d.step_count == 1, "step_count not incremented on first emit")
    assert_true(len(d.visited) == 1, "visited not recorded on first emit")
    assert_true(d.handles[handle].state == "InFlight", "state not InFlight")


@scenario("T04A_TRANSPORT_RETRY_SAFE")
def t04a():
    d, h = new_domain()
    h.step("stage(dedup)", tx.stage_local, "node:op4", "op4", "r1", "usd", 10,
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
    rcpt = ExecutionReceipt("r6", "rcpt-1", "usd", 15)
    h.step("deliver", tx.admit_completion, handle, "rcpt-1", receipt=rcpt)
    ledger_before = dict(d.scope_spent)
    h.step("settle", tx.settle, handle)
    after_once = dict(d.scope_spent)
    h.step("duplicate-settle", tx.settle, handle)   # duplicate delivery
    assert_true(after_once == d.scope_spent, "ledger mutated twice for one completion")
    h.step("apply", tx.apply_semantic, handle)
    graph_state = dict(d.nodes)
    h.step("apply-again", tx.apply_semantic, handle)
    assert_true(graph_state == d.nodes, "graph transitioned twice")


@scenario("T07_RECEIPT_EQUIVOCATION")
def t07():
    from model import SpaceOutcome
    d, h = new_domain()
    h.step("stage", tx.stage_local, "node:op7", "op7", "r7", "usd", 5)
    handle = h.step("emit", tx.emit_external, "r7")
    rcpt_a = ExecutionReceipt("r7", "rcpt-A", "usd", 5)
    h.step("deliver-A", tx.admit_completion, handle, "rcpt-A",
           semantic_payload=SpaceOutcome(successors=["succA"]), receipt=rcpt_a)
    rcpt_b = ExecutionReceipt("r7", "rcpt-B", "usd", 5)
    try:
        h.step("deliver-B-conflict", tx.admit_completion, handle, "rcpt-B",
               semantic_payload=SpaceOutcome(successors=["succB"]), receipt=rcpt_b)
        raise AssertionError("equivocating receipt accepted without violation")
    except tx.FatalInvariantViolation:
        pass
    # Durable evidence of the conflict exists NOW (T07B precondition)
    assert_true(len(d.protocol_violations) > 0, "no durable violation evidence")


@scenario("T07B_EQUIVOCATION_CRASH")
def t07b():
    """R22: Crash after durable conflict commit, before fatal control flow completes.
    Recovery MUST reconstruct from durable state: conflict and obligations survive."""
    from model import SpaceOutcome
    d, h = new_domain()
    h.step("stage", tx.stage_local, "node:op8", "op8", "r8", "usd", 5)
    handle = h.step("emit", tx.emit_external, "r8")
    rcpt_a = ExecutionReceipt("r8", "rcpt-A", "usd", 5)
    h.step("deliver-A", tx.admit_completion, handle, "rcpt-A",
           semantic_payload=SpaceOutcome(successors=["succA"]), receipt=rcpt_a)

    # Conflict arrives on receipt B: admitted + persisted violation + fatal_close raised
    rcpt_b = ExecutionReceipt("r8", "rcpt-B", "usd", 5)
    try:
        h.step("deliver-B", tx.admit_completion, handle, "rcpt-B",
               semantic_payload=SpaceOutcome(successors=["succB"]), receipt=rcpt_b)
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
    h_rec.step("late-settle", tx.settle, handle)
    h_rec.step("drain", tx.finish_if_drained)
    assert_true(d_recovered.frame_status == SearchStatus.FAILED,
                f"expected Failed after drain, got {d_recovered.frame_status}")


@scenario("T08_CRASH_AFTER_SETTLEMENT")
def t08():
    d, h = new_domain()
    h.step("stage", tx.stage_local, "node:op9", "op9", "r9", "usd", 25)
    handle = h.step("emit", tx.emit_external, "r9")
    rcpt = ExecutionReceipt("r9", "rcpt-8", "usd", 25)
    h.step("deliver", tx.admit_completion, handle, "rcpt-8", receipt=rcpt)
    h.step("settle", tx.settle, handle)
    snapshot = h.snapshot()   # durable: settlement record persisted
    try:
        h.inject_crash("after_settlement_before_apply")
        raise AssertionError("crash injection failed to fire")
    except CrashInjected:
        pass
    # forward recovery: settlement survives, application happens exactly once
    assert_true(d.handles[handle].settlement is not None, "settlement record lost before recovery")
    from transitions import recover
    recover(d, snapshot, "after_settlement_before_apply")
    st = d.handles[handle]
    assert_true(st.applied and st.state == "Applied", "recovery did not forward-apply")
    # applying again is still a no-op (exactly-once)
    h.step("apply-idempotent", tx.apply_semantic, handle)


@scenario("T09_CRASH_DURING_SEMANTIC_APPLY")
def t09():
    """R22: Crash mid-apply loop resets uncommitted partial RAM state back to durable pre-state."""
    d, h = new_domain()
    h.step("stage", tx.stage_local, "node:op10", "op10", "r10", "usd", 30)
    handle = h.step("emit", tx.emit_external, "r10")
    rcpt = ExecutionReceipt("r10", "rcpt-9", "usd", 30)
    h.step("deliver", tx.admit_completion, handle, "rcpt-9", receipt=rcpt)
    h.step("settle", tx.settle, handle)
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
    rcpt = ExecutionReceipt("r11", "rcpt-10", "usd", 40)
    h.step("deliver", tx.admit_completion, handle, "rcpt-10", receipt=rcpt)
    h.step("cancel", tx.cancel)
    assert_true(d.frame_status == SearchStatus.CLOSING, "not Closing after cancel")
    frontier_before = list(d.frontier)
    # late settlement STILL processes in the ledger
    h.step("late-settle", tx.settle, handle)
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
    rcpt = ExecutionReceipt("r12", "rcpt-11", "usd", 50)
    h.step("deliver", tx.admit_completion, handle, "rcpt-11", receipt=rcpt)
    # fatal failure occurs with in-flight obligation H
    h.step("fatal-close", tx.fatal_close, "FatalInvariantViolation")
    reason = d.closing_reason
    assert_true(reason.kind == "PendingFailure" and reason.error == "FatalInvariantViolation",
                f"bad closing reason: {reason}")
    frontier_before = list(d.frontier)
    # later, a valid settlement for H arrives → reconcile exactly once
    h.step("late-settle", tx.settle, handle)
    h.step("duplicate-late-settle", tx.settle, handle)
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
    # Settle r1 and apply -> now r2 can be staged and emitted
    from model import SpaceOutcome
    rcpt1 = ExecutionReceipt("r1", "rc1", "usd", 10)
    h.step("deliver-1", tx.admit_completion, h1, "rc1",
           semantic_payload=SpaceOutcome(successors=[]), receipt=rcpt1)
    h.step("settle-1", tx.settle, h1)
    h.step("apply-1", tx.apply_space_completion, h1)
    h2 = h.step("stage-2-after-settle", tx.stage_local, "n2", "op2", "r2", "usd", 10)
    h.step("emit-2-after-settle", tx.emit_external, "r2")
    assert_true(d.current_in_flight.request_id == "r2", "r2 not admitted after settlement")


@scenario("T13_EXHAUST_WHILE_COMMITMENT_PENDING")
def t13():
    """R13: search exhausts while commitment is pending -> Closing(PendingExhausted) -> drains to Exhausted (never Satisfied)."""
    d, h = new_domain()
    h.step("stage", tx.stage_local, "node:op13", "op13", "r13", "usd", 20)
    handle = h.step("emit", tx.emit_external, "r13")
    rcpt = ExecutionReceipt("r13", "rcpt-13", "usd", 20)
    h.step("deliver", tx.admit_completion, handle, "rcpt-13", receipt=rcpt)
    # Frontier runs dry or fuel exhausted while commitment is pending:
    h.step("exhaust-pending", tx.exhaust)
    assert_true(d.frame_status == SearchStatus.CLOSING, f"expected Closing, got {d.frame_status}")
    assert_true(d.closing_reason.kind == "PendingExhausted", f"expected PendingExhausted, got {d.closing_reason.kind}")
    # Late settlement arrives:
    h.step("late-settle", tx.settle, handle)
    # Drain obligations:
    h.step("drain", tx.finish_if_drained)
    assert_true(d.frame_status == SearchStatus.EXHAUSTED, f"expected Exhausted, got {d.frame_status}")


@scenario("T14_SETTLEMENT_EXCEEDS_CEILING")
def t14():
    """R16: settlement charge exceeding ceiling or charging on zero reservation must be refused."""
    d, h = new_domain()
    h.step("stage-10", tx.stage_local, "n14", "op14", "r14", "usd", 10)
    handle = h.step("emit", tx.emit_external, "r14")
    rcpt_exceeds = ExecutionReceipt("r14", "rcpt-14", "usd", 15)
    h.step("deliver", tx.admit_completion, handle, "rcpt-14", receipt=rcpt_exceeds)
    # Charge 15 on ceiling 10 -> raises FatalInvariantViolation
    try:
        h.step("settle-exceeds", tx.settle, handle)
        raise AssertionError("settlement exceeding ceiling was permitted")
    except tx.FatalInvariantViolation:
        pass
    assert_true(len(d.protocol_violations) > 0, "no protocol violation recorded for settlement exceeding ceiling")

    # Second case: zero reservation cannot settle positive charge
    d2, h2 = new_domain()
    h2.step("stage-0", tx.stage_local, "n14b", "op14b", "r14b", "usd", 0)
    handle2 = h2.step("emit-0", tx.emit_external, "r14b")
    rcpt_zero = ExecutionReceipt("r14b", "rcpt-14b", "usd", 5)
    h2.step("deliver-0", tx.admit_completion, handle2, "rcpt-14b", receipt=rcpt_zero)
    try:
        h2.step("settle-positive-on-zero", tx.settle, handle2)
        raise AssertionError("settling positive charge on zero reservation was permitted")
    except tx.TransitionError as e:
        assert_true("ChargeOnZeroReservation" in str(e), f"wrong refusal: {e}")


@scenario("T15_CRASH_DURING_SPACE_APPLY_RECOVERY")
def t15():
    """R27/R32: Autonomous crash recovery for space completion from durable SpaceOutcome."""
    from model import SpaceOutcome
    d, h = new_domain()
    h.step("stage", tx.stage_local, "n15", "op15", "r15", "usd", 20)
    handle = h.step("emit", tx.emit_external, "r15")
    rcpt = ExecutionReceipt("r15", "rcpt-15", "usd", 20)
    h.step("deliver", tx.admit_completion, handle, "rcpt-15",
           semantic_payload=SpaceOutcome(successors=["succA", "succB"]), receipt=rcpt)
    h.step("settle", tx.settle, handle)

    # Durable pre-apply snapshot
    pre_snap = h.snapshot()

    # Simulate crash before apply commits; recover autonomously reads SpaceOutcome:
    d_rec = pre_snap.copy()
    from transitions import recover
    recover(d_rec, pre_snap, "after_settlement_before_apply")
    assert_true(d_rec.handles[handle].applied and d_rec.handles[handle].state == "Applied", "handle not Applied")
    assert_true("succA" in d_rec.nodes and "succB" in d_rec.nodes, "successors not in nodes")
    assert_true("succA" in d_rec.frontier and "succB" in d_rec.frontier, "successors not in frontier")


@scenario("T16_CRASH_DURING_SATISFIER_APPLY_RECOVERY")
def t16():
    """R27/R32: Autonomous crash recovery for satisfier completion from durable SatisfierOutcome."""
    from model import SatisfierOutcome
    d, h = new_domain()
    h.step("stage", tx.stage_local, "cand16", "opSat", "r16", "usd", 5, is_expansion=False)
    handle = h.step("emit", tx.emit_external, "r16")
    rcpt = ExecutionReceipt("r16", "rcpt-16", "usd", 5)
    h.step("deliver", tx.admit_completion, handle, "rcpt-16",
           semantic_payload=SatisfierOutcome(node_id="cand16", op_id="opSat", satisfied=True, value="T-sat-val"), receipt=rcpt)
    h.step("settle", tx.settle, handle)

    # Durable pre-apply snapshot
    pre_snap = h.snapshot()

    # Simulate crash before apply commits; recover autonomously reads SatisfierOutcome:
    d_rec = pre_snap.copy()
    from transitions import recover
    recover(d_rec, pre_snap, "after_settlement_before_apply")
    assert_true(d_rec.handles[handle].applied and d_rec.handles[handle].state == "Applied", "handle not Applied")
    assert_true(d_rec.frame_status == SearchStatus.SATISFIED, "frame not Satisfied")
    assert_true(d_rec.satisfied_value == "T-sat-val", "satisfied value missing")


@scenario("T17_REQUEST_ID_REUSE_REJECTED")
def t17():
    """R43: StageLocal for a new request must reject a historical request_id before any reservation."""
    from model import SpaceOutcome
    d, h = new_domain()
    h.step("stage-1", tx.stage_local, "n1", "op1", "r_unique", "usd", 10)
    handle1 = h.step("emit-1", tx.emit_external, "r_unique")
    rcpt1 = ExecutionReceipt("r_unique", "rcpt-1", "usd", 10)
    h.step("deliver-1", tx.admit_completion, handle1, "rcpt-1",
           semantic_payload=SpaceOutcome(successors=[]), receipt=rcpt1)
    h.step("settle-1", tx.settle, handle1)
    h.step("apply-1", tx.apply_space_completion, handle1)

    # Now attempt to reuse "r_unique" for a different node / attempt:
    avail_before = d.intent_available["usd"]
    res_before = d.intent_reserved.get("usd", 0)
    comm_before = d.scope_committed.get("usd", 0)
    try:
        h.step("stage-reuse", tx.stage_local, "n2", "op2", "r_unique", "usd", 10)
        raise AssertionError("request_id reuse was permitted")
    except tx.TransitionError as e:
        assert_true("RequestIdAlreadyUsed" in str(e), f"wrong refusal: {e}")

    # Assert zero deltas before rejection
    assert_true(d.intent_available["usd"] == avail_before, "available mutated on rejected reuse")
    assert_true(d.intent_reserved.get("usd", 0) == res_before, "reserved mutated on rejected reuse")
    assert_true(d.scope_committed.get("usd", 0) == comm_before, "committed mutated on rejected reuse")


@scenario("T18_GENERIC_APPLY_REFUSED_ON_TYPED_COMPLETION")
def t18():
    """R38: generic apply_semantic must refuse when handle carries typed SpaceOutcome."""
    from model import SpaceOutcome
    d, h = new_domain()
    h.step("stage", tx.stage_local, "n18", "op18", "r18", "usd", 10)
    handle = h.step("emit", tx.emit_external, "r18")
    rcpt = ExecutionReceipt("r18", "rcpt-18", "usd", 10)
    h.step("deliver", tx.admit_completion, handle, "rcpt-18",
           semantic_payload=SpaceOutcome(successors=["childX"]), receipt=rcpt)
    h.step("settle", tx.settle, handle)

    # Calling generic apply_semantic on typed completion must raise TransitionError:
    try:
        h.step("generic-apply", tx.apply_semantic, handle)
        raise AssertionError("generic apply was accepted on typed completion")
    except tx.TransitionError as e:
        assert_true("generic apply_semantic refused" in str(e), f"wrong refusal: {e}")


@scenario("T19_RECOVERY_SNAPSHOT_AUTHORITATIVE")
def t19():
    """R53: Recovery must redrive exclusively on the durable snapshot state; volatile RAM cannot corrupt recovery."""
    from model import SpaceOutcome, CompletionRecord, SearchNode
    d, h = new_domain()
    h.step("stage", tx.stage_local, "n19", "op19", "r19", "usd", 10)
    handle = h.step("emit", tx.emit_external, "r19")
    rcpt = ExecutionReceipt("r19", "rcpt-19", "usd", 10)
    h.step("deliver", tx.admit_completion, handle, "rcpt-19",
           semantic_payload=SpaceOutcome(successors=["GOOD_SUCC"]), receipt=rcpt)
    h.step("settle", tx.settle, handle)

    # Durable pre-apply snapshot taken
    snapshot = h.snapshot()

    # Simulate post-crash volatile corruption in live RAM before recover() is called
    bad_payload = SpaceOutcome(successors=["BAD_SUCC"])
    d.handles[handle].completion = CompletionRecord(
        handle_id=handle, receipt_id="rcpt-19-bad", digest="digest-bad", outcome="Success",
        semantic_payload=bad_payload, receipt=ExecutionReceipt("r19", "rcpt-19-bad", "usd", 10),
    )
    d.nodes["BAD_SUCC"] = SearchNode("BAD_SUCC", "Expanding")

    # Recover from the durable snapshot
    from transitions import recover
    recover(d, snapshot, "after_settlement_before_apply")

    # Verify that ONLY the durable snapshot outcome (GOOD_SUCC) was incorporated!
    assert_true("GOOD_SUCC" in d.frontier, "GOOD_SUCC not incorporated into frontier")
    assert_true("GOOD_SUCC" in d.nodes, "GOOD_SUCC not incorporated into nodes")
    assert_true("BAD_SUCC" not in d.frontier, "volatile BAD_SUCC leaked into frontier")
    assert_true("BAD_SUCC" not in d.nodes, "volatile BAD_SUCC leaked into nodes")


@scenario("T20_PENDING_CANCELLED_LATE_SATISFACTION_DISCARDED")
def t20():
    """R58: Late satisfaction arriving during Closing(PendingCancelled) is discarded; frame drains to Cancelled."""
    from model import SatisfierOutcome
    d, h = new_domain()
    h.step("stage", tx.stage_local, "root", "opSat", "r20", "usd", 5, is_expansion=False)
    handle = h.step("emit", tx.emit_external, "r20")
    rcpt = ExecutionReceipt("r20", "rcpt-20", "usd", 5)
    h.step("deliver", tx.admit_completion, handle, "rcpt-20",
           semantic_payload=SatisfierOutcome("root", "opSat", True, "T-late"), receipt=rcpt)
    h.step("cancel", tx.cancel)
    assert_true(d.frame_status == SearchStatus.CLOSING, "expected Closing")
    assert_true(d.closing_reason.kind == "PendingCancelled", "expected PendingCancelled")

    h.step("late-settle", tx.settle, handle)
    # Apply satisfier completion during Closing — must safely discard satisfaction outcome!
    h.step("apply-late-satisfaction", tx.apply_satisfier_completion, handle)
    assert_true(d.frame_status == SearchStatus.CLOSING, "status changed during Closing")

    h.step("drain", tx.finish_if_drained)
    assert_true(d.frame_status == SearchStatus.CANCELLED, f"expected Cancelled, got {d.frame_status}")
    assert_true(d.satisfied_value is None, f"satisfied_value leaked: {d.satisfied_value}")


@scenario("T21_PENDING_FAILURE_LATE_SPACE_DISCARDED")
def t21():
    """R58: Late space outcome arriving during Closing(PendingFailure) is discarded; frontier unchanged."""
    from model import SpaceOutcome
    d, h = new_domain()
    h.step("stage", tx.stage_local, "n21", "op21", "r21", "usd", 10)
    handle = h.step("emit", tx.emit_external, "r21")
    rcpt = ExecutionReceipt("r21", "rcpt-21", "usd", 10)
    h.step("deliver", tx.admit_completion, handle, "rcpt-21",
           semantic_payload=SpaceOutcome(successors=["LATE_CHILD"]), receipt=rcpt)
    h.step("fatal-close", tx.fatal_close, "InvariantBreach")
    assert_true(d.frame_status == SearchStatus.CLOSING, "expected Closing")
    assert_true(d.closing_reason.kind == "PendingFailure", "expected PendingFailure")

    h.step("late-settle", tx.settle, handle)
    # Apply space completion during Closing — must discard successors without error
    h.step("apply-late-space", tx.apply_space_completion, handle)
    assert_true("LATE_CHILD" not in d.frontier, "LATE_CHILD mutated frontier during Closing")

    h.step("drain", tx.finish_if_drained)
    assert_true(d.frame_status == SearchStatus.FAILED, f"expected Failed, got {d.frame_status}")


@scenario("T22_RECOVERY_WHILE_CLOSING_DISCARDS_SEMANTIC_PAYLOAD")
def t22():
    """R58: Crash recovery while Closing forward-applies settled handles without mutating frontier or changing Closing reason."""
    from model import SpaceOutcome
    d, h = new_domain()
    h.step("stage", tx.stage_local, "n22", "op22", "r22", "usd", 10)
    handle = h.step("emit", tx.emit_external, "r22")
    rcpt = ExecutionReceipt("r22", "rcpt-22", "usd", 10)
    h.step("deliver", tx.admit_completion, handle, "rcpt-22",
           semantic_payload=SpaceOutcome(successors=["CRASH_CHILD"]), receipt=rcpt)
    h.step("cancel", tx.cancel)
    h.step("late-settle", tx.settle, handle)
    snapshot = h.snapshot()

    # Recover from snapshot while Closing
    from transitions import recover
    recover(d, snapshot, "after_settlement_before_apply")

    assert_true(d.frame_status == SearchStatus.CLOSING, "frame_status corrupted during recovery")
    assert_true(d.closing_reason.kind == "PendingCancelled", "closing_reason corrupted during recovery")
    assert_true("CRASH_CHILD" not in d.frontier, "CRASH_CHILD incorporated during Closing recovery")
    h_rec = Harness(d)
    h_rec.step("drain", tx.finish_if_drained)
    assert_true(d.frame_status == SearchStatus.CANCELLED, f"expected Cancelled, got {d.frame_status}")


@scenario("T23_SATISFACTION_RETRY_SURVIVES_CRASH")
def t23():
    """R59/R61: SatisfactionState.RetryableFailure survives crash and redrives second attempt."""
    from model import SatisfierOutcome
    d, h = new_domain()
    d.on_satisfier_error = "retry"
    h.step("stage-sat-1", tx.stage_local, "cand23", "opSat", "r23-1", "usd", 5, is_expansion=False)
    handle1 = h.step("emit-sat-1", tx.emit_external, "r23-1")
    rcpt1 = ExecutionReceipt("r23-1", "rcpt-23-1", "usd", 5)
    h.step("deliver-sat-1", tx.admit_completion, handle1, "rcpt-23-1",
           semantic_payload=SatisfierOutcome("cand23", "opSat", satisfied=False, error="transient failure"),
           receipt=rcpt1)
    h.step("settle-sat-1", tx.settle, handle1)
    h.step("apply-sat-1", tx.apply_satisfier_completion, handle1)

    assert_true(d.nodes["cand23"].satisfaction_state == SatisfactionState.RETRYABLE_FAILURE, "not RetryableFailure")
    assert_true(d.nodes["cand23"].satisfaction_retries == 1, "retries not 1")

    # Crash after attempt 1
    snapshot = h.snapshot()
    d_rec = snapshot.copy()
    from transitions import recover
    recover(d_rec, snapshot, "after_settlement_before_apply")

    assert_true(d_rec.nodes["cand23"].satisfaction_state == SatisfactionState.RETRYABLE_FAILURE, "recovery lost RetryableFailure")
    assert_true(d_rec.nodes["cand23"].satisfaction_retries == 1, "recovery lost retries counter")

    # Attempt 2 redrives on recovered domain
    h_rec = Harness(d_rec)
    h_rec.step("stage-sat-2", tx.stage_local, "cand23", "opSat", "r23-2", "usd", 5, is_expansion=False)
    handle2 = h_rec.step("emit-sat-2", tx.emit_external, "r23-2")
    rcpt2 = ExecutionReceipt("r23-2", "rcpt-23-2", "usd", 5)
    h_rec.step("deliver-sat-2", tx.admit_completion, handle2, "rcpt-23-2",
               semantic_payload=SatisfierOutcome("cand23", "opSat", satisfied=True, value="T-retry-val"),
               receipt=rcpt2)
    h_rec.step("settle-sat-2", tx.settle, handle2)
    h_rec.step("apply-sat-2", tx.apply_satisfier_completion, handle2)

    assert_true(d_rec.frame_status == SearchStatus.SATISFIED, "expected Satisfied after attempt 2")
    assert_true(d_rec.satisfied_value == "T-retry-val", "satisfied_value mismatch")


@scenario("T24_CONFIRMED_NOT_DELIVERED")
def t24():
    """R65: Transport layer confirms request was not delivered; releases obligations back to domain."""
    d, h = new_domain()
    h.step("stage", tx.stage_local, "node:op24", "op24", "r24", "usd", 20)
    handle = h.step("emit", tx.emit_external, "r24", deliver_unknown=True)
    assert_true(d.frame_status == SearchStatus.WAITING, "expected Waiting")
    assert_true(d.intent_reserved["usd"] == 20, "reserved not 20")
    assert_true(d.scope_committed["usd"] == 20, "committed not 20")

    # ConfirmedNotDelivered transition fires
    h.step("confirm-not-delivered", tx.confirmed_not_delivered, handle)
    assert_true(d.handles[handle].state == "ConfirmedNotDelivered", "state not ConfirmedNotDelivered")
    assert_true(d.intent_reserved["usd"] == 0, "reserved not released on ConfirmedNotDelivered")
    assert_true(d.intent_available["usd"] == 100, "available not restored on ConfirmedNotDelivered")
    assert_true(d.scope_committed["usd"] == 0, "committed not released on ConfirmedNotDelivered")
    assert_true(d.frame_status == SearchStatus.SEARCHING, "frame not returned to Searching")


# =====================================================================
print("\n" + "=" * 70)
print(f"CAMPAIGN 1 RESULT: {PASS} scenarios passed, {FAIL} failed ({PASS + FAIL} total)")
if FAIL:
    sys.exit(1)
print("Phase D lowering survived every adversarial scenario under full invariant checking.")
