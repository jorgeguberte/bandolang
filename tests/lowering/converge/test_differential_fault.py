"""test_differential_fault.py — Campaign 2 fault battery D07–D12 (post-audit round 2).

R8: ScenarioProgram defines search space and environmental fault specifications.
R9: SemanticFrame executes purely via its own run_program() method.
R6: exact value comparison.

Run: python test_differential_fault.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from scenarios import D07, D08, D09, D10, D11, D12, ScenarioProgram
from differential import compare, classify, lowered_observation
from harness import Harness
from model import ConvergeTransactionDomain
from semantic_model import SemanticFrame
from test_differential_basic import drive_lowered_program

PASS, FAIL = 0, 0


def run(prog: ScenarioProgram) -> None:
    global PASS, FAIL
    # R9: semantic model executes autonomously via run_program()
    sem_frame = SemanticFrame()
    sem_frame.run_program(prog)
    sem_obs = sem_frame.observe()

    # Lowered machine executes autonomously via drive_lowered_program()
    d = ConvergeTransactionDomain()
    d.scope_limit["usd"] = prog.budget_limit
    d.intent_initial_total["usd"] = 100
    d.intent_available["usd"] = 100
    h = Harness(d)
    try:
        drive_lowered_program(prog, d, h)
        low_obs = lowered_observation(d, bk=h.bk, initial_available=100)
    except Exception as e:
        print(f"  \u2717 FAIL {prog.name}: lowered crashed: {type(e).__name__}: {e}")
        FAIL += 1
        return

    divs = compare(prog.name, sem_obs, low_obs)
    if divs:
        for dv in divs:
            print(f"  \u2717 {dv.render()}\n    classification: {classify(dv)}")
        FAIL += 1
    else:
        # Extra assertion for D11: Cancelled must be distinct from Exhausted
        if prog.name == "D11_cancel_while_in_flight":
            assert sem_obs["status"] == "Cancelled" == low_obs["status"], (
                f"R2: cancellation must observe Cancelled, got sem={sem_obs['status']} low={low_obs['status']}")
            print("    \u2713 R2 verified: status==Cancelled (distinct from Exhausted)")

        # R51 assertion for D08: safe transport retry succeeds and reaches Satisfied(T-retry)
        if prog.name == "D08_safe_transport_retry":
            assert sem_obs["status"] == "Satisfied", f"R51: status must be Satisfied, got {sem_obs['status']}"
            assert sem_obs["value"] == "T-retry", f"R51: value must be 'T-retry', got {sem_obs['value']}"
            assert sem_obs["step_count"] == 1, f"R51: step_count must be 1, got {sem_obs['step_count']}"
            assert sem_obs["visited"] == ["root"], f"R51: visited must be ['root'], got {sem_obs['visited']}"
            h_obj = list(d.handles.values())[0]
            assert h_obj.transport_attempts == 2, f"R51: transport_attempts must be 2, got {h_obj.transport_attempts}"
            print("    \u2713 R51 verified: safe transport retry succeeded on attempt 2 -> Satisfied(T-retry)")

        print(f"  \u2713 PASS {prog.name}  (status={sem_obs['status']} value={sem_obs['value']!r})")
        PASS += 1


print("=" * 70)
print("CAMPAIGN 2 FAULT — declarative ScenarioProgram, autonomous execution")
for prog in (D07, D08, D09, D10, D11, D12):
    run(prog)

print("=" * 70)
print(f"CAMPAIGN 2 FAULT RESULT: {PASS} passed, {FAIL} failed")
if FAIL:
    sys.exit(1)
