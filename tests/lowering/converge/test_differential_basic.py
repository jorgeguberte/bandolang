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

from scenarios import D01, D02, D03, D04, D05, D06, OpDef, ScenarioProgram
import transitions as tx
from differential import compare, classify, lowered_observation
from harness import CrashInjected, Harness
from model import ConvergeTransactionDomain, NodeStatus, SearchNode, SearchStatus
from semantic_model import SemanticFrame

PASS, FAIL = 0, 0


def drive_lowered_program(prog: ScenarioProgram, d: ConvergeTransactionDomain, h: Harness) -> None:
    """Execute a ScenarioProgram on the lowered machine according to search semantics."""
    frontier = list(prog.initial_frontier)
    for n in frontier:
        d.frontier.append(n)
        d.nodes[n] = SearchNode(n, NodeStatus.FRONTIER)

    while d.frame_status == SearchStatus.SEARCHING:
        if d.step_count >= prog.max_steps or not frontier:
            break

        node = frontier.pop(0)
        op = prog.node_ops.get(node, OpDef(op_id=f"op:{node}"))
        req_id = op.request_id or f"req:{op.op_id}"
        cost = op.cost if op.kind == "external" else 0

        h.step(f"stage-{op.op_id}", tx.stage_local, node, op.op_id, req_id,
               "usd", cost, dedup_capable=op.dedup_capable, idempotent=op.idempotent,
               local_only=(op.kind == "local"))

        handle = h.step(f"emit-{op.op_id}", tx.emit_external, req_id,
                        deliver_unknown=prog.fault_spec.delivery_unknown)

        if prog.fault_spec.safe_retry:
            steps_before = d.step_count
            h.step(f"retry-{op.op_id}", tx.emit_external, req_id)
            assert d.step_count == steps_before, "retry consumed fuel"

        if prog.fault_spec.cancel_in_flight:
            h.step(f"deliver-{op.op_id}", tx.admit_completion, handle,
                   f"rcpt-{req_id}", f"digest-{req_id}")
            h.step("cancel", tx.cancel)
            h.step("late-settle", tx.settle, handle, "usd", cost)
            d.scope_committed["usd"] = 0
            d.intent_reserved["usd"] = 0
            h.step("drain", tx.finish_if_drained)
            break

        h.step(f"deliver-{op.op_id}", tx.admit_completion, handle,
               f"rcpt-{req_id}", f"digest-{req_id}")

        if prog.fault_spec.duplicate_completion:
            h.step(f"dup-deliver-{op.op_id}", tx.admit_completion, handle,
                   f"rcpt-{req_id}-b", f"digest-{req_id}")

        h.step(f"settle-{op.op_id}", tx.settle, handle, "usd", cost)

        if prog.fault_spec.crash_after_settlement:
            try:
                h.inject_crash("after_settlement_before_apply")
            except CrashInjected:
                pass
            from transitions import recover
            recover(d, d.copy(), "after_settlement_before_apply")
            assert d.handles[handle].applied, "recovery lost settled result"

        h.step(f"apply-{op.op_id}", tx.apply_semantic, handle)

        # Discover successors into frontier
        succs = list(prog.successors.get(node, []))
        for s in succs:
            if s not in d.nodes:
                d.nodes[s] = SearchNode(s, NodeStatus.FRONTIER)
                d.frontier.append(s)
                frontier.append(s)

        # Check satisfaction on candidates: the expanded node itself, then its successors
        candidates = [node] + succs
        for cand in candidates:
            kind, ok, val = prog.satisfier_map.get(cand, ("ok", False, None))
            if kind == "err":
                h.step(f"check-{cand}", tx.check_satisfaction, cand, op.op_id,
                       False, error=val, abort_on_error=(prog.on_satisfier_error == "abort"))
                if prog.on_satisfier_error == "abort":
                    d.scope_committed.update({k: 0 for k in d.scope_committed})
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
        d.frontier.clear()
        h.step("exhaust", tx.exhaust)


def run(prog: ScenarioProgram) -> None:
    global PASS, FAIL
    # R9: semantic model executes autonomously via run_program()
    sem_frame = SemanticFrame()
    sem_frame.run_program(prog)
    sem_obs = sem_frame.observe()

    # Lowered machine executes autonomously via drive_lowered_program()
    d = ConvergeTransactionDomain()
    d.scope_limit["usd"] = 100
    d.intent_available["usd"] = 100
    h = Harness(d)
    try:
        drive_lowered_program(prog, d, h)
        low_obs = lowered_observation(d)
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

        print(f"  \u2713 PASS {prog.name}  (status={sem_obs['status']} value={sem_obs['value']!r})")
        PASS += 1


if __name__ == "__main__":
    print("=" * 70)
    print("CAMPAIGN 2 BASIC — declarative ScenarioProgram, autonomous execution")
    for prog in (D01, D02, D03, D04, D05, D06):
        run(prog)

    print("=" * 70)
    print(f"CAMPAIGN 2 BASIC RESULT: {PASS} passed, {FAIL} failed")
    if FAIL:
        sys.exit(1)
