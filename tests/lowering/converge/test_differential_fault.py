"""test_differential_fault.py — Campaign 2 fault battery D07–D12 (post-audit).

Shared descriptors; both models derive independently. The semantic model does
NOT simulate crash/retry mechanics — the question remains: after ALL
administrative/recovery transitions of the lowered model, what is the
equivalent semantic observation?

Run: python test_differential_fault.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from scenarios import Scenario, Step
import transitions as tx
from differential import compare, classify, lowered_observation
from harness import CrashInjected, Harness
from model import ConvergeTransactionDomain
from semantic_model import SemanticFrame, SemanticOutcome, Status

PASS, FAIL = 0, 0


def drive_semantic(sc: Scenario) -> dict:
    f = SemanticFrame(max_steps=sc.max_steps)
    steps = list(sc.steps)
    seed = steps[0].node if steps else "root"
    f.frontier.append(seed)
    f.nodes[seed] = "Frontier"

    for st in steps:
        if f.status != "Searching":
            break
        if st.node in f.frontier:
            f.frontier.remove(st.node)
        f.expand_local(st.node)
        if st.kind == "external":
            f.budget_spent += st.cost
            f.effects.append(f"external({st.op})")
        if st.check_after:
            f.satisfaction_attempts += 1
            if st.check_result.startswith("satisfied:"):
                value = st.check_result.split(":", 1)[1]
                f.status = Status.SATISFIED
                f.outcome = SemanticOutcome(Status.SATISFIED, value=value)
            elif st.check_result.startswith("error:"):
                msg = st.check_result.split(":", 1)[1]
                f.status = Status.FAILED
                f.outcome = SemanticOutcome(Status.FAILED, error=msg)

    if sc.cancel_at_end and f.status == "Searching":
        f.status = Status.CANCELLED
        f.outcome = SemanticOutcome(Status.CANCELLED)
    if f.status == "Searching":
        f.status = Status.EXHAUSTED
        f.outcome = SemanticOutcome(Status.EXHAUSTED)
    return f.observe()


def drive_lowered(sc: Scenario, d: ConvergeTransactionDomain, h: Harness,
                  fault: str = None) -> None:
    for i, st in enumerate(sc.steps):
        h.step(f"stage-{st.op}", tx.stage_local, st.node, st.op, st.request,
               "usd", st.cost, dedup_capable=True, idempotent=True,
               local_only=(st.kind == "local"))
        handle = h.step(f"emit-{st.op}", tx.emit_external, st.request,
                        deliver_unknown=(fault in ("delivery_unknown", "safe_retry")
                                         and i == 0))
        if fault == "safe_retry" and i == 0:
            steps_before = d.step_count
            h.step(f"retry-{st.op}", tx.emit_external, st.request)
            assert d.step_count == steps_before, "retry consumed fuel"
        h.step(f"deliver-{st.op}", tx.admit_completion, handle,
               f"rcpt-{st.request}", f"d-{st.request}")
        if fault == "duplicate_completion" and i == 0:
            h.step(f"dup-deliver-{st.op}", tx.admit_completion, handle,
                   f"rcpt-{st.request}b", f"d-{st.request}")   # same digest
        h.step(f"settle-{st.op}", tx.settle, handle, "usd", st.cost)
        if fault == "crash_after_settlement" and i == 0:
            try:
                h.inject_crash("after_settlement_before_apply")
            except CrashInjected:
                pass
            from transitions import recover
            recover(d, d.copy(), "after_settlement_before_apply")
            assert d.handles[handle].applied, "recovery lost settled result"
        h.step(f"apply-{st.op}", tx.apply_semantic, handle)
        if st.check_after:
            if st.check_result.startswith("satisfied:"):
                h.step(f"check-{st.op}", tx.check_satisfaction, st.node, st.op,
                       True, value=st.check_result.split(":", 1)[1])
            elif st.check_result.startswith("error:"):
                h.step(f"check-{st.op}", tx.check_satisfaction, st.node, st.op,
                       False, error=st.check_result.split(":", 1)[1],
                       abort_on_error=st.abort_on_error)
            else:
                h.step(f"check-{st.op}", tx.check_satisfaction, st.node, st.op, False)


def finish_lowered(sc: Scenario, d, h):
    if sc.end_state == "Exhausted":
        d.frontier.clear()
        h.step("exhaust", tx.exhaust)
    elif sc.end_state in ("Failed", "Cancelled"):
        for hid, s in list(d.handles.items()):
            if s.settlement is None:
                h.step(f"late-settle-{hid}", tx.settle, hid, "usd", 0)
        d.scope_committed.update({k: 0 for k in d.scope_committed})
        h.step("drain", tx.finish_if_drained)


def run(name: str, sc: Scenario, fault: str = None) -> None:
    global PASS, FAIL
    sem_obs = drive_semantic(sc)
    d = ConvergeTransactionDomain()
    d.scope_limit["usd"] = 100
    d.intent_available["usd"] = 100
    h = Harness(d)
    try:
        drive_lowered(sc, d, h, fault)
        finish_lowered(sc, d, h)
        low_obs = lowered_observation(d)
    except Exception as e:
        print(f"  \u2717 FAIL {name}: lowered crashed: {type(e).__name__}: {e}")
        FAIL += 1
        return
    divs = compare(name, sem_obs, low_obs)
    if divs:
        for dv in divs:
            print(f"  \u2717 {dv.render()}\n    classification: {classify(dv)}")
        FAIL += 1
    else:
        print(f"  \u2713 PASS {name}  (status={sem_obs['status']} value={sem_obs['value']!r})")
        PASS += 1


# =====================================================================
print("=" * 70)
print("CAMPAIGN 2 FAULT — shared descriptors, independent derivation")

D07 = Scenario(
    name="D07_delivery_unknown",
    max_steps=6,
    steps=[Step("root", "op7", "r7", "external", cost=10,
                check_after=True, check_result="fail")],
    end_state="Exhausted",
)
run(D07.name, D07, fault="delivery_unknown")

D08 = Scenario(
    name="D08_safe_transport_retry",
    max_steps=6,
    steps=[Step("root", "op8", "r8", "external", cost=15,
                check_after=True, check_result="satisfied:T-retry")],
    end_state="Satisfied",
)
run(D08.name, D08, fault="safe_retry")

D09 = Scenario(
    name="D09_duplicate_completion",
    max_steps=6,
    steps=[Step("root", "op9", "r9", "external", cost=20,
                check_after=True, check_result="fail")],
    end_state="Exhausted",
)
run(D09.name, D09, fault="duplicate_completion")

D10 = Scenario(
    name="D10_crash_after_settlement",
    max_steps=6,
    steps=[Step("root", "op10", "r10", "external", cost=25,
                check_after=True, check_result="satisfied:T-crash")],
    end_state="Satisfied",
)
run(D10.name, D10, fault="crash_after_settlement")

D11 = Scenario(
    name="D11_cancel_while_in_flight",
    max_steps=6,
    steps=[Step("root", "op11", "r11", "external", cost=40)],
    cancel_at_end=True,
    end_state="Cancelled",
)


def run_d11():
    global PASS, FAIL
    sem_obs = drive_semantic(D11)
    d = ConvergeTransactionDomain()
    d.scope_limit["usd"] = 100
    d.intent_available["usd"] = 100
    h = Harness(d)
    st = D11.steps[0]
    h.step("stage", tx.stage_local, st.node, st.op, st.request, "usd", st.cost)
    handle = h.step("emit", tx.emit_external, st.request)
    h.step("deliver", tx.admit_completion, handle, f"rcpt-{st.request}", f"d-{st.request}")
    h.step("cancel", tx.cancel)
    h.step("late-settle", tx.settle, handle, "usd", st.cost)
    frontier_before = list(d.frontier)
    try:
        h.step("frontier-mutation-refused", tx.apply_semantic, handle,
               mutate_frontier=True)
        raise AssertionError("I8 should refuse frontier mutation while Closing")
    except tx.TransitionError:
        pass
    assert list(d.frontier) == frontier_before, "frontier advanced during Closing"
    d.scope_committed["usd"] = 0
    d.intent_reserved["usd"] = 0
    h.step("drain", tx.finish_if_drained)
    low_obs = lowered_observation(d)
    # R2: cancellation must be distinguishable from exhaustion
    divs = compare(D11.name, sem_obs, low_obs)
    if divs or low_obs["status"] != "Cancelled":
        for dv in divs:
            print(f"  \u2717 {dv.render()}\n    classification: {classify(dv)}")
        if low_obs["status"] != "Cancelled":
            print(f"  \u2717 R2 VIOLATION: cancelled frame observed as {low_obs['status']!r}")
        FAIL += 1
        return
    print(f"  \u2713 PASS {D11.name}  (status=Cancelled — distinct from Exhausted)")
    PASS += 1


run_d11()

D12 = Scenario(
    name="D12_late_settlement_fatal_closing",
    max_steps=6,
    steps=[Step("root", "op12", "r12", "external", cost=50,
                check_after=True, check_result="error:fatal protocol breach",
                abort_on_error=True)],
    end_state="Failed",
)
run(D12.name, D12)

print("=" * 70)
print(f"CAMPAIGN 2 FAULT RESULT: {PASS} passed, {FAIL} failed")
if FAIL:
    sys.exit(1)
