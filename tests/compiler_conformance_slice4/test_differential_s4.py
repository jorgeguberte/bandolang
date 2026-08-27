"""test_differential_s4.py — Exact 14-Observable Differential Conformance for SOMA-IR Slice 4.

Compares every frozen semantic observable established by Campaign 2:
1. status
2. value
3. error
4. step_count
5. satisfaction_attempts
6. visited
7. frontier
8. budget_spent
9. outstanding_scope_commitment
10. unsettled_request_count
11. attributable_owner_reserved
12. intent_available_consumed
13. effects
14. exhaustion_reason

Exact canonical comparison between Python Semantic Oracle and Rust Toolchain.
All programs are compiled and executed through the complete SOMA-IR compiler pipeline:
Instruction::Converge -> HighLevelVerifier -> LoweringContext -> VmVerifier -> VmInterpreter.

Includes all 33 Campaign 2 scenarios (D01–D06, D13–D29, D31–D34, D07–D12) + negative divergence probes.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "compiler_conformance"))
sys.path.insert(0, str(Path(__file__).parent.parent / "lowering" / "converge"))

from protocol import invoke_rust_conformance
from scenarios import (
    D01, D02, D03, D04, D05, D06, D13, D14, D15, D16, D17,
    D18_WAITING, D19_CRASH_RECOVERY, D20_TARGETED_DELIVERY_UNKNOWN,
    D21_SATISFACTION_LIMIT, D22_DELIVERY_UNKNOWN_NO_SUCCESSORS,
    D23_EFFECTFUL_SATISFIER_ERR_ABORT, D24_EFFECTFUL_SATISFIER_ERR_RETRY,
    D25_TARGETED_EFFECTFUL_SATISFIER_DELIVERY_UNKNOWN,
    D26_SATISFIER_RETRY_LIMIT_BLOCKS_RETRY, D27_IDEMPOTENT_SAFE_RETRY,
    D28_DOUBLE_DELIVERY_UNKNOWN_REMAINS_WAITING,
    D29_CHECKED_NOT_SATISFIED_NEVER_RECHECKED,
    D31_POST_FUEL_CHECK_NONE_EXHAUSTS,
    D32_DYNAMIC_GATE_REJECTION_STEP_FAILURE,
    D33_SPACE_STEP_FAILURE_PRUNE_CONTINUES,
    D34_SPACE_STEP_FAILURE_REQUEUE_RETRIES_WITH_NEW_REQUEST,
    D07, D08, D09, D10, D11, D12,
    ScenarioProgram,
)
from semantic_model import SemanticFrame

PASS, FAIL = 0, 0

ALL_14_OBSERVABLES = [
    "status",
    "value",
    "error",
    "step_count",
    "satisfaction_attempts",
    "visited",
    "frontier",
    "budget_spent",
    "outstanding_scope_commitment",
    "unsettled_request_count",
    "attributable_owner_reserved",
    "intent_available_consumed",
    "effects",
    "exhaustion_reason",
]


def canonical_repr(d):
    return json.dumps(d, sort_keys=True)


def convert_scenario_to_rust_json(prog: ScenarioProgram) -> dict:
    space_effs = []
    node_ops_json = {}
    for node, op in prog.node_ops.items():
        effs = [{"Act": op.op_id}] if op.kind == "external" else []
        if op.kind == "external" and {"Act": op.op_id} not in space_effs:
            space_effs.append({"Act": op.op_id})

        node_ops_json[node] = {
            "op_id": op.op_id,
            "kind": op.kind,
            "cost": op.cost,
            "actual_cost": op.actual_cost,
            "request_id": op.request_id,
            "dedup_capable": op.dedup_capable,
            "idempotent": op.idempotent,
            "required_effects": effs,
        }

    partial_map_json = {}
    for node, p in prog.partial_map.items():
        if isinstance(p, str):
            partial_map_json[node] = {"kind": "String", "payload": p}
        elif isinstance(p, dict):
            partial_map_json[node] = p
        else:
            partial_map_json[node] = {"kind": "String", "payload": str(p)}

    satisfier_map_json = {}
    for node, sat in prog.satisfier_map.items():
        if isinstance(sat, list):
            entries = []
            for item in sat:
                tag, is_sat, val = item[0], item[1], item[2]
                val_json = None
                if val is not None:
                    if isinstance(val, str):
                        val_json = {"kind": "String", "payload": val}
                    elif isinstance(val, dict):
                        val_json = val
                    else:
                        val_json = {"kind": "String", "payload": str(val)}
                entries.append([tag, is_sat, val_json])
            satisfier_map_json[node] = entries
        else:
            tag, is_sat, val = sat[0], sat[1], sat[2]
            val_json = None
            if val is not None:
                if isinstance(val, str):
                    val_json = {"kind": "String", "payload": val}
                elif isinstance(val, dict):
                    val_json = val
                else:
                    val_json = {"kind": "String", "payload": str(val)}
            satisfier_map_json[node] = [tag, is_sat, val_json]

    satisfier_effs = []
    effectful_sat_json = None
    if prog.effectful_satisfier is not None:
        es = prog.effectful_satisfier
        satisfier_effs.append({"Act": es.op_id})
        effectful_sat_json = {
            "op_id": es.op_id,
            "kind": es.kind,
            "cost": es.cost,
            "actual_cost": es.actual_cost,
            "request_id": es.request_id,
            "dedup_capable": es.dedup_capable,
            "idempotent": es.idempotent,
            "required_effects": [{"Act": es.op_id}],
        }

    all_declared_effs = list(space_effs)
    for e in satisfier_effs:
        if e not in all_declared_effs:
            all_declared_effs.append(e)

    ret_ty = {
        "kind": "Result",
        "payload": {
            "ok": {
                "kind": "ConvergenceOutcome",
                "payload": {
                    "satisfied": {"kind": "String"},
                    "exhausted": {"kind": "ExhaustionReport", "payload": {"kind": "String"}},
                },
            },
            "err": {"kind": "String"},
        },
    }

    return {
        "name": prog.name,
        "entry_func": "main",
        "inputs": {},
        "module": {
            "name": "mod_" + prog.name,
            "functions": [
                {
                    "name": "main",
                    "params": [],
                    "return_type": ret_ty,
                    "declared_effects": {"effects": all_declared_effs},
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
                                        "root_node": prog.initial_frontier[0] if prog.initial_frontier else "root",
                                        "initial_frontier": list(prog.initial_frontier),
                                        "successors": dict(prog.successors),
                                        "node_ops": node_ops_json,
                                        "satisfier": {
                                            "kind": "external" if prog.effectful_satisfier is not None else "local",
                                            "effectful_op": effectful_sat_json,
                                            "satisfier_map": satisfier_map_json,
                                        },
                                        "partial_map": partial_map_json,
                                        "space_faults": dict(prog.space_faults),
                                        "fault_spec": {
                                            "delivery_unknown": prog.fault_spec.delivery_unknown,
                                            "delivery_unknown_ops": list(prog.fault_spec.delivery_unknown_ops),
                                            "safe_retry": prog.fault_spec.safe_retry,
                                            "double_delivery_unknown": prog.fault_spec.double_delivery_unknown,
                                            "duplicate_completion": prog.fault_spec.duplicate_completion,
                                            "crash_after_settlement": prog.fault_spec.crash_after_settlement,
                                            "cancel_in_flight": prog.fault_spec.cancel_in_flight,
                                        },
                                        "space_ops": [],
                                        "satisfier_op": "local_satisfier",
                                        "search_policy": {
                                            "policy_id": "pure_policy",
                                            "on_step_failure": prog.on_step_failure,
                                            "on_satisfier_error": prog.on_satisfier_error,
                                            "policy_effects": {"effects": []},
                                        },
                                        "budget_scope": {
                                            "resource": "usd",
                                            "limit": prog.budget_limit,
                                        },
                                        "max_steps": prog.max_steps,
                                        "max_satisfaction_attempts": prog.max_satisfaction_attempts,
                                        "space_effects": {"effects": space_effs},
                                        "satisfier_effects": {"effects": satisfier_effs},
                                        "partial_type": {"kind": "String"},
                                        "satisfied_type": {"kind": "String"},
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


def normalize_rust_observation(obs: dict) -> dict:
    c_obs = obs.get("converge_observation", {})
    val = c_obs.get("value")
    val_norm = val.get("payload") if isinstance(val, dict) else val

    return {
        "status": c_obs.get("status"),
        "value": val_norm,
        "error": c_obs.get("error"),
        "step_count": c_obs.get("step_count"),
        "satisfaction_attempts": c_obs.get("satisfaction_attempts"),
        "visited": c_obs.get("visited", []),
        "frontier": c_obs.get("frontier", []),
        "budget_spent": c_obs.get("budget_spent"),
        "outstanding_scope_commitment": c_obs.get("outstanding_scope_commitment"),
        "unsettled_request_count": c_obs.get("unsettled_request_count"),
        "attributable_owner_reserved": c_obs.get("attributable_owner_reserved"),
        "intent_available_consumed": c_obs.get("intent_available_consumed"),
        "effects": c_obs.get("effects", []),
        "exhaustion_reason": c_obs.get("exhaustion_reason"),
    }


def run_differential_scenario(prog: ScenarioProgram) -> None:
    global PASS, FAIL
    name = prog.name
    print(f"\n--- CONFORMANCE DIFFERENTIAL (Slice 4): {name}")
    try:
        # 1. Oracle run (SemanticFrame)
        sem = SemanticFrame()
        sem.run_program(prog)
        oracle_obs = sem.observe()

        # 2. Rust toolchain run through full compiler pipeline
        rust_prog = convert_scenario_to_rust_json(prog)
        raw_rust_obs = invoke_rust_conformance(rust_prog)
        rust_obs = normalize_rust_observation(raw_rust_obs)

        # 3. Exact 14-field comparison
        divergences = []
        for key in ALL_14_OBSERVABLES:
            o_v = oracle_obs.get(key)
            r_v = rust_obs.get(key)
            if o_v != r_v:
                divergences.append((key, o_v, r_v))

        if divergences:
            print(f"  ✗ FAIL {name}: {len(divergences)} field divergence(s):")
            for k, o_v, r_v in divergences:
                print(f"    - {k}: expected {o_v!r}, got {r_v!r}")
            FAIL += 1
        else:
            print(f"  ✓ PASS {name} (exact agreement across all 14 canonical observables)")
            PASS += 1
    except Exception as e:
        print(f"  ✗ FAIL {name}: crashed with exception {type(e).__name__}: {e}")
        FAIL += 1


def run_divergence_probe(name: str, base_obs: dict, mutated_obs: dict, expected_diff_key: str) -> None:
    global PASS, FAIL
    print(f"\n--- PROBE TEST (Slice 4): {name}")
    divergences = []
    for key in ALL_14_OBSERVABLES:
        b_v = base_obs.get(key)
        m_v = mutated_obs.get(key)
        if b_v != m_v:
            divergences.append((key, b_v, m_v))

    diff_keys = [k for k, _, _ in divergences]
    if expected_diff_key in diff_keys:
        print(f"  ✓ PASS {name} (probe correctly triggered comparator rejection on '{expected_diff_key}')")
        PASS += 1
    else:
        print(f"  ✗ FAIL {name}: comparator failed to flag expected divergence on '{expected_diff_key}'")
        FAIL += 1


def main():
    print("=" * 70)
    print("SOMA COMPILER CONFORMANCE v0 (SLICE 4) — Python Oracle vs Rust Toolchain Exact 14-Observable Differential")

    # Basic battery (27 scenarios)
    basic_battery = [
        D01, D02, D03, D04, D05, D06, D13, D14, D15, D16, D17,
        D18_WAITING, D19_CRASH_RECOVERY, D20_TARGETED_DELIVERY_UNKNOWN,
        D21_SATISFACTION_LIMIT, D22_DELIVERY_UNKNOWN_NO_SUCCESSORS,
        D23_EFFECTFUL_SATISFIER_ERR_ABORT, D24_EFFECTFUL_SATISFIER_ERR_RETRY,
        D25_TARGETED_EFFECTFUL_SATISFIER_DELIVERY_UNKNOWN,
        D26_SATISFIER_RETRY_LIMIT_BLOCKS_RETRY, D27_IDEMPOTENT_SAFE_RETRY,
        D28_DOUBLE_DELIVERY_UNKNOWN_REMAINS_WAITING,
        D29_CHECKED_NOT_SATISFIED_NEVER_RECHECKED,
        D31_POST_FUEL_CHECK_NONE_EXHAUSTS,
        D32_DYNAMIC_GATE_REJECTION_STEP_FAILURE,
        D33_SPACE_STEP_FAILURE_PRUNE_CONTINUES,
        D34_SPACE_STEP_FAILURE_REQUEUE_RETRIES_WITH_NEW_REQUEST,
    ]

    for p in basic_battery:
        run_differential_scenario(p)

    # Fault battery (6 scenarios)
    fault_battery = [D07, D08, D09, D10, D11, D12]
    for p in fault_battery:
        run_differential_scenario(p)

    # Negative probes
    sample_obs = {
        "status": "Satisfied",
        "value": "T-sample",
        "error": None,
        "step_count": 2,
        "satisfaction_attempts": 1,
        "visited": ["A", "B"],
        "frontier": [],
        "budget_spent": 20,
        "outstanding_scope_commitment": 0,
        "unsettled_request_count": 0,
        "attributable_owner_reserved": 0,
        "intent_available_consumed": 20,
        "effects": ["external(opA)"],
        "exhaustion_reason": None,
    }

    # Probe 1: Status
    p1 = copy.deepcopy(sample_obs)
    p1["status"] = "Exhausted"
    run_divergence_probe("PROBE_status_divergence", sample_obs, p1, "status")

    # Probe 2: Value
    p2 = copy.deepcopy(sample_obs)
    p2["value"] = "T-forged"
    run_divergence_probe("PROBE_value_divergence", sample_obs, p2, "value")

    # Probe 3: Step count
    p3 = copy.deepcopy(sample_obs)
    p3["step_count"] = 3
    run_divergence_probe("PROBE_step_count_divergence", sample_obs, p3, "step_count")

    # Probe 4: Visited
    p4 = copy.deepcopy(sample_obs)
    p4["visited"] = ["A", "B", "C"]
    run_divergence_probe("PROBE_visited_divergence", sample_obs, p4, "visited")

    # Probe 5: Budget spent
    p5 = copy.deepcopy(sample_obs)
    p5["budget_spent"] = 30
    run_divergence_probe("PROBE_budget_spent_divergence", sample_obs, p5, "budget_spent")

    # Probe 6: Effects
    p6 = copy.deepcopy(sample_obs)
    p6["effects"] = ["external(opA)", "external(opForged)"]
    run_divergence_probe("PROBE_effects_divergence", sample_obs, p6, "effects")

    # Probe 7: Exhaustion reason
    p7 = copy.deepcopy(sample_obs)
    p7["exhaustion_reason"] = "BudgetDepleted"
    run_divergence_probe("PROBE_exhaustion_reason_divergence", sample_obs, p7, "exhaustion_reason")

    print("=" * 70)
    print(f"SLICE 4 DIFFERENTIAL RESULT: {PASS} passed, {FAIL} failed ({PASS + FAIL} total)")
    if FAIL > 0:
        sys.exit(1)
    print("Exact 14-Observable differential agreement strictly confirmed between Python Oracle and Rust Toolchain across all 33 scenarios + 7 probes.")


if __name__ == "__main__":
    main()
