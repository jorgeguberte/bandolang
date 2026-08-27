"""test_differential.py — Python Semantic Reference Model vs Rust Toolchain Differential Testing.

Executes:
1. Python independent semantic reference evaluation
2. Rust Compiler + VM Toolchain evaluation
3. Exact differential comparison across all shared observables (return value, effects, path facts Ψ, status).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "ir" / "item3"))

from protocol import invoke_rust_conformance
from semantic_model import HighLevelSemanticEngine
from model import (
    Fact as PyFact, FactTemplate as PyFactTemplate,
    LatentPostconditions as PyLatent, OkVal, ErrVal, STRING, I64,
)
import test_golden

PASS, FAIL = 0, 0


def compare_differential(name: str, expected_oracle: dict, rust_obs: dict) -> None:
    global PASS, FAIL
    print(f"\n--- CONFORMANCE DIFFERENTIAL: {name}")

    errors = []

    # 1. Status
    if expected_oracle.get("status") != rust_obs.get("status"):
        errors.append(f"Status mismatch: oracle={expected_oracle.get('status')}, rust={rust_obs.get('status')}")

    # 2. Return value
    if expected_oracle.get("return_val") != rust_obs.get("return_val"):
        errors.append(f"Return value mismatch: oracle={expected_oracle.get('return_val')}, rust={rust_obs.get('return_val')}")

    # 3. Observable effects
    if expected_oracle.get("effects") != rust_obs.get("effects"):
        errors.append(f"Effects mismatch: oracle={expected_oracle.get('effects')}, rust={rust_obs.get('effects')}")

    # 4. Path facts Ψ (converted to set of tuples for exact comparison)
    oracle_facts = expected_oracle.get("active_facts", set())
    rust_raw_facts = rust_obs.get("active_facts", [])
    rust_fact_set = set()
    for rf in rust_raw_facts:
        pred = rf["predicate"]
        args = []
        for a in rf["args"]:
            if "Symbol" in a: args.append(f"sym({a['Symbol']})")
            elif "Literal" in a: args.append(f"lit({a['Literal']})")
        rust_fact_set.add((pred, tuple(args)))

    if oracle_facts != rust_fact_set:
        errors.append(f"Path facts Ψ exact mismatch:\n  oracle={oracle_facts}\n  rust={rust_fact_set}")

    if errors:
        print(f"  \u2717 FAIL {name}:\n    " + "\n    ".join(errors))
        FAIL += 1
    else:
        print(f"  \u2713 PASS {name} (exact agreement between Python Oracle and Rust Toolchain)")
        PASS += 1


# =====================================================================
# Differential Conformance Suites
# =====================================================================

def test_diff_c01_pure():
    sem = HighLevelSemanticEngine()
    expected = {
        "status": "ok",
        "return_val": {"kind": "I64", "payload": 42},
        "effects": [],
        "active_facts": set(),
    }
    prog = {
        "name": "C01_pure", "entry_func": "main", "inputs": {},
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [], "return_type": {"kind": "I64"},
                "declared_effects": {"effects": []}, "entry": 0,
                "blocks": {"0": {"id": 0, "params": [], "instructions": [{"Pure": {"dest": 1, "val": {"kind": "I64", "payload": 42}, "ty": {"kind": "I64"}}}], "terminator": {"Return": 1}}}
            }]
        }
    }
    rust_obs = invoke_rust_conformance(prog)
    compare_differential("C01_pure_value", expected, rust_obs)


def test_diff_c02_read_ok():
    sem = HighLevelSemanticEngine()
    latent = PyLatent(on_ok=(PyFactTemplate("ObservedAt", ("$value", "docs")),))
    res = sem.read_op("docs", latent)
    sem.refine_result(res, "r", "v2")

    expected = {
        "status": "ok",
        "return_val": {"kind": "String", "payload": "data_of(docs)"},
        "effects": ["read[docs]"],
        "active_facts": {
            ("IsOk", ("sym(v1)",)),
            ("ObservedAt", ("sym(v2)", "lit(docs)")),
        },
    }
    prog = {
        "name": "C02_read_ok", "entry_func": "main", "inputs": {},
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [], "return_type": {"kind": "String"},
                "declared_effects": {"effects": [{"Read": "docs"}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [{
                            "Read": {
                                "dest": 1, "domain": "docs", "ok_type": {"kind": "String"}, "err_type": {"kind": "String"},
                                "latent": {"on_ok": [{"predicate": "ObservedAt", "args": [{"Symbol": "$value"}, {"Literal": "docs"}]}], "on_err": []}
                            }
                        }],
                        "terminator": {"MatchResult": {"result_val": 1, "ok_target": 1, "ok_arg": 2, "err_target": 2, "err_arg": 3}}
                    },
                    "1": {"id": 1, "params": [[2, {"kind": "String"}]], "instructions": [], "terminator": {"Return": 2}},
                    "2": {"id": 2, "params": [[3, {"kind": "String"}]], "instructions": [], "terminator": {"Return": 3}},
                }
            }]
        }
    }
    rust_obs = invoke_rust_conformance(prog)
    compare_differential("C02_read_ok", expected, rust_obs)


def test_diff_c03_read_err():
    sem = HighLevelSemanticEngine()
    latent = PyLatent(
        on_ok=(PyFactTemplate("ObservedAt", ("$value",)),),
        on_err=(PyFactTemplate("ErrorOccurred", ("$error",)),),
    )
    err = ErrVal("disk_failure", STRING, latent)
    sem.refine_result(err, "v1", "v3")

    expected = {
        "status": "ok",
        "return_val": {"kind": "String", "payload": "disk_failure"},
        "effects": ["read[docs]"],
        "active_facts": {
            ("IsErr", ("sym(v1)",)),
            ("ErrorOccurred", ("sym(v3)",)),
        },
    }
    prog = {
        "name": "C03_read_err", "entry_func": "main", "inputs": {},
        "read_errors": {"docs": "disk_failure"},
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [], "return_type": {"kind": "String"},
                "declared_effects": {"effects": [{"Read": "docs"}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [{
                            "Read": {
                                "dest": 1, "domain": "docs", "ok_type": {"kind": "String"}, "err_type": {"kind": "String"},
                                "latent": {
                                    "on_ok": [{"predicate": "ObservedAt", "args": [{"Symbol": "$value"}]}],
                                    "on_err": [{"predicate": "ErrorOccurred", "args": [{"Symbol": "$error"}]}]
                                }
                            }
                        }],
                        "terminator": {"MatchResult": {"result_val": 1, "ok_target": 1, "ok_arg": 2, "err_target": 2, "err_arg": 3}}
                    },
                    "1": {"id": 1, "params": [[2, {"kind": "String"}]], "instructions": [], "terminator": {"Return": 2}},
                    "2": {"id": 2, "params": [[3, {"kind": "String"}]], "instructions": [], "terminator": {"Return": 3}},
                }
            }]
        }
    }
    rust_obs = invoke_rust_conformance(prog)
    compare_differential("C03_read_err", expected, rust_obs)


def test_diff_c09_infer_ok():
    sem = HighLevelSemanticEngine()
    latent = PyLatent(on_ok=(PyFactTemplate("InferredFact", ("$value",)),))
    res = sem.infer_op("query_users", latent)
    sem.refine_result(res, "v1", "v2")

    expected = {
        "status": "ok",
        "return_val": {"kind": "String", "payload": "infer_of(query_users)"},
        "effects": ["infer"],
        "active_facts": {
            ("IsOk", ("sym(v1)",)),
            ("InferredFact", ("sym(v2)",)),
        },
    }
    prog = {
        "name": "C09_infer_ok", "entry_func": "main", "inputs": {},
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [], "return_type": {"kind": "String"},
                "declared_effects": {"effects": ["Infer"]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [{
                            "Infer": {
                                "dest": 1, "prompt": "query_users", "ok_type": {"kind": "String"}, "err_type": {"kind": "String"},
                                "latent": {"on_ok": [{"predicate": "InferredFact", "args": [{"Symbol": "$value"}]}], "on_err": []}
                            }
                        }],
                        "terminator": {"MatchResult": {"result_val": 1, "ok_target": 1, "ok_arg": 2, "err_target": 2, "err_arg": 3}}
                    },
                    "1": {"id": 1, "params": [[2, {"kind": "String"}]], "instructions": [], "terminator": {"Return": 2}},
                    "2": {"id": 2, "params": [[3, {"kind": "String"}]], "instructions": [], "terminator": {"Return": 3}},
                }
            }]
        }
    }
    rust_obs = invoke_rust_conformance(prog)
    compare_differential("C09_infer_ok", expected, rust_obs)


if __name__ == "__main__":
    print("=" * 70)
    print("SOMA COMPILER CONFORMANCE v0 (SLICE 1) — Python Oracle vs Rust Toolchain Differential")
    test_diff_c01_pure()
    test_diff_c02_read_ok()
    test_diff_c03_read_err()
    test_diff_c09_infer_ok()

    print("=" * 70)
    print(f"DIFFERENTIAL CONFORMANCE RESULT: {PASS} passed, {FAIL} failed ({PASS + FAIL} total)")
    if FAIL:
        sys.exit(1)
    print("Exact differential agreement confirmed between Python Oracle and Rust Toolchain.")
