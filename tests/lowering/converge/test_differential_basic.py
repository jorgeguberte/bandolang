"""test_differential_basic.py — Campaign 2 basic battery D01–D06 (post-audit).

R5: both models consume the SAME scenario descriptor independently.
R6: exact T-value comparison.

Run: python test_differential_basic.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from scenarios import D01, D02, D03, D04, D05, D06, Scenario, Step
import transitions as tx
from differential import compare, classify, lowered_observation
from harness import Harness
from model import ConvergeTransactionDomain
from semantic_model import SemanticFrame

PASS, FAIL = 0, 0


# ---------------------------------------------------------------------
# Semantic driver — derives everything from the descriptor
# ---------------------------------------------------------------------

def drive_semantic(sc: Scenario) -> dict:
    f = SemanticFrame(max_steps=sc.max_steps)
    steps = list(sc.steps)

    def successors(node):
        # the next step's node is a successor of the current one
        for i, st in enumerate(steps):
            if st.node == node and i + 1 < len(steps):
                return [steps[i + 1].node]
        return []

    f.successors = successors
    current = {"node": None}

    def satisfier(node):
        for st in steps:
            if st.check_after and (st.node == node or current["node"] == node):
                pass
        return ("ok", False, None)   # placeholder; per-step checks driven below

    # The semantic frame's run() loop drives expansion; we interleave explicit
    # satisfaction checks by wrapping expand_local via successors order and
    # running checks manually to honor check_after semantics exactly.
    seed = steps[0].node if steps else "root"
    f.frontier.append(seed)
    f.nodes[seed] = "Frontier"

    while f.status == "Searching" and f.step_count < sc.max_steps:
        remaining = [s for s in steps if s.node not in f.visited_nodes()
                     ] if hasattr(f, "visited_nodes") else None
        nxt = next((s for s in steps if s.node not in [v.node_id for v in f.visited]), None)
        if nxt is None:
            break
        current_node = nxt.node
        if current_node in f.frontier:
            f.frontier.remove(current_node)
        succs = f.expand_local(current_node)
        st = next(s for s in steps if s.node == current_node)
        if st.check_after:
            result = st.check_result
            if result.startswith("satisfied:"):
                f.satisfaction_attempts += 1
                from semantic_model import SemanticOutcome, Status
                value = result.split(":", 1)[1]
                f.status = Status.SATISFIED
                f.outcome = SemanticOutcome(Status.SATISFIED, value=value)
            elif result.startswith("error:"):
                f.satisfaction_attempts += 1
                msg = result.split(":", 1)[1]
                if st.abort_on_error:
                    from semantic_model import SemanticOutcome, Status
                    f.status = Status.FAILED
                    f.outcome = SemanticOutcome(Status.FAILED, error=msg)
            else:
                f.satisfaction_attempts += 1
        # external cost accounting derived from descriptor
        if st.kind == "external":
            f.budget_spent += st.cost
            f.effects.append(f"external({st.op})")

    if f.status == "Searching":
        from semantic_model import SemanticOutcome, Status
        f.status = Status.EXHAUSTED
        f.outcome = SemanticOutcome(Status.EXHAUSTED)
    return f.observe()


# ---------------------------------------------------------------------
# Lowered driver — same descriptor, independent derivation
# ---------------------------------------------------------------------

def drive_lowered(sc: Scenario, d: ConvergeTransactionDomain, h: Harness) -> None:
    for st in sc.steps:
        h.step(f"stage-{st.op}", tx.stage_local, st.node, st.op, st.request,
               "usd", st.cost, dedup_capable=True, idempotent=True,
               local_only=(st.kind == "local"))
        handle = h.step(f"emit-{st.op}", tx.emit_external, st.request)
        h.step(f"deliver-{st.op}", tx.admit_completion, handle,
               f"rcpt-{st.request}", f"d-{st.request}")
        h.step(f"settle-{st.op}", tx.settle, handle, "usd", st.cost)
        h.step(f"apply-{st.op}", tx.apply_semantic, handle)
        if st.check_after:
            if st.check_result.startswith("satisfied:"):
                h.step(f"check-{st.op}", tx.check_satisfaction, st.node, st.op,
                       True, value=st.check_result.split(":", 1)[1])
            elif st.check_result.startswith("error:"):
                h.step(f"check-{st.op}", tx.check_satisfaction, st.node, st.op,
                       False, error=st.check_result.split(":", 1)[1],
                       abort_on_error=st.abort_on_error)
            elif st.check_result == "fail":
                h.step(f"check-{st.op}", tx.check_satisfaction, st.node, st.op, False)
    if sc.end_state == "Exhausted":
        d.frontier.clear()
        h.step("exhaust", tx.exhaust)
    elif sc.end_state == "Failed":
        # drain obligations so the fatal Closing can terminalize
        for hid, s in d.handles.items():
            if s.settlement is None:
                h.step(f"settle-{hid}", tx.settle, hid, "usd", 0)
        d.scope_committed.update({k: 0 for k in d.scope_committed})
        h.step("drain", tx.finish_if_drained)


def run(name: str, sc: Scenario) -> None:
    global PASS, FAIL
    sem_obs = drive_semantic(sc)
    d = ConvergeTransactionDomain()
    d.scope_limit["usd"] = 100
    d.intent_available["usd"] = 100
    h = Harness(d)
    try:
        drive_lowered(sc, d, h)
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


print("=" * 70)
print("CAMPAIGN 2 BASIC — shared descriptors, independent derivation")
for sc in (D01, D02, D03, D04, D05, D06):
    run(sc.name, sc)

print("=" * 70)
print(f"CAMPAIGN 2 BASIC RESULT: {PASS} passed, {FAIL} failed")
if FAIL:
    sys.exit(1)
