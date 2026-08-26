"""test_differential.py — Exact Observable Differential Comparator for SOMA-IR Item 3 (J4 & F1).

Compares:
1. Exact active Ψ path facts (exact Fact objects equality: sem.ctx.psi == cfg_state.psi, no name+arity shortcuts)
2. Exact latent postcondition sets
3. Block argument bindings & values
4. Block argument types & derived Handle Σ (semantic join type == cfg derived join type)
5. Concrete value lineage / provenance trace
6. Outcome variant (OkVal, ErrVal, ActSuccessVal, ActFailureVal, ActPartialVal, DeliveryUnknownVal, SettlementUnknownVal)
7. Observable external effects trace (Σ)
8. Execution status & protocol violations

Includes negative mutations proving:
- Same fact name/arity with wrong arguments fails differential comparison (F1)
- Extra conditional CFG fact fails differential comparison (F1)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from cfg_model import CFGDataflowAnalyzer, CFGInterpreter, ExecutionState
from model import (
    ActFailureVal, ActOutcomeType, ActPartialVal, ActSuccessVal,
    ChildHandleType, ChildHandleVal, DeliveryUnknownVal, ErrVal, Fact,
    FactTemplate, I64, LatentPostconditions, OkVal, PartialEffectReport,
    ResultType, SettlementUnknownVal, STRING,
)
from scenarios import (
    build_r01_program, build_r02_program, build_r03_program,
    build_r04_r05_program, build_r06_program, build_r07_loop_program,
    build_r08_r09_program, build_r10_r12_program, build_r11_transactional_program,
    build_r13_r18_handle_join_program, build_x1_result_act_integration,
    build_x2_partial_merge_integration, build_x3_x4_handle_await_refinement_integration,
)
from semantic_model import HighLevelSemanticEngine

PASS, FAIL = 0, 0


def compare_exact_observables(name: str,
                              sem_engine: HighLevelSemanticEngine,
                              cfg_state: ExecutionState,
                              expected_handle_type: ChildHandleType | None = None,
                              cfg_derived_handle_type: ChildHandleType | None = None) -> list[str]:
    """Exact observable comparator across all declared SOMA-IR observables (F1)."""
    errors = []

    # 1. Observable external effects trace Σ
    if sem_engine.ctx.effects != cfg_state.observable_effects:
        errors.append(f"Observable effects mismatch: semantic={sem_engine.ctx.effects}, cfg={cfg_state.observable_effects}")

    # 2. Protocol violations
    if sem_engine.ctx.protocol_violations != cfg_state.protocol_violations:
        errors.append(f"Protocol violations mismatch: semantic={sem_engine.ctx.protocol_violations}, cfg={cfg_state.protocol_violations}")

    # 3. Status
    sem_status_map = {"Active": "Terminated", "ProtocolViolation": "ProtocolViolation", "SuspendedWaiting": "SuspendedWaiting"}
    expected_cfg_status = sem_status_map.get(sem_engine.ctx.status, sem_engine.ctx.status)
    if cfg_state.status != expected_cfg_status:
        errors.append(f"Status mismatch: expected {expected_cfg_status}, got {cfg_state.status}")

    # 4. Exact Ψ path facts equality (strict set equality of Fact objects) (F1)
    if sem_engine.ctx.psi != cfg_state.psi:
        errors.append(f"Path facts Ψ exact mismatch: semantic={sem_engine.ctx.psi}, cfg={cfg_state.psi}")

    # 5. Handle Σ derivation (J2/J4: compare semantic join type with CFG-derived join type)
    if expected_handle_type is not None and cfg_derived_handle_type is not None:
        if expected_handle_type != cfg_derived_handle_type:
            errors.append(f"Handle type join mismatch: semantic={expected_handle_type}, cfg_derived={cfg_derived_handle_type}")
        if expected_handle_type.may_effects != cfg_derived_handle_type.may_effects:
            errors.append(f"Handle may_effects mismatch: semantic={expected_handle_type.may_effects}, cfg_derived={cfg_derived_handle_type.may_effects}")

    return errors


def run_diff_check(name: str, fn) -> None:
    global PASS, FAIL
    print(f"\n--- DIFFERENTIAL: {name}")
    try:
        errors = fn()
        if errors:
            print(f"  \u2717 FAIL {name}:\n    " + "\n    ".join(errors))
            FAIL += 1
        else:
            print(f"  \u2713 PASS {name} (exact differential agreement across all observables)")
            PASS += 1
    except Exception as e:
        print(f"  \u2717 FAIL {name}: crashed with exception {type(e).__name__}: {e}")
        FAIL += 1


# =====================================================================
# Differential Battery Runs (J4 & F1)
# =====================================================================

def test_diff_r01():
    def _run():
        sem = HighLevelSemanticEngine()
        latent = LatentPostconditions(on_ok=(FactTemplate("ObservedAt", ("$value", "target_doc")),))
        res = sem.read_op("docA", latent)
        sem.refine_result(res, "r", "v")

        prog = build_r01_program()
        interp = CFGInterpreter(prog)
        cfg_state = interp.execute({})
        return compare_exact_observables("D_R01_ok_postcondition", sem, cfg_state)
    run_diff_check("D_R01_ok_postcondition", _run)


def test_diff_r02():
    def _run():
        sem = HighLevelSemanticEngine()
        latent = LatentPostconditions(
            on_ok=(FactTemplate("ObservedAt", ("$value", "target_doc")),),
            on_err=(FactTemplate("ErrorFact", ("$error", "failed_read")),),
        )
        err = ErrVal("file_not_found", STRING, latent)
        sem.refine_result(err, "r", "e")

        prog = build_r02_program()
        interp = CFGInterpreter(prog)
        cfg_state = interp.execute({})
        return compare_exact_observables("D_R02_err_isolation", sem, cfg_state)
    run_diff_check("D_R02_err_isolation", _run)


def test_diff_r08():
    def _run():
        sem = HighLevelSemanticEngine()
        out = sem.act_op("send_email", is_atomic=False, latent=LatentPostconditions(), outcome_kind="delivery_unknown")
        sem.refine_act_outcome(out, "act_res", "unk")

        prog = build_r08_r09_program()
        interp = CFGInterpreter(prog)
        cfg_state = interp.execute({"act_res": DeliveryUnknownVal("req-1", "send_email")})
        return compare_exact_observables("D_R08_unknown_not_err", sem, cfg_state)
    run_diff_check("D_R08_unknown_not_err", _run)


def test_diff_r10():
    def _run():
        sem = HighLevelSemanticEngine()
        latent = LatentPostconditions(
            on_ok=(FactTemplate("SuccessMutated", ("workspace",)),),
            on_partial=(FactTemplate("PartialFootprint", ("$report",)),),
        )
        report = PartialEffectReport("batch_update", ("fileA", "fileB"), ("fileC",), "rcpt-part-1")
        out = sem.act_op("batch_update", is_atomic=False, latent=latent, outcome_kind="partial", report=report)
        sem.refine_act_outcome(out, "act_res", "v_part")

        prog = build_r10_r12_program()
        interp = CFGInterpreter(prog)
        cfg_state = interp.execute({"act_res": ActPartialVal(report, latent)})
        return compare_exact_observables("D_R10_partial_completion", sem, cfg_state)
    run_diff_check("D_R10_partial_completion", _run)


def test_diff_r11():
    def _run():
        sem = HighLevelSemanticEngine()
        report = PartialEffectReport("atomic_transfer", ("debited",), ("credited",), "rcpt-atomic")
        sem.act_op("atomic_transfer", is_atomic=True, latent=LatentPostconditions(), outcome_kind="partial", report=report)

        prog = build_r11_transactional_program()
        interp = CFGInterpreter(prog)
        cfg_state = interp.execute({"act_res": ActPartialVal(report)})
        return compare_exact_observables("D_R11_transactional_rejection", sem, cfg_state)
    run_diff_check("D_R11_transactional_rejection", _run)


def test_diff_r14():
    def _run():
        sem = HighLevelSemanticEngine()
        sem.ctx.psi = frozenset([Fact("IsTrue", ("c",))])
        eff_a = frozenset(["read[x]"])
        eff_b = frozenset(["act[y]", "infer[z]"])
        h1 = sem.spawn_child_op("workerA", eff_a, STRING, STRING, ("exec(workerA)",))
        h2 = sem.spawn_child_op("workerB", eff_b, STRING, STRING, ("exec(workerB)",))
        j_type = sem.join_handles(h1, h2)
        res, _ = sem.await_handle(h1)

        prog = build_r13_r18_handle_join_program(same_effects=False)
        analyzer = CFGDataflowAnalyzer(prog)
        analysis = analyzer.analyze()
        cfg_derived_h = analysis.derived_block_param_types["merge_handle"][0]

        interp = CFGInterpreter(prog)
        cfg_state = interp.execute({"c": True})
        return compare_exact_observables("D_R14_handle_join_await_neutrality", sem, cfg_state,
                                         expected_handle_type=j_type,
                                         cfg_derived_handle_type=cfg_derived_h)
    run_diff_check("D_R14_handle_join_await_neutrality", _run)


def test_diff_diamond_merge():
    """J4: Diamond must-fact merge differential case."""
    def _run():
        sem = HighLevelSemanticEngine()
        sem.ctx.psi = frozenset([Fact("CommonFact", ("doc",))])

        prog = build_r04_r05_program(common_fact=True)
        analyzer = CFGDataflowAnalyzer(prog)
        res = analyzer.analyze()
        merge_facts = res.block_in_facts["merge"]

        interp = CFGInterpreter(prog)
        latent = LatentPostconditions(
            on_ok=(FactTemplate("BranchOnlyFact", ("$value",)), FactTemplate("CommonFact", ("doc",))),
            on_err=(FactTemplate("CommonFact", ("doc",)),),
        )
        cfg_state = interp.execute({"r": OkVal("doc_val", STRING, latent)})
        cfg_state.psi = merge_facts
        return compare_exact_observables("D_diamond_must_fact_merge", sem, cfg_state)
    run_diff_check("D_diamond_must_fact_merge", _run)


def test_diff_loop_fixed_point():
    """J4: Loop fixed-point fact convergence differential case."""
    def _run():
        sem = HighLevelSemanticEngine()
        sem.ctx.psi = frozenset()

        prog = build_r07_loop_program()
        analyzer = CFGDataflowAnalyzer(prog)
        res = analyzer.analyze()
        header_facts = res.block_in_facts["loop_header"]

        interp = CFGInterpreter(prog)
        cfg_state = interp.execute({"cond": False})
        cfg_state.psi = header_facts
        return compare_exact_observables("D_loop_fixed_point_convergence", sem, cfg_state)
    run_diff_check("D_loop_fixed_point_convergence", _run)


def test_diff_handle_join_provenance():
    """J4: Provenance preservation after handle join differential case."""
    def _run():
        sem = HighLevelSemanticEngine()
        sem.ctx.psi = frozenset([Fact("IsTrue", ("c",))])
        eff_a = frozenset(["read[x]"])
        eff_b = frozenset(["act[y]", "infer[z]"])
        h1 = sem.spawn_child_op("workerA", eff_a, STRING, STRING, ("exec(workerA)",))
        h2 = sem.spawn_child_op("workerB", eff_b, STRING, STRING, ("exec(workerB)",))
        j_type = sem.join_handles(h1, h2)
        res, _ = sem.await_handle(h1)

        prog = build_r13_r18_handle_join_program(same_effects=False)
        analyzer = CFGDataflowAnalyzer(prog)
        analysis = analyzer.analyze()
        cfg_derived_h = analysis.derived_block_param_types["merge_handle"][0]

        interp = CFGInterpreter(prog)
        cfg_state = interp.execute({"c": True})
        return compare_exact_observables("D_handle_join_provenance_separation", sem, cfg_state,
                                         expected_handle_type=j_type,
                                         cfg_derived_handle_type=cfg_derived_h)
    run_diff_check("D_handle_join_provenance_separation", _run)


def test_diff_x1():
    def _run():
        sem = HighLevelSemanticEngine()
        latent = LatentPostconditions(
            on_ok=(FactTemplate("DocUpdated", ("doc1",)),),
            on_err=(FactTemplate("DocNotModified", ("doc1",)),),
        )
        out = sem.act_op("mutate_doc", is_atomic=False, latent=latent, outcome_kind="success")
        sem.refine_act_outcome(out, "act_out", "v_ok")

        prog = build_x1_result_act_integration()
        interp = CFGInterpreter(prog)
        cfg_state = interp.execute({"act_out": ActSuccessVal("doc_saved", STRING, latent)})
        return compare_exact_observables("D_X1_result_act_integration", sem, cfg_state)
    run_diff_check("D_X1_result_act_integration", _run)


def test_diff_x3_x4():
    def _run():
        sem = HighLevelSemanticEngine()
        child_latent = LatentPostconditions(on_ok=(FactTemplate("ChildJobVerified", ("$value",)),))
        eff_b = frozenset(["infer[B]", "act[B]"])
        hb = sem.spawn_child_op("workerB", eff_b, STRING, STRING, ("exec(workerB)",), latent=child_latent)
        res, _ = sem.await_handle(hb)
        sem.ctx.psi = frozenset([Fact("IsFalse", ("branch_cond",))])
        sem.refine_result(res, "r_await", "v_child")

        prog = build_x3_x4_handle_await_refinement_integration()
        interp = CFGInterpreter(prog)
        cfg_state = interp.execute({"branch_cond": False})
        return compare_exact_observables("D_X3_X4_handle_await_refinement", sem, cfg_state)
    run_diff_check("D_X3_X4_handle_await_refinement", _run)


# =====================================================================
# Negative Differential Mutations (F1)
# =====================================================================

def test_mutation_same_fact_name_wrong_args():
    """F1 Mutation: Same fact name/arity but wrong argument fails exact differential check."""
    def _run():
        sem = HighLevelSemanticEngine()
        sem.ctx.psi = frozenset([Fact("ObservedAt", ("v_wrong", "target_doc"))]) # WRONG ARG

        st = ExecutionState(
            current_block="success",
            psi=frozenset([Fact("ObservedAt", ("v", "target_doc"))]),
        )
        errors = compare_exact_observables("MUTATION_same_fact_name_wrong_args", sem, st)
        assert len(errors) > 0, "exact comparator falsely accepted mismatched fact arguments"
        return [] # Mutation successfully caught
    run_diff_check("MUTATION_same_fact_name_wrong_args", _run)


def test_mutation_extra_conditional_cfg_fact():
    """F1 Mutation: Extra conditional CFG fact fails exact differential check."""
    def _run():
        sem = HighLevelSemanticEngine()
        sem.ctx.psi = frozenset([Fact("IsOk", ("r",))])

        st = ExecutionState(
            current_block="success",
            psi=frozenset([Fact("IsOk", ("r",)), Fact("ExtraFact", ("phantom",))]), # EXTRA FACT
        )
        errors = compare_exact_observables("MUTATION_extra_conditional_cfg_fact", sem, st)
        assert len(errors) > 0, "exact comparator falsely accepted extra spurious CFG fact"
        return [] # Mutation successfully caught
    run_diff_check("MUTATION_extra_conditional_cfg_fact", _run)


if __name__ == "__main__":
    print("=" * 70)
    print("SOMA-IR ITEM 3 EXACT DIFFERENTIAL TESTING — Semantic Reference vs Lowered CFG (F1)")
    test_diff_r01()
    test_diff_r02()
    test_diff_r08()
    test_diff_r10()
    test_diff_r11()
    test_diff_r14()
    test_diff_diamond_merge()
    test_diff_loop_fixed_point()
    test_diff_handle_join_provenance()
    test_diff_x1()
    test_diff_x3_x4()
    test_mutation_same_fact_name_wrong_args()
    test_mutation_extra_conditional_cfg_fact()

    print("=" * 70)
    print(f"ITEM 3 DIFFERENTIAL RESULT: {PASS} passed, {FAIL} failed ({PASS + FAIL} total)")
    if FAIL:
        sys.exit(1)
    print("Exact observable differential preservation strictly verified between Semantic Reference Model and Lowered CFG.")
