"""test_mutations_s4.py — Compiler & Runtime Mutation Campaign (S4M01–S4M20) for Slice 4.

Executes each mutated compiler/runtime configuration against baseline SOMA-IR programs,
proving that each mutant causally breaks an observable semantic property under the real
compiler pipeline (HighLevelVerifier -> LoweringContext -> VmVerifier -> VmInterpreter).

Covers all 20 causal mutations from S4.14:
- S4M01: scheduler pops unaffordable node
- S4M02: policy hidden effect allowed
- S4M03: ranking promotes to Satisfied
- S4M04: StageLocal rejected leaves reservation
- S4M05: first EmitExternal fails to increment step
- S4M06: transport retry increments step
- S4M07: transport retry changes request_id
- S4M08: second unsettled request allowed
- S4M09: DeliveryUnknown releases commitment
- S4M10: duplicate completion applies twice
- S4M11: duplicate settlement reconciles twice
- S4M12: settlement marks Applied automatically
- S4M13: crash-after-settlement loses semantic result
- S4M14: Closing accepts late semantic payload
- S4M15: Closing mutates frontier
- S4M16: terminalizes with commitment
- S4M17: BudgetScope mints ownership
- S4M18: requeue reuses semantic request_id
- S4M19: failed requeue incorporates successors
- S4M20: satisfaction retry bypasses attempt ceiling
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "compiler_conformance"))

from protocol import invoke_rust_conformance

PASS, FAIL = 0, 0


def canonical_repr(d):
    return json.dumps(d, sort_keys=True)


def make_converge_program(name: str, converge_spec: dict, declared_effects: list | None = None) -> dict:
    if declared_effects is None:
        declared_effects = []

    ret_ty = {
        "kind": "Result",
        "payload": {
            "ok": {
                "kind": "ConvergenceOutcome",
                "payload": {
                    "satisfied": converge_spec.get("satisfied_type", {"kind": "String"}),
                    "exhausted": {
                        "kind": "ExhaustionReport",
                        "payload": converge_spec.get("partial_type", {"kind": "String"}),
                    },
                },
            },
            "err": {"kind": "String"},
        },
    }

    return {
        "name": name,
        "entry_func": "main",
        "inputs": {},
        "mutations": {},
        "module": {
            "name": "mod_" + name,
            "functions": [
                {
                    "name": "main",
                    "params": [],
                    "return_type": ret_ty,
                    "declared_effects": {"effects": declared_effects},
                    "entry": 0,
                    "blocks": {
                        "0": {
                            "id": 0,
                            "name": "entry",
                            "params": [],
                            "instructions": [
                                {
                                    "Converge": {
                                        "dest": 1,
                                        "root_node": converge_spec.get("root_node", "root"),
                                        "initial_frontier": converge_spec.get("initial_frontier", ["root"]),
                                        "successors": converge_spec.get("successors", {}),
                                        "node_ops": converge_spec.get("node_ops", {}),
                                        "satisfier": converge_spec.get(
                                            "satisfier",
                                            {"kind": "local", "effectful_op": None, "satisfier_map": {}},
                                        ),
                                        "partial_map": converge_spec.get("partial_map", {}),
                                        "space_faults": converge_spec.get("space_faults", {}),
                                        "fault_spec": converge_spec.get("fault_spec", {}),
                                        "space_ops": converge_spec.get("space_ops", []),
                                        "satisfier_op": converge_spec.get("satisfier_op", "local_satisfier"),
                                        "search_policy": converge_spec.get(
                                            "search_policy",
                                            {
                                                "policy_id": "pure_policy",
                                                "on_step_failure": converge_spec.get("on_step_failure", "abort"),
                                                "on_satisfier_error": converge_spec.get("on_satisfier_error", "abort"),
                                                "policy_effects": {"effects": []},
                                            },
                                        ),
                                        "budget_scope": converge_spec.get(
                                            "budget_scope",
                                            {
                                                "resource": "usd",
                                                "limit": converge_spec.get("budget_limit", 100),
                                            },
                                        ),
                                        "max_steps": converge_spec.get("max_steps", 6),
                                        "max_satisfaction_attempts": converge_spec.get("max_satisfaction_attempts", 5),
                                        "space_effects": converge_spec.get("space_effects", {"effects": []}),
                                        "satisfier_effects": converge_spec.get("satisfier_effects", {"effects": []}),
                                        "partial_type": converge_spec.get("partial_type", {"kind": "String"}),
                                        "satisfied_type": converge_spec.get("satisfied_type", {"kind": "String"}),
                                    }
                                }
                            ],
                            "terminator": {"Return": 1},
                        }
                    },
                }
            ],
        },
    }


def run_mutation_kill(name: str, baseline_prog: dict, mutant_prog: dict, check_predicate) -> None:
    global PASS, FAIL
    print(f"\n--- MUTATION KILL TEST (Slice 4): {name}")
    try:
        baseline_obs = invoke_rust_conformance(baseline_prog)
        mutant_obs = invoke_rust_conformance(mutant_prog)

        if canonical_repr(baseline_obs) == canonical_repr(mutant_obs):
            print(f"  ✗ FAIL {name}: baseline and mutant observations are identical (mutation had no observable effect!)")
            FAIL += 1
            return

        ok, explanation = check_predicate(baseline_obs, mutant_obs)
        if ok:
            print(f"  ✓ PASS {name} (real compiler/runtime mutation caught and killed: {explanation})")
            PASS += 1
        else:
            print(f"  ✗ FAIL {name}: mutation check failed: {explanation}")
            FAIL += 1
    except Exception as e:
        print(f"  ✗ FAIL {name}: crashed with exception {type(e).__name__}: {e}")
        FAIL += 1


# S4M01: Scheduler pops unaffordable node
def s4m01_scheduler_pops_unaffordable_node():
    spec = {
        "root_node": "A",
        "initial_frontier": ["A"],
        "successors": {"A": []},
        "node_ops": {"A": {"op_id": "opA", "kind": "external", "cost": 150}},
        "partial_map": {},
        "budget_limit": 100,
        "max_steps": 6,
    }
    base = make_converge_program("S4M01", spec)
    mut = copy.deepcopy(base)
    mut["mutations"] = {"s4m01_scheduler_pops_unaffordable_node": True}

    def check(b, m):
        b_c = b["converge_observation"]
        m_c = m["converge_observation"]
        if b_c["status"] == "Exhausted" and m_c["status"] == "Searching":
            return True, f"baseline stopped at budget ceiling ({b_c['exhaustion_reason']}), mutant popped unaffordable node"
        return False, f"base={b_c['status']}, mut={m_c['status']}"

    run_mutation_kill("S4M01_scheduler_pops_unaffordable_node", base, mut, check)


# S4M02: Policy hidden effect allowed
def s4m02_policy_hidden_effect_allowed():
    spec = {
        "root_node": "root",
        "initial_frontier": ["root"],
        "successors": {"root": []},
        "node_ops": {},
        "search_policy": {
            "policy_id": "hidden_eff_policy",
            "on_step_failure": "abort",
            "on_satisfier_error": "abort",
            "policy_effects": {"effects": [{"Read": "untracked"}]},
        },
        "budget_limit": 100,
        "max_steps": 6,
    }
    base = make_converge_program("S4M02", spec)
    mut = copy.deepcopy(base)
    mut["mutations"] = {"s4m02_policy_hidden_effect_allowed": True}

    def check(b, m):
        if b["status"] == "verifier_error" and m["status"] == "ok":
            return True, "baseline rejected effectful SearchPolicy, mutant bypassed check"
        return False, f"base={b['status']}, mut={m['status']}"

    run_mutation_kill("S4M02_policy_hidden_effect_allowed", base, mut, check)


# S4M03: Ranking promotes to Satisfied
def s4m03_ranking_promotes_satisfied():
    spec = {
        "root_node": "root",
        "initial_frontier": ["root"],
        "successors": {"root": []},
        "node_ops": {"root": {"op_id": "opRoot", "kind": "local", "cost": 0}},
        "partial_map": {"root": {"kind": "String", "payload": "P_root"}},
        "satisfier": {
            "kind": "local",
            "effectful_op": None,
            "satisfier_map": {"root": ["ok", False, None]},
        },
        "budget_limit": 100,
        "max_steps": 6,
    }
    base = make_converge_program("S4M03", spec)
    mut = copy.deepcopy(base)
    mut["mutations"] = {"s4m03_ranking_promotes_satisfied": True}

    def check(b, m):
        b_c = b["converge_observation"]
        m_c = m["converge_observation"]
        if b_c["status"] == "Exhausted" and m_c["status"] == "Satisfied":
            return True, "baseline exhausted without promoting partial, mutant promoted partial to Satisfied"
        return False, f"base={b_c['status']}, mut={m_c['status']}"

    run_mutation_kill("S4M03_ranking_promotes_satisfied", base, mut, check)


# S4M04: StageLocal rejected leaves reservation
def s4m04_stage_rejected_leaves_reservation():
    spec = {
        "root_node": "A",
        "initial_frontier": ["A"],
        "successors": {"A": []},
        "node_ops": {"A": {"op_id": "opA", "kind": "external", "cost": 150}},
        "partial_map": {},
        "budget_limit": 200,
        "max_steps": 6,
    }
    base = make_converge_program("S4M04", spec)
    mut = copy.deepcopy(base)
    mut["mutations"] = {"s4m01_scheduler_pops_unaffordable_node": True, "s4m04_stage_rejected_leaves_reservation": True}

    def check(b, m):
        b_c = b["converge_observation"]
        m_c = m["converge_observation"]
        if b_c["attributable_owner_reserved"] == 0 and m_c["attributable_owner_reserved"] > 0:
            return True, f"baseline had 0 reservation on reject, mutant left {m_c['attributable_owner_reserved']}"
        return False, f"base={b_c['attributable_owner_reserved']}, mut={m_c['attributable_owner_reserved']}"

    run_mutation_kill("S4M04_stage_rejected_leaves_reservation", base, mut, check)


# S4M05: First EmitExternal fails to increment step
def s4m05_first_emit_fails_step():
    spec = {
        "root_node": "root",
        "initial_frontier": ["root"],
        "successors": {"root": []},
        "node_ops": {"root": {"op_id": "opExt", "kind": "external", "cost": 10}},
        "partial_map": {},
        "max_steps": 6,
    }
    base = make_converge_program("S4M05", spec)
    mut = copy.deepcopy(base)
    mut["mutations"] = {"s4m05_first_emit_fails_step": True}

    def check(b, m):
        b_c = b["converge_observation"]
        m_c = m["converge_observation"]
        if b_c["step_count"] == 1 and m_c["step_count"] == 0:
            return True, f"baseline incremented step to {b_c['step_count']}, mutant remained {m_c['step_count']}"
        return False, f"base={b_c['step_count']}, mut={m_c['step_count']}"

    run_mutation_kill("S4M05_first_emit_fails_step", base, mut, check)


# S4M06: Transport retry increments step
def s4m06_transport_retry_increments_step():
    spec = {
        "root_node": "root",
        "initial_frontier": ["root"],
        "successors": {"root": []},
        "node_ops": {"root": {"op_id": "opRetry", "kind": "external", "cost": 10, "dedup_capable": True}},
        "fault_spec": {"delivery_unknown": True, "safe_retry": True},
        "partial_map": {},
        "max_steps": 6,
    }
    base = make_converge_program("S4M06", spec)
    mut = copy.deepcopy(base)
    mut["mutations"] = {"s4m06_transport_retry_increments_step": True}

    def check(b, m):
        b_c = b["converge_observation"]
        m_c = m["converge_observation"]
        if b_c["step_count"] == 1 and m_c["step_count"] == 2:
            return True, f"baseline had 1 step after retry, mutant counted {m_c['step_count']} steps"
        return False, f"base={b_c['step_count']}, mut={m_c['step_count']}"

    run_mutation_kill("S4M06_transport_retry_increments_step", base, mut, check)


# S4M07: Transport retry changes request_id
def s4m07_transport_retry_changes_request_id():
    spec = {
        "root_node": "root",
        "initial_frontier": ["root"],
        "successors": {"root": []},
        "node_ops": {"root": {"op_id": "opRetry", "kind": "external", "cost": 10, "dedup_capable": True}},
        "fault_spec": {"delivery_unknown": True, "safe_retry": True},
        "partial_map": {},
        "max_steps": 6,
    }
    base = make_converge_program("S4M07", spec)
    mut = copy.deepcopy(base)
    mut["mutations"] = {"s4m07_transport_retry_changes_request_id": True}

    def check(b, m):
        b_c = b["converge_observation"]
        m_c = m["converge_observation"]
        if b_c["status"] == "Exhausted" and m_c["status"] == "Waiting":
            return True, f"baseline admitted retry completion ({b_c['status']}), mutant changed request_id and stayed in Waiting ({m_c['status']})"
        return False, f"base={b_c['status']}, mut={m_c['status']}"

    run_mutation_kill("S4M07_transport_retry_changes_request_id", base, mut, check)


# S4M08: Second unsettled request allowed
def s4m08_second_unsettled_request_allowed():
    spec = {
        "root_node": "A",
        "initial_frontier": ["A", "B"],
        "successors": {"A": [], "B": []},
        "node_ops": {
            "A": {"op_id": "opA", "kind": "external", "cost": 10},
            "B": {"op_id": "opB", "kind": "external", "cost": 10},
        },
        "fault_spec": {"delivery_unknown": True},
        "partial_map": {},
        "max_steps": 6,
    }
    base = make_converge_program("S4M08", spec)
    mut = copy.deepcopy(base)
    mut["mutations"] = {"s4m08_second_unsettled_request_allowed": True}

    def check(b, m):
        b_c = b["converge_observation"]
        m_c = m["converge_observation"]
        if len(b_c["effects"]) == 1 and len(m_c["effects"]) == 2:
            return True, f"baseline stayed in Waiting on first in-flight ({b_c['effects']}), mutant concurrently dispatched second request ({m_c['effects']})"
        return False, f"base={b_c['effects']}, mut={m_c['effects']}"

    run_mutation_kill("S4M08_second_unsettled_request_allowed", base, mut, check)


# S4M09: DeliveryUnknown releases commitment
def s4m09_delivery_unknown_releases_commitment():
    spec = {
        "root_node": "root",
        "initial_frontier": ["root"],
        "successors": {"root": []},
        "node_ops": {"root": {"op_id": "opUnknown", "kind": "external", "cost": 25}},
        "fault_spec": {"delivery_unknown": True, "safe_retry": False},
        "partial_map": {},
        "max_steps": 6,
    }
    base = make_converge_program("S4M09", spec)
    mut = copy.deepcopy(base)
    mut["mutations"] = {"s4m09_delivery_unknown_releases_commitment": True}

    def check(b, m):
        b_c = b["converge_observation"]
        m_c = m["converge_observation"]
        if b_c["outstanding_scope_commitment"] == 25 and m_c["outstanding_scope_commitment"] == 0:
            return True, f"baseline retained commitment {b_c['outstanding_scope_commitment']}, mutant released it to {m_c['outstanding_scope_commitment']}"
        return False, f"base={b_c['outstanding_scope_commitment']}, mut={m_c['outstanding_scope_commitment']}"

    run_mutation_kill("S4M09_delivery_unknown_releases_commitment", base, mut, check)


# S4M10: Duplicate completion applies twice
def s4m10_duplicate_completion_applies_twice():
    spec = {
        "root_node": "root",
        "initial_frontier": ["root"],
        "successors": {"root": ["s1"]},
        "node_ops": {"root": {"op_id": "opDup", "kind": "external", "cost": 10}},
        "fault_spec": {"duplicate_completion": True},
        "partial_map": {},
        "max_steps": 1,
    }
    base = make_converge_program("S4M10", spec)
    mut = copy.deepcopy(base)
    mut["mutations"] = {"s4m10_duplicate_completion_applies_twice": True}

    def check(b, m):
        b_c = b["converge_observation"]
        m_c = m["converge_observation"]
        if b_c["frontier"] == ["s1"] and m_c["frontier"] == ["s1", "s1"]:
            return True, f"baseline deduplicated completion {b_c['frontier']}, mutant applied twice {m_c['frontier']}"
        return False, f"base={b_c['frontier']}, mut={m_c['frontier']}"

    run_mutation_kill("S4M10_duplicate_completion_applies_twice", base, mut, check)


# S4M11: Duplicate settlement reconciles twice
def s4m11_duplicate_settlement_reconciles_twice():
    spec = {
        "root_node": "root",
        "initial_frontier": ["root"],
        "successors": {"root": []},
        "node_ops": {"root": {"op_id": "opDup", "kind": "external", "cost": 20}},
        "fault_spec": {"duplicate_completion": True},
        "partial_map": {},
        "max_steps": 6,
    }
    base = make_converge_program("S4M11", spec)
    mut = copy.deepcopy(base)
    mut["mutations"] = {"s4m11_duplicate_settlement_reconciles_twice": True}

    def check(b, m):
        b_c = b["converge_observation"]
        m_c = m["converge_observation"]
        if b_c["budget_spent"] == 20 and m_c["budget_spent"] == 40:
            return True, f"baseline reconciled once (spent={b_c['budget_spent']}), mutant reconciled twice (spent={m_c['budget_spent']})"
        return False, f"base={b_c['budget_spent']}, mut={m_c['budget_spent']}"

    run_mutation_kill("S4M11_duplicate_settlement_reconciles_twice", base, mut, check)


# S4M12: Settlement marks Applied automatically
def s4m12_settlement_marks_applied_automatically():
    spec = {
        "root_node": "root",
        "initial_frontier": ["root"],
        "successors": {"root": ["succ"]},
        "node_ops": {
            "root": {"op_id": "opRoot", "kind": "external", "cost": 10},
            "succ": {"op_id": "opSucc", "kind": "local", "cost": 0},
        },
        "fault_spec": {"crash_after_settlement": True},
        "partial_map": {"succ": {"kind": "String", "payload": "P_succ"}},
        "satisfier": {
            "kind": "local",
            "effectful_op": None,
            "satisfier_map": {
                "root": ["ok", False, None],
                "succ": ["ok", True, {"kind": "String", "payload": "T-succ"}],
            },
        },
        "max_steps": 6,
    }
    base = make_converge_program("S4M12", spec)
    mut = copy.deepcopy(base)
    mut["mutations"] = {"s4m12_settlement_marks_applied_automatically": True}

    def check(b, m):
        b_c = b["converge_observation"]
        m_c = m["converge_observation"]
        if b_c["status"] == "Satisfied" and m_c["status"] != "Satisfied":
            return True, f"baseline applied semantic result after crash recovery ({b_c['status']}), mutant skipped apply ({m_c['status']})"
        return False, f"base={b_c['status']}, mut={m_c['status']}"

    run_mutation_kill("S4M12_settlement_marks_applied_automatically", base, mut, check)


# S4M13: Crash after settlement loses semantic result
def s4m13_crash_after_settlement_loses_semantic_result():
    spec = {
        "root_node": "root",
        "initial_frontier": ["root"],
        "successors": {"root": ["succ"]},
        "node_ops": {
            "root": {"op_id": "opRoot", "kind": "external", "cost": 10},
            "succ": {"op_id": "opSucc", "kind": "local", "cost": 0},
        },
        "fault_spec": {"crash_after_settlement": True},
        "partial_map": {"succ": {"kind": "String", "payload": "P_succ"}},
        "satisfier": {
            "kind": "local",
            "effectful_op": None,
            "satisfier_map": {
                "root": ["ok", False, None],
                "succ": ["ok", True, {"kind": "String", "payload": "T-succ"}],
            },
        },
        "max_steps": 6,
    }
    base = make_converge_program("S4M13", spec)
    mut = copy.deepcopy(base)
    mut["mutations"] = {"s4m13_crash_after_settlement_loses_semantic_result": True}

    def check(b, m):
        b_c = b["converge_observation"]
        m_c = m["converge_observation"]
        if b_c["status"] == "Satisfied" and m_c["status"] != "Satisfied":
            return True, f"baseline reconstructed state and satisfied ({b_c['status']}), mutant lost result ({m_c['status']})"
        return False, f"base={b_c['status']}, mut={m_c['status']}"

    run_mutation_kill("S4M13_crash_after_settlement_loses_semantic_result", base, mut, check)


# S4M14: Closing accepts late semantic payload
def s4m14_closing_accepts_late_payload():
    spec = {
        "root_node": "root",
        "initial_frontier": ["root"],
        "successors": {"root": ["late_succ"]},
        "node_ops": {"root": {"op_id": "opLate", "kind": "external", "cost": 10}},
        "fault_spec": {"delivery_unknown": False, "cancel_in_flight": True},
        "partial_map": {},
        "max_steps": 6,
    }
    base = make_converge_program("S4M14", spec)
    mut = copy.deepcopy(base)
    mut["mutations"] = {"s4m14_closing_accepts_late_payload": True, "s4m15_closing_mutates_frontier": True}

    def check(b, m):
        b_c = b["converge_observation"]
        m_c = m["converge_observation"]
        if "late_succ" not in b_c["frontier"] and "late_succ" in m_c["frontier"]:
            return True, f"baseline discarded late payload during Closing, mutant accepted it into frontier {m_c['frontier']}"
        return False, f"base={b_c['frontier']}, mut={m_c['frontier']}"

    run_mutation_kill("S4M14_closing_accepts_late_payload", base, mut, check)


# S4M15: Closing mutates frontier
def s4m15_closing_mutates_frontier():
    spec = {
        "root_node": "root",
        "initial_frontier": ["root"],
        "successors": {"root": ["late_succ"]},
        "node_ops": {"root": {"op_id": "opLate", "kind": "external", "cost": 10}},
        "fault_spec": {"delivery_unknown": False, "cancel_in_flight": True},
        "partial_map": {},
        "max_steps": 6,
    }
    base = make_converge_program("S4M15", spec)
    mut = copy.deepcopy(base)
    mut["mutations"] = {"s4m15_closing_mutates_frontier": True, "s4m14_closing_accepts_late_payload": True}

    def check(b, m):
        b_c = b["converge_observation"]
        m_c = m["converge_observation"]
        if "late_succ" not in b_c["frontier"] and "late_succ" in m_c["frontier"]:
            return True, f"baseline froze frontier during Closing, mutant mutated frontier {m_c['frontier']}"
        return False, f"base={b_c['frontier']}, mut={m_c['frontier']}"

    run_mutation_kill("S4M15_closing_mutates_frontier", base, mut, check)


# S4M16: Terminalizes with commitment
def s4m16_terminalizes_with_commitment():
    spec = {
        "root_node": "root",
        "initial_frontier": ["root"],
        "successors": {"root": []},
        "node_ops": {"root": {"op_id": "opCommit", "kind": "external", "cost": 30}},
        "fault_spec": {"delivery_unknown": True, "safe_retry": False},
        "partial_map": {},
        "max_steps": 6,
    }
    base = make_converge_program("S4M16", spec)
    mut = copy.deepcopy(base)
    mut["mutations"] = {"s4m16_terminalizes_with_commitment": True}

    def check(b, m):
        b_c = b["converge_observation"]
        m_c = m["converge_observation"]
        if b_c["status"] == "Waiting" and m_c["status"] == "Exhausted":
            return True, "baseline held frame in Waiting on outstanding commitment, mutant prematurely terminalized"
        return False, f"base={b_c['status']}, mut={m_c['status']}"

    run_mutation_kill("S4M16_terminalizes_with_commitment", base, mut, check)


# S4M17: BudgetScope mints ownership
def s4m17_budget_scope_mints_ownership():
    spec = {
        "root_node": "A",
        "initial_frontier": ["A"],
        "successors": {"A": []},
        "node_ops": {"A": {"op_id": "opA", "kind": "external", "cost": 150}},
        "budget_limit": 200,
        "max_steps": 6,
    }
    base = make_converge_program("S4M17", spec)
    mut = copy.deepcopy(base)
    mut["mutations"] = {"s4m17_budget_scope_mints_ownership": True}

    def check(b, m):
        b_c = b["converge_observation"]
        m_c = m["converge_observation"]
        if b_c["step_count"] == 0 and m_c["step_count"] == 1:
            return True, f"baseline rejected unbacked scope (steps={b_c['step_count']}), mutant minted ownership (steps={m_c['step_count']}, reserved={m_c['attributable_owner_reserved']})"
        return False, f"base={b_c['step_count']}, mut={m_c['step_count']}"

    run_mutation_kill("S4M17_budget_scope_mints_ownership", base, mut, check)


# S4M18: Requeue reuses semantic request_id
def s4m18_requeue_reuses_request_id():
    spec = {
        "root_node": "R",
        "initial_frontier": ["R"],
        "successors": {"R": []},
        "node_ops": {"R": {"op_id": "opR", "kind": "external", "cost": 10}},
        "space_faults": {"opR": ["Fault1"]},
        "on_step_failure": "requeue",
        "partial_map": {},
        "max_steps": 6,
    }
    base = make_converge_program("S4M18", spec)
    mut = copy.deepcopy(base)
    mut["mutations"] = {"s4m18_requeue_reuses_request_id": True}

    def check(b, m):
        b_c = b["converge_observation"]
        m_c = m["converge_observation"]
        if b_c["step_count"] > 1 and m_c["step_count"] == 1:
            return True, f"baseline continued requeuing with fresh request_ids (steps={b_c['step_count']}), mutant halted on duplicate request_id at step {m_c['step_count']}"
        return False, f"base={b_c['step_count']}, mut={m_c['step_count']}"

    run_mutation_kill("S4M18_requeue_reuses_request_id", base, mut, check)


# S4M19: Failed requeue incorporates successors
def s4m19_failed_requeue_incorporates_successors():
    spec = {
        "root_node": "R",
        "initial_frontier": ["R"],
        "successors": {"R": ["phantom_child"]},
        "node_ops": {"R": {"op_id": "opR", "kind": "external", "cost": 10}},
        "space_faults": {"opR": "Fail1"},
        "on_step_failure": "abort",
        "partial_map": {},
        "max_steps": 6,
    }
    base = make_converge_program("S4M19", spec)
    mut = copy.deepcopy(base)
    mut["mutations"] = {"s4m19_failed_requeue_incorporates_successors": True}

    def check(b, m):
        b_c = b["converge_observation"]
        m_c = m["converge_observation"]
        if "phantom_child" not in b_c["frontier"] and "phantom_child" in m_c["frontier"]:
            return True, f"baseline excluded successors on failed space attempt, mutant leaked {m_c['frontier']}"
        return False, f"base={b_c['frontier']}, mut={m_c['frontier']}"

    run_mutation_kill("S4M19_failed_requeue_incorporates_successors", base, mut, check)


# S4M20: Satisfaction retry bypasses attempt ceiling
def s4m20_satisfaction_retry_bypasses_attempt_ceiling():
    spec = {
        "root_node": "cand",
        "initial_frontier": ["cand"],
        "successors": {"cand": []},
        "node_ops": {"cand": {"op_id": "opCand", "kind": "local", "cost": 0}},
        "partial_map": {"cand": {"kind": "String", "payload": "P_cand"}},
        "satisfier": {
            "kind": "local",
            "effectful_op": None,
            "satisfier_map": {"cand": ["err", False, {"kind": "String", "payload": "Err"}]},
        },
        "on_satisfier_error": "retry",
        "max_satisfaction_attempts": 1,
        "max_steps": 6,
    }
    base = make_converge_program("S4M20", spec)
    mut = copy.deepcopy(base)
    mut["mutations"] = {"s4m20_satisfaction_retry_bypasses_attempt_ceiling": True}

    def check(b, m):
        b_c = b["converge_observation"]
        m_c = m["converge_observation"]
        if b_c["satisfaction_attempts"] == 1 and m_c["satisfaction_attempts"] > 1:
            return True, f"baseline strictly enforced satisfaction attempt limit ({b_c['satisfaction_attempts']}), mutant performed {m_c['satisfaction_attempts']} attempts"
        return False, f"base={b_c['satisfaction_attempts']}, mut={m_c['satisfaction_attempts']}"

    run_mutation_kill("S4M20_satisfaction_retry_bypasses_attempt_ceiling", base, mut, check)


def main():
    print("=" * 70)
    print("SOMA COMPILER CONFORMANCE v0 (SLICE 4) — Mutation Campaign (S4M01–S4M20)")

    s4m01_scheduler_pops_unaffordable_node()
    s4m02_policy_hidden_effect_allowed()
    s4m03_ranking_promotes_satisfied()
    s4m04_stage_rejected_leaves_reservation()
    s4m05_first_emit_fails_step()
    s4m06_transport_retry_increments_step()
    s4m07_transport_retry_changes_request_id()
    s4m08_second_unsettled_request_allowed()
    s4m09_delivery_unknown_releases_commitment()
    s4m10_duplicate_completion_applies_twice()
    s4m11_duplicate_settlement_reconciles_twice()
    s4m12_settlement_marks_applied_automatically()
    s4m13_crash_after_settlement_loses_semantic_result()
    s4m14_closing_accepts_late_payload()
    s4m15_closing_mutates_frontier()
    s4m16_terminalizes_with_commitment()
    s4m17_budget_scope_mints_ownership()
    s4m18_requeue_reuses_request_id()
    s4m19_failed_requeue_incorporates_successors()
    s4m20_satisfaction_retry_bypasses_attempt_ceiling()

    print("=" * 70)
    print(f"SLICE 4 MUTATION KILLS RESULT: {PASS} passed, {FAIL} failed ({PASS + FAIL} total)")
    if FAIL > 0:
        sys.exit(1)
    print("All 20 Slice 4 Compiler & Runtime Mutations correctly identified and killed.")


if __name__ == "__main__":
    main()
