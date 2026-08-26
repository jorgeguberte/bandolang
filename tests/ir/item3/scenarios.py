"""scenarios.py — Golden Test Scenarios (R01–R18) and Integrated Cross-Cutting Cases (X1–X4) for SOMA-IR Item 3.

Covers:
- Track A (RESULT-LATENT-POSTCOND): R01–R07
- Track B (ACT-SETTLEMENT-OUTCOME): R08–R09
- Track C (ACT-PARTIAL-COMPLETION): R10–R12
- Track D (HANDLE-EFFECT-JOIN): R13–R18
- Integrated Tracks: X1–X4
"""
from __future__ import annotations

from model import (
    BOOL, I64, STRING, UNIT, ActOutcomeType, BasicBlock, CFGProgram,
    ChildHandleType, ChildHandleVal, Constant, DeliveryUnknownVal, ErrVal,
    Fact, FactTemplate, InstAct, InstAssign, InstAwaitHandle, InstInfer,
    InstRead, InstSpawnChild, InstVerify, LatentPostconditions, OkVal,
    PartialEffectReport, ResultType, SettlementUnknownVal, TermBr, TermCondBr,
    TermReturn, TermSwitchActOutcome, TermSwitchResult, TermUnreachable,
    Variable,
)


def build_r01_program() -> CFGProgram:
    """R01: Result Ok -> on_ok facts materialize."""
    latent = LatentPostconditions(
        on_ok=(FactTemplate("ObservedAt", ("$value", "target_doc")),)
    )
    b_entry = BasicBlock(
        name="entry",
        instructions=[
            InstRead(dest=Variable("r", ResultType(STRING, STRING)), target="docA", latent=latent)
        ],
        terminator=TermSwitchResult(
            result_var=Variable("r", ResultType(STRING, STRING)),
            ok_target="success",
            ok_arg=Variable("v", STRING),
            err_target="failure",
            err_arg=Variable("e", STRING),
        ),
    )
    b_succ = BasicBlock(
        name="success",
        params=[Variable("v", STRING)],
        terminator=TermReturn(Variable("v", STRING)),
    )
    b_fail = BasicBlock(
        name="failure",
        params=[Variable("e", STRING)],
        terminator=TermReturn(Variable("e", STRING)),
    )
    return CFGProgram(name="R01_ok_postcondition", entry="entry", blocks={
        "entry": b_entry, "success": b_succ, "failure": b_fail,
    })


def build_r02_program() -> CFGProgram:
    """R02: Result Err -> on_ok does NOT materialize; on_err materializes."""
    latent = LatentPostconditions(
        on_ok=(FactTemplate("ObservedAt", ("$value", "target_doc")),),
        on_err=(FactTemplate("ErrorFact", ("$error", "failed_read")),),
    )
    b_entry = BasicBlock(
        name="entry",
        instructions=[
            InstAssign(
                dest=Variable("r", ResultType(STRING, STRING)),
                source=Constant(ErrVal("file_not_found", STRING, latent), ResultType(STRING, STRING)),
            )
        ],
        terminator=TermSwitchResult(
            result_var=Variable("r", ResultType(STRING, STRING)),
            ok_target="success",
            ok_arg=Variable("v", STRING),
            err_target="failure",
            err_arg=Variable("e", STRING),
        ),
    )
    b_succ = BasicBlock(
        name="success",
        params=[Variable("v", STRING)],
        terminator=TermReturn(Variable("v", STRING)),
    )
    b_fail = BasicBlock(
        name="failure",
        params=[Variable("e", STRING)],
        terminator=TermReturn(Variable("e", STRING)),
    )
    return CFGProgram(name="R02_err_isolation", entry="entry", blocks={
        "entry": b_entry, "success": b_succ, "failure": b_fail,
    })


def build_r03_program() -> CFGProgram:
    """R03: Block argument rename -> facts use new SSA symbol."""
    latent = LatentPostconditions(
        on_ok=(FactTemplate("ObservedAt", ("$value", "resource_X")),)
    )
    b_entry = BasicBlock(
        name="entry",
        instructions=[
            InstRead(dest=Variable("r", ResultType(STRING, STRING)), target="resX", latent=latent)
        ],
        terminator=TermSwitchResult(
            result_var=Variable("r", ResultType(STRING, STRING)),
            ok_target="success_block",
            ok_arg=Variable("renamed_val", STRING),
            err_target="failure_block",
            err_arg=Variable("err_val", STRING),
        ),
    )
    b_succ = BasicBlock(
        name="success_block",
        params=[Variable("renamed_val", STRING)],
        terminator=TermReturn(Variable("renamed_val", STRING)),
    )
    b_fail = BasicBlock(
        name="failure_block",
        params=[Variable("err_val", STRING)],
        terminator=TermReturn(Variable("err_val", STRING)),
    )
    return CFGProgram(name="R03_block_argument_rename", entry="entry", blocks={
        "entry": b_entry, "success_block": b_succ, "failure_block": b_fail,
    })


def build_r04_r05_program(common_fact: bool = False) -> CFGProgram:
    """R04/R05: Merge must-facts intersection: branch-only fact is lost; common fact survives."""
    if common_fact:
        latent_ok = LatentPostconditions(
            on_ok=(FactTemplate("BranchOnlyFact", ("$value",)), FactTemplate("CommonFact", ("doc",)))
        )
        latent_err = LatentPostconditions(
            on_err=(FactTemplate("CommonFact", ("doc",)),)
        )
    else:
        latent_ok = LatentPostconditions(
            on_ok=(FactTemplate("BranchOnlyFact", ("$value",)),)
        )
        latent_err = LatentPostconditions()
    b_entry = BasicBlock(
        name="entry",
        instructions=[
            InstRead(dest=Variable("r", ResultType(STRING, STRING)), target="doc", latent=latent_ok)
        ],
        terminator=TermSwitchResult(
            result_var=Variable("r", ResultType(STRING, STRING)),
            ok_target="branch_ok",
            ok_arg=Variable("v", STRING),
            err_target="branch_err",
            err_arg=Variable("e", STRING),
        ),
    )
    b_ok = BasicBlock(
        name="branch_ok",
        params=[Variable("v", STRING)],
        terminator=TermBr(target="merge", args=(Variable("v", STRING),)),
    )
    b_err = BasicBlock(
        name="branch_err",
        params=[Variable("e", STRING)],
        terminator=TermBr(target="merge", args=(Variable("e", STRING),)),
    )
    b_merge = BasicBlock(
        name="merge",
        params=[Variable("m", STRING)],
        terminator=TermReturn(Variable("m", STRING)),
    )
    name = "R05_merge_preserves_common_fact" if common_fact else "R04_merge_loses_branch_only_fact"
    return CFGProgram(name=name, entry="entry", blocks={
        "entry": b_entry, "branch_ok": b_ok, "branch_err": b_err, "merge": b_merge,
    })


def build_r06_program() -> CFGProgram:
    """R06: Forwarded Result without switch keeps postconditions latent."""
    latent = LatentPostconditions(
        on_ok=(FactTemplate("LatentFact", ("$value",)),)
    )
    b_entry = BasicBlock(
        name="entry",
        instructions=[
            InstRead(dest=Variable("r", ResultType(STRING, STRING)), target="doc", latent=latent)
        ],
        terminator=TermBr(target="forward_block", args=(Variable("r", ResultType(STRING, STRING)),)),
    )
    b_fwd = BasicBlock(
        name="forward_block",
        params=[Variable("r_fwd", ResultType(STRING, STRING))],
        terminator=TermReturn(Variable("r_fwd", ResultType(STRING, STRING))),
    )
    return CFGProgram(name="R06_forwarded_result_remains_latent", entry="entry", blocks={
        "entry": b_entry, "forward_block": b_fwd,
    })


def build_r07_loop_program() -> CFGProgram:
    """R07: Loop fixed-point: Ok fact of one iteration cannot leak to loop header without proof."""
    latent = LatentPostconditions(
        on_ok=(FactTemplate("IterationFact", ("$value",)),)
    )
    b_entry = BasicBlock(
        name="entry",
        terminator=TermBr(target="loop_header", args=(Constant(0, I64),)),
    )
    b_header = BasicBlock(
        name="loop_header",
        params=[Variable("i", I64)],
        instructions=[
            InstRead(dest=Variable("r", ResultType(STRING, STRING)), target="doc", latent=latent)
        ],
        terminator=TermCondBr(
            cond=Variable("cond", BOOL),
            true_target="loop_body",
            true_args=(Variable("i", I64),),
            false_target="exit",
            false_args=(Variable("i", I64),),
        ),
    )
    b_body = BasicBlock(
        name="loop_body",
        params=[Variable("i_body", I64)],
        terminator=TermSwitchResult(
            result_var=Variable("r", ResultType(STRING, STRING)),
            ok_target="loop_step",
            ok_arg=Variable("v", STRING),
            err_target="exit",
            err_arg=Variable("v", STRING),
        ),
    )
    b_step = BasicBlock(
        name="loop_step",
        params=[Variable("v_step", STRING)],
        terminator=TermBr(target="loop_header", args=(Constant(1, I64),)),
    )
    b_exit = BasicBlock(
        name="exit",
        params=[Variable("out", I64)],
        terminator=TermReturn(Variable("out", I64)),
    )
    return CFGProgram(name="R07_loop_leakage_kill", entry="entry", blocks={
        "entry": b_entry, "loop_header": b_header, "loop_body": b_body,
        "loop_step": b_step, "exit": b_exit,
    })


def build_r08_r09_program() -> CFGProgram:
    """R08/R09: Unknown is NOT Err; confirmed failure becomes clean Error."""
    b_entry = BasicBlock(
        name="entry",
        instructions=[
            InstAct(dest=Variable("act_res", ActOutcomeType(STRING, STRING)), op_id="send_email", is_atomic=False)
        ],
        terminator=TermSwitchActOutcome(
            outcome_var=Variable("act_res", ActOutcomeType(STRING, STRING)),
            success_target="on_success",
            success_arg=Variable("ok_val", STRING),
            failure_target="on_failure",
            failure_arg=Variable("err_val", STRING),
            unknown_target="on_unknown",
            unknown_arg=None,
        ),
    )
    b_succ = BasicBlock(name="on_success", params=[Variable("ok_val", STRING)], terminator=TermReturn(Variable("ok_val", STRING)))
    b_fail = BasicBlock(name="on_failure", params=[Variable("err_val", STRING)], terminator=TermReturn(Variable("err_val", STRING)))
    b_unk = BasicBlock(name="on_unknown", terminator=TermReturn(Constant("suspended_unknown", STRING)))
    return CFGProgram(name="R08_R09_unknown_vs_err", entry="entry", blocks={
        "entry": b_entry, "on_success": b_succ, "on_failure": b_fail, "on_unknown": b_unk,
    })


def build_r10_r12_program() -> CFGProgram:
    """R10/R12: Partial completion is distinct from Success/Failure; carries partial report facts."""
    latent = LatentPostconditions(
        on_ok=(FactTemplate("SuccessMutated", ("workspace",)),),
        on_partial=(FactTemplate("PartialFootprint", ("$report",)),),
    )
    b_entry = BasicBlock(
        name="entry",
        instructions=[
            InstAct(dest=Variable("act_res", ActOutcomeType(STRING, STRING)), op_id="batch_update", is_atomic=False, latent=latent)
        ],
        terminator=TermSwitchActOutcome(
            outcome_var=Variable("act_res", ActOutcomeType(STRING, STRING)),
            success_target="succ_block",
            success_arg=Variable("v_succ", STRING),
            failure_target="fail_block",
            failure_arg=Variable("v_fail", STRING),
            partial_target="part_block",
            partial_arg=Variable("v_part", PartialEffectReport),
        ),
    )
    b_succ = BasicBlock(name="succ_block", params=[Variable("v_succ", STRING)], terminator=TermReturn(Variable("v_succ", STRING)))
    b_fail = BasicBlock(name="fail_block", params=[Variable("v_fail", STRING)], terminator=TermReturn(Variable("v_fail", STRING)))
    b_part = BasicBlock(name="part_block", params=[Variable("v_part", PartialEffectReport)], terminator=TermReturn(Variable("v_part", PartialEffectReport)))
    return CFGProgram(name="R10_R12_partial_completion", entry="entry", blocks={
        "entry": b_entry, "succ_block": b_succ, "fail_block": b_fail, "part_block": b_part,
    })


def build_r11_transactional_program() -> CFGProgram:
    """R11: Transactional adapter contract rejects PartialCompletion with ProtocolViolation."""
    b_entry = BasicBlock(
        name="entry",
        instructions=[
            InstAct(dest=Variable("act_res", ActOutcomeType(STRING, STRING)), op_id="atomic_transfer", is_atomic=True)
        ],
        terminator=TermReturn(Variable("act_res", ActOutcomeType(STRING, STRING))),
    )
    return CFGProgram(name="R11_transactional_rejects_partial", entry="entry", blocks={"entry": b_entry})


def build_r13_r18_handle_join_program(same_effects: bool = False, type_mismatch: bool = False) -> CFGProgram:
    """R13–R18: Handle join may-effect union, await neutrality, and concrete provenance."""
    eff_a = frozenset(["read[x]"])
    eff_b = frozenset(["read[x]"]) if same_effects else frozenset(["act[y]", "infer[z]"])
    t_b = I64 if type_mismatch else STRING

    b_entry = BasicBlock(
        name="entry",
        terminator=TermCondBr(
            cond=Variable("c", BOOL),
            true_target="branch_left",
            true_args=(),
            false_target="branch_right",
            false_args=(),
        ),
    )
    b_left = BasicBlock(
        name="branch_left",
        instructions=[
            InstSpawnChild(dest=Variable("h_left", ChildHandleType(STRING, STRING, eff_a)), child_id="workerA", may_effects=eff_a, ok_type=STRING, err_type=STRING)
        ],
        terminator=TermBr(target="merge_handle", args=(Variable("h_left", ChildHandleType(STRING, STRING, eff_a)),)),
    )
    b_right = BasicBlock(
        name="branch_right",
        instructions=[
            InstSpawnChild(dest=Variable("h_right", ChildHandleType(t_b, STRING, eff_b)), child_id="workerB", may_effects=eff_b, ok_type=t_b, err_type=STRING)
        ],
        terminator=TermBr(target="merge_handle", args=(Variable("h_right", ChildHandleType(t_b, STRING, eff_b)),)),
    )
    b_merge = BasicBlock(
        name="merge_handle",
        params=[Variable("h_joined", ChildHandleType(STRING, STRING, eff_a | eff_b))],
        instructions=[
            InstAwaitHandle(dest=Variable("r_await", ResultType(STRING, STRING)), handle=Variable("h_joined", ChildHandleType(STRING, STRING, eff_a | eff_b)))
        ],
        terminator=TermReturn(Variable("r_await", ResultType(STRING, STRING))),
    )
    name = "R15_type_mismatch" if type_mismatch else ("R13_same_effects_join" if same_effects else "R14_heterogeneous_effects_join")
    return CFGProgram(name=name, entry="entry", blocks={
        "entry": b_entry, "branch_left": b_left, "branch_right": b_right, "merge_handle": b_merge,
    })


# ---------------------------------------------------------------------
# Integrated Cross-Cutting Programs (X1–X4)
# ---------------------------------------------------------------------

def build_x1_result_act_integration() -> CFGProgram:
    """X1: Result + Act Integration: Refinements across Success, Clean Failure, Unknown, Partial."""
    latent = LatentPostconditions(
        on_ok=(FactTemplate("DocUpdated", ("doc1",)),),
        on_err=(FactTemplate("DocNotModified", ("doc1",)),),
        on_partial=(FactTemplate("DocPartiallyTouched", ("doc1",)),),
    )
    b_entry = BasicBlock(
        name="entry",
        instructions=[
            InstAct(dest=Variable("act_out", ActOutcomeType(STRING, STRING)), op_id="mutate_doc", is_atomic=False, latent=latent)
        ],
        terminator=TermSwitchActOutcome(
            outcome_var=Variable("act_out", ActOutcomeType(STRING, STRING)),
            success_target="succ",
            success_arg=Variable("v_ok", STRING),
            failure_target="fail",
            failure_arg=Variable("v_err", STRING),
            partial_target="part",
            partial_arg=Variable("v_part", PartialEffectReport),
            unknown_target="unk",
        ),
    )
    b_succ = BasicBlock(name="succ", params=[Variable("v_ok", STRING)], terminator=TermReturn(Variable("v_ok", STRING)))
    b_fail = BasicBlock(name="fail", params=[Variable("v_err", STRING)], terminator=TermReturn(Variable("v_err", STRING)))
    b_part = BasicBlock(name="part", params=[Variable("v_part", PartialEffectReport)], terminator=TermReturn(Variable("v_part", PartialEffectReport)))
    b_unk = BasicBlock(name="unk", terminator=TermReturn(Constant("suspended", STRING)))
    return CFGProgram(name="X1_result_act_integration", entry="entry", blocks={
        "entry": b_entry, "succ": b_succ, "fail": b_fail, "part": b_part, "unk": b_unk,
    })


def build_x2_partial_merge_integration() -> CFGProgram:
    """X2: Partial + Merge: CompleteSuccess on branch A, PartialCompletion on branch B merge cleanly."""
    latent = LatentPostconditions(
        on_ok=(FactTemplate("CompleteSuccessFact", ("cluster",)), FactTemplate("ClusterKnown", ("cluster",))),
        on_partial=(FactTemplate("PartialFootprintFact", ("$report",)), FactTemplate("ClusterKnown", ("cluster",))),
    )
    b_entry = BasicBlock(
        name="entry",
        terminator=TermCondBr(
            cond=Variable("c", BOOL),
            true_target="branch_a",
            true_args=(),
            false_target="branch_b",
            false_args=(),
        ),
    )
    b_a = BasicBlock(
        name="branch_a",
        instructions=[
            InstAct(dest=Variable("act_a", ActOutcomeType(STRING, STRING)), op_id="update_cluster_a", is_atomic=False, latent=latent)
        ],
        terminator=TermSwitchActOutcome(
            outcome_var=Variable("act_a", ActOutcomeType(STRING, STRING)),
            success_target="merge",
            success_arg=Variable("res_a", STRING),
            failure_target="merge",
            failure_arg=Variable("res_a", STRING),
        ),
    )
    b_b = BasicBlock(
        name="branch_b",
        instructions=[
            InstAct(dest=Variable("act_b", ActOutcomeType(STRING, STRING)), op_id="update_cluster_b", is_atomic=False, latent=latent)
        ],
        terminator=TermSwitchActOutcome(
            outcome_var=Variable("act_b", ActOutcomeType(STRING, STRING)),
            success_target="merge",
            success_arg=Variable("res_b", STRING),
            failure_target="merge",
            failure_arg=Variable("res_b", STRING),
            partial_target="merge",
            partial_arg=Variable("res_b", STRING),
        ),
    )
    b_merge = BasicBlock(
        name="merge",
        params=[Variable("res_m", STRING)],
        terminator=TermReturn(Variable("res_m", STRING)),
    )
    return CFGProgram(name="X2_partial_merge_integration", entry="entry", blocks={
        "entry": b_entry, "branch_a": b_a, "branch_b": b_b, "merge": b_merge,
    })


def build_x3_x4_handle_await_refinement_integration() -> CFGProgram:
    """X3/X4: Handle join + await (Σ_await=∅) + Result Refinement with latent postconditions."""
    child_latent = LatentPostconditions(
        on_ok=(FactTemplate("ChildJobVerified", ("$value",)),)
    )
    eff_a = frozenset(["read[A]"])
    eff_b = frozenset(["infer[B]", "act[B]"])

    b_entry = BasicBlock(
        name="entry",
        terminator=TermCondBr(
            cond=Variable("branch_cond", BOOL),
            true_target="branch_worker_a",
            true_args=(),
            false_target="branch_worker_b",
            false_args=(),
        ),
    )
    b_wa = BasicBlock(
        name="branch_worker_a",
        instructions=[
            InstSpawnChild(dest=Variable("h_a", ChildHandleType(STRING, STRING, eff_a)), child_id="workerA", may_effects=eff_a, ok_type=STRING, err_type=STRING, latent=child_latent)
        ],
        terminator=TermBr(target="join_point", args=(Variable("h_a", ChildHandleType(STRING, STRING, eff_a)),)),
    )
    b_wb = BasicBlock(
        name="branch_worker_b",
        instructions=[
            InstSpawnChild(dest=Variable("h_b", ChildHandleType(STRING, STRING, eff_b)), child_id="workerB", may_effects=eff_b, ok_type=STRING, err_type=STRING, latent=child_latent)
        ],
        terminator=TermBr(target="join_point", args=(Variable("h_b", ChildHandleType(STRING, STRING, eff_b)),)),
    )
    b_join = BasicBlock(
        name="join_point",
        params=[Variable("h_merged", ChildHandleType(STRING, STRING, eff_a | eff_b))],
        instructions=[
            InstAwaitHandle(dest=Variable("r_await", ResultType(STRING, STRING)), handle=Variable("h_merged", ChildHandleType(STRING, STRING, eff_a | eff_b)))
        ],
        terminator=TermSwitchResult(
            result_var=Variable("r_await", ResultType(STRING, STRING)),
            ok_target="child_ok",
            ok_arg=Variable("v_child", STRING),
            err_target="child_err",
            err_arg=Variable("e_child", STRING),
        ),
    )
    b_ok = BasicBlock(name="child_ok", params=[Variable("v_child", STRING)], terminator=TermReturn(Variable("v_child", STRING)))
    b_err = BasicBlock(name="child_err", params=[Variable("e_child", STRING)], terminator=TermReturn(Variable("e_child", STRING)))
    return CFGProgram(name="X3_X4_handle_await_refinement_integration", entry="entry", blocks={
        "entry": b_entry, "branch_worker_a": b_wa, "branch_worker_b": b_wb,
        "join_point": b_join, "child_ok": b_ok, "child_err": b_err,
    })
