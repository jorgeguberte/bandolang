"""test_negative_s4.py — Negative Verifier Tests S4V01–S4V07 for Compiler Conformance v0 (Slice 4).

Verifies fail-closed static enforcement of:
- Pure search policy (Σ_search_policy = ∅)
- Complete declared effect envelope (Σ_converge = Σ_space ∪ Σ_satisfier)
- Non-zero positive budget scope limit
- Non-zero positive step fuel limit
- Non-zero positive satisfaction attempt limit
- Valid on_step_failure policy descriptor
- Valid on_satisfier_error policy descriptor
Asserts exact DiagnosticCode values.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "compiler_conformance"))

from protocol import invoke_rust_conformance

PASS = 0
FAIL = 0


def make_type_string():
    return {"kind": "String"}


def make_type_result(ok, err):
    return {"kind": "Result", "payload": {"ok": ok, "err": err}}


def make_type_convergence_outcome(satisfied, exhausted):
    return {
        "kind": "ConvergenceOutcome",
        "payload": {
            "satisfied": satisfied,
            "exhausted": {"kind": "ExhaustionReport", "payload": exhausted},
        },
    }


def run_negative(name: str, program: dict, expected_code: str) -> None:
    global PASS, FAIL
    print(f"\n--- NEGATIVE VERIFIER TEST (Slice 4): {name}")
    try:
        obs = invoke_rust_conformance(program)
        if obs["status"] not in ("verifier_error", "vm_verifier_error"):
            print(f"  ✗ FAIL {name}: expected verifier error, got '{obs['status']}'")
            FAIL += 1
            return
        diags = obs.get("diagnostics", [])
        codes = [d.get("code") for d in diags]
        if expected_code not in codes:
            print(f"  ✗ FAIL {name}: expected diagnostic code '{expected_code}', got {codes}")
            FAIL += 1
            return
        print(f"  ✓ PASS {name} (correctly rejected with {expected_code})")
        PASS += 1
    except Exception as e:
        print(f"  ✗ FAIL {name}: crashed with exception {type(e).__name__}: {e}")
        FAIL += 1


def base_converge_program(converge_inst: dict, declared_effects: list = None) -> dict:
    if declared_effects is None:
        declared_effects = [{"Read": "space_data"}, {"Act": "target_ws"}]
    return {
        "name": "NegativeTest",
        "entry_func": "main",
        "inputs": {},
        "module": {
            "name": "m",
            "functions": [
                {
                    "name": "main",
                    "params": [],
                    "return_type": make_type_result(
                        make_type_convergence_outcome(make_type_string(), make_type_string()),
                        make_type_string(),
                    ),
                    "declared_effects": {"effects": declared_effects},
                    "entry": 0,
                    "blocks": {
                        "0": {
                            "id": 0,
                            "params": [],
                            "instructions": [{"Converge": converge_inst}],
                            "terminator": {"Return": 1},
                        }
                    },
                }
            ],
        },
    }


# S4V01: Effectful SearchPolicy
def s4v01_effectful_search_policy():
    inst = {
        "dest": 1,
        "root_node": "root",
        "space_ops": ["op_space"],
        "satisfier_op": "local_satisfier",
        "search_policy": {
            "policy_id": "dirty_policy",
            "on_step_failure": "abort",
            "on_satisfier_error": "abort",
            "policy_effects": {"effects": [{"Read": "hidden_db"}]},
        },
        "budget_scope": {"resource": "usd", "limit": 100},
        "max_steps": 10,
        "max_satisfaction_attempts": 5,
        "space_effects": {"effects": [{"Read": "space_data"}]},
        "satisfier_effects": {"effects": []},
        "partial_type": make_type_string(),
        "satisfied_type": make_type_string(),
    }
    prog = base_converge_program(inst, declared_effects=[{"Read": "space_data"}, {"Read": "hidden_db"}])
    run_negative("S4V01_effectful_search_policy", prog, "EffectfulSearchPolicy")


# S4V02: Converge effect undeclared
def s4v02_converge_effect_undeclared():
    inst = {
        "dest": 1,
        "root_node": "root",
        "space_ops": ["op_space"],
        "satisfier_op": "local_satisfier",
        "search_policy": {
            "policy_id": "pure_policy",
            "on_step_failure": "abort",
            "on_satisfier_error": "abort",
            "policy_effects": {"effects": []},
        },
        "budget_scope": {"resource": "usd", "limit": 100},
        "max_steps": 10,
        "max_satisfaction_attempts": 5,
        "space_effects": {"effects": [{"Read": "space_data"}, {"Act": "target_ws"}]},
        "satisfier_effects": {"effects": []},
        "partial_type": make_type_string(),
        "satisfied_type": make_type_string(),
    }
    # Declared effects omits Act[target_ws]
    prog = base_converge_program(inst, declared_effects=[{"Read": "space_data"}])
    run_negative("S4V02_converge_effect_undeclared", prog, "EffectUndeclared")


# S4V03: Invalid budget limit zero
def s4v03_invalid_budget_limit_zero():
    inst = {
        "dest": 1,
        "root_node": "root",
        "space_ops": ["op_space"],
        "satisfier_op": "local_satisfier",
        "search_policy": {
            "policy_id": "pure_policy",
            "on_step_failure": "abort",
            "on_satisfier_error": "abort",
            "policy_effects": {"effects": []},
        },
        "budget_scope": {"resource": "usd", "limit": 0},
        "max_steps": 10,
        "max_satisfaction_attempts": 5,
        "space_effects": {"effects": [{"Read": "space_data"}]},
        "satisfier_effects": {"effects": []},
        "partial_type": make_type_string(),
        "satisfied_type": make_type_string(),
    }
    prog = base_converge_program(inst, declared_effects=[{"Read": "space_data"}])
    run_negative("S4V03_invalid_budget_limit_zero", prog, "InvalidBudgetLimit")


# S4V04: Invalid max_steps zero
def s4v04_invalid_max_steps_zero():
    inst = {
        "dest": 1,
        "root_node": "root",
        "space_ops": ["op_space"],
        "satisfier_op": "local_satisfier",
        "search_policy": {
            "policy_id": "pure_policy",
            "on_step_failure": "abort",
            "on_satisfier_error": "abort",
            "policy_effects": {"effects": []},
        },
        "budget_scope": {"resource": "usd", "limit": 100},
        "max_steps": 0,
        "max_satisfaction_attempts": 5,
        "space_effects": {"effects": [{"Read": "space_data"}]},
        "satisfier_effects": {"effects": []},
        "partial_type": make_type_string(),
        "satisfied_type": make_type_string(),
    }
    prog = base_converge_program(inst, declared_effects=[{"Read": "space_data"}])
    run_negative("S4V04_invalid_max_steps_zero", prog, "InvalidAttemptLimit")


# S4V05: Invalid max_satisfaction_attempts zero
def s4v05_invalid_max_satisfaction_attempts_zero():
    inst = {
        "dest": 1,
        "root_node": "root",
        "space_ops": ["op_space"],
        "satisfier_op": "local_satisfier",
        "search_policy": {
            "policy_id": "pure_policy",
            "on_step_failure": "abort",
            "on_satisfier_error": "abort",
            "policy_effects": {"effects": []},
        },
        "budget_scope": {"resource": "usd", "limit": 100},
        "max_steps": 10,
        "max_satisfaction_attempts": 0,
        "space_effects": {"effects": [{"Read": "space_data"}]},
        "satisfier_effects": {"effects": []},
        "partial_type": make_type_string(),
        "satisfied_type": make_type_string(),
    }
    prog = base_converge_program(inst, declared_effects=[{"Read": "space_data"}])
    run_negative("S4V05_invalid_max_satisfaction_attempts_zero", prog, "InvalidAttemptLimit")


# S4V06: Malformed on_step_failure policy
def s4v06_malformed_on_step_failure():
    inst = {
        "dest": 1,
        "root_node": "root",
        "space_ops": ["op_space"],
        "satisfier_op": "local_satisfier",
        "search_policy": {
            "policy_id": "pure_policy",
            "on_step_failure": "illegal_fallback_policy",
            "on_satisfier_error": "abort",
            "policy_effects": {"effects": []},
        },
        "budget_scope": {"resource": "usd", "limit": 100},
        "max_steps": 10,
        "max_satisfaction_attempts": 5,
        "space_effects": {"effects": [{"Read": "space_data"}]},
        "satisfier_effects": {"effects": []},
        "partial_type": make_type_string(),
        "satisfied_type": make_type_string(),
    }
    prog = base_converge_program(inst, declared_effects=[{"Read": "space_data"}])
    run_negative("S4V06_malformed_on_step_failure", prog, "MalformedDescriptor")


# S4V07: Malformed on_satisfier_error policy
def s4v07_malformed_on_satisfier_error():
    inst = {
        "dest": 1,
        "root_node": "root",
        "space_ops": ["op_space"],
        "satisfier_op": "local_satisfier",
        "search_policy": {
            "policy_id": "pure_policy",
            "on_step_failure": "abort",
            "on_satisfier_error": "invented_error_handler",
            "policy_effects": {"effects": []},
        },
        "budget_scope": {"resource": "usd", "limit": 100},
        "max_steps": 10,
        "max_satisfaction_attempts": 5,
        "space_effects": {"effects": [{"Read": "space_data"}]},
        "satisfier_effects": {"effects": []},
        "partial_type": make_type_string(),
        "satisfied_type": make_type_string(),
    }
    prog = base_converge_program(inst, declared_effects=[{"Read": "space_data"}])
    run_negative("S4V07_malformed_on_satisfier_error", prog, "MalformedDescriptor")


def main():
    print("=" * 70)
    print("SOMA COMPILER CONFORMANCE v0 (SLICE 4) — Negative Verifier Tests (S4V01–S4V07)")

    s4v01_effectful_search_policy()
    s4v02_converge_effect_undeclared()
    s4v03_invalid_budget_limit_zero()
    s4v04_invalid_max_steps_zero()
    s4v05_invalid_max_satisfaction_attempts_zero()
    s4v06_malformed_on_step_failure()
    s4v07_malformed_on_satisfier_error()

    print("=" * 70)
    print(f"SLICE 4 NEGATIVE VERIFIER RESULT: {PASS} passed, {FAIL} failed ({PASS + FAIL} total)")
    if FAIL > 0:
        sys.exit(1)
    print("All 7 Slice 4 Negative Verifier Tests correctly rejected by Rust Verifier.")


if __name__ == "__main__":
    main()
