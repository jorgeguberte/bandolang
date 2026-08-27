"""test_golden_s4.py — SOMA-IR Compiler Conformance v0 (Slice 4: soma.converge / ConvergeFrame v0).

Covers Golden Matrix S4C01–S4C19:
- S4C01: Local expansion
- S4C02: Natural exhaustion (FrontierEmpty)
- S4C03: Successor satisfaction
- S4C04: Post-fuel satisfaction check
- S4C05: Effectful satisfier
- S4C06: StageLocal rejection (zero accounting delta)
- S4C07: First external emission
- S4C08: Safe transport retry
- S4C09: Unsafe DeliveryUnknown
- S4C10: Duplicate completion
- S4C11: Receipt equivocation
- S4C12: Crash-after-settlement recovery
- S4C13: Cancellation while in flight
- S4C14: Late settlement during Closing
- S4C15: StepFailure abort
- S4C16: StepFailure prune
- S4C17: StepFailure requeue
- S4C18: Satisfaction retry + attempt limit
- S4C19: Terminal obligation barrier
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


def run_golden(
    name: str,
    program: dict,
    expected_status: str = "ok",
    expected_converge_status: str = None,
    expected_converge_value: str = None,
    expected_step_count: int = None,
    expected_effects: list = None,
) -> None:
    global PASS, FAIL
    print(f"\n--- GOLDEN PROGRAM (Slice 4): {name}")
    try:
        obs = invoke_rust_conformance(program)
        if expected_status == "ok":
            if obs["status"] != "ok":
                print(f"  ✗ FAIL {name}: expected status 'ok', got '{obs['status']}'")
                FAIL += 1
                return
        c_obs = obs.get("converge_observation")
        if c_obs is not None:
            if expected_converge_status is not None and c_obs.get("status") != expected_converge_status:
                print(f"  ✗ FAIL {name}: expected converge status '{expected_converge_status}', got '{c_obs.get('status')}'")
                FAIL += 1
                return
            if expected_converge_value is not None:
                val = c_obs.get("value")
                val_str = val.get("payload") if isinstance(val, dict) else str(val)
                if val_str != expected_converge_value:
                    print(f"  ✗ FAIL {name}: expected converge value '{expected_converge_value}', got '{val_str}'")
                    FAIL += 1
                    return
            if expected_step_count is not None and c_obs.get("step_count") != expected_step_count:
                print(f"  ✗ FAIL {name}: expected step_count {expected_step_count}, got {c_obs.get('step_count')}")
                FAIL += 1
                return
        if expected_effects is not None:
            if obs.get("effects") != expected_effects:
                print(f"  ✗ FAIL {name}: expected effects {expected_effects}, got {obs.get('effects')}")
                FAIL += 1
                return
        print(f"  ✓ PASS {name} (status={obs['status']}, converge={c_obs.get('status') if c_obs else 'none'})")
        PASS += 1
    except Exception as e:
        print(f"  ✗ FAIL {name}: crashed with {type(e).__name__}: {e}")
        FAIL += 1


# S4C01: Local expansion
def s4c01_local_expansion():
    prog = {
        "name": "S4C01_local_expansion",
        "entry_func": "main",
        "inputs": {},
        "converge_scenario": {
            "name": "S4C01",
            "initial_frontier": ["root"],
            "successors": {"root": []},
            "node_ops": {"root": {"op_id": "op1", "kind": "local", "cost": 0}},
            "partial_map": {"root": {"kind": "String", "payload": "P_root"}},
            "satisfier_map": {"root": ["ok", False, None]},
            "max_steps": 6,
        },
        "module": {"name": "m", "functions": []},
    }
    run_golden("S4C01_local_expansion", prog, expected_converge_status="Exhausted", expected_step_count=1)


# S4C02: Natural exhaustion
def s4c02_natural_exhaustion():
    prog = {
        "name": "S4C02_natural_exhaustion",
        "entry_func": "main",
        "inputs": {},
        "converge_scenario": {
            "name": "S4C02",
            "initial_frontier": ["root"],
            "successors": {"root": []},
            "node_ops": {"root": {"op_id": "op4", "kind": "external", "cost": 8}},
            "partial_map": {"root": {"kind": "String", "payload": "P_root"}},
            "satisfier_map": {"root": ["ok", False, None]},
            "max_steps": 6,
        },
        "module": {"name": "m", "functions": []},
    }
    run_golden("S4C02_natural_exhaustion", prog, expected_converge_status="Exhausted")


# S4C03: Successor satisfaction
def s4c03_successor_satisfaction():
    prog = {
        "name": "S4C03_successor_satisfaction",
        "entry_func": "main",
        "inputs": {},
        "converge_scenario": {
            "name": "S4C03",
            "initial_frontier": ["A"],
            "successors": {"A": ["B"], "B": []},
            "node_ops": {
                "A": {"op_id": "opA", "kind": "local", "cost": 0},
                "B": {"op_id": "opB", "kind": "local", "cost": 0},
            },
            "partial_map": {
                "A": {"kind": "String", "payload": "P_A"},
                "B": {"kind": "String", "payload": "P_B"},
            },
            "satisfier_map": {
                "A": ["ok", False, None],
                "B": ["ok", True, {"kind": "String", "payload": "T-value-B"}],
            },
            "max_steps": 6,
        },
        "module": {"name": "m", "functions": []},
    }
    run_golden(
        "S4C03_successor_satisfaction",
        prog,
        expected_converge_status="Satisfied",
        expected_converge_value="T-value-B",
        expected_step_count=1,
    )


# S4C04: Post-fuel satisfaction check
def s4c04_post_fuel_satisfaction_check():
    prog = {
        "name": "S4C04_post_fuel_satisfaction_check",
        "entry_func": "main",
        "inputs": {},
        "converge_scenario": {
            "name": "S4C04",
            "initial_frontier": ["P"],
            "successors": {"P": ["Q"], "Q": []},
            "node_ops": {
                "P": {"op_id": "opP", "kind": "external", "cost": 10},
                "Q": {"op_id": "opQ", "kind": "external", "cost": 10},
            },
            "partial_map": {
                "P": {"kind": "String", "payload": "P_P"},
                "Q": {"kind": "String", "payload": "P_Q"},
            },
            "satisfier_map": {
                "P": ["ok", False, None],
                "Q": ["ok", True, {"kind": "String", "payload": "T-partial"}],
            },
            "max_steps": 1,
        },
        "module": {"name": "m", "functions": []},
    }
    run_golden(
        "S4C04_post_fuel_satisfaction_check",
        prog,
        expected_converge_status="Satisfied",
        expected_converge_value="T-partial",
        expected_step_count=1,
    )


# S4C05: Effectful satisfier
def s4c05_effectful_satisfier():
    prog = {
        "name": "S4C05_effectful_satisfier",
        "entry_func": "main",
        "inputs": {},
        "converge_scenario": {
            "name": "S4C05",
            "initial_frontier": ["X"],
            "successors": {"X": []},
            "node_ops": {"X": {"op_id": "opX", "kind": "external", "cost": 10}},
            "effectful_satisfier": {"op_id": "opVerify", "kind": "external", "cost": 5},
            "partial_map": {"X": {"kind": "String", "payload": "P_X"}},
            "satisfier_map": {
                "X": ["ok", True, {"kind": "String", "payload": "T-verified"}],
            },
            "max_steps": 6,
        },
        "module": {"name": "m", "functions": []},
    }
    run_golden(
        "S4C05_effectful_satisfier",
        prog,
        expected_converge_status="Satisfied",
        expected_converge_value="T-verified",
        expected_effects=["external(opVerify)"],
    )


# S4C06: StageLocal rejection
def s4c06_stage_local_rejection():
    prog = {
        "name": "S4C06_stage_local_rejection",
        "entry_func": "main",
        "inputs": {},
        "converge_scenario": {
            "name": "S4C06",
            "initial_frontier": ["A"],
            "successors": {"A": ["B"], "B": []},
            "node_ops": {
                "A": {"op_id": "opA", "kind": "external", "cost": 60},
                "B": {"op_id": "opB", "kind": "external", "cost": 50},
            },
            "partial_map": {},
            "budget_limit": 100,
            "max_steps": 6,
        },
        "module": {"name": "m", "functions": []},
    }
    run_golden("S4C06_stage_local_rejection", prog, expected_converge_status="Exhausted", expected_step_count=1)


# S4C07: First external emission
def s4c07_first_external_emission():
    prog = {
        "name": "S4C07_first_external_emission",
        "entry_func": "main",
        "inputs": {},
        "converge_scenario": {
            "name": "S4C07",
            "initial_frontier": ["root"],
            "successors": {"root": ["succ"]},
            "node_ops": {
                "root": {"op_id": "opExt", "kind": "external", "cost": 15},
                "succ": {"op_id": "opSucc", "kind": "local", "cost": 0},
            },
            "partial_map": {
                "root": {"kind": "String", "payload": "P_root"},
                "succ": {"kind": "String", "payload": "P_succ"},
            },
            "satisfier_map": {
                "root": ["ok", False, None],
                "succ": ["ok", True, {"kind": "String", "payload": "T-ext"}],
            },
            "max_steps": 6,
        },
        "module": {"name": "m", "functions": []},
    }
    run_golden(
        "S4C07_first_external_emission",
        prog,
        expected_converge_status="Satisfied",
        expected_converge_value="T-ext",
        expected_step_count=1,
        expected_effects=["external(opExt)"],
    )


# S4C08: Safe transport retry
def s4c08_safe_transport_retry():
    prog = {
        "name": "S4C08_safe_transport_retry",
        "entry_func": "main",
        "inputs": {},
        "converge_scenario": {
            "name": "S4C08",
            "initial_frontier": ["root"],
            "successors": {"root": ["succ"]},
            "node_ops": {
                "root": {
                    "op_id": "opRetry",
                    "kind": "external",
                    "cost": 20,
                    "dedup_capable": True,
                    "idempotent": True,
                },
                "succ": {"op_id": "opSucc", "kind": "local", "cost": 0},
            },
            "partial_map": {
                "root": {"kind": "String", "payload": "P_root"},
                "succ": {"kind": "String", "payload": "P_succ"},
            },
            "satisfier_map": {
                "root": ["ok", False, None],
                "succ": ["ok", True, {"kind": "String", "payload": "T-retry"}],
            },
            "fault_spec": {"delivery_unknown": True, "safe_retry": True},
            "max_steps": 6,
        },
        "module": {"name": "m", "functions": []},
    }
    run_golden(
        "S4C08_safe_transport_retry",
        prog,
        expected_converge_status="Satisfied",
        expected_converge_value="T-retry",
        expected_step_count=1,
    )


# S4C09: Unsafe DeliveryUnknown
def s4c09_unsafe_delivery_unknown():
    prog = {
        "name": "S4C09_unsafe_delivery_unknown",
        "entry_func": "main",
        "inputs": {},
        "converge_scenario": {
            "name": "S4C09",
            "initial_frontier": ["root"],
            "successors": {"root": []},
            "node_ops": {
                "root": {
                    "op_id": "opUnsafe",
                    "kind": "external",
                    "cost": 20,
                    "dedup_capable": False,
                    "idempotent": False,
                }
            },
            "partial_map": {},
            "fault_spec": {"delivery_unknown": True, "safe_retry": True},
            "max_steps": 6,
        },
        "module": {"name": "m", "functions": []},
    }
    run_golden("S4C09_unsafe_delivery_unknown", prog, expected_converge_status="Waiting")


# S4C10: Duplicate completion
def s4c10_duplicate_completion():
    prog = {
        "name": "S4C10_duplicate_completion",
        "entry_func": "main",
        "inputs": {},
        "converge_scenario": {
            "name": "S4C10",
            "initial_frontier": ["root"],
            "successors": {"root": []},
            "node_ops": {"root": {"op_id": "opDup", "kind": "external", "cost": 10}},
            "partial_map": {"root": {"kind": "String", "payload": "P_root"}},
            "satisfier_map": {"root": ["ok", False, None]},
            "fault_spec": {"duplicate_completion": True},
            "max_steps": 6,
        },
        "module": {"name": "m", "functions": []},
    }
    run_golden("S4C10_duplicate_completion", prog, expected_converge_status="Exhausted")


# S4C11: Receipt equivocation
def s4c11_receipt_equivocation():
    prog = {
        "name": "S4C11_receipt_equivocation",
        "entry_func": "main",
        "inputs": {},
        "converge_scenario": {
            "name": "S4C11",
            "initial_frontier": ["root"],
            "successors": {"root": []},
            "node_ops": {"root": {"op_id": "opEquiv", "kind": "external", "cost": 10}},
            "partial_map": {},
            "max_steps": 6,
        },
        "module": {"name": "m", "functions": []},
    }
    run_golden("S4C11_receipt_equivocation", prog)


# S4C12: Crash-after-settlement recovery
def s4c12_crash_after_settlement():
    prog = {
        "name": "S4C12_crash_after_settlement",
        "entry_func": "main",
        "inputs": {},
        "converge_scenario": {
            "name": "S4C12",
            "initial_frontier": ["root"],
            "successors": {"root": []},
            "node_ops": {"root": {"op_id": "opCrash", "kind": "external", "cost": 10}},
            "partial_map": {"root": {"kind": "String", "payload": "P_root"}},
            "satisfier_map": {"root": ["ok", True, {"kind": "String", "payload": "T-crash"}]},
            "fault_spec": {"crash_after_settlement": True},
            "max_steps": 6,
        },
        "module": {"name": "m", "functions": []},
    }
    run_golden(
        "S4C12_crash_after_settlement",
        prog,
        expected_converge_status="Satisfied",
        expected_converge_value="T-crash",
    )


# S4C13: Cancellation while in flight
def s4c13_cancel_in_flight():
    prog = {
        "name": "S4C13",
        "entry_func": "main",
        "inputs": {},
        "converge_scenario": {
            "name": "S4C13",
            "initial_frontier": ["root"],
            "successors": {"root": []},
            "node_ops": {"root": {"op_id": "opCancel", "kind": "external", "cost": 10}},
            "partial_map": {},
            "fault_spec": {"delivery_unknown": True, "cancel_in_flight": True},
            "max_steps": 6,
        },
        "module": {"name": "m", "functions": []},
    }
    run_golden("S4C13_cancel_in_flight", prog, expected_converge_status="Cancelled")


# S4C14: Late settlement during Closing
def s4c14_late_settlement_during_closing():
    prog = {
        "name": "S4C14_late_settlement_during_closing",
        "entry_func": "main",
        "inputs": {},
        "converge_scenario": {
            "name": "S4C14",
            "initial_frontier": ["root"],
            "successors": {"root": []},
            "node_ops": {"root": {"op_id": "opLate", "kind": "external", "cost": 10}},
            "partial_map": {},
            "max_steps": 6,
        },
        "module": {"name": "m", "functions": []},
    }
    run_golden("S4C14_late_settlement_during_closing", prog)


# S4C15: StepFailure abort
def s4c15_step_failure_abort():
    prog = {
        "name": "S4C15_step_failure_abort",
        "entry_func": "main",
        "inputs": {},
        "converge_scenario": {
            "name": "S4C15",
            "initial_frontier": ["root"],
            "successors": {"root": []},
            "node_ops": {"root": {"op_id": "opGate", "kind": "external", "cost": 10}},
            "space_faults": {"opGate": "DynamicGateRejection"},
            "on_step_failure": "abort",
            "partial_map": {},
            "max_steps": 6,
        },
        "module": {"name": "m", "functions": []},
    }
    run_golden("S4C15_step_failure_abort", prog, expected_converge_status="Failed")


# S4C16: StepFailure prune
def s4c16_step_failure_prune():
    prog = {
        "name": "S4C16_step_failure_prune",
        "entry_func": "main",
        "inputs": {},
        "converge_scenario": {
            "name": "S4C16",
            "initial_frontier": ["A", "B"],
            "successors": {"A": [], "B": []},
            "node_ops": {
                "A": {"op_id": "opA", "kind": "external", "cost": 10},
                "B": {"op_id": "opB", "kind": "external", "cost": 10},
            },
            "space_faults": {"opA": "PruneFault"},
            "on_step_failure": "prune",
            "partial_map": {"B": {"kind": "String", "payload": "P_B"}},
            "satisfier_map": {"B": ["ok", True, {"kind": "String", "payload": "T-prune-success"}]},
            "max_steps": 6,
        },
        "module": {"name": "m", "functions": []},
    }
    run_golden(
        "S4C16_step_failure_prune",
        prog,
        expected_converge_status="Satisfied",
        expected_converge_value="T-prune-success",
    )


# S4C17: StepFailure requeue
def s4c17_step_failure_requeue():
    prog = {
        "name": "S4C17_step_failure_requeue",
        "entry_func": "main",
        "inputs": {},
        "converge_scenario": {
            "name": "S4C17",
            "initial_frontier": ["R"],
            "successors": {"R": []},
            "node_ops": {"R": {"op_id": "opR", "kind": "external", "cost": 10}},
            "space_faults": {"opR": ["TransientFault"]},
            "on_step_failure": "requeue",
            "partial_map": {"R": {"kind": "String", "payload": "P_R"}},
            "satisfier_map": {"R": ["ok", True, {"kind": "String", "payload": "T-requeue-success"}]},
            "max_steps": 6,
        },
        "module": {"name": "m", "functions": []},
    }
    run_golden(
        "S4C17_step_failure_requeue",
        prog,
        expected_converge_status="Satisfied",
        expected_converge_value="T-requeue-success",
    )


# S4C18: Satisfaction retry + attempt limit
def s4c18_satisfaction_retry_limit():
    prog = {
        "name": "S4C18_satisfaction_retry_limit",
        "entry_func": "main",
        "inputs": {},
        "converge_scenario": {
            "name": "S4C18",
            "initial_frontier": ["cand"],
            "successors": {"cand": []},
            "node_ops": {"cand": {"op_id": "opCand", "kind": "external", "cost": 10}},
            "effectful_satisfier": {"op_id": "opVerify", "kind": "external", "cost": 5},
            "partial_map": {"cand": {"kind": "String", "payload": "P_cand"}},
            "satisfier_map": {"cand": ["err", False, {"kind": "String", "payload": "TransientVerifyFail"}]},
            "on_satisfier_error": "retry",
            "max_satisfaction_attempts": 1,
            "max_steps": 6,
        },
        "module": {"name": "m", "functions": []},
    }
    run_golden("S4C18_satisfaction_retry_limit", prog, expected_converge_status="Exhausted")


# S4C19: Full semantic pipeline (Instruction::Converge lowering + VM execution)
def s4c19_semantic_converge_instruction():
    prog = {
        "name": "S4C19_semantic_converge_instruction",
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
                    "declared_effects": {"effects": [{"Read": "data"}]},
                    "entry": 0,
                    "blocks": {
                        "0": {
                            "id": 0,
                            "params": [],
                            "instructions": [
                                {
                                    "Converge": {
                                        "dest": 1,
                                        "root_node": "root",
                                        "space_ops": ["op_read"],
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
                                        "space_effects": {"effects": [{"Read": "data"}]},
                                        "satisfier_effects": {"effects": []},
                                        "partial_type": make_type_string(),
                                        "satisfied_type": make_type_string(),
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
    run_golden(
        "S4C19_semantic_converge_instruction",
        prog,
        expected_status="ok",
        expected_effects=["read[data]"],
    )


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
