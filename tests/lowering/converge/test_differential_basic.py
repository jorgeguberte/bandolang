"""test_differential_basic.py — Campaign 2 basic battery D01–D06 (post-audit round 2).

R8: ScenarioProgram defines search space declaratively; zero scripted traces,
    zero end_state oracles.
R9: SemanticFrame executes purely via its own run_program() method.
R10: D02 preserves: Expand A -> successor B -> CheckSatisfaction(B) -> Satisfied;
     B is NEVER expanded, never in visited, never consumes step fuel.
R4: D03 explicitly asserts step_count == max_steps before partial satisfaction check.

Run: python test_differential_basic.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from scenarios import (
    D01, D02, D03, D04, D05, D06, D13, D14, D15, D16, OpDef, ScenarioProgram,
)
import transitions as tx
from differential import compare, classify, lowered_observation
from harness import CrashInjected, Harness
from model import ConvergeTransactionDomain, NodeStatus, SearchNode, SearchStatus
from semantic_model import SemanticFrame

PASS, FAIL = 0, 0


def drive_lowered_program(prog: ScenarioProgram, d: ConvergeTransactionDomain, h: Harness) -> None:
    """Execute a ScenarioProgram on the lowered machine according to search semantics."""
    tx.discover_successors(d, prog.initial_frontier)

    while d.frame_status == SearchStatus.SEARCHING:
        if d.step_count >= prog.max_steps or not d.frontier:
            break

        node = d.frontier[0]
        op = prog.node_ops.get(node, OpDef(op_id=f"op:{node}"))
        cost = op.cost if op.kind == "external" else 0
        charge = op.charge() if op.kind == "external" else 0
        succs = list(prog.successors.get(node, []))

        if op.kind == "local":
            # R19: Real local dispatch — zero handles, zero outbox, zero settlement
            h.step(f"dispatch-local-{op.op_id}", tx.dispatch_local, node, op.op_id, succs)
        else:
            # R20: Check eligibility before staging
            if not tx.classify_runnable(d, cost, "usd"):
                # Cannot afford node under headroom; pop and continue
                d.frontier.pop(0)
                continue

            req_id = op.request_id or f"req:{op.op_id}"
            handle = h.step(f"stage-{op.op_id}", tx.stage_local, node, op.op_id, req_id,
                            "usd", cost, dedup_capable=op.dedup_capable, idempotent=op.idempotent,
                            local_only=False)

            h.step(f"emit-{op.op_id}", tx.emit_external, handle,
                   deliver_unknown=prog.fault_spec.delivery_unknown)

            if prog.fault_spec.safe_retry:
                steps_before = d.step_count
                h.step(f"retry-{op.op_id}", tx.emit_external, handle)
                assert d.step_count == steps_before, "retry consumed fuel"

            if prog.fault_spec.cancel_in_flight:
                h.step(f"deliver-{op.op_id}", tx.admit_completion, handle,
                       f"rcpt-{req_id}", f"digest-{req_id}")
                h.step("cancel", tx.cancel)
                h.step("late-settle", tx.settle, handle, "usd", charge)
                h.step("drain", tx.finish_if_drained)
                break

            h.step(f"deliver-{op.op_id}", tx.admit_completion, handle,
                   f"rcpt-{req_id}", f"digest-{req_id}")

            if prog.fault_spec.duplicate_completion:
                h.step(f"dup-deliver-{op.op_id}", tx.admit_completion, handle,
                       f"rcpt-{req_id}-b", f"digest-{req_id}")

            h.step(f"settle-{op.op_id}", tx.settle, handle, "usd", charge)

            if prog.fault_spec.crash_after_settlement:
                try:
                    h.inject_crash("after_settlement_before_apply")
                except CrashInjected:
                    pass
                from transitions import recover
                recover(d, d.copy(), "after_settlement_before_apply")
                assert d.handles[handle].applied, "recovery lost settled result"

            h.step(f"apply-{op.op_id}", tx.apply_semantic, handle)
            tx.discover_successors(d, succs)

        # Check satisfaction on candidates: the expanded node itself, then its successors
        candidates = [node] + succs
        for cand in candidates:
            # R24: effectful satisfier
            if prog.effectful_satisfier:
                es = prog.effectful_satisfier
                if not tx.classify_runnable(d, es.cost, "usd"):
                    continue
                h_req = f"req:{es.op_id}:{cand}"
                h_handle = h.step(f"stage-sat-{es.op_id}", tx.stage_local, cand, es.op_id, h_req,
                                  "usd", es.cost, is_expansion=False)
                h.step(f"emit-sat-{es.op_id}", tx.emit_external, h_handle)
                h.step(f"deliver-sat-{es.op_id}", tx.admit_completion, h_handle, f"rcpt-sat-{cand}", f"digest-sat-{cand}")
                h.step(f"settle-sat-{es.op_id}", tx.settle, h_handle, "usd", es.charge())
                h.step(f"apply-sat-{es.op_id}", tx.apply_semantic, h_handle)

            kind, ok, val = prog.satisfier_map.get(cand, ("ok", False, None))
            if kind == "err":
                h.step(f"check-{cand}", tx.check_satisfaction, cand, op.op_id,
                       False, error=val, abort_on_error=(prog.on_satisfier_error == "abort"))
                if prog.on_satisfier_error == "abort":
                    h.step("drain", tx.finish_if_drained)
                    break
            elif ok:
                h.step(f"check-{cand}", tx.check_satisfaction, cand, op.op_id, True, value=val)
                break
            else:
                h.step(f"check-{cand}", tx.check_satisfaction, cand, op.op_id, False)

    # Post-fuel / partial check (D03)
    if d.frame_status == SearchStatus.SEARCHING and prog.check_partial_after_fuel:
        assert d.step_count == prog.max_steps, (
            f"R4 assertion: expected step_count==max_steps ({prog.max_steps}), got {d.step_count}")
        cand = prog.check_partial_after_fuel
        kind, ok, val = prog.satisfier_map.get(cand, ("ok", False, None))
        if ok:
            h.step(f"check-partial-{cand}", tx.check_satisfaction, cand,
                   "partial_check", True, value=val)

    if d.frame_status == SearchStatus.SEARCHING:
        h.step("exhaust", tx.exhaust)


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
        # R19: D01/D02 must assert zero handles, zero outbox, zero settlements
        if prog.name in ("D01_local_expand_exhausted", "D02_expand_successor_satisfied"):
            assert len(d.handles) == 0, f"R19: local op must have 0 handles, got {len(d.handles)}"
            assert len(d.outbox) == 0, f"R19: local op must have 0 outbox records, got {len(d.outbox)}"
            assert len(d.completions) == 0, f"R19: local op must have 0 completions, got {len(d.completions)}"
            print("    \u2713 R19 verified: local expansion has 0 handles, 0 outbox, 0 settlements")

        # Additional R10 specific assertion for D02
        if prog.name == "D02_expand_successor_satisfied":
            assert sem_obs["visited"] == ["A"], f"R10: visited must be ['A'], got {sem_obs['visited']}"
            assert sem_obs["step_count"] == 1, f"R10: step_count must be 1, got {sem_obs['step_count']}"
            assert sem_obs["value"] == "T-value-B", f"R10: value must be 'T-value-B', got {sem_obs['value']}"
            print("    \u2713 R10 verified: B was never expanded, step_count==1, visited==['A']")

        # Additional R4 specific assertion for D03
        if prog.name == "D03_max_steps_partial_still_checked":
            assert sem_obs["step_count"] == 2, f"R4: step_count must reach max_steps (2), got {sem_obs['step_count']}"
            assert sem_obs["value"] == "T-partial", f"R4: value must be 'T-partial', got {sem_obs['value']}"
            print("    \u2713 R4 verified: step_count==max_steps (2) before partial check -> Satisfied(T-partial)")

        # R20 assertion for D15
        if prog.name == "D15_unaffordable_ceiling_refused":
            assert sem_obs["step_count"] == 1, f"R20: step_count must be 1, got {sem_obs['step_count']}"
            assert sem_obs["budget_spent"] == 60, f"R20: spent must be 60, got {sem_obs['budget_spent']}"
            assert sem_obs["status"] == "Exhausted", f"R20: status must be Exhausted, got {sem_obs['status']}"
            print("    \u2713 R20 verified: unaffordable ceiling refused, step_count==1, spent==60")

        # R24 assertion for D16
        if prog.name == "D16_effectful_satisfier":
            assert sem_obs["effects"] == ["external(opVerify)", "external(opVerify)"], (
                f"R24: effects must contain 2 external(opVerify) calls, got {sem_obs['effects']}")
            assert sem_obs["budget_spent"] == 10, f"R24: budget_spent must be 10, got {sem_obs['budget_spent']}"
            assert sem_obs["value"] == "T-verified", f"R24: value must be 'T-verified', got {sem_obs['value']}"
            print("    \u2713 R24 verified: effectful satisfier executed external actions (2 calls, spent 10), satisfied T-verified")

        print(f"  \u2713 PASS {prog.name}  (status={sem_obs['status']} value={sem_obs['value']!r})")
        PASS += 1


if __name__ == "__main__":
    print("=" * 70)
    print("CAMPAIGN 2 BASIC — declarative ScenarioProgram, autonomous execution")
    for prog in (D01, D02, D03, D04, D05, D06, D13, D14, D15, D16):
        run(prog)

    print("=" * 70)
    print(f"CAMPAIGN 2 BASIC RESULT: {PASS} passed, {FAIL} failed")
    if FAIL:
        sys.exit(1)
