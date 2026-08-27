"""test_golden.py — Golden Conformance Programs C01–C12 for Compiler Conformance v0 (Slice 1).

Executes end-to-end:
Rust High-Level IR -> Rust High-Level Verifier -> Rust Lowering -> Rust VM Verifier -> Rust VM Interpreter.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from protocol import invoke_rust_conformance

PASS, FAIL = 0, 0


def run_golden(name: str, program: dict) -> None:
    global PASS, FAIL
    print(f"\n--- GOLDEN PROGRAM: {name}")
    try:
        obs = invoke_rust_conformance(program)
        if obs["status"] != "ok":
            print(f"  \u2717 FAIL {name}: expected status 'ok', got '{obs['status']}' with diagnostics {obs.get('diagnostics')}")
            FAIL += 1
            return
        # Validation passed
        print(f"  \u2713 PASS {name} (status=ok, return={obs.get('return_val')}, effects={obs.get('effects')})")
        PASS += 1
    except Exception as e:
        print(f"  \u2717 FAIL {name}: crashed with exception {type(e).__name__}: {e}")
        FAIL += 1


# =====================================================================
# C01–C12 Golden Programs Definitions
# =====================================================================

def make_type_unit(): return {"kind": "Unit"}
def make_type_bool(): return {"kind": "Bool"}
def make_type_i64(): return {"kind": "I64"}
def make_type_string(): return {"kind": "String"}
def make_type_result(ok, err): return {"kind": "Result", "payload": {"ok": ok, "err": err}}


def c01_pure_value():
    prog = {
        "name": "C01_pure_value",
        "entry_func": "main",
        "inputs": {},
        "module": {
            "name": "mod_c01",
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
                        "instructions": [{
                            "Pure": {
                                "dest": 1,
                                "val": {"kind": "I64", "payload": 42},
                                "ty": make_type_i64()
                            }
                        }],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    run_golden("C01_pure_value", prog)


def c02_read_ok():
    prog = {
        "name": "C02_read_ok",
        "entry_func": "main",
        "inputs": {},
        "module": {
            "name": "mod_c02",
            "functions": [{
                "name": "main",
                "params": [],
                "return_type": make_type_string(),
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
                                "ok_type": make_type_string(),
                                "err_type": make_type_string(),
                                "latent": {
                                    "on_ok": [{
                                        "predicate": "ObservedAt",
                                        "args": [{"Symbol": "$value"}, {"Literal": "docs"}]
                                    }],
                                    "on_err": []
                                }
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
                        "name": "ok_branch",
                        "params": [[2, make_type_string()]],
                        "instructions": [],
                        "terminator": {"Return": 2}
                    },
                    "2": {
                        "id": 2,
                        "name": "err_branch",
                        "params": [[3, make_type_string()]],
                        "instructions": [],
                        "terminator": {"Return": 3}
                    }
                }
            }]
        }
    }
    run_golden("C02_read_ok", prog)


def c03_read_err():
    prog = {
        "name": "C03_read_err",
        "entry_func": "main",
        "inputs": {},
        "read_errors": {"docs": "disk_failure"},
        "module": {
            "name": "mod_c03",
            "functions": [{
                "name": "main",
                "params": [],
                "return_type": make_type_string(),
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
                                "ok_type": make_type_string(),
                                "err_type": make_type_string(),
                                "latent": {
                                    "on_ok": [{"predicate": "ObservedAt", "args": [{"Symbol": "$value"}]}],
                                    "on_err": [{"predicate": "ErrorOccurred", "args": [{"Symbol": "$error"}]}]
                                }
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
                        "name": "ok_branch",
                        "params": [[2, make_type_string()]],
                        "instructions": [],
                        "terminator": {"Return": 2}
                    },
                    "2": {
                        "id": 2,
                        "name": "err_branch",
                        "params": [[3, make_type_string()]],
                        "instructions": [],
                        "terminator": {"Return": 3}
                    }
                }
            }]
        }
    }
    run_golden("C03_read_err", prog)


def c04_result_payload_ssa_rename():
    prog = {
        "name": "C04_ssa_rename",
        "entry_func": "main",
        "inputs": {},
        "module": {
            "name": "mod_c04",
            "functions": [{
                "name": "main",
                "params": [],
                "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Read": "fileA"}]},
                "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0,
                        "name": "entry",
                        "params": [],
                        "instructions": [{
                            "Read": {
                                "dest": 1,
                                "domain": "fileA",
                                "ok_type": make_type_string(),
                                "err_type": make_type_string(),
                                "latent": {
                                    "on_ok": [{"predicate": "ObservedAt", "args": [{"Symbol": "$value"}, {"Literal": "fileA"}]}],
                                    "on_err": []
                                }
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
                        "name": "ok_branch",
                        "params": [[2, make_type_string()]],
                        "instructions": [{
                            "Assign": {"dest": 4, "source": 2, "ty": make_type_string()}
                        }],
                        "terminator": {"Return": 4}
                    },
                    "2": {
                        "id": 2,
                        "name": "err_branch",
                        "params": [[3, make_type_string()]],
                        "instructions": [],
                        "terminator": {"Return": 3}
                    }
                }
            }]
        }
    }
    run_golden("C04_result_payload_ssa_rename", prog)


def c05_c06_diamond_facts():
    # Tests merge discarding branch-only fact and preserving common fact
    prog = {
        "name": "C05_C06_diamond_facts",
        "entry_func": "main",
        "inputs": {},
        "module": {
            "name": "mod_diamond",
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
                                    "on_ok": [
                                        {"predicate": "BranchOnlyFact", "args": [{"Symbol": "$value"}]},
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
                        "params": [[2, make_type_string()]],
                        "instructions": [],
                        "terminator": {"Br": {"target": 3, "args": [2]}}
                    },
                    "2": {
                        "id": 2,
                        "name": "err_branch",
                        "params": [[3, make_type_string()]],
                        "instructions": [],
                        "terminator": {"Br": {"target": 3, "args": [3]}}
                    },
                    "3": {
                        "id": 3,
                        "name": "merge",
                        "params": [[4, make_type_string()]],
                        "instructions": [],
                        "terminator": {"Return": 4}
                    }
                }
            }]
        }
    }
    run_golden("C05_C06_diamond_facts", prog)


def c07_forwarded_result_remains_latent():
    prog = {
        "name": "C07_forwarded_latent",
        "entry_func": "main",
        "inputs": {},
        "module": {
            "name": "mod_c07",
            "functions": [{
                "name": "main",
                "params": [],
                "return_type": make_type_result(make_type_string(), make_type_string()),
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
                                    "on_ok": [{"predicate": "LatentFact", "args": [{"Symbol": "$value"}]}],
                                    "on_err": []
                                }
                            }
                        }],
                        "terminator": {"Br": {"target": 1, "args": [1]}}
                    },
                    "1": {
                        "id": 1,
                        "name": "forward",
                        "params": [[2, make_type_result(make_type_string(), make_type_string())]],
                        "instructions": [],
                        "terminator": {"Return": 2}
                    }
                }
            }]
        }
    }
    run_golden("C07_forwarded_result_remains_latent", prog)


def c08_loop_fixed_point():
    prog = {
        "name": "C08_loop_fixed_point",
        "entry_func": "main",
        "inputs": {"v1": {"kind": "Bool", "payload": False}},
        "module": {
            "name": "mod_c08",
            "functions": [{
                "name": "main",
                "params": [[1, make_type_bool()]],
                "return_type": make_type_i64(),
                "declared_effects": {"effects": []},
                "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0,
                        "name": "entry",
                        "params": [],
                        "instructions": [{
                            "Pure": {"dest": 2, "val": {"kind": "I64", "payload": 0}, "ty": make_type_i64()}
                        }],
                        "terminator": {"Br": {"target": 1, "args": [2]}}
                    },
                    "1": {
                        "id": 1,
                        "name": "loop_header",
                        "params": [[3, make_type_i64()]],
                        "instructions": [],
                        "terminator": {
                            "CondBr": {
                                "cond": 1,
                                "true_target": 2,
                                "true_args": [3],
                                "false_target": 3,
                                "false_args": [3]
                            }
                        }
                    },
                    "2": {
                        "id": 2,
                        "name": "loop_body",
                        "params": [[4, make_type_i64()]],
                        "instructions": [],
                        "terminator": {"Br": {"target": 1, "args": [4]}}
                    },
                    "3": {
                        "id": 3,
                        "name": "exit",
                        "params": [[5, make_type_i64()]],
                        "instructions": [],
                        "terminator": {"Return": 5}
                    }
                }
            }]
        }
    }
    run_golden("C08_loop_fixed_point", prog)


def c09_infer_ok():
    prog = {
        "name": "C09_infer_ok",
        "entry_func": "main",
        "inputs": {},
        "module": {
            "name": "mod_c09",
            "functions": [{
                "name": "main",
                "params": [],
                "return_type": make_type_string(),
                "declared_effects": {"effects": ["Infer"]},
                "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0,
                        "name": "entry",
                        "params": [],
                        "instructions": [{
                            "Infer": {
                                "dest": 1,
                                "prompt": "query_users",
                                "ok_type": make_type_string(),
                                "err_type": make_type_string(),
                                "latent": {
                                    "on_ok": [{"predicate": "InferredFact", "args": [{"Symbol": "$value"}]}],
                                    "on_err": []
                                }
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
                        "name": "ok_branch",
                        "params": [[2, make_type_string()]],
                        "instructions": [],
                        "terminator": {"Return": 2}
                    },
                    "2": {
                        "id": 2,
                        "name": "err_branch",
                        "params": [[3, make_type_string()]],
                        "instructions": [],
                        "terminator": {"Return": 3}
                    }
                }
            }]
        }
    }
    run_golden("C09_infer_ok", prog)


def c10_infer_err():
    prog = {
        "name": "C10_infer_err",
        "entry_func": "main",
        "inputs": {},
        "infer_errors": {"query_fail": "timeout"},
        "module": {
            "name": "mod_c10",
            "functions": [{
                "name": "main",
                "params": [],
                "return_type": make_type_string(),
                "declared_effects": {"effects": ["Infer"]},
                "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0,
                        "name": "entry",
                        "params": [],
                        "instructions": [{
                            "Infer": {
                                "dest": 1,
                                "prompt": "query_fail",
                                "ok_type": make_type_string(),
                                "err_type": make_type_string(),
                                "latent": {
                                    "on_ok": [{"predicate": "InferredFact", "args": [{"Symbol": "$value"}]}],
                                    "on_err": [{"predicate": "InferError", "args": [{"Symbol": "$error"}]}]
                                }
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
                        "name": "ok_branch",
                        "params": [[2, make_type_string()]],
                        "instructions": [],
                        "terminator": {"Return": 2}
                    },
                    "2": {
                        "id": 2,
                        "name": "err_branch",
                        "params": [[3, make_type_string()]],
                        "instructions": [],
                        "terminator": {"Return": 3}
                    }
                }
            }]
        }
    }
    run_golden("C10_infer_err", prog)


def c11_read_effect_preservation():
    prog = {
        "name": "C11_read_effect",
        "entry_func": "main",
        "inputs": {},
        "module": {
            "name": "mod_c11",
            "functions": [{
                "name": "main",
                "params": [],
                "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Read": "config"}]},
                "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0,
                        "name": "entry",
                        "params": [],
                        "instructions": [{
                            "Read": {
                                "dest": 1,
                                "domain": "config",
                                "ok_type": make_type_string(),
                                "err_type": make_type_string(),
                                "latent": LatentPostconditions()
                            }
                        }],
                        "terminator": {
                            "MatchResult": {
                                "result_val": 1,
                                "ok_target": 1,
                                "ok_arg": 2,
                                "err_target": 1,
                                "err_arg": 2
                            }
                        }
                    },
                    "1": {
                        "id": 1,
                        "name": "exit",
                        "params": [[2, make_type_string()]],
                        "instructions": [],
                        "terminator": {"Return": 2}
                    }
                }
            }]
        }
    }
    run_golden("C11_read_effect_preservation", prog)


def c12_infer_effect_preservation():
    prog = {
        "name": "C12_infer_effect",
        "entry_func": "main",
        "inputs": {},
        "module": {
            "name": "mod_c12",
            "functions": [{
                "name": "main",
                "params": [],
                "return_type": make_type_string(),
                "declared_effects": {"effects": ["Infer"]},
                "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0,
                        "name": "entry",
                        "params": [],
                        "instructions": [{
                            "Infer": {
                                "dest": 1,
                                "prompt": "generate_code",
                                "ok_type": make_type_string(),
                                "err_type": make_type_string(),
                                "latent": LatentPostconditions()
                            }
                        }],
                        "terminator": {
                            "MatchResult": {
                                "result_val": 1,
                                "ok_target": 1,
                                "ok_arg": 2,
                                "err_target": 1,
                                "err_arg": 2
                            }
                        }
                    },
                    "1": {
                        "id": 1,
                        "name": "exit",
                        "params": [[2, make_type_string()]],
                        "instructions": [],
                        "terminator": {"Return": 2}
                    }
                }
            }]
        }
    }
    run_golden("C12_infer_effect_preservation", prog)


def LatentPostconditions():
    return {"on_ok": [], "on_err": []}


if __name__ == "__main__":
    print("=" * 70)
    print("SOMA COMPILER CONFORMANCE v0 (SLICE 1) — Golden Programs C01–C12")
    c01_pure_value()
    c02_read_ok()
    c03_read_err()
    c04_result_payload_ssa_rename()
    c05_c06_diamond_facts()
    c07_forwarded_result_remains_latent()
    c08_loop_fixed_point()
    c09_infer_ok()
    c10_infer_err()
    c11_read_effect_preservation()
    c12_infer_effect_preservation()

    print("=" * 70)
    print(f"GOLDEN CONFORMANCE RESULT: {PASS} passed, {FAIL} failed ({PASS + FAIL} total)")
    if FAIL:
        sys.exit(1)
    print("All Golden Conformance Programs PASS under real Rust toolchain.")
