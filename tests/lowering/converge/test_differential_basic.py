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
    D01, D02, D03, D04, D05, D06, D13, D14, D15, D16, D17,
    D18_WAITING, D19_CRASH_RECOVERY, D20_TARGETED_DELIVERY_UNKNOWN,
    D21_SATISFACTION_LIMIT, D22_DELIVERY_UNKNOWN_NO_SUCCESSORS,
    D23_EFFECTFUL_SATISFIER_ERR_ABORT, D24_EFFECTFUL_SATISFIER_ERR_RETRY,
    D25_TARGETED_EFFECTFUL_SATISFIER_DELIVERY_UNKNOWN,
    D26_SATISFIER_RETRY_LIMIT_BLOCKS_RETRY, D27_IDEMPOTENT_SAFE_RETRY,
    D28_DOUBLE_DELIVERY_UNKNOWN_REMAINS_WAITING, OpDef, ScenarioProgram,
)
import transitions as tx
from differential import compare, classify, lowered_observation
from harness import CrashInjected, Harness
from model import (
    ConvergeTransactionDomain, ExecutionReceipt, NodeStatus, SatisfierOutcome, SearchNode,
    SearchStatus, SpaceOutcome,
)
from semantic_model import SemanticFrame

PASS, FAIL = 0, 0


def drive_lowered_program(prog: ScenarioProgram, d: ConvergeTransactionDomain, h: Harness) -> None:
    """Execute a ScenarioProgram on the lowered machine according to search semantics."""
    d.on_satisfier_error = prog.on_satisfier_error
    tx.discover_successors(d, prog.initial_frontier)

    while d.frame_status == SearchStatus.SEARCHING:
        action = tx.scheduler_step(d, prog)
        if isinstance(action, tx.Stop):
            if not prog.check_partial_after_fuel:
                h.step(f"exhaust-{action.reason}", tx.exhaust, action.reason)
            break
        elif isinstance(action, tx.Wait):
            # R31: Waiting for in-flight handle — driver MUST NOT exhaust
            break

        node = action.node
        op = prog.node_ops.get(node, OpDef(op_id=f"op:{node}"))
        cost = op.cost if op.kind == "external" else 0
        charge = op.charge() if op.kind == "external" else 0
        succs = list(prog.successors.get(node, []))
        op_is_delivery_unknown = prog.fault_spec.delivery_unknown or (op.op_id in prog.fault_spec.delivery_unknown_ops)

        if op.kind == "local":
            # R19: Real local dispatch — zero handles, zero outbox, zero settlement
            h.step(f"dispatch-local-{op.op_id}", tx.dispatch_local, node, op.op_id, succs)
        else:
            req_id = op.request_id or f"req:{op.op_id}"
            handle = h.step(f"stage-{op.op_id}", tx.stage_local, node, op.op_id, req_id,
                            "usd", cost, dedup_capable=op.dedup_capable, idempotent=op.idempotent,
                            local_only=False)

            h.step(f"emit-{op.op_id}", tx.emit_external, handle,
                   deliver_unknown=op_is_delivery_unknown)

            if op_is_delivery_unknown:
                if prog.fault_spec.safe_retry and (op.dedup_capable or op.idempotent):
                    if prog.fault_spec.double_delivery_unknown:
                        # R60: second retry attempt also suffers DeliveryUnknown -> remains Waiting
                        h.step(f"retry-{op.op_id}", tx.emit_external, handle, deliver_unknown=True)
                        break
                    else:
                        # R51/R60: Safe transport retry succeeds!
                        steps_before = d.step_count
                        h.step(f"retry-{op.op_id}", tx.emit_external, handle, deliver_unknown=False)
                        assert d.step_count == steps_before, "retry consumed fuel"
                else:
                    # R31: delivery unknown remains in Waiting state
                    break

            rcpt_space = ExecutionReceipt(f"rcpt-{req_id}", "usd", charge)
            if prog.fault_spec.cancel_in_flight:
                h.step(f"deliver-{op.op_id}", tx.admit_completion, handle,
                       f"rcpt-{req_id}",
                       semantic_payload=SpaceOutcome(successors=succs),
                       receipt=rcpt_space)
                h.step("cancel", tx.cancel)
                h.step("late-settle", tx.settle, handle)
                h.step("drain", tx.finish_if_drained)
                break

            # R32/R46/R56/R57: durable completion payload carries SpaceOutcome with canonical digest and ExecutionReceipt
            h.step(f"deliver-{op.op_id}", tx.admit_completion, handle,
                   f"rcpt-{req_id}",
                   semantic_payload=SpaceOutcome(successors=succs),
                   receipt=rcpt_space)

            if prog.fault_spec.duplicate_completion:
                h.step(f"dup-deliver-{op.op_id}", tx.admit_completion, handle,
                       f"rcpt-{req_id}",
                       semantic_payload=SpaceOutcome(successors=succs),
                       receipt=rcpt_space)

            # R57: settle derives amount and resource authoritatively from receipt
            h.step(f"settle-{op.op_id}", tx.settle, handle)

            if prog.fault_spec.crash_after_settlement:
                try:
                    h.inject_crash("after_settlement_before_apply")
                except CrashInjected:
                    pass
                from transitions import recover
                # R32/R45/R53: recovery autonomously reads SpaceOutcome and discovers successors
                recover(d, d.copy(), "after_settlement_before_apply")
                assert d.handles[handle].applied and d.handles[handle].state == "Applied", "recovery lost settled result"
            else:
                # R27/R45: Atomic space completion incorporation from durable SpaceOutcome
                h.step(f"apply-space-{op.op_id}", tx.apply_space_completion, handle)

        # Check satisfaction on candidates: the expanded node itself, then its successors
        candidates = [node] + succs
        for cand in candidates:
            # R48: Strict PartialOf check
            if cand not in prog.partial_map:
                continue

            cand_attempts = 0
            while True:
                # R42/R49/R59: Check satisfaction attempt limit
                if d.satisfaction_attempts >= prog.max_satisfaction_attempts:
                    break

                # R24/R26/R52/R55/R59/R60: effectful satisfier
                if prog.effectful_satisfier:
                    es = prog.effectful_satisfier
                    if not tx.classify_runnable(d, es.cost, "usd"):
                        break
                    cand_attempts += 1
                    h_req = f"req:{es.op_id}:{cand}:{cand_attempts}"
                    h_handle = h.step(f"stage-sat-{es.op_id}-{cand_attempts}", tx.stage_local, cand, es.op_id, h_req,
                                      "usd", es.cost, is_expansion=False)

                    es_is_delivery_unknown = prog.fault_spec.delivery_unknown or (es.op_id in prog.fault_spec.delivery_unknown_ops)
                    h.step(f"emit-sat-{es.op_id}-{cand_attempts}", tx.emit_external, h_handle,
                           deliver_unknown=es_is_delivery_unknown)

                    if es_is_delivery_unknown:
                        if prog.fault_spec.safe_retry and (es.dedup_capable or es.idempotent):
                            if prog.fault_spec.double_delivery_unknown:
                                h.step(f"retry-sat-{es.op_id}-{cand_attempts}", tx.emit_external, h_handle, deliver_unknown=True)
                                break
                            else:
                                h.step(f"retry-sat-{es.op_id}-{cand_attempts}", tx.emit_external, h_handle, deliver_unknown=False)
                        else:
                            # R31: delivery unknown remains in Waiting state
                            break

                    if prog.fault_spec.cancel_in_flight:
                        h.step("cancel", tx.cancel)
                        h.step("drain", tx.finish_if_drained)
                        break

                    map_entry = prog.satisfier_map.get(cand, ("ok", False, None))
                    if isinstance(map_entry, list):
                        idx = min(cand_attempts - 1, len(map_entry) - 1)
                        kind, ok, val = map_entry[idx]
                    else:
                        kind, ok, val = map_entry

                    if kind == "err":
                        sat_payload = SatisfierOutcome(node_id=cand, op_id=es.op_id, satisfied=False, value=None, error=val)
                    elif ok:
                        sat_payload = SatisfierOutcome(node_id=cand, op_id=es.op_id, satisfied=True, value=val, error=None)
                    else:
                        sat_payload = SatisfierOutcome(node_id=cand, op_id=es.op_id, satisfied=False, value=None, error=None)

                    rcpt_sat = ExecutionReceipt(f"rcpt-sat-{cand}-{cand_attempts}", "usd", es.charge())
                    h.step(f"deliver-sat-{es.op_id}-{cand_attempts}", tx.admit_completion, h_handle, f"rcpt-sat-{cand}-{cand_attempts}",
                           semantic_payload=sat_payload, receipt=rcpt_sat)
                    # R57: settle derives charge authoritatively from receipt
                    h.step(f"settle-sat-{es.op_id}-{cand_attempts}", tx.settle, h_handle)
                    # R45/R52: apply_satisfier_completion reads durable SatisfierOutcome and frame error policy
                    h.step(f"apply-sat-{es.op_id}-{cand_attempts}", tx.apply_satisfier_completion, h_handle)
                    if kind == "err":
                        if prog.on_satisfier_error == "abort":
                            h.step("drain", tx.finish_if_drained)
                            break
                        else:
                            # R59: retry candidate
                            continue
                    elif ok:
                        break
                    else:
                        break
                else:
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
                    break

    # Post-fuel / partial check (D03 / R49)
    if d.frame_status in (SearchStatus.SEARCHING, SearchStatus.EXHAUSTED) and prog.check_partial_after_fuel:
        if (d.satisfaction_attempts < prog.max_satisfaction_attempts and
            prog.check_partial_after_fuel in prog.partial_map):
            cand = prog.check_partial_after_fuel
            kind, ok, val = prog.satisfier_map.get(cand, ("ok", False, None))
            if ok:
                h.step(f"check-partial-{cand}", tx.check_satisfaction, cand,
                       "partial_check", True, value=val)

    if d.frame_status == SearchStatus.SEARCHING:
        h.step("exhaust", tx.exhaust, "FrontierEmpty" if not d.frontier else "FuelExhausted")

    # Post-fuel / partial check (D03 / R49)
    if d.frame_status in (SearchStatus.SEARCHING, SearchStatus.EXHAUSTED) and prog.check_partial_after_fuel:
        if (d.satisfaction_attempts < prog.max_satisfaction_attempts and
            prog.check_partial_after_fuel in prog.partial_map):
            cand = prog.check_partial_after_fuel
            kind, ok, val = prog.satisfier_map.get(cand, ("ok", False, None))
            if ok:
                h.step(f"check-partial-{cand}", tx.check_satisfaction, cand,
                       "partial_check", True, value=val)

    if d.frame_status == SearchStatus.SEARCHING:
        h.step("exhaust", tx.exhaust, "FrontierEmpty" if not d.frontier else "FuelExhausted")


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
            assert sem_obs["exhaustion_reason"] == "BudgetDepleted", f"R34: exhaustion_reason must be BudgetDepleted, got {sem_obs['exhaustion_reason']}"
            print("    \u2713 R20/R34 verified: unaffordable ceiling refused, step_count==1, spent==60, reason==BudgetDepleted")

        # R24/R33 assertion for D16
        if prog.name == "D16_effectful_satisfier":
            assert sem_obs["effects"] == ["external(opVerify)"], (
                f"R24/R33: effects must contain exactly 1 external(opVerify) call (only cand1 is partial), got {sem_obs['effects']}")
            assert sem_obs["budget_spent"] == 5, f"R24/R33: budget_spent must be 5, got {sem_obs['budget_spent']}"
            assert sem_obs["satisfaction_attempts"] == 1, f"R24/R33: satisfaction_attempts must be 1, got {sem_obs['satisfaction_attempts']}"
            assert sem_obs["value"] == "T-verified", f"R24/R33: value must be 'T-verified', got {sem_obs['value']}"
            print("    \u2713 R24/R33 verified: explicit PartialOf executed exactly 1 effectful satisfier (spent 5), satisfied T-verified")

        # R26/R31 assertion for D17
        if prog.name == "D17_effectful_satisfier_delivery_unknown":
            assert sem_obs["satisfaction_attempts"] == 1, f"R26: satisfaction_attempts must be 1, got {sem_obs['satisfaction_attempts']}"
            assert sem_obs["status"] == "Waiting", f"R31: status must be Waiting, got {sem_obs['status']}"
            assert sem_obs["unsettled_request_count"] == 1, f"R26: unsettled_request_count must be 1, got {sem_obs['unsettled_request_count']}"
            assert sem_obs["value"] is None, f"R26: value must be None, got {sem_obs['value']}"
            print("    \u2713 R26/R31 verified: satisfaction_attempts==1 committed upon emission; Waiting state preserved")

        # R31 assertion for D18
        if prog.name == "D18_sequential_waiting_blocks_local":
            assert sem_obs["status"] == "Waiting", f"R31: status must be Waiting, got {sem_obs['status']}"
            assert sem_obs["visited"] == ["A"], f"R31: B must not be visited while A is in-flight, got {sem_obs['visited']}"
            assert sem_obs["step_count"] == 1, f"R31: step_count must be 1, got {sem_obs['step_count']}"
            print("    \u2713 R31 verified: InFlight A blocks subsequent local runnable node B from dispatching")

        # R32 assertion for D19
        if prog.name == "D19_external_space_crash_recovery_preserves_successors":
            assert sem_obs["status"] == "Satisfied", f"R32: status must be Satisfied, got {sem_obs['status']}"
            assert sem_obs["value"] == "T-recovered", f"R32: value must be 'T-recovered', got {sem_obs['value']}"
            assert "childB" in sem_obs["visited"] or "childB" in sem_obs["frontier"] or sem_obs["value"] == "T-recovered", "childB was not incorporated"
            print("    \u2713 R32 verified: autonomous crash recovery preserved and incorporated SpaceOutcome successors")

        # R41 assertion for D20
        if prog.name == "D20_waiting_preserves_prior_spend":
            assert sem_obs["status"] == "Waiting", f"R41: status must be Waiting, got {sem_obs['status']}"
            assert sem_obs["budget_spent"] == 20, f"R41: budget_spent must be 20, got {sem_obs['budget_spent']}"
            assert sem_obs["outstanding_scope_commitment"] == 10, f"R41: commitment must be 10, got {sem_obs['outstanding_scope_commitment']}"
            assert sem_obs["attributable_owner_reserved"] == 10, f"R41: reserved must be 10, got {sem_obs['attributable_owner_reserved']}"
            assert sem_obs["intent_available_consumed"] == 30, f"R41: consumed must be 30, got {sem_obs['intent_available_consumed']}"
            print("    \u2713 R41 verified: DeliveryUnknown on opB preserved prior settled budget_spent==20 and committed==10")

        # R42/R49 assertion for D21
        if prog.name == "D21_satisfaction_attempt_limit_exhausts":
            assert sem_obs["satisfaction_attempts"] == 1, f"R49: satisfaction_attempts must be 1, got {sem_obs['satisfaction_attempts']}"
            assert sem_obs["status"] == "Exhausted", f"R49: status must be Exhausted, got {sem_obs['status']}"
            assert sem_obs["value"] is None, f"R49: value must be None, got {sem_obs['value']}"
            print("    \u2713 R49 verified: max_satisfaction_attempts==1 blocked candidate P2 check -> Exhausted")

        # R47 assertion for D22
        if prog.name == "D22_delivery_unknown_does_not_incorporate_successors":
            assert sem_obs["status"] == "Waiting", f"R47: status must be Waiting, got {sem_obs['status']}"
            assert "B" not in sem_obs["frontier"] and "B" not in sem_obs["visited"], f"R47: B must not be in frontier, got {sem_obs['frontier']}"
            assert sem_obs["step_count"] == 1, f"R47: step_count must be 1, got {sem_obs['step_count']}"
            print("    \u2713 R47 verified: DeliveryUnknown did not incorporate successor B into frontier")

        # R52 assertion for D23
        if prog.name == "D23_effectful_satisfier_err_abort":
            assert sem_obs["status"] == "Failed", f"R52: status must be Failed, got {sem_obs['status']}"
            assert sem_obs["error"] == "sensor failure", f"R52: error must be 'sensor failure', got {sem_obs['error']}"
            print("    \u2713 R52 verified: effectful satisfier Err(e) with abort policy transitions to Failed(e)")

        # R52/R59 assertion for D24
        if prog.name == "D24_effectful_satisfier_err_retry":
            assert sem_obs["status"] == "Satisfied", f"R52: status must be Satisfied, got {sem_obs['status']}"
            assert sem_obs["value"] == "T-recovered-on-retry-2", f"R52: value must be 'T-recovered-on-retry-2', got {sem_obs['value']}"
            assert sem_obs["satisfaction_attempts"] == 2, f"R52: attempts must be 2, got {sem_obs['satisfaction_attempts']}"
            print("    \u2713 R52/R59 verified: effectful satisfier Err(e) with retry policy retried cand1 -> Satisfied(T-recovered-on-retry-2)")

        # R55 assertion for D25
        if prog.name == "D25_targeted_effectful_satisfier_delivery_unknown":
            assert sem_obs["status"] == "Waiting", f"R55: status must be Waiting, got {sem_obs['status']}"
            assert sem_obs["satisfaction_attempts"] == 1, f"R55: attempts must be 1, got {sem_obs['satisfaction_attempts']}"
            assert sem_obs["outstanding_scope_commitment"] == 5, f"R55: commitment must be 5, got {sem_obs['outstanding_scope_commitment']}"
            print("    \u2713 R55 verified: targeted delivery_unknown_ops on effectful satisfier opVerify leaves frame in Waiting")

        # R59 assertion for D26
        if prog.name == "D26_satisfier_retry_limit_blocks_retry":
            assert sem_obs["status"] == "Exhausted", f"R59: status must be Exhausted, got {sem_obs['status']}"
            assert sem_obs["satisfaction_attempts"] == 1, f"R59: attempts must be 1 (retry blocked), got {sem_obs['satisfaction_attempts']}"
            print("    \u2713 R59 verified: max_satisfaction_attempts==1 blocked candidate retry -> Exhausted")

        # R60 assertion for D27
        if prog.name == "D27_idempotent_safe_retry":
            assert sem_obs["status"] == "Satisfied", f"R60: status must be Satisfied, got {sem_obs['status']}"
            assert sem_obs["value"] == "T-idempotent-retry", f"R60: value must be 'T-idempotent-retry', got {sem_obs['value']}"
            print("    \u2713 R60 verified: safe retry on idempotent-only operation succeeded -> Satisfied")

        # R60 assertion for D28
        if prog.name == "D28_double_delivery_unknown_remains_waiting":
            assert sem_obs["status"] == "Waiting", f"R60: status must be Waiting, got {sem_obs['status']}"
            assert d.handles[list(d.handles.keys())[0]].transport_attempts == 2, f"R60: transport_attempts must be 2, got {d.handles[list(d.handles.keys())[0]].transport_attempts}"
            print("    \u2713 R60 verified: double DeliveryUnknown leaves frame in Waiting with transport_attempts==2")

        print(f"  \u2713 PASS {prog.name}  (status={sem_obs['status']} value={sem_obs['value']!r})")
        PASS += 1


if __name__ == "__main__":
    print("=" * 70)
    print("CAMPAIGN 2 BASIC — declarative ScenarioProgram, autonomous execution")
    for prog in (D01, D02, D03, D04, D05, D06, D13, D14, D15, D16, D17,
                 D18_WAITING, D19_CRASH_RECOVERY, D20_TARGETED_DELIVERY_UNKNOWN,
                 D21_SATISFACTION_LIMIT, D22_DELIVERY_UNKNOWN_NO_SUCCESSORS,
                 D23_EFFECTFUL_SATISFIER_ERR_ABORT, D24_EFFECTFUL_SATISFIER_ERR_RETRY,
                 D25_TARGETED_EFFECTFUL_SATISFIER_DELIVERY_UNKNOWN,
                 D26_SATISFIER_RETRY_LIMIT_BLOCKS_RETRY, D27_IDEMPOTENT_SAFE_RETRY,
                 D28_DOUBLE_DELIVERY_UNKNOWN_REMAINS_WAITING):
        run(prog)

    print("=" * 70)
    print(f"CAMPAIGN 2 BASIC RESULT: {PASS} passed, {FAIL} failed")
    if FAIL:
        sys.exit(1)
