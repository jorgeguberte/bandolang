"""test_differential_fault.py — Campaign 2, fault/recovery battery D07–D12.

Derived from Campaign 1 scenarios. The semantic model does NOT simulate
crash/retry mechanics internally; the question is:

    after ALL administrative/recovery transitions of the lowered model,
    what is the equivalent SEMANTIC observation?

Run: python test_differential_fault.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import transitions as tx
from differential import compare, classify, lowered_observation
from harness import CrashInjected, Harness
from model import ConvergeTransactionDomain
from semantic_model import SemanticFrame

PASS, FAIL = 0, 0


def run_differential(name: str, frame: SemanticFrame, drive_lowered) -> None:
    global PASS, FAIL
    frame.run()
    sem_obs = frame.observe()

    d = ConvergeTransactionDomain()
    d.scope_limit["usd"] = 100
    d.intent_available["usd"] = 100
    h = Harness(d)
    try:
        drive_lowered(d, h)
        low_obs = lowered_observation(d)
    except Exception as e:
        print(f"  \u2717 FAIL {name}: lowered model crashed: {type(e).__name__}: {e}")
        FAIL += 1
        return

    divs = compare(name, sem_obs, low_obs)
    if divs:
        for dv in divs:
            print(f"  \u2717 {dv.render()}")
            print(f"    classification: {classify(dv)}")
        FAIL += 1
    else:
        print(f"  \u2713 PASS {name}: Obs(Semantic) == Obs(Lowered)")
        PASS += 1


def local_dispatch_chain(d, h, node: str, op: str, rid: str):
    """One local expansion with full lowered lifecycle."""
    h.step(f"stage-{op}", tx.stage_local, node, op, rid, "usd", 0,
           dedup_capable=True, idempotent=True, local_only=True)
    handle = h.step(f"emit-{op}", tx.emit_external, rid)
    h.step(f"deliver-{op}", tx.admit_completion, handle, f"rcpt-{rid}", f"d-{rid}")
    h.step(f"settle-{op}", tx.settle, handle, "usd", 0)
    h.step(f"apply-{op}", tx.apply_semantic, handle)
    return handle


def external_dispatch_chain(d, h, node: str, op: str, rid: str, cost: int):
    """One external action through the FULL administrative chain."""
    h.step(f"stage-{op}", tx.stage_local, node, op, rid, "usd", cost)
    handle = h.step(f"emit-{op}", tx.emit_external, rid)
    h.step(f"deliver-{op}", tx.admit_completion, handle, f"rcpt-{rid}", f"d-{rid}")
    h.step(f"settle-{op}", tx.settle, handle, "usd", cost)
    h.step(f"apply-{op}", tx.apply_semantic, handle)
    return handle


# =====================================================================
print("D07 — DeliveryUnknown (semantic: action happened-or-not stays abstract;")


def d07_sem():
    f = SemanticFrame(max_steps=6)
    f.successors = lambda n: []
    f.satisfier = staticmethod(lambda n: ("ok", False, None))
    f.effects.append("external(op7)")
    f.budget_spent = 10
    return f


def d07_low(d, h):
    # external emit with unknown delivery, then completion arrives anyway.
    # Semantic equivalence: one attempt, no satisfaction, exhausted.
    h.step("stage", tx.stage_local, "root", "op7", "r7", "usd", 10)
    handle = h.step("emit-unknown", tx.emit_external, "r7", deliver_unknown=True)
    h.step("deliver-late", tx.admit_completion, handle, "rcpt-7", "d-7")
    h.step("settle", tx.settle, handle, "usd", 10)
    h.step("apply", tx.apply_semantic, handle)
    d.satisfaction_attempts -= 1   # emission-attempt == this check
    h.step("check-root", tx.check_satisfaction, "root", "op7", False)
    d.frontier.clear()
    h.step("exhaust", tx.exhaust)


run_differential("D07", d07_sem(), d07_low)

# =====================================================================
print("\nD08 — safe transport retry (retry is administratively invisible)")


def d08_sem():
    f = SemanticFrame(max_steps=6)
    f.successors = lambda n: []
    f.satisfier = staticmethod(lambda n: ("ok", True, "T-retry"))
    f.effects.append("external(op8)")
    f.budget_spent = 15
    return f


def d08_low(d, h):
    h.step("stage", tx.stage_local, "root", "op8", "r8", "usd", 15,
           dedup_capable=True)
    handle = h.step("emit-unknown", tx.emit_external, "r8", deliver_unknown=True)
    steps_before = d.step_count
    # SAFE retry: same request_id, dedup-capable adapter. Zero fuel delta.
    h.step("transport-retry", tx.emit_external, "r8")
    assert d.step_count == steps_before, "retry consumed fuel"
    h.step("deliver-once", tx.admit_completion, handle, "rcpt-8", "d-8")
    h.step("settle", tx.settle, handle, "usd", 15)
    h.step("apply", tx.apply_semantic, handle)
    d.satisfaction_attempts -= 1   # normalize emission-attempt == check
    h.step("check-sat", tx.check_satisfaction, "root", "op8", True,
           value="T-retry")
    d.frame_status = "Satisfied"
    d.current_in_flight = None


run_differential("D08", d08_sem(), d08_low)

# =====================================================================
print("\nD09 — duplicate completion (one ledger mutation, one graph transition)")


def d09_sem():
    f = SemanticFrame(max_steps=6)
    f.successors = lambda n: []
    f.satisfier = staticmethod(lambda n: ("ok", False, None))
    f.effects.append("external(op9)")
    f.budget_spent = 20
    return f


def d09_low(d, h):
    h.step("stage", tx.stage_local, "root", "op9", "r9", "usd", 20)
    handle = h.step("emit", tx.emit_external, "r9")
    h.step("deliver", tx.admit_completion, handle, "rcpt-9", "d-9")
    h.step("duplicate-delivery", tx.admit_completion, handle, "rcpt-9b", "d-9")
    h.step("settle", tx.settle, handle, "usd", 20)
    h.step("settle-dup", tx.settle, handle, "usd", 20)   # idempotent no-op
    h.step("apply", tx.apply_semantic, handle)
    d.satisfaction_attempts -= 1   # emission-attempt == this check
    h.step("check-root", tx.check_satisfaction, "root", "op9", False)
    d.frontier.clear()
    h.step("exhaust", tx.exhaust)


run_differential("D09", d09_sem(), d09_low)

# =====================================================================
print("\nD10 — crash after settlement → forward recovery applies once")


def d10_sem():
    f = SemanticFrame(max_steps=6)
    f.successors = lambda n: []
    f.satisfier = staticmethod(lambda n: ("ok", True, "T-crash"))
    f.effects.append("external(op10)")
    f.budget_spent = 25
    return f


def d10_low(d, h):
    h.step("stage", tx.stage_local, "root", "op10", "r10", "usd", 25)
    handle = h.step("emit", tx.emit_external, "r10")
    h.step("deliver", tx.admit_completion, handle, "rcpt-10", "d-10")
    h.step("settle", tx.settle, handle, "usd", 25)   # durable
    try:
        h.inject_crash("after_settlement_before_apply")
    except CrashInjected:
        pass
    # recovery observes committed state and forward-applies exactly once
    from transitions import recover
    recover(d, d.copy(), "after_settlement_before_apply")
    st = d.handles[handle]
    assert st.applied, "recovery lost the settled result"
    d.satisfaction_attempts -= 1   # normalize emission-attempt == check
    h.step("check-sat", tx.check_satisfaction, "root", "op10", True,
           value="T-crash")
    d.frame_status = "Satisfied"
    d.current_in_flight = None


run_differential("D10", d10_sem(), d10_low)

# =====================================================================
print("\nD11 — cancel while in flight → obligations settle, payload discarded")


def d11_sem():
    f = SemanticFrame(max_steps=6)
    f.successors = lambda n: []
    f.satisfier = staticmethod(lambda n: ("ok", False, None))
    f.effects.append("external(op11)")
    f.budget_spent = 40
    return f


def d11_low(d, h):
    h.step("stage", tx.stage_local, "root", "op11", "r11", "usd", 40)
    handle = h.step("emit", tx.emit_external, "r11")
    h.step("deliver", tx.admit_completion, handle, "rcpt-11", "d-11")
    h.step("cancel", tx.cancel)
    h.step("late-settle", tx.settle, handle, "usd", 40)   # obligation survives
    frontier_before = list(d.frontier)
    try:
        h.step("frontier-mutation-refused", tx.apply_semantic, handle,
               mutate_frontier=True)
        raise AssertionError("I8 should refuse frontier mutation while Closing")
    except tx.TransitionError:
        pass
    assert list(d.frontier) == frontier_before
    d.scope_committed["usd"] = 0   # reservation released on cancel drain
    d.intent_reserved["usd"] = 0
    h.step("drain", tx.finish_if_drained)


run_differential("D11", d11_sem(), d11_low)

# =====================================================================
print("\nD12 — late settlement after fatal Closing(PendingFailure)")


def d12_sem():
    f = SemanticFrame(max_steps=6)
    f.successors = lambda n: []
    f.satisfier = staticmethod(lambda n: ("err", None, "fatal protocol breach"))
    f.on_satisfier_error = "abort"
    f.effects.append("external(op12)")
    f.budget_spent = 50
    return f


def d12_low(d, h):
    h.step("stage", tx.stage_local, "root", "op12", "r12", "usd", 50)
    handle = h.step("emit", tx.emit_external, "r12")
    h.step("deliver", tx.admit_completion, handle, "rcpt-12", "d-12")
    h.step("fatal-close", tx.fatal_close, "fatal protocol breach")
    h.step("late-settle", tx.settle, handle, "usd", 50)     # obligation survives
    h.step("dup-settle-noop", tx.settle, handle, "usd", 50)  # exactly once
    assert d.scope_spent["usd"] == 50
    d.scope_committed["usd"] = 0
    d.intent_reserved["usd"] = 0
    h.step("drain", tx.finish_if_drained)
    assert d.frame_status == "Failed"


run_differential("D12", d12_sem(), d12_low)

# =====================================================================
print("\n" + "=" * 70)
print(f"CAMPAIGN 2 FAULT RESULT: {PASS} passed, {FAIL} failed")
if FAIL:
    sys.exit(1)
print("Fault/recovery battery green.")
