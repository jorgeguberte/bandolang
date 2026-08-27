"""test_negative.py — Negative Verifier Cases V01–V12 for Compiler Conformance v0 (Slice 1).

Validates that the Rust High-Level Verifier and VM Verifier correctly reject invalid programs
with structured DiagnosticCode, including real SSA dominance and visibility rules (R3).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from protocol import invoke_rust_conformance

PASS, FAIL = 0, 0


def expect_verifier_error(name: str, program: dict, expected_code: str) -> None:
    global PASS, FAIL
    print(f"\n--- NEGATIVE VERIFIER TEST: {name}")
    try:
        obs = invoke_rust_conformance(program)
        if obs["status"] not in ("verifier_error", "vm_verifier_error"):
            print(f"  \u2717 FAIL {name}: expected verifier error, but got status '{obs['status']}'")
            FAIL += 1
            return
        diags = obs.get("diagnostics", [])
        matched = any(d.get("code") == expected_code for d in diags)
        if not matched:
            print(f"  \u2717 FAIL {name}: expected diagnostic code '{expected_code}', got {diags}")
            FAIL += 1
            return
        print(f"  \u2713 PASS {name} (correctly rejected with {expected_code})")
        PASS += 1
    except Exception as e:
        print(f"  \u2717 FAIL {name}: crashed with exception {type(e).__name__}: {e}")
        FAIL += 1


def make_type_bool(): return {"kind": "Bool"}
def make_type_i64(): return {"kind": "I64"}
def make_type_string(): return {"kind": "String"}
def make_type_result(ok, err): return {"kind": "Result", "payload": {"ok": ok, "err": err}}


def v01_duplicate_ssa():
    prog = {
        "name": "V01_duplicate_ssa",
        "entry_func": "main",
        "inputs": {},
        "module": {
            "name": "mod_v01",
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
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "I64", "payload": 10}, "ty": make_type_i64()}},
                            {"Pure": {"dest": 1, "val": {"kind": "I64", "payload": 20}, "ty": make_type_i64()}}  # DUPLICATE 1
                        ],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    expect_verifier_error("V01_duplicate_ssa", prog, "SsaDuplicateDef")


def v02_use_before_definition():
    prog = {
        "name": "V02_use_before_def",
        "entry_func": "main",
        "inputs": {},
        "module": {
            "name": "mod_v02",
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
                        "instructions": [
                            {"Assign": {"dest": 1, "source": 99, "ty": make_type_i64()}}  # USE 99 UNDEFINED
                        ],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    expect_verifier_error("V02_use_before_definition", prog, "SsaUseBeforeDef")


def v03_wrong_ok_payload_type():
    prog = {
        "name": "V03_wrong_ok_payload_type",
        "entry_func": "main",
        "inputs": {},
        "module": {
            "name": "mod_v03",
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
                                "ok_arg": 2,
                                "ok_body": {
                                    "instructions": [{"Assign": {"dest": 4, "source": 2, "ty": make_type_i64()}}],  # TREATS STRING AS I64
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
    expect_verifier_error("V03_wrong_ok_payload_type", prog, "TypeMismatch")


def v04_wrong_err_payload_type():
    prog = {
        "name": "V04_wrong_err_payload_type",
        "entry_func": "main",
        "inputs": {},
        "module": {
            "name": "mod_v04",
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
                                "ok_arg": 2,
                                "ok_body": {"instructions": [], "terminator": {"Return": 2}},
                                "err_arg": 3,
                                "err_body": {
                                    "instructions": [{"Assign": {"dest": 5, "source": 3, "ty": make_type_bool()}}],  # TREATS STRING AS BOOL
                                    "terminator": {"Return": 5}
                                }
                            }
                        }
                    }
                }
            }]
        }
    }
    expect_verifier_error("V04_wrong_err_payload_type", prog, "TypeMismatch")


def v05_block_arg_arity():
    prog = {
        "name": "V05_block_arg_arity",
        "entry_func": "main",
        "inputs": {},
        "module": {
            "name": "mod_v05",
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
                        "instructions": [{"Pure": {"dest": 1, "val": {"kind": "I64", "payload": 10}, "ty": make_type_i64()}}],
                        "terminator": {"Br": {"target": 1, "args": [1, 1]}}  # PASSES 2 ARGS TO BLOCK EXPECTING 1
                    },
                    "1": {
                        "id": 1,
                        "name": "target",
                        "params": [[2, make_type_i64()]],
                        "instructions": [],
                        "terminator": {"Return": 2}
                    }
                }
            }]
        }
    }
    expect_verifier_error("V05_block_arg_arity", prog, "BlockArgArity")


def v06_block_arg_type():
    prog = {
        "name": "V06_block_arg_type",
        "entry_func": "main",
        "inputs": {},
        "module": {
            "name": "mod_v06",
            "functions": [{
                "name": "main",
                "params": [],
                "return_type": make_type_string(),
                "declared_effects": {"effects": []},
                "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0,
                        "name": "entry",
                        "params": [],
                        "instructions": [{"Pure": {"dest": 1, "val": {"kind": "I64", "payload": 10}, "ty": make_type_i64()}}],
                        "terminator": {"Br": {"target": 1, "args": [1]}}  # PASSES I64 TO STRING PARAM
                    },
                    "1": {
                        "id": 1,
                        "name": "target",
                        "params": [[2, make_type_string()]],
                        "instructions": [],
                        "terminator": {"Return": 2}
                    }
                }
            }]
        }
    }
    expect_verifier_error("V06_block_arg_type", prog, "BlockArgType")


def v07_invalid_target_block():
    prog = {
        "name": "V07_invalid_target",
        "entry_func": "main",
        "inputs": {},
        "module": {
            "name": "mod_v07",
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
                        "terminator": {"Br": {"target": 999, "args": []}}  # BLOCK 999 DOES NOT EXIST
                    }
                }
            }]
        }
    }
    expect_verifier_error("V07_invalid_target_block", prog, "CfgBadTarget")


def v08_missing_read_effect():
    prog = {
        "name": "V08_missing_read_effect",
        "entry_func": "main",
        "inputs": {},
        "module": {
            "name": "mod_v08",
            "functions": [{
                "name": "main",
                "params": [],
                "return_type": make_type_string(),
                "declared_effects": {"effects": []},  # EMPTY EFFECTS
                "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0,
                        "name": "entry",
                        "params": [],
                        "instructions": [{
                            "Read": {"dest": 1, "domain": "secret_doc", "ok_type": make_type_string(), "err_type": make_type_string(), "latent": {"on_ok": [], "on_err": []}}
                        }],
                        "terminator": {"Return": None}
                    }
                }
            }]
        }
    }
    expect_verifier_error("V08_missing_read_effect", prog, "EffectUndeclared")


def v09_missing_infer_effect():
    prog = {
        "name": "V09_missing_infer_effect",
        "entry_func": "main",
        "inputs": {},
        "module": {
            "name": "mod_v09",
            "functions": [{
                "name": "main",
                "params": [],
                "return_type": make_type_string(),
                "declared_effects": {"effects": []},  # EMPTY EFFECTS
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
    expect_verifier_error("V09_missing_infer_effect", prog, "EffectUndeclared")


def v10_type_mismatch_assign():
    prog = {
        "name": "V10_type_mismatch_assign",
        "entry_func": "main",
        "inputs": {},
        "module": {
            "name": "mod_v10",
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
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "hello"}, "ty": make_type_string()}},
                            {"Assign": {"dest": 2, "source": 1, "ty": make_type_i64()}}  # ASSIGN STRING TO I64
                        ],
                        "terminator": {"Return": 2}
                    }
                }
            }]
        }
    }
    expect_verifier_error("V10_type_mismatch_assign", prog, "TypeMismatch")


def v11_return_type_mismatch():
    prog = {
        "name": "V11_return_type_mismatch",
        "entry_func": "main",
        "inputs": {},
        "module": {
            "name": "mod_v11",
            "functions": [{
                "name": "main",
                "params": [],
                "return_type": make_type_string(),  # EXPECTS STRING
                "declared_effects": {"effects": []},
                "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0,
                        "name": "entry",
                        "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "I64", "payload": 42}, "ty": make_type_i64()}}
                        ],
                        "terminator": {"Return": 1}  # RETURNS I64
                    }
                }
            }]
        }
    }
    expect_verifier_error("V11_return_type_mismatch", prog, "TypeMismatch")


def v12_sibling_block_ssa_use_without_block_arg():
    # R3: Sibling block value used without block argument transport => REJECTED
    prog = {
        "name": "V12_sibling_block_use",
        "entry_func": "main",
        "inputs": {},
        "module": {
            "name": "mod_v12",
            "functions": [{
                "name": "main",
                "params": [[1, make_type_bool()]],
                "return_type": make_type_i64(),
                "declared_effects": {"effects": []},
                "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "name": "entry", "params": [], "instructions": [],
                        "terminator": {"CondBr": {"cond": 1, "true_target": 1, "true_args": [], "false_target": 2, "false_args": []}}
                    },
                    "1": {
                        "id": 1, "name": "left", "params": [],
                        "instructions": [{"Pure": {"dest": 2, "val": {"kind": "I64", "payload": 100}, "ty": make_type_i64()}}],
                        "terminator": {"Return": 2}
                    },
                    "2": {
                        "id": 2, "name": "right", "params": [], "instructions": [],
                        "terminator": {"Return": 2}  # ILLEGAL USE OF VALUE 2 FROM SIBLING BLOCK 1!
                    }
                }
            }]
        }
    }
    expect_verifier_error("V12_sibling_block_ssa_use_without_block_arg", prog, "SsaUseBeforeDef")


def v13_region_local_def_leak():
    # S1: Region-local Ok definition used outside MatchResult without block argument
    prog = {
        "name": "V13_region_local_leak",
        "entry_func": "main",
        "inputs": {},
        "module": {
            "name": "mod_v13",
            "functions": [{
                "name": "main",
                "params": [],
                "return_type": make_type_i64(),
                "declared_effects": {"effects": []},
                "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "name": "entry", "params": [],
                        "instructions": [{"Pure": {"dest": 1, "val": {"kind": "I64", "payload": 10}, "ty": make_type_result(make_type_i64(), make_type_i64())}}],
                        "terminator": {
                            "MatchResult": {
                                "result_val": 1,
                                "ok_arg": 2,
                                "ok_body": {
                                    "instructions": [{"Pure": {"dest": 4, "val": {"kind": "I64", "payload": 42}, "ty": make_type_i64()}}],
                                    "terminator": {"Br": {"target": 1, "args": []}}  # DID NOT TRANSPORT 4!
                                },
                                "err_arg": 3,
                                "err_body": {"instructions": [], "terminator": {"Br": {"target": 1, "args": []}}}
                            }
                        }
                    },
                    "1": {
                        "id": 1, "name": "merge", "params": [], "instructions": [],
                        "terminator": {"Return": 4}  # ILLEGAL USE OF REGION-LOCAL VALUE 4!
                    }
                }
            }]
        }
    }
    expect_verifier_error("V13_region_local_def_leak", prog, "SsaUseBeforeDef")


def v14_region_cross_use():
    # S1: Region-local Err definition used inside Ok region
    prog = {
        "name": "V14_region_cross_use",
        "entry_func": "main",
        "inputs": {},
        "module": {
            "name": "mod_v14",
            "functions": [{
                "name": "main",
                "params": [],
                "return_type": make_type_i64(),
                "declared_effects": {"effects": []},
                "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "name": "entry", "params": [],
                        "instructions": [{"Pure": {"dest": 1, "val": {"kind": "I64", "payload": 10}, "ty": make_type_result(make_type_i64(), make_type_i64())}}],
                        "terminator": {
                            "MatchResult": {
                                "result_val": 1,
                                "ok_arg": 2,
                                "ok_body": {
                                    "instructions": [],
                                    "terminator": {"Return": 4}  # USES 4 DEFINED ONLY IN ERR REGION!
                                },
                                "err_arg": 3,
                                "err_body": {
                                    "instructions": [{"Pure": {"dest": 4, "val": {"kind": "I64", "payload": 99}, "ty": make_type_i64()}}],
                                    "terminator": {"Return": 4}
                                }
                            }
                        }
                    }
                }
            }]
        }
    }
    expect_verifier_error("V14_region_cross_use", prog, "SsaUseBeforeDef")


if __name__ == "__main__":
    print("=" * 70)
    print("SOMA COMPILER CONFORMANCE v0 (SLICE 1) — Negative Verifier Tests V01–V14 (R3 & S1)")
    v01_duplicate_ssa()
    v02_use_before_definition()
    v03_wrong_ok_payload_type()
    v04_wrong_err_payload_type()
    v05_block_arg_arity()
    v06_block_arg_type()
    v07_invalid_target_block()
    v08_missing_read_effect()
    v09_missing_infer_effect()
    v10_type_mismatch_assign()
    v11_return_type_mismatch()
    v12_sibling_block_ssa_use_without_block_arg()
    v13_region_local_def_leak()
    v14_region_cross_use()

    print("=" * 70)
    print(f"NEGATIVE VERIFIER RESULT: {PASS} passed, {FAIL} failed ({PASS + FAIL} total)")
    if FAIL:
        sys.exit(1)
    print("All Negative Verifier Tests correctly rejected by Rust Verifier.")
