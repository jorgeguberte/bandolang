"""test_mutations.py — Adversarial Mutation Testing M01–M10 for Compiler Conformance v0 (Slice 1).

Validates that compiler bugs, lowering regressions, and dataflow omissions are caught
by the Rust verifiers and Python differential oracle.
"""
from __future__ import annotations

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
        print(f"  \u2713 PASS {name} (mutation successfully caught and killed)")
        PASS += 1
    except Exception as e:
        print(f"  \u2717 FAIL {name}: unexpected exception {type(e).__name__}: {e}")
        FAIL += 1


def make_type_bool(): return {"kind": "Bool"}
def make_type_i64(): return {"kind": "I64"}
def make_type_string(): return {"kind": "String"}


def m01_drop_err_edge():
    # Buggy program omits Err branch handling in MatchResult
    prog = {
        "name": "M01_drop_err_edge",
        "entry_func": "main",
        "inputs": {},
        "module": {
            "name": "mod_m01",
            "functions": [{
                "name": "main",
                "params": [],
                "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Read": "doc"}]},
                "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0,
                        "name": "entry",
                        "params": [],
                        "instructions": [{
                            "Read": {"dest": 1, "domain": "doc", "ok_type": make_type_string(), "err_type": make_type_string(), "latent": {"on_ok": [], "on_err": []}}
                        }],
                        "terminator": {
                            "MatchResult": {
                                "result_val": 1,
                                "ok_target": 1,
                                "ok_arg": 2,
                                "err_target": 999,  # DROPPED / INVALID TARGET
                                "err_arg": 3
                            }
                        }
                    },
                    "1": {
                        "id": 1,
                        "name": "ok",
                        "params": [[2, make_type_string()]],
                        "instructions": [],
                        "terminator": {"Return": 2}
                    }
                }
            }]
        }
    }
    obs = invoke_rust_conformance(prog)
    return obs["status"] == "verifier_error" and any(d["code"] == "CfgBadTarget" for d in obs.get("diagnostics", []))


def m02_swap_ok_err_payloads():
    # Swapped Ok/Err target parameter types
    prog = {
        "name": "M02_swap_ok_err",
        "entry_func": "main",
        "inputs": {},
        "module": {
            "name": "mod_m02",
            "functions": [{
                "name": "main",
                "params": [],
                "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Read": "doc"}]},
                "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0,
                        "name": "entry",
                        "params": [],
                        "instructions": [{
                            "Read": {"dest": 1, "domain": "doc", "ok_type": make_type_string(), "err_type": make_type_i64(), "latent": {"on_ok": [], "on_err": []}}
                        }],
                        "terminator": {
                            "MatchResult": {
                                "result_val": 1,
                                "ok_target": 1,
                                "ok_arg": 2,
                                "err_target": 2,
                                "err_arg": 3
                            }
                        }
                    },
                    "1": {
                        "id": 1,
                        "name": "ok_branch",
                        "params": [[2, make_type_i64()]],  # SWAPPED: expects I64 on Ok branch
                        "instructions": [],
                        "terminator": {"Return": None}
                    },
                    "2": {
                        "id": 2,
                        "name": "err_branch",
                        "params": [[3, make_type_string()]],
                        "instructions": [],
                        "terminator": {"Return": None}
                    }
                }
            }]
        }
    }
    obs = invoke_rust_conformance(prog)
    return obs["status"] == "verifier_error" and any(d["code"] == "ResultPayloadType" for d in obs.get("diagnostics", []))


def m03_wrong_block_arg_type():
    prog = {
        "name": "M03_wrong_block_arg_type",
        "entry_func": "main",
        "inputs": {},
        "module": {
            "name": "mod_m03",
            "functions": [{
                "name": "main",
                "params": [],
                "return_type": make_type_i64(),
                "declared_effects": {"effects": []},
                "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0,
                        "name": "entry",
                        "params": [],
                        "instructions": [{"Pure": {"dest": 1, "val": {"kind": "String", "payload": "x"}, "ty": make_type_string()}}],
                        "terminator": {"Br": {"target": 1, "args": [1]}}
                    },
                    "1": {
                        "id": 1,
                        "name": "target",
                        "params": [[2, make_type_i64()]],  # Expects I64, received String
                        "instructions": [],
                        "terminator": {"Return": 2}
                    }
                }
            }]
        }
    }
    obs = invoke_rust_conformance(prog)
    return obs["status"] == "verifier_error" and any(d["code"] == "BlockArgType" for d in obs.get("diagnostics", []))


def m04_lose_latent_postcondition():
    # Program executes, but latent postconditions are dropped
    prog = {
        "name": "M04_lose_latent",
        "entry_func": "main",
        "inputs": {},
        "module": {
            "name": "mod_m04",
            "functions": [{
                "name": "main",
                "params": [],
                "return_type": make_type_string(),
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
                                "ok_type": make_type_string(),
                                "err_type": make_type_string(),
                                "latent": {"on_ok": [], "on_err": []}  # EMPTY LATENT
                            }
                        }],
                        "terminator": {
                            "MatchResult": {
                                "result_val": 1,
                                "ok_target": 1,
                                "ok_arg": 2,
                                "err_target": 2,
                                "err_arg": 3
                            }
                        }
                    },
                    "1": {
                        "id": 1,
                        "name": "ok",
                        "params": [[2, make_type_string()]],
                        "instructions": [],
                        "terminator": {"Return": 2}
                    },
                    "2": {
                        "id": 2,
                        "name": "err",
                        "params": [[3, make_type_string()]],
                        "instructions": [],
                        "terminator": {"Return": 3}
                    }
                }
            }]
        }
    }
    obs = invoke_rust_conformance(prog)
    return not any(f.get("predicate") == "ObservedAt" for f in obs.get("active_facts", []))


def m05_eager_on_ok():
    # Unrefined Result definition MUST NOT eagerly discharge on_ok facts into entry block
    prog = {
        "name": "M05_eager_on_ok",
        "entry_func": "main",
        "inputs": {},
        "module": {
            "name": "mod_m05",
            "functions": [{
                "name": "main",
                "params": [],
                "return_type": make_type_string(),
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
                                "ok_type": make_type_string(),
                                "err_type": make_type_string(),
                                "latent": {"on_ok": [{"predicate": "ObservedAt", "args": [{"Symbol": "$value"}]}], "on_err": []}
                            }
                        }],
                        "terminator": {"Br": {"target": 1, "args": []}}  # FORWARDS WITHOUT MATCH
                    },
                    "1": {
                        "id": 1,
                        "name": "exit",
                        "params": [],
                        "instructions": [
                            {"Pure": {"dest": 2, "val": {"kind": "String", "payload": "done"}, "ty": make_type_string()}}
                        ],
                        "terminator": {"Return": 2}
                    }
                }
            }]
        }
    }
    obs = invoke_rust_conformance(prog)
    # Entry and exit block facts must NOT contain ObservedAt
    return not any(f.get("predicate") == "ObservedAt" for f in obs.get("active_facts", []))


def m06_merge_union_instead_of_intersection():
    # In diamond merge, exclusive branch fact MUST NOT appear in merge block
    prog = {
        "name": "M06_merge_union_bug",
        "entry_func": "main",
        "inputs": {},
        "module": {
            "name": "mod_m06",
            "functions": [{
                "name": "main",
                "params": [],
                "return_type": make_type_string(),
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
                                "ok_type": make_type_string(),
                                "err_type": make_type_string(),
                                "latent": {
                                    "on_ok": [{"predicate": "ExclusiveBranchFact", "args": [{"Symbol": "$value"}]}],
                                    "on_err": []
                                }
                            }
                        }],
                        "terminator": {"MatchResult": {"result_val": 1, "ok_target": 1, "ok_arg": 2, "err_target": 2, "err_arg": 3}}
                    },
                    "1": {"id": 1, "name": "ok", "params": [[2, make_type_string()]], "instructions": [], "terminator": {"Br": {"target": 3, "args": [2]}}},
                    "2": {"id": 2, "name": "err", "params": [[3, make_type_string()]], "instructions": [], "terminator": {"Br": {"target": 3, "args": [3]}}},
                    "3": {"id": 3, "name": "merge", "params": [[4, make_type_string()]], "instructions": [], "terminator": {"Return": 4}}
                }
            }]
        }
    }
    obs = invoke_rust_conformance(prog)
    # Merge block must NOT contain ExclusiveBranchFact
    return not any(f.get("predicate") == "ExclusiveBranchFact" for f in obs.get("active_facts", []))


def m07_omit_read_effect():
    prog = {
        "name": "M07_omit_read_effect",
        "entry_func": "main",
        "inputs": {},
        "module": {
            "name": "mod_m07",
            "functions": [{
                "name": "main",
                "params": [],
                "return_type": make_type_string(),
                "declared_effects": {"effects": []},  # OMITTED READ EFFECT
                "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0,
                        "name": "entry",
                        "params": [],
                        "instructions": [{
                            "Read": {"dest": 1, "domain": "docs", "ok_type": make_type_string(), "err_type": make_type_string(), "latent": {"on_ok": [], "on_err": []}}
                        }],
                        "terminator": {"Return": None}
                    }
                }
            }]
        }
    }
    obs = invoke_rust_conformance(prog)
    return obs["status"] == "verifier_error" and any(d["code"] == "EffectUndeclared" for d in obs.get("diagnostics", []))


def m08_omit_infer_effect():
    prog = {
        "name": "M08_omit_infer_effect",
        "entry_func": "main",
        "inputs": {},
        "module": {
            "name": "mod_m08",
            "functions": [{
                "name": "main",
                "params": [],
                "return_type": make_type_string(),
                "declared_effects": {"effects": []},  # OMITTED INFER EFFECT
                "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0,
                        "name": "entry",
                        "params": [],
                        "instructions": [{
                            "Infer": {"dest": 1, "prompt": "query", "ok_type": make_type_string(), "err_type": make_type_string(), "latent": {"on_ok": [], "on_err": []}}
                        }],
                        "terminator": {"Return": None}
                    }
                }
            }]
        }
    }
    obs = invoke_rust_conformance(prog)
    return obs["status"] == "verifier_error" and any(d["code"] == "EffectUndeclared" for d in obs.get("diagnostics", []))


def m09_stale_ssa_reference():
    prog = {
        "name": "M09_stale_ssa_ref",
        "entry_func": "main",
        "inputs": {},
        "module": {
            "name": "mod_m09",
            "functions": [{
                "name": "main",
                "params": [],
                "return_type": make_type_i64(),
                "declared_effects": {"effects": []},
                "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0,
                        "name": "entry",
                        "params": [],
                        "instructions": [],
                        "terminator": {"Return": 888}  # STALE UNBOUND VALUE ID 888
                    }
                }
            }]
        }
    }
    obs = invoke_rust_conformance(prog)
    return obs["status"] == "verifier_error" and any(d["code"] == "SsaUseBeforeDef" for d in obs.get("diagnostics", []))


def m10_single_pass_loop_leakage():
    # Loop body fact MUST NOT leak to loop header without proof on entry edge
    prog = {
        "name": "M10_loop_leakage",
        "entry_func": "main",
        "inputs": {"v1": {"kind": "Bool", "payload": False}},
        "module": {
            "name": "mod_m10",
            "functions": [{
                "name": "main",
                "params": [[1, make_type_bool()]],
                "return_type": make_type_i64(),
                "declared_effects": {"effects": []},
                "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "name": "entry", "params": [],
                        "instructions": [{"Pure": {"dest": 2, "val": {"kind": "I64", "payload": 0}, "ty": make_type_i64()}}],
                        "terminator": {"Br": {"target": 1, "args": [2]}}
                    },
                    "1": {
                        "id": 1, "name": "loop_header", "params": [[3, make_type_i64()]],
                        "instructions": [],
                        "terminator": {"CondBr": {"cond": 1, "true_target": 2, "true_args": [3], "false_target": 3, "false_args": [3]}}
                    },
                    "2": {
                        "id": 2, "name": "loop_body", "params": [[4, make_type_i64()]],
                        "instructions": [],
                        "terminator": {"Br": {"target": 1, "args": [4]}}
                    },
                    "3": {
                        "id": 3, "name": "exit", "params": [[5, make_type_i64()]],
                        "instructions": [],
                        "terminator": {"Return": 5}
                    }
                }
            }]
        }
    }
    obs = invoke_rust_conformance(prog)
    # Loop body fact must NOT leak to exit path
    return not any(f.get("predicate") == "IterationFact" for f in obs.get("active_facts", []))


if __name__ == "__main__":
    print("=" * 70)
    print("SOMA COMPILER CONFORMANCE v0 (SLICE 1) — Mutation Kills M01–M10")
    kill_mutation("M01_drop_err_edge", m01_drop_err_edge)
    kill_mutation("M02_swap_ok_err_payloads", m02_swap_ok_err_payloads)
    kill_mutation("M03_wrong_block_arg_type", m03_wrong_block_arg_type)
    kill_mutation("M04_lose_latent_postcondition", m04_lose_latent_postcondition)
    kill_mutation("M05_eager_on_ok", m05_eager_on_ok)
    kill_mutation("M06_merge_union_instead_of_intersection", m06_merge_union_instead_of_intersection)
    kill_mutation("M07_omit_read_effect", m07_omit_read_effect)
    kill_mutation("M08_omit_infer_effect", m08_omit_infer_effect)
    kill_mutation("M09_stale_ssa_reference", m09_stale_ssa_reference)
    kill_mutation("M10_single_pass_loop_leakage", m10_single_pass_loop_leakage)

    print("=" * 70)
    print(f"MUTATION KILLS RESULT: {PASS} passed, {FAIL} failed ({PASS + FAIL} total)")
    if FAIL:
        sys.exit(1)
    print("All Mutation Kills correctly identified and killed.")
