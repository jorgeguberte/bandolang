"""test_mutations.py — Real Compiler Mutation Testing M01–M10 for Compiler Conformance v0 (Slice 1, R4 & S2).

Takes valid golden high-level programs and enables real compiler/lowering/analysis mutations
to prove that every mutation causes a test failure.
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from protocol import invoke_rust_conformance

PASS, FAIL = 0, 0


def kill_mutation(name: str, check_fn) -> None:
    global PASS, FAIL
    print(f"\n--- MUTATION KILL TEST: {name}")
    try:
        caught = check_fn()
        if not caught:
            print(f"  \u2717 FAIL {name}: mutation survived without being caught!")
            FAIL += 1
            return
        print(f"  \u2713 PASS {name} (real compiler mutation successfully caught and killed)")
        PASS += 1
    except Exception as e:
        print(f"  \u2717 FAIL {name}: unexpected exception {type(e).__name__}: {e}")
        FAIL += 1


def base_c02_program():
    return {
        "name": "C02_valid",
        "entry_func": "main",
        "inputs": {},
        "module": {
            "name": "mod_c02",
            "functions": [{
                "name": "main",
                "params": [],
                "return_type": {"kind": "String"},
                "declared_effects": {"effects": [{"Read": "docs"}]},
                "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0,
                        "name": "entry",
                        "params": [],
                        "instructions": [{
                            "Read": {
                                "dest": 1,
                                "domain": "docs",
                                "ok_type": {"kind": "String"},
                                "err_type": {"kind": "String"},
                                "latent": {
                                    "on_ok": [{"predicate": "ObservedAt", "args": [{"Symbol": "$value"}, {"Literal": "docs"}]}],
                                    "on_err": []
                                }
                            }
                        }],
                        "terminator": {
                            "MatchResult": {
                                "result_val": 1,
                                "ok_arg": 2,
                                "ok_body": {"instructions": [], "terminator": {"Return": 2}},
                                "err_arg": 3,
                                "err_body": {"instructions": [], "terminator": {"Return": 3}}
                            }
                        }
                    }
                }
            }]
        }
    }


def base_diamond_program():
    return {
        "name": "C05_C06_valid",
        "entry_func": "main",
        "inputs": {},
        "module": {
            "name": "mod_diamond",
            "functions": [{
                "name": "main",
                "params": [],
                "return_type": {"kind": "String"},
                "declared_effects": {"effects": [{"Read": "doc"}]},
                "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0,
                        "name": "entry",
                        "params": [],
                        "instructions": [{
                            "Read": {
                                "dest": 1,
                                "domain": "doc",
                                "ok_type": {"kind": "String"},
                                "err_type": {"kind": "String"},
                                "latent": {
                                    "on_ok": [
                                        {"predicate": "ExclusiveOk", "args": [{"Symbol": "$value"}]},
                                        {"predicate": "CommonFact", "args": [{"Literal": "doc"}]}
                                    ],
                                    "on_err": [
                                        {"predicate": "CommonFact", "args": [{"Literal": "doc"}]}
                                    ]
                                }
                            }
                        }],
                        "terminator": {
                            "MatchResult": {
                                "result_val": 1,
                                "ok_arg": 2,
                                "ok_body": {"instructions": [], "terminator": {"Br": {"target": 1, "args": [2]}}},
                                "err_arg": 3,
                                "err_body": {"instructions": [], "terminator": {"Br": {"target": 1, "args": [3]}}}
                            }
                        }
                    },
                    "1": {
                        "id": 1,
                        "name": "merge",
                        "params": [[4, {"kind": "String"}]],
                        "instructions": [],
                        "terminator": {"Return": 4}
                    }
                }
            }]
        }
    }


def m01_drop_err_edge():
    # R4: Lowering drops Err edge in generated SwitchResult
    prog = base_c02_program()
    prog["mutations"] = {"m01_drop_err_edge": True}
    obs = invoke_rust_conformance(prog)
    return obs["status"] == "vm_verifier_error" and any(d["code"] == "CfgBadTarget" for d in obs.get("diagnostics", []))


def m02_swap_ok_err_targets():
    # R4: Lowering swaps ok_target and err_target
    prog = base_c02_program()
    prog["mutations"] = {"m02_swap_ok_err_targets": True}
    obs = invoke_rust_conformance(prog)
    return obs["status"] != "ok" or obs.get("return_val") != {"kind": "String", "payload": "data_of(docs)"}


def m03_corrupt_block_arg_type():
    # R4: Lowering corrupts generated block argument type to Bool
    prog = base_diamond_program()
    prog["mutations"] = {"m03_corrupt_block_arg_type": True}
    obs = invoke_rust_conformance(prog)
    return obs["status"] == "vm_verifier_error" and any(d["code"] == "BlockArgType" for d in obs.get("diagnostics", []))


def m04_lose_latent_postcondition():
    # R4: Lowering drops latent postcondition metadata
    prog = base_c02_program()
    prog["mutations"] = {"m04_drop_latent_metadata": True}
    obs = invoke_rust_conformance(prog)
    return not any(f.get("predicate") == "ObservedAt" for f in obs.get("active_facts", []))


def m05_eager_on_ok_materialization():
    # R4: Analyzer eagerly discharges on_ok in unrefined entry block
    prog = {
        "name": "M05_eager",
        "entry_func": "main",
        "inputs": {},
        "mutations": {"m05_eager_on_ok_materialization": True},
        "module": {
            "name": "m",
            "functions": [{
                "name": "main", "params": [], "return_type": {"kind": "String"},
                "declared_effects": {"effects": [{"Read": "doc"}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Read": {"dest": 1, "domain": "doc", "ok_type": {"kind": "String"}, "err_type": {"kind": "String"},
                                      "latent": {"on_ok": [{"predicate": "ObservedAt", "args": [{"Symbol": "$value"}]}], "on_err": []}}},
                            {"Pure": {"dest": 2, "val": {"kind": "String", "payload": "done"}, "ty": {"kind": "String"}}}
                        ],
                        "terminator": {"Return": 2}
                    }
                }
            }]
        }
    }
    obs = invoke_rust_conformance(prog)
    return any(f.get("predicate") == "ObservedAt" for f in obs.get("active_facts", []))


def m06_merge_union_instead_of_intersection():
    # R4: Analyzer uses union instead of intersection at merge
    prog = base_diamond_program()
    prog["mutations"] = {"m06_merge_union_facts": True}
    obs = invoke_rust_conformance(prog)
    return any(f.get("predicate") == "ExclusiveOk" for f in obs.get("active_facts", []))


def m07_omit_read_effect():
    # R4: Lowering drops Read[D] from VM effect row
    prog = base_c02_program()
    prog["mutations"] = {"m07_drop_read_effect": True}
    obs = invoke_rust_conformance(prog)
    return obs["status"] == "vm_verifier_error" and any(d["code"] == "EffectUndeclared" for d in obs.get("diagnostics", []))


def m08_omit_infer_effect():
    # R4: Lowering drops Infer from VM effect row
    prog = {
        "name": "C09_infer",
        "entry_func": "main",
        "inputs": {},
        "mutations": {"m08_drop_infer_effect": True},
        "module": {
            "name": "m",
            "functions": [{
                "name": "main", "params": [], "return_type": {"kind": "String"},
                "declared_effects": {"effects": ["Infer"]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [{"Infer": {"dest": 1, "prompt": "query", "ok_type": {"kind": "String"}, "err_type": {"kind": "String"}, "latent": {"on_ok": [], "on_err": []}}}],
                        "terminator": {"MatchResult": {"result_val": 1, "ok_arg": 2, "ok_body": {"instructions": [], "terminator": {"Return": 2}}, "err_arg": 3, "err_body": {"instructions": [], "terminator": {"Return": 3}}}}
                    }
                }
            }]
        }
    }
    obs = invoke_rust_conformance(prog)
    return obs["status"] == "vm_verifier_error" and any(d["code"] == "EffectUndeclared" for d in obs.get("diagnostics", []))


def m09_stale_ssa_reference():
    # R4: Lowering assigns stale unbound ValueId in generated Assign instruction
    prog = {
        "name": "C04_ssa_assign",
        "entry_func": "main",
        "inputs": {},
        "mutations": {"m09_stale_source_value_id": True},
        "module": {
            "name": "m",
            "functions": [{
                "name": "main", "params": [], "return_type": {"kind": "String"},
                "declared_effects": {"effects": [{"Read": "fileA"}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Read": {"dest": 1, "domain": "fileA", "ok_type": {"kind": "String"}, "err_type": {"kind": "String"}, "latent": {"on_ok": [], "on_err": []}}}
                        ],
                        "terminator": {
                            "MatchResult": {
                                "result_val": 1,
                                "ok_arg": 2,
                                "ok_body": {
                                    "instructions": [{"Assign": {"dest": 4, "source": 2, "ty": {"kind": "String"}}}],
                                    "terminator": {"Return": 4}
                                },
                                "err_arg": 3,
                                "err_body": {"instructions": [], "terminator": {"Return": 3}}
                            }
                        }
                    }
                }
            }]
        }
    }
    obs = invoke_rust_conformance(prog)
    return obs["status"] == "vm_verifier_error" and any(d["code"] == "SsaUseBeforeDef" for d in obs.get("diagnostics", []))


def m10_single_pass_loop_leakage():
    # S2: Loop requires backedge fixed point convergence to eliminate entry-only fact
    prog = {
        "name": "M10_loop_fixed_point_kill",
        "entry_func": "main",
        "inputs": {"v1": {"kind": "Bool", "payload": False}},
        "module": {
            "name": "mod_m10",
            "functions": [{
                "name": "main",
                "params": [[1, {"kind": "Bool"}]],
                "return_type": {"kind": "I64"},
                "declared_effects": {"effects": [{"Read": "doc"}]},
                "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "name": "entry", "params": [],
                        "instructions": [
                            {"Read": {
                                "dest": 2, "domain": "doc", "ok_type": {"kind": "I64"}, "err_type": {"kind": "I64"},
                                "latent": {
                                    "on_ok": [{"predicate": "EntryOnlyFact", "args": [{"Symbol": "$value"}]}],
                                    "on_err": []
                                }
                            }}
                        ],
                        "terminator": {
                            "MatchResult": {
                                "result_val": 2,
                                "ok_arg": 3,
                                "ok_body": {"instructions": [], "terminator": {"Br": {"target": 1, "args": [3]}}},
                                "err_arg": 4,
                                "err_body": {"instructions": [], "terminator": {"Br": {"target": 1, "args": [4]}}}
                            }
                        }
                    },
                    "1": {
                        "id": 1, "name": "loop_header", "params": [[5, {"kind": "I64"}]],
                        "instructions": [],
                        "terminator": {
                            "CondBr": {
                                "cond": 1,
                                "true_target": 2,
                                "true_args": [5],
                                "false_target": 3,
                                "false_args": [5]
                            }
                        }
                    },
                    "2": {
                        "id": 2, "name": "loop_body", "params": [[6, {"kind": "I64"}]],
                        "instructions": [],
                        "terminator": {"Br": {"target": 1, "args": [6]}}
                    },
                    "3": {
                        "id": 3, "name": "exit", "params": [[7, {"kind": "I64"}]],
                        "instructions": [],
                        "terminator": {"Return": 7}
                    }
                }
            }]
        }
    }

    # 1. Baseline analysis (without mutation): full fixed-point iteration produces canonical facts
    baseline_prog = copy.deepcopy(prog)
    baseline_obs = invoke_rust_conformance(baseline_prog)

    # 2. Mutant analysis (with single-pass): skips fixed point re-evaluations and produces a divergent fact set
    mutant_prog = copy.deepcopy(prog)
    mutant_prog["mutations"] = {"m10_single_pass_loop_analysis": True}
    mutant_obs = invoke_rust_conformance(mutant_prog)

    # Mutation is killed because mutant produces an incorrect, divergent fact set from baseline fixed point (S2)
    return baseline_obs.get("active_facts") != mutant_obs.get("active_facts")


if __name__ == "__main__":
    print("=" * 70)
    print("SOMA COMPILER CONFORMANCE v0 (SLICE 1) — Real Mutation Kills M01–M10 (R4 & S2)")
    kill_mutation("M01_drop_err_edge", m01_drop_err_edge)
    kill_mutation("M02_swap_ok_err_payloads", m02_swap_ok_err_targets)
    kill_mutation("M03_corrupt_block_arg_type", m03_corrupt_block_arg_type)
    kill_mutation("M04_lose_latent_postcondition", m04_lose_latent_postcondition)
    kill_mutation("M05_eager_on_ok", m05_eager_on_ok_materialization)
    kill_mutation("M06_merge_union_instead_of_intersection", m06_merge_union_instead_of_intersection)
    kill_mutation("M07_omit_read_effect", m07_omit_read_effect)
    kill_mutation("M08_omit_infer_effect", m08_omit_infer_effect)
    kill_mutation("M09_stale_ssa_reference", m09_stale_ssa_reference)
    kill_mutation("M10_single_pass_loop_leakage", m10_single_pass_loop_leakage)

    print("=" * 70)
    print(f"MUTATION KILLS RESULT: {PASS} passed, {FAIL} failed ({PASS + FAIL} total)")
    if FAIL:
        sys.exit(1)
    print("All Real Compiler Mutations correctly identified and killed.")
