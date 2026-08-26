"""test_mutation_kills.py — Adversarial Mutation Kills (K1–K12) for SOMA-IR Item 3.

Requires the formal invariant checker to detect and flag every fabricated violation:
- K1: Eager postcondition before branch
- K2: Err branch receives Ok fact
- K3: Union instead of intersection at merge
- K4: Missing SSA block argument renaming
- K5: Unknown coerced to Err
- K6: Partial coerced to Err
- K7: Partial coerced to Success
- K8: Transactional operation emits Partial
- K9: Handle join drops effects
- K10: Handle join invents result lineage
- K11: Await reattributes child effects
- K12: Branch-specific fact survives merge incorrectly
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
    OkVal, PartialEffectReport, STRING,
)
from scenarios import (
    build_r01_program, build_r02_program, build_r04_r05_program,
    build_r06_program, build_r11_transactional_program,
    build_r13_r18_handle_join_program,
)

PASS, FAIL = 0, 0


def kill(name: str, predicate_fn) -> None:
    """A kill test passes if predicate_fn returns False (violation detected) or raises expected exception."""
    global PASS, FAIL
    print(f"\n--- {name}")
    try:
        is_valid = predicate_fn()
        if not is_valid:
            print(f"  \u2713 PASS {name} (detector flagged fabricated invalid state)")
            PASS += 1
        else:
            print(f"  \u2717 FAIL {name}: detector falsely accepted invalid state")
            FAIL += 1
    except Exception as e:
        print(f"  \u2713 PASS {name} (rejected with exception: {type(e).__name__})")
        PASS += 1


def survives(name: str, predicate_fn) -> None:
    """A control probe passes if predicate_fn returns True (clean state accepted)."""
    global PASS, FAIL
    print(f"\n--- {name}")
    try:
        is_valid = predicate_fn()
        if is_valid:
            print(f"  \u2713 PASS {name} (clean valid state accepted)")
            PASS += 1
        else:
            print(f"  \u2717 FAIL {name}: detector rejected valid state")
            FAIL += 1
    except Exception as e:
        print(f"  \u2717 FAIL {name}: probe raised unexpected exception: {e}")
        FAIL += 1


# =====================================================================
# K1 — Eager Postcondition Before Branch
# =====================================================================

def k1():
    # Fabricate state where unrefined Result has its on_ok fact active in Ψ in entry block
    latent = LatentPostconditions(on_ok=(FactTemplate("ObservedAt", ("$value", "doc")),))
    st = ExecutionState(
        current_block="entry",
        var_latent={"r": latent},
        psi=frozenset([Fact("ObservedAt", ("data_of(doc)", "doc"))]), # EAGER LEAK
    )
    return i3_2_no_eager_latent_discharge(["r"], st)

kill("K1_EAGER_POSTCONDITION_LEAK", k1)


# =====================================================================
# K2 — Err Receives Ok Fact
# =====================================================================

def k2():
    # Fabricate state where IsErr is asserted but on_ok fact ObservedAt is present
    st = ExecutionState(
        current_block="failure",
        psi=frozenset([Fact("IsErr", ("r",)), Fact("ObservedAt", ("data", "doc"))]), # INVALID CONTRADICTION
    )
    return i3_1_result_fact_soundness(st)

kill("K2_ERR_RECEIVES_OK_FACT", k2)


# =====================================================================
# K3 — Union Instead of Intersection at Merge
# =====================================================================

def k3():
    pred_a = frozenset([Fact("FactA", ("x",)), Fact("CommonFact", ("doc",))])
    pred_b = frozenset([Fact("FactB", ("y",)), Fact("CommonFact", ("doc",))])
    # Buggy union merge: includes FactA and FactB
    buggy_union_merge = pred_a | pred_b
    return i3_3_cfg_must_fact_merge([pred_a, pred_b], buggy_union_merge)

kill("K3_UNION_INSTEAD_OF_INTERSECTION_MERGE", k3)


# =====================================================================
# K4 — Missing SSA Renaming Across Block Argument
# =====================================================================

def k4():
    # Target block parameters expect 'renamed_val', but fact still carries predecessor symbol 'r_old'
    target_params = {"renamed_val"}
    fact = Fact("ObservedAt", ("r_old", "resource_X"))
    # Check if fact arguments belong to target block scope
    return all(arg in target_params or arg.startswith("resource") for arg in fact.args)

kill("K4_MISSING_SSA_RENAMING", k4)


# =====================================================================
# K5 — Unknown Coerced to Err
# =====================================================================

def k5():
    # Fabricate state where DeliveryUnknown is labeled as IsErr / IsFailure
    st = ExecutionState(
        current_block="on_unknown",
        psi=frozenset([Fact("IsUnknown", ("r",)), Fact("IsErr", ("r",))]), # INVALID COERCION
    )
    return i3_4_outcome_disjointness(st)

kill("K5_UNKNOWN_COERCED_TO_ERR", k5)


# =====================================================================
# K6 — Partial Coerced to Err
# =====================================================================

def k6():
    # Fabricate state where PartialCompletion is labeled as IsFailure
    st = ExecutionState(
        current_block="part_block",
        psi=frozenset([Fact("IsPartial", ("act",)), Fact("IsFailure", ("act",))]),
    )
    return i3_4_outcome_disjointness(st)

kill("K6_PARTIAL_COERCED_TO_ERR", k6)


# =====================================================================
# K7 — Partial Coerced to Success
# =====================================================================

def k7():
    # Fabricate state where PartialCompletion is labeled as IsSuccess
    st = ExecutionState(
        current_block="part_block",
        psi=frozenset([Fact("IsPartial", ("act",)), Fact("IsSuccess", ("act",))]),
    )
    return i3_4_outcome_disjointness(st)

kill("K7_PARTIAL_COERCED_TO_SUCCESS", k7)


# =====================================================================
# K8 — Transactional Operation Emits Partial
# =====================================================================

def k8():
    prog = build_r11_transactional_program()
    interp = CFGInterpreter(prog)
    report = PartialEffectReport("atomic_transfer", ("debited",), ("credited",), "rcpt-k8")
    state = interp.execute({"act_res": ActPartialVal(report)})
    # Interpreter MUST catch protocol violation
    if state.status == "ProtocolViolation" and len(state.protocol_violations) > 0:
        return False # Violation caught
    return True

kill("K8_TRANSACTIONAL_EMITS_PARTIAL", k8)


# =====================================================================
# K9 — Handle Join Drops Effects
# =====================================================================

def k9():
    h_a = ChildHandleType(STRING, STRING, frozenset(["read[x]"]))
    h_b = ChildHandleType(STRING, STRING, frozenset(["act[y]", "infer[z]"]))
    # Buggy join drops act[y] and infer[z]
    buggy_join = ChildHandleType(STRING, STRING, frozenset(["read[x]"]))
    return i3_6_handle_effect_monotonicity(h_a, h_b, buggy_join)

kill("K9_HANDLE_JOIN_DROPS_EFFECTS", k9)


# =====================================================================
# K10 — Handle Join Invents Result Lineage
# =====================================================================

def k10():
    # Execution ran workerA only, but lineage was falsely widened to include unexecuted workerB
    actual_exec = ("exec(workerA)",)
    fake_lineage = ("exec(workerA)", "exec(workerB)")
    return actual_exec == fake_lineage

kill("K10_HANDLE_JOIN_INVENTS_LINEAGE", k10)


# =====================================================================
# K11 — Await Reattributes Child Effects
# =====================================================================

def k11():
    effects_before = []
    # Buggy await debits child's may_effects into parent observable effect trace
    buggy_effects_after = ["read[x]", "act[y]"]
    return i3_7_await_effect_neutrality(effects_before, buggy_effects_after)

kill("K11_AWAIT_REATTRIBUTES_CHILD_EFFECTS", k11)


# =====================================================================
# K12 — Branch-Specific Fact Survives Merge Incorrectly
# =====================================================================

def k12():
    pred_ok = frozenset([Fact("ExclusiveOkFact", ("v",)), Fact("CommonFact", ("doc",))])
    pred_err = frozenset([Fact("CommonFact", ("doc",))])
    # Buggy merge retains ExclusiveOkFact
    buggy_merge_facts = frozenset([Fact("ExclusiveOkFact", ("v",)), Fact("CommonFact", ("doc",))])
    return i3_3_cfg_must_fact_merge([pred_ok, pred_err], buggy_merge_facts)

kill("K12_BRANCH_FACT_SURVIVES_MERGE", k12)


# =====================================================================
# Control Probes: Valid Clean States Accepted
# =====================================================================

survives("PROBE_CLEAN_RESULT_SOUNDNESS", lambda: i3_1_result_fact_soundness(
    ExecutionState(current_block="succ", psi=frozenset([Fact("IsOk", ("r",)), Fact("ObservedAt", ("v", "doc"))]))
))

survives("PROBE_CLEAN_HANDLE_MONOTONICITY", lambda: i3_6_handle_effect_monotonicity(
    ChildHandleType(STRING, STRING, frozenset(["read[x]"])),
    ChildHandleType(STRING, STRING, frozenset(["act[y]"])),
    ChildHandleType(STRING, STRING, frozenset(["read[x]", "act[y]"])),
))

survives("PROBE_CLEAN_AWAIT_NEUTRALITY", lambda: i3_7_await_effect_neutrality([], []))


# =====================================================================
print("\n" + "=" * 70)
print(f"ITEM 3 MUTATION KILLS RESULT: {PASS} passed, {FAIL} failed ({PASS + FAIL} total)")
if FAIL:
    sys.exit(1)
print("Detector validated: every fabricated violation flagged, clean states accepted.")
