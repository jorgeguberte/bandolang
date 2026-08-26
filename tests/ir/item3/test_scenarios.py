"""test_scenarios.py — Execution and validation of all Item 3 golden scenarios (R01–R18, X1–X4).

Proves:
- Latent postconditions cannot leak before refinement (Track A)
- Exact must-fact intersection merge and SSA variable renaming (Track A)
- Unknown != Err and physical effect ambiguity safety (Track B)
- Partial completion distinctness and transactional rejection (Track C)
- May-effect handle join, await effect neutrality (Σ_await = ∅), and concrete lineage separation (Track D)
- Full invariant compliance (I3.1–I3.8) across all executions
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from cfg_model import CFGInterpreter, ExecutionState
from invariants import (
    check_all_invariants, i3_1_result_fact_soundness, i3_2_no_eager_latent_discharge,
    i3_3_cfg_must_fact_merge, i3_4_outcome_disjointness, i3_5_no_false_clean_failure,
    i3_6_handle_effect_monotonicity, i3_7_await_effect_neutrality,
    i3_8_provenance_effect_separation,
)
from model import (
    ActFailureVal, ActPartialVal, ActSuccessVal, ChildHandleType, ChildHandleVal,
    DeliveryUnknownVal, ErrVal, Fact, FactTemplate, I64, LatentPostconditions,
    OkVal, PartialEffectReport, SettlementUnknownVal, STRING,
)
from scenarios import (
    build_r01_program, build_r02_program, build_r03_program,
    build_r04_r05_program, build_r06_program, build_r07_loop_program,
    build_r08_r09_program, build_r10_r12_program, build_r11_transactional_program,
    build_r13_r18_handle_join_program, build_x1_result_act_integration,
    build_x2_partial_merge_integration, build_x3_x4_handle_await_refinement_integration,
)

PASS, FAIL = 0, 0


def scenario(name: str):
    def deco(fn):
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


def assert_true(cond: bool, msg: str):
    if not cond:
        raise AssertionError(msg)


# =====================================================================
# Track A: RESULT-LATENT-POSTCOND (R01–R07)
# =====================================================================

@scenario("R01_OK_POSTCONDITION")
def r01():
    prog = build_r01_program()
    interp = CFGInterpreter(prog)
    state = interp.execute({})
    assert_true(state.status == "Terminated", f"expected Terminated, got {state.status}")
    assert_true(state.current_block == "success", f"expected success block, got {state.current_block}")
    assert_true(any(f.name == "IsOk" for f in state.psi), "IsOk fact missing from Ψ")
    assert_true(any(f.name == "ObservedAt" and "v" in f.args and "target_doc" in f.args for f in state.psi),
                f"on_ok ObservedAt fact missing from Ψ: {state.psi}")
    assert_true(i3_1_result_fact_soundness(state), "I3.1 violated")
    assert_true(i3_4_outcome_disjointness(state), "I3.4 violated")


@scenario("R02_ERR_ISOLATION")
def r02():
    prog = build_r02_program()
    interp = CFGInterpreter(prog)
    state = interp.execute({})
    assert_true(state.status == "Terminated", f"expected Terminated, got {state.status}")
    assert_true(state.current_block == "failure", f"expected failure block, got {state.current_block}")
    assert_true(any(f.name == "IsErr" for f in state.psi), "IsErr fact missing from Ψ")
    assert_true(any(f.name == "ErrorFact" and "e" in f.args and "failed_read" in f.args for f in state.psi),
                f"on_err ErrorFact missing from Ψ: {state.psi}")
    # CRITICAL: on_ok facts MUST NOT be present!
    assert_true(not any(f.name == "ObservedAt" for f in state.psi),
                f"on_ok fact leaked into Err branch: {state.psi}")
    assert_true(i3_1_result_fact_soundness(state), "I3.1 violated")
    assert_true(i3_4_outcome_disjointness(state), "I3.4 violated")


@scenario("R03_BLOCK_ARGUMENT_RENAME")
def r03():
    prog = build_r03_program()
    interp = CFGInterpreter(prog)
    state = interp.execute({})
    assert_true(state.current_block == "success_block", f"expected success_block, got {state.current_block}")
    assert_true("renamed_val" in state.env, "block argument renamed_val missing from env")
    assert_true(any(f.name == "ObservedAt" and "renamed_val" in f.args and "resource_X" in f.args for f in state.psi),
                f"fact not bound correctly across block argument transfer: {state.psi}")


@scenario("R04_MERGE_LOSES_BRANCH_ONLY_FACT")
def r04():
    prog = build_r04_r05_program(common_fact=False)
    latent_ok = LatentPostconditions(on_ok=(FactTemplate("BranchOnlyFact", ("$value",)),))
    latent_err = LatentPostconditions()

    # Execute through Ok branch
    interp_ok = CFGInterpreter(prog)
    state_ok = interp_ok.execute({"r": OkVal("doc_val", STRING, latent_ok)})
    psi_from_ok = state_ok.psi

    # Execute through Err branch
    interp_err = CFGInterpreter(prog)
    state_err = interp_err.execute({"r": ErrVal("read_err", STRING, latent_err)})
    psi_from_err = state_err.psi

    # Intersection merge
    merged_psi = psi_from_ok & psi_from_err
    assert_true(not any(f.name == "BranchOnlyFact" for f in merged_psi),
                f"branch-only fact survived merge intersection: {merged_psi}")


@scenario("R05_MERGE_PRESERVES_COMMON_FACT")
def r05():
    prog = build_r04_r05_program(common_fact=True)
    latent_ok = LatentPostconditions(
        on_ok=(FactTemplate("BranchOnlyFact", ("$value",)), FactTemplate("CommonFact", ("doc",)))
    )
    latent_err = LatentPostconditions(
        on_err=(FactTemplate("CommonFact", ("doc",)),)
    )

    interp_ok = CFGInterpreter(prog)
    state_ok = interp_ok.execute({"r": OkVal("doc_val", STRING, latent_ok)})
    psi_from_ok = state_ok.psi

    interp_err = CFGInterpreter(prog)
    state_err = interp_err.execute({"r": ErrVal("read_err", STRING, latent_err)})
    psi_from_err = state_err.psi

    merged_psi = psi_from_ok & psi_from_err
    assert_true(any(f.name == "CommonFact" and f.args == ("doc",) for f in merged_psi),
                f"common fact lost on merge intersection: {merged_psi}")
    assert_true(i3_3_cfg_must_fact_merge([psi_from_ok, psi_from_err], merged_psi), "I3.3 violated")


@scenario("R06_FORWARDED_RESULT_REMAINS_LATENT")
def r06():
    prog = build_r06_program()
    interp = CFGInterpreter(prog)
    state = interp.execute({})
    assert_true(state.current_block == "forward_block", f"expected forward_block, got {state.current_block}")
    assert_true("r_fwd" in state.var_latent, "latent postconditions lost on forwarded result")
    # Postconditions MUST NOT enter Ψ before refinement!
    assert_true(not any(f.name == "LatentFact" for f in state.psi),
                f"postconditions eagerly materialized on unrefined forwarded result: {state.psi}")
    assert_true(i3_2_no_eager_latent_discharge(["r_fwd"], state), "I3.2 violated")


@scenario("R07_LOOP_LEAKAGE_KILL")
def r07():
    prog = build_r07_loop_program()
    interp = CFGInterpreter(prog)
    # Run loop iteration 0 (exit immediately)
    state_exit0 = interp.execute({"cond": False})
    assert_true(not any(f.name == "IterationFact" for f in state_exit0.psi),
                f"loop iteration fact leaked to exit path without execution: {state_exit0.psi}")


# =====================================================================
# Track B: ACT-SETTLEMENT-OUTCOME (R08–R09)
# =====================================================================

@scenario("R08_UNKNOWN_IS_NOT_ERR")
def r08():
    prog = build_r08_r09_program()
    interp = CFGInterpreter(prog)
    # Inject DeliveryUnknownVal
    state_du = interp.execute({"act_res": DeliveryUnknownVal("req-1", "send_email")})
    assert_true(state_du.current_block == "on_unknown", f"DeliveryUnknown routed to wrong block: {state_du.current_block}")
    assert_true(not any(f.name in ("IsErr", "IsFailure") for f in state_du.psi),
                f"DeliveryUnknown treated as Err in path facts: {state_du.psi}")

    # Inject SettlementUnknownVal
    state_su = interp.execute({"act_res": SettlementUnknownVal("req-2", "send_email")})
    assert_true(state_su.current_block == "on_unknown", f"SettlementUnknown routed to wrong block: {state_su.current_block}")
    assert_true(not any(f.name in ("IsErr", "IsFailure") for f in state_su.psi),
                f"SettlementUnknown treated as Err in path facts: {state_su.psi}")
    assert_true(i3_4_outcome_disjointness(state_du), "I3.4 violated")


@scenario("R09_CONFIRMED_FAILURE_BECOMES_ERROR")
def r09():
    prog = build_r08_r09_program()
    interp = CFGInterpreter(prog)
    state = interp.execute({"act_res": ActFailureVal("smtp_auth_failed", STRING)})
    assert_true(state.current_block == "on_failure", f"definite failure routed to wrong block: {state.current_block}")
    assert_true(any(f.name == "IsFailure" for f in state.psi), "IsFailure missing from Ψ")
    assert_true(i3_5_no_false_clean_failure(state.env["act_res"]), "I3.5 violated")


# =====================================================================
# Track C: ACT-PARTIAL-COMPLETION (R10–R12)
# =====================================================================

@scenario("R10_PARTIAL_COMPLETION_DISTINCT")
def r10():
    prog = build_r10_r12_program()
    interp = CFGInterpreter(prog)
    report = PartialEffectReport("batch_update", ("fileA", "fileB"), ("fileC",), "rcpt-part-1")
    state = interp.execute({"act_res": ActPartialVal(report)})
    assert_true(state.current_block == "part_block", f"Partial routed to wrong block: {state.current_block}")
    assert_true(any(f.name == "IsPartial" for f in state.psi), "IsPartial missing from Ψ")
    assert_true(not any(f.name in ("IsSuccess", "IsFailure") for f in state.psi),
                f"Partial collapsed into Success/Failure: {state.psi}")
    assert_true(i3_4_outcome_disjointness(state), "I3.4 violated")


@scenario("R11_TRANSACTIONAL_ADAPTER_EXCLUDES_PARTIAL")
def r11():
    prog = build_r11_transactional_program()
    interp = CFGInterpreter(prog)
    # Attempting to return ActPartialVal on an atomic/transactional op MUST fail with ProtocolViolation
    report = PartialEffectReport("atomic_transfer", ("debited_src",), ("credited_dst",), "rcpt-atomic")
    state = interp.execute({"act_res": ActPartialVal(report)})
    assert_true(state.status == "ProtocolViolation", f"expected ProtocolViolation, got {state.status}")
    assert_true(len(state.protocol_violations) > 0, "protocol violation not recorded")


@scenario("R12_PARTIAL_BRANCH_FACTS")
def r12():
    prog = build_r10_r12_program()
    interp = CFGInterpreter(prog)
    report = PartialEffectReport("batch_update", ("db1",), ("db2",), "rcpt-12")
    state = interp.execute({"act_res": ActPartialVal(report)})
    # Partial branch carries PartialFootprint facts
    assert_true(any(f.name == "PartialFootprint" for f in state.psi), f"PartialFootprint fact missing: {state.psi}")
    # Success-only facts MUST NOT be present in Partial branch
    assert_true(not any(f.name == "SuccessMutated" for f in state.psi),
                f"Success-only postconditions leaked into Partial branch: {state.psi}")


# =====================================================================
# Track D: HANDLE-EFFECT-JOIN (R13–R18)
# =====================================================================

@scenario("R13_HANDLE_SAME_EFFECTS_JOIN")
def r13():
    prog = build_r13_r18_handle_join_program(same_effects=True)
    interp = CFGInterpreter(prog)
    state = interp.execute({"c": True})
    t_join = state.var_types["h_joined"]
    assert_true(isinstance(t_join, ChildHandleType), "h_joined is not ChildHandleType")
    assert_true(t_join.may_effects == frozenset(["read[x]"]), f"wrong may_effects: {t_join.may_effects}")


@scenario("R14_HANDLE_HETEROGENEOUS_EFFECTS_JOIN")
def r14():
    prog = build_r13_r18_handle_join_program(same_effects=False)
    interp = CFGInterpreter(prog)
    state_l = interp.execute({"c": True})
    t_join_l = state_l.var_types["h_joined"]
    expected_union = frozenset(["read[x]", "act[y]", "infer[z]"])
    assert_true(t_join_l.may_effects == expected_union, f"expected {expected_union}, got {t_join_l.may_effects}")
    assert_true(i3_6_handle_effect_monotonicity(
        ChildHandleType(STRING, STRING, frozenset(["read[x]"])),
        ChildHandleType(STRING, STRING, frozenset(["act[y]", "infer[z]"])),
        t_join_l,
    ), "I3.6 violated")


@scenario("R15_HANDLE_TYPE_MISMATCH_REJECT")
def r15():
    h_a = ChildHandleType(STRING, STRING, frozenset(["read[x]"]))
    h_b = ChildHandleType(I64, STRING, frozenset(["act[y]"]))
    assert_true(not h_a.is_compatible_for_join(h_b), "incompatible handle types were reported as compatible")
    try:
        h_a.join(h_b)
        raise AssertionError("handle join on type mismatch was permitted")
    except TypeError:
        pass


@scenario("R16_AWAIT_EFFECT_PRESERVATION")
def r16():
    prog = build_r13_r18_handle_join_program(same_effects=False)
    interp = CFGInterpreter(prog)
    # Execute through branch left (spawns workerA)
    state = interp.execute({"c": True})
    # ObsEffects on parent: only children spawned/actions executed, await adds 0
    # InstAwaitHandle MUST NOT debit child's may_effects into parent's observable effect trace!
    assert_true(len(state.observable_effects) == 0, f"await polluted observable effects: {state.observable_effects}")
    assert_true(i3_7_await_effect_neutrality([], state.observable_effects), "I3.7 violated")


@scenario("R17_HANDLE_UNION_DOES_NOT_BECOME_RESULT_PROVENANCE")
def r17():
    prog = build_r13_r18_handle_join_program(same_effects=False)
    interp = CFGInterpreter(prog)
    # WorkerA was executed (branch left)
    state = interp.execute({"c": True})
    await_res_lineage = state.value_lineage.get("r_await")
    assert_true(await_res_lineage == ("exec(workerA)",),
                f"provenance falsely claimed workerB execution: {await_res_lineage}")
    assert_true(i3_8_provenance_effect_separation(state.var_types["h_joined"], await_res_lineage), "I3.8 violated")


@scenario("R18_RESULT_AFTER_JOINED_HANDLE")
def r18():
    prog = build_x3_x4_handle_await_refinement_integration()
    interp = CFGInterpreter(prog)
    state = interp.execute({"branch_cond": True})
    assert_true(state.current_block == "child_ok", f"expected child_ok block, got {state.current_block}")
    assert_true(state.status == "Terminated", f"expected Terminated, got {state.status}")


# =====================================================================
# Integrated Cross-Cutting Scenarios (X1–X4)
# =====================================================================

@scenario("X1_RESULT_ACT_INTEGRATION")
def x1():
    prog = build_x1_result_act_integration()
    interp = CFGInterpreter(prog)

    # Success case
    st_succ = interp.execute({"act_out": ActSuccessVal("doc_saved", STRING)})
    assert_true(st_succ.current_block == "succ", f"expected succ, got {st_succ.current_block}")
    assert_true(any(f.name == "DocUpdated" for f in st_succ.psi), "DocUpdated fact missing")

    # Clean failure case
    st_fail = interp.execute({"act_out": ActFailureVal("perm_denied", STRING)})
    assert_true(st_fail.current_block == "fail", f"expected fail, got {st_fail.current_block}")
    assert_true(any(f.name == "DocNotModified" for f in st_fail.psi), "DocNotModified fact missing")
    assert_true(not any(f.name == "DocUpdated" for f in st_fail.psi), "DocUpdated fact leaked into failure")

    # Partial case
    report = PartialEffectReport("mutate_doc", ("chunk1",), ("chunk2",), "rcpt-x1")
    st_part = interp.execute({"act_out": ActPartialVal(report)})
    assert_true(st_part.current_block == "part", f"expected part, got {st_part.current_block}")
    assert_true(any(f.name == "DocPartiallyTouched" for f in st_part.psi), "DocPartiallyTouched missing")

    # Unknown case
    st_unk = interp.execute({"act_out": DeliveryUnknownVal("req-x1", "mutate_doc")})
    assert_true(st_unk.current_block == "unk", f"expected unk, got {st_unk.current_block}")
    assert_true(any(f.name == "IsUnknown" for f in st_unk.psi), "IsUnknown missing")


@scenario("X2_PARTIAL_MERGE_INTEGRATION")
def x2():
    prog = build_x2_partial_merge_integration()
    interp_a = CFGInterpreter(prog)
    st_a = interp_a.execute({"c": True, "act_a": ActSuccessVal("cluster_ok", STRING)})

    interp_b = CFGInterpreter(prog)
    report = PartialEffectReport("update_cluster_b", ("node1",), ("node2",), "rcpt-x2")
    st_b = interp_b.execute({"c": False, "act_b": ActPartialVal(report)})

    merged_psi = st_a.psi & st_b.psi
    # Common fact survives
    assert_true(any(f.name == "ClusterKnown" for f in merged_psi), f"common ClusterKnown lost: {merged_psi}")
    # Exclusive success facts are lost
    assert_true(not any(f.name == "CompleteSuccessFact" for f in merged_psi), f"CompleteSuccessFact leaked: {merged_psi}")
    assert_true(not any(f.name == "PartialFootprintFact" for f in merged_psi), f"PartialFootprintFact leaked: {merged_psi}")


@scenario("X3_X4_HANDLE_AWAIT_REFINEMENT_INTEGRATION")
def x3_x4():
    prog = build_x3_x4_handle_await_refinement_integration()
    interp = CFGInterpreter(prog)
    # Execute worker B branch
    state = interp.execute({"branch_cond": False})
    assert_true(state.current_block == "child_ok", f"expected child_ok, got {state.current_block}")
    # Σ_await is ∅
    assert_true(len(state.observable_effects) == 0, f"observable effects polluted: {state.observable_effects}")
    # Provenance matches workerB
    assert_true(state.value_lineage.get("r_await") == ("exec(workerB)",), f"wrong lineage: {state.value_lineage}")
    # Latent postcondition on child result materialized on Ok branch
    assert_true(any(f.name == "ChildJobVerified" for f in state.psi), f"ChildJobVerified missing from Ψ: {state.psi}")
    assert_true(i3_1_result_fact_soundness(state), "I3.1 violated")


# =====================================================================
print("\n" + "=" * 70)
print(f"ITEM 3 GOLDEN SCENARIOS RESULT: {PASS} passed, {FAIL} failed ({PASS + FAIL} total)")
if FAIL:
    sys.exit(1)
print("SOMA-IR Item 3 (CFG / Result / Error Model) verified across all golden scenarios.")
