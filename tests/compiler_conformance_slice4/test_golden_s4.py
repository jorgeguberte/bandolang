"""test_golden_s4.py — SOMA-IR Compiler Conformance v0 (Slice 4: soma.converge / ConvergeFrame v0).

All tests compile real SOMA-IR programs through the full compiler pipeline:
HighLevelVerifier -> LoweringContext -> VmVerifier -> VmInterpreter.

Covers Golden Matrix S4C01–S4C19:
- S4C01: Local expansion
- S4C02: Natural exhaustion (FrontierEmpty)
- S4C03: Successor satisfaction
- S4C04: Post-fuel satisfaction check
- S4C05: Effectful satisfier
- S4C06: StageLocal rejection
- S4C07: First external emission
- S4C08: Safe transport retry
- S4C09: Unsafe delivery unknown
- S4C10: Duplicate completion
- S4C11: Receipt equivocation
- S4C12: Crash after settlement recovery
- S4C13: Cancellation while in flight
- S4C14: Late settlement during Closing
- S4C15: Space step failure with abort
- S4C16: Space step failure with prune
- S4C17: Space step failure with requeue
- S4C18: Satisfaction retry and attempt limit
- S4C19: Full semantic pipeline & May-effects preservation (R4)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "compiler_conformance"))

from protocol import invoke_rust_conformance

PASS, FAIL = 0, 0


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


def run_golden(name: str, prog: dict, expected_converge_status: str, expected_val_payload=None) -> None:
    global PASS, FAIL
    print(f"\n--- GOLDEN PROGRAM (Slice 4): {name}")
    try:
        obs = invoke_rust_conformance(prog)
        if obs["status"] != "ok":
            print(f"  ✗ FAIL {name}: expected status 'ok', got {obs['status']}")
            FAIL += 1
            return

        c_obs = obs.get("converge_observation")
        if not c_obs:
            print(f"  ✗ FAIL {name}: missing converge_observation in toolchain output")
            FAIL += 1
            return

        if c_obs["status"] != expected_converge_status:
            print(f"  ✗ FAIL {name}: expected converge status '{expected_converge_status}', got '{c_obs['status']}'")
            FAIL += 1
            return

        if expected_val_payload is not None:
            val = c_obs.get("value")
            payload = val.get("payload") if isinstance(val, dict) else val
            if payload != expected_val_payload:
                print(f"  ✗ FAIL {name}: expected value payload '{expected_val_payload}', got '{payload}'")
                FAIL += 1
                return

        print(f"  ✓ PASS {name} (status=ok, converge={c_obs['status']})")
        PASS += 1
    except Exception as e:
        print(f"  ✗ FAIL {name}: crashed with exception {type(e).__name__}: {e}")
        FAIL += 1


# S4C01: Local expansion
def s4c01_local_expansion():
    spec = {
        "root_node": "root",
        "initial_frontier": ["root"],
        "successors": {"root": ["succ1", "succ2"]},
        "node_ops": {"root": {"op_id": "opRoot", "kind": "local", "cost": 0}},
        "max_steps": 6,
    }
    prog = make_converge_program("S4C01_local_expansion", spec)
    run_golden("S4C01_local_expansion", prog, expected_converge_status="Exhausted")


# S4C02: Natural exhaustion (FrontierEmpty)
def s4c02_natural_exhaustion():
    spec = {
        "root_node": "root",
        "initial_frontier": ["root"],
        "successors": {"root": []},
        "node_ops": {"root": {"op_id": "opRoot", "kind": "local", "cost": 0}},
        "max_steps": 6,
    }
    prog = make_converge_program("S4C02_natural_exhaustion", spec)
    run_golden("S4C02_natural_exhaustion", prog, expected_converge_status="Exhausted")


# S4C03: Successor satisfaction
def s4c03_successor_satisfaction():
    spec = {
        "root_node": "root",
        "initial_frontier": ["root"],
        "successors": {"root": ["succ"]},
        "node_ops": {"root": {"op_id": "opRoot", "kind": "local", "cost": 0}},
        "partial_map": {"succ": {"kind": "String", "payload": "P_succ"}},
        "satisfier": {
            "kind": "local",
            "effectful_op": None,
            "satisfier_map": {
                "root": ["ok", False, None],
                "succ": ["ok", True, {"kind": "String", "payload": "T-satisfied"}],
            },
        },
        "max_steps": 6,
    }
    prog = make_converge_program("S4C03_successor_satisfaction", spec)
    run_golden("S4C03_successor_satisfaction", prog, expected_converge_status="Satisfied", expected_val_payload="T-satisfied")


# S4C04: Post-fuel satisfaction check
def s4c04_post_fuel_satisfaction_check():
    spec = {
        "root_node": "root",
        "initial_frontier": ["root"],
        "successors": {"root": ["s1"]},
        "node_ops": {"root": {"op_id": "op1", "kind": "local", "cost": 0}},
        "partial_map": {"s1": {"kind": "String", "payload": "P_s1"}},
        "satisfier": {
            "kind": "local",
            "effectful_op": None,
            "satisfier_map": {
                "root": ["ok", False, None],
                "s1": ["ok", True, {"kind": "String", "payload": "T-post-fuel"}],
            },
        },
        "max_steps": 1,
    }
    prog = make_converge_program("S4C04_post_fuel_satisfaction_check", spec)
    run_golden("S4C04_post_fuel_satisfaction_check", prog, expected_converge_status="Satisfied", expected_val_payload="T-post-fuel")


# S4C05: Effectful satisfier
def s4c05_effectful_satisfier():
    spec = {
        "root_node": "root",
        "initial_frontier": ["root"],
        "successors": {"root": []},
        "node_ops": {"root": {"op_id": "opRoot", "kind": "local", "cost": 0}},
        "partial_map": {"root": {"kind": "String", "payload": "P_root"}},
        "satisfier": {
            "kind": "external",
            "effectful_op": {"op_id": "opSatExt", "kind": "external", "cost": 15, "actual_cost": 12},
            "satisfier_map": {
                "root": ["ok", True, {"kind": "String", "payload": "T-effectful"}],
            },
        },
        "budget_limit": 100,
        "max_steps": 6,
    }
    prog = make_converge_program("S4C05_effectful_satisfier", spec)
    run_golden("S4C05_effectful_satisfier", prog, expected_converge_status="Satisfied", expected_val_payload="T-effectful")


# S4C06: StageLocal rejection
def s4c06_stage_local_rejection():
    spec = {
        "root_node": "root",
        "initial_frontier": ["root"],
        "successors": {"root": []},
        "node_ops": {"root": {"op_id": "opExpensive", "kind": "external", "cost": 150}},
        "partial_map": {},
        "budget_limit": 100,
        "max_steps": 6,
    }
    prog = make_converge_program("S4C06_stage_local_rejection", spec)
    run_golden("S4C06_stage_local_rejection", prog, expected_converge_status="Exhausted")


# S4C07: First external emission
def s4c07_first_external_emission():
    spec = {
        "root_node": "root",
        "initial_frontier": ["root"],
        "successors": {"root": ["succ"]},
        "node_ops": {
            "root": {"op_id": "opExt", "kind": "external", "cost": 15},
            "succ": {"op_id": "opSucc", "kind": "local", "cost": 0},
        },
        "partial_map": {"succ": {"kind": "String", "payload": "P_succ"}},
        "satisfier": {
            "kind": "local",
            "effectful_op": None,
            "satisfier_map": {
                "root": ["ok", False, None],
                "succ": ["ok", True, {"kind": "String", "payload": "T-ext"}],
            },
        },
        "budget_limit": 100,
        "max_steps": 6,
    }
    prog = make_converge_program("S4C07_first_external_emission", spec)
    run_golden("S4C07_first_external_emission", prog, expected_converge_status="Satisfied", expected_val_payload="T-ext")


# S4C08: Safe transport retry
def s4c08_safe_transport_retry():
    spec = {
        "root_node": "root",
        "initial_frontier": ["root"],
        "successors": {"root": ["succ"]},
        "node_ops": {
            "root": {"op_id": "opRetry", "kind": "external", "cost": 20, "dedup_capable": True},
            "succ": {"op_id": "opSucc", "kind": "local", "cost": 0},
        },
        "fault_spec": {"delivery_unknown": True, "safe_retry": True},
        "partial_map": {"succ": {"kind": "String", "payload": "P_succ"}},
        "satisfier": {
            "kind": "local",
            "effectful_op": None,
            "satisfier_map": {
                "root": ["ok", False, None],
                "succ": ["ok", True, {"kind": "String", "payload": "T-retry"}],
            },
        },
        "budget_limit": 100,
        "max_steps": 6,
    }
    prog = make_converge_program("S4C08_safe_transport_retry", spec)
    run_golden("S4C08_safe_transport_retry", prog, expected_converge_status="Satisfied", expected_val_payload="T-retry")


# S4C09: Unsafe delivery unknown
def s4c09_unsafe_delivery_unknown():
    spec = {
        "root_node": "root",
        "initial_frontier": ["root"],
        "successors": {"root": []},
        "node_ops": {"root": {"op_id": "opNonIdemp", "kind": "external", "cost": 30, "dedup_capable": False, "idempotent": False}},
        "fault_spec": {"delivery_unknown": True, "safe_retry": False},
        "partial_map": {},
        "budget_limit": 100,
        "max_steps": 6,
    }
    prog = make_converge_program("S4C09_unsafe_delivery_unknown", spec)
    run_golden("S4C09_unsafe_delivery_unknown", prog, expected_converge_status="Waiting")


# S4C10: Duplicate completion
def s4c10_duplicate_completion():
    spec = {
        "root_node": "root",
        "initial_frontier": ["root"],
        "successors": {"root": []},
        "node_ops": {"root": {"op_id": "opDup", "kind": "external", "cost": 10}},
        "fault_spec": {"duplicate_completion": True},
        "partial_map": {},
        "max_steps": 6,
    }
    prog = make_converge_program("S4C10_duplicate_completion", spec)
    run_golden("S4C10_duplicate_completion", prog, expected_converge_status="Exhausted")


# S4C11: Receipt equivocation
def s4c11_receipt_equivocation():
    spec = {
        "root_node": "root",
        "initial_frontier": ["root"],
        "successors": {"root": []},
        "node_ops": {"root": {"op_id": "opEquiv", "kind": "local", "cost": 0}},
        "partial_map": {},
        "max_steps": 6,
    }
    prog = make_converge_program("S4C11_receipt_equivocation", spec)
    run_golden("S4C11_receipt_equivocation", prog, expected_converge_status="Exhausted")


# S4C12: Crash after settlement recovery
def s4c12_crash_after_settlement():
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
                "succ": ["ok", True, {"kind": "String", "payload": "T-recovered"}],
            },
        },
        "max_steps": 6,
    }
    prog = make_converge_program("S4C12_crash_after_settlement", spec)
    run_golden("S4C12_crash_after_settlement", prog, expected_converge_status="Satisfied", expected_val_payload="T-recovered")


# S4C13: Cancellation while in flight
def s4c13_cancel_in_flight():
    spec = {
        "root_node": "root",
        "initial_frontier": ["root"],
        "successors": {"root": []},
        "node_ops": {"root": {"op_id": "opCancel", "kind": "external", "cost": 10}},
        "partial_map": {},
        "fault_spec": {"delivery_unknown": False, "cancel_in_flight": True},
        "max_steps": 6,
    }
    prog = make_converge_program("S4C13_cancel_in_flight", spec)
    run_golden("S4C13_cancel_in_flight", prog, expected_converge_status="Cancelled")


# S4C14: Late settlement during Closing
def s4c14_late_settlement_during_closing():
    spec = {
        "root_node": "root",
        "initial_frontier": ["root"],
        "successors": {"root": []},
        "node_ops": {"root": {"op_id": "opLate", "kind": "external", "cost": 10}},
        "partial_map": {},
        "max_steps": 6,
    }
    prog = make_converge_program("S4C14_late_settlement_during_closing", spec)
    run_golden("S4C14_late_settlement_during_closing", prog, expected_converge_status="Exhausted")


# S4C15: Space step failure with abort
def s4c15_step_failure_abort():
    spec = {
        "root_node": "root",
        "initial_frontier": ["root"],
        "successors": {"root": []},
        "node_ops": {"root": {"op_id": "opFail", "kind": "external", "cost": 10}},
        "space_faults": {"opFail": "StepError"},
        "on_step_failure": "abort",
        "partial_map": {},
        "max_steps": 6,
    }
    prog = make_converge_program("S4C15_step_failure_abort", spec)
    run_golden("S4C15_step_failure_abort", prog, expected_converge_status="Failed")


# S4C16: Space step failure with prune
def s4c16_step_failure_prune():
    spec = {
        "root_node": "root",
        "initial_frontier": ["root", "other"],
        "successors": {"root": [], "other": []},
        "node_ops": {
            "root": {"op_id": "opFail", "kind": "external", "cost": 10},
            "other": {"op_id": "opOther", "kind": "local", "cost": 0},
        },
        "space_faults": {"opFail": "PruneError"},
        "on_step_failure": "prune",
        "partial_map": {"other": {"kind": "String", "payload": "P_other"}},
        "satisfier": {
            "kind": "local",
            "effectful_op": None,
            "satisfier_map": {
                "root": ["ok", False, None],
                "other": ["ok", True, {"kind": "String", "payload": "T-prune-success"}],
            },
        },
        "max_steps": 6,
    }
    prog = make_converge_program("S4C16_step_failure_prune", spec)
    run_golden("S4C16_step_failure_prune", prog, expected_converge_status="Satisfied", expected_val_payload="T-prune-success")


# S4C17: Space step failure with requeue
def s4c17_step_failure_requeue():
    spec = {
        "root_node": "root",
        "initial_frontier": ["root"],
        "successors": {"root": ["succQ"]},
        "node_ops": {
            "root": {"op_id": "opRequeue", "kind": "external", "cost": 10},
            "succQ": {"op_id": "opSuccQ", "kind": "local", "cost": 0},
        },
        "space_faults": {"opRequeue": ["TransientFail", None]},
        "on_step_failure": "requeue",
        "partial_map": {"succQ": {"kind": "String", "payload": "P_succQ"}},
        "satisfier": {
            "kind": "local",
            "effectful_op": None,
            "satisfier_map": {
                "root": ["ok", False, None],
                "succQ": ["ok", True, {"kind": "String", "payload": "T-requeue-success"}],
            },
        },
        "max_steps": 6,
    }
    prog = make_converge_program("S4C17_step_failure_requeue", spec)
    run_golden("S4C17_step_failure_requeue", prog, expected_converge_status="Satisfied", expected_val_payload="T-requeue-success")


# S4C18: Satisfaction retry and attempt limit
def s4c18_satisfaction_retry_limit():
    spec = {
        "root_node": "root",
        "initial_frontier": ["root"],
        "successors": {"root": []},
        "node_ops": {"root": {"op_id": "opRoot", "kind": "local", "cost": 0}},
        "partial_map": {"root": {"kind": "String", "payload": "P_root"}},
        "satisfier": {
            "kind": "local",
            "effectful_op": None,
            "satisfier_map": {
                "root": [["err", False, "Err1"], ["err", False, "Err2"]],
            },
        },
        "on_satisfier_error": "retry",
        "max_satisfaction_attempts": 2,
        "max_steps": 6,
    }
    prog = make_converge_program("S4C18_satisfaction_retry_limit", spec)
    run_golden("S4C18_satisfaction_retry_limit", prog, expected_converge_status="Exhausted")


# S4C19: Semantic converge pipeline & may-effects preservation (R4)
def s4c19_semantic_converge_instruction():
    spec = {
        "root_node": "root",
        "initial_frontier": ["root"],
        "successors": {"root": []},
        "node_ops": {"root": {"op_id": "opRoot", "kind": "local", "cost": 0}},
        "partial_map": {},
        "space_effects": {"effects": [{"Read": "data"}]},
        "satisfier_effects": {"effects": []},
        "max_steps": 6,
    }
    prog = make_converge_program("S4C19_semantic_converge_instruction", spec, declared_effects=[{"Read": "data"}])
    run_golden("S4C19_semantic_converge_instruction", prog, expected_converge_status="Exhausted")

    # R4 Check: verify unexecuted may-effect does NOT appear in runtime effects trace
    obs = invoke_rust_conformance(prog)
    assert obs["effects"] == [], f"R4: unexecuted may-effect appeared in runtime effects: {obs['effects']}"


def main():
    print("=" * 70)
    print("SOMA COMPILER CONFORMANCE v0 (SLICE 4) — Golden Programs (S4C01–S4C19)")

    s4c01_local_expansion()
    s4c02_natural_exhaustion()
    s4c03_successor_satisfaction()
    s4c04_post_fuel_satisfaction_check()
    s4c05_effectful_satisfier()
    s4c06_stage_local_rejection()
    s4c07_first_external_emission()
    s4c08_safe_transport_retry()
    s4c09_unsafe_delivery_unknown()
    s4c10_duplicate_completion()
    s4c11_receipt_equivocation()
    s4c12_crash_after_settlement()
    s4c13_cancel_in_flight()
    s4c14_late_settlement_during_closing()
    s4c15_step_failure_abort()
    s4c16_step_failure_prune()
    s4c17_step_failure_requeue()
    s4c18_satisfaction_retry_limit()
    s4c19_semantic_converge_instruction()

    print("=" * 70)
    print(f"SLICE 4 GOLDEN CONFORMANCE RESULT: {PASS} passed, {FAIL} failed ({PASS + FAIL} total)")
    if FAIL > 0:
        sys.exit(1)
    print("All 19 Slice 4 Golden Conformance Programs PASS under real Rust toolchain.")


if __name__ == "__main__":
    main()
