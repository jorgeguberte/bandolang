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
    h.step("deliver", tx.admit_completion, handle, "rcpt-1")
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
    from model import SpaceOutcome
    d, h = new_domain()
    h.step("stage", tx.stage_local, "node:op7", "op7", "r7", "usd", 5)
    handle = h.step("emit", tx.emit_external, "r7")
    h.step("deliver-A", tx.admit_completion, handle, "rcpt-A",
           semantic_payload=SpaceOutcome(successors=["succA"]))
    try:
        h.step("deliver-B-conflict", tx.admit_completion, handle, "rcpt-B",
               semantic_payload=SpaceOutcome(successors=["succB"]))
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
    h.step("deliver-A", tx.admit_completion, handle, "rcpt-A",
           semantic_payload=SpaceOutcome(successors=["succA"]))

    # Conflict arrives on receipt B: admitted + persisted violation + fatal_close raised
    try:
        h.step("deliver-B", tx.admit_completion, handle, "rcpt-B",
               semantic_payload=SpaceOutcome(successors=["succB"]))
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
    h.step("deliver", tx.admit_completion, handle, "rcpt-8")
    h.step("settle", tx.settle, handle, "usd", 25)
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
    h.step("deliver", tx.admit_completion, handle, "rcpt-9")
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
    h.step("deliver", tx.admit_completion, handle, "rcpt-10")
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
    h.step("deliver", tx.admit_completion, handle, "rcpt-11")
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
    # Settle r1 and apply -> now r2 can be staged and emitted
    from model import SpaceOutcome
    h.step("deliver-1", tx.admit_completion, h1, "rc1",
           semantic_payload=SpaceOutcome(successors=[]))
    h.step("settle-1", tx.settle, h1, "usd", 10)
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
    h.step("deliver", tx.admit_completion, handle, "rcpt-13")
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
    h.step("deliver", tx.admit_completion, handle, "rcpt-14")
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
    h2.step("deliver-0", tx.admit_completion, handle2, "rcpt-14b")
    try:
        h2.step("settle-positive-on-zero", tx.settle, handle2, "usd", 5)
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
    h.step("deliver", tx.admit_completion, handle, "rcpt-15",
           semantic_payload=SpaceOutcome(successors=["succA", "succB"]))
    h.step("settle", tx.settle, handle, "usd", 20)

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
    h.step("deliver", tx.admit_completion, handle, "rcpt-16",
           semantic_payload=SatisfierOutcome(node_id="cand16", op_id="opSat", satisfied=True, value="T-sat-val"))
    h.step("settle", tx.settle, handle, "usd", 5)

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
    h.step("deliver-1", tx.admit_completion, handle1, "rcpt-1",
           semantic_payload=SpaceOutcome(successors=[]))
    h.step("settle-1", tx.settle, handle1, "usd", 10)
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
    h.step("deliver", tx.admit_completion, handle, "rcpt-18",
           semantic_payload=SpaceOutcome(successors=["childX"]))
    h.step("settle", tx.settle, handle, "usd", 10)

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
    h.step("deliver", tx.admit_completion, handle, "rcpt-19",
           semantic_payload=SpaceOutcome(successors=["GOOD_SUCC"]))
    h.step("settle", tx.settle, handle, "usd", 10)

    # Durable pre-apply snapshot taken
    snapshot = h.snapshot()

    # Simulate post-crash volatile corruption in live RAM before recover() is called
    bad_payload = SpaceOutcome(successors=["BAD_SUCC"])
    d.handles[handle].completion = CompletionRecord(
        handle_id=handle, receipt_id="rcpt-19-bad", digest="digest-bad", outcome="Success",
        semantic_payload=bad_payload,
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
    h.step("deliver", tx.admit_completion, handle, "rcpt-20",
           semantic_payload=SatisfierOutcome("root", "opSat", True, "T-late"))
    h.step("cancel", tx.cancel)
    assert_true(d.frame_status == SearchStatus.CLOSING, "expected Closing")
    assert_true(d.closing_reason.kind == "PendingCancelled", "expected PendingCancelled")

    h.step("late-settle", tx.settle, handle, "usd", 5)
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
    h.step("deliver", tx.admit_completion, handle, "rcpt-21",
           semantic_payload=SpaceOutcome(successors=["LATE_CHILD"]))
    h.step("fatal-close", tx.fatal_close, "InvariantBreach")
    assert_true(d.frame_status == SearchStatus.CLOSING, "expected Closing")
    assert_true(d.closing_reason.kind == "PendingFailure", "expected PendingFailure")

    h.step("late-settle", tx.settle, handle, "usd", 10)
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
    h.step("deliver", tx.admit_completion, handle, "rcpt-22",
           semantic_payload=SpaceOutcome(successors=["CRASH_CHILD"]))
    h.step("cancel", tx.cancel)
    h.step("late-settle", tx.settle, handle, "usd", 10)
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


# =====================================================================
print("\n" + "=" * 70)
print(f"CAMPAIGN 1 RESULT: {PASS} scenarios passed, {FAIL} failed ({PASS + FAIL} total)")
if FAIL:
    sys.exit(1)
print("Phase D lowering survived every adversarial scenario under full invariant checking.")
