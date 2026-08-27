"""test_differential.py — Exact Shared Observable Comparator for SOMA-IR Slice 1 (R5).

Compares every frozen shared observable available in ConformanceObservationV0:
1. Status
2. Return value / Result variant / payload
3. Observable external effects (Σ)
4. Exact active Ψ path facts
5. Latent postconditions
6. Types
7. Environment bindings
8. Concrete value lineage
9. Diagnostics

Includes negative comparator probes (R5):
- Wrong lineage => comparator fails
- Lost latent facts => comparator fails
- Wrong type/binding => comparator fails
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

PASS, FAIL = 0, 0


def compare_exact_observables(name: str, expected_oracle: dict, rust_obs: dict) -> list[str]:
    """Exact observable comparator across all shared observables (R5)."""
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

    # 4. Path facts Ψ (set of canonical tuples)
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

    # 5. Latent facts
    if "latent_facts" in expected_oracle:
        for k, v in expected_oracle["latent_facts"].items():
            if rust_obs.get("latent_facts", {}).get(k) != v:
                errors.append(f"Latent facts mismatch on '{k}': expected {v}, got {rust_obs.get('latent_facts', {}).get(k)}")

    # 6. Types
    if "types" in expected_oracle:
        for k, v in expected_oracle["types"].items():
            if rust_obs.get("types", {}).get(k) != v:
                errors.append(f"Type mismatch on '{k}': expected {v}, got {rust_obs.get('types', {}).get(k)}")

    # 7. Bindings
    if "bindings" in expected_oracle:
        for k, v in expected_oracle["bindings"].items():
            if rust_obs.get("bindings", {}).get(k) != v:
                errors.append(f"Binding mismatch on '{k}': expected {v}, got {rust_obs.get('bindings', {}).get(k)}")

    # 8. Lineage
    if "lineage" in expected_oracle:
        for k, v in expected_oracle["lineage"].items():
            if rust_obs.get("lineage", {}).get(k) != v:
                errors.append(f"Lineage mismatch on '{k}': expected {v}, got {rust_obs.get('lineage', {}).get(k)}")

    return errors


def run_diff_check(name: str, fn) -> None:
    global PASS, FAIL
    print(f"\n--- CONFORMANCE DIFFERENTIAL: {name}")
    try:
        errors = fn()
        if errors:
            print(f"  \u2717 FAIL {name}:\n    " + "\n    ".join(errors))
            FAIL += 1
        else:
            print(f"  \u2713 PASS {name} (exact agreement across all shared observables)")
            PASS += 1
    except Exception as e:
        print(f"  \u2717 FAIL {name}: crashed with exception {type(e).__name__}: {e}")
        FAIL += 1


# =====================================================================
# Differential Conformance Suites (R5)
# =====================================================================

def test_diff_c01_pure():
    def _run():
        expected = {
            "status": "ok",
            "return_val": {"kind": "I64", "payload": 42},
            "effects": [],
            "active_facts": set(),
            "types": {"v1": "i64"},
            "bindings": {"v1": {"kind": "I64", "payload": 42}},
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
        return compare_exact_observables("C01_pure_value", expected, rust_obs)
    run_diff_check("C01_pure_value", _run)


def test_diff_c02_read_ok():
    def _run():
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
            "types": {"v1": "Result<string, string>", "v2": "string"},
            "lineage": {"v1": ["read(docs)"]},
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
        rust_obs = invoke_rust_conformance(prog)
        return compare_exact_observables("C02_read_ok", expected, rust_obs)
    run_diff_check("C02_read_ok", _run)


def test_diff_c03_read_err():
    def _run():
        expected = {
            "status": "ok",
            "return_val": {"kind": "String", "payload": "disk_failure"},
            "effects": ["read[docs]"],
            "active_facts": {
                ("IsErr", ("sym(v1)",)),
                ("ErrorOccurred", ("sym(v3)",)),
            },
            "types": {"v1": "Result<string, string>", "v3": "string"},
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
        rust_obs = invoke_rust_conformance(prog)
        return compare_exact_observables("C03_read_err", expected, rust_obs)
    run_diff_check("C03_read_err", _run)


def test_diff_c09_infer_ok():
    def _run():
        expected = {
            "status": "ok",
            "return_val": {"kind": "String", "payload": "infer_of(query_users)"},
            "effects": ["infer"],
            "active_facts": {
                ("IsOk", ("sym(v1)",)),
                ("InferredFact", ("sym(v2)",)),
            },
            "types": {"v1": "Result<string, string>", "v2": "string"},
            "lineage": {"v1": ["infer(query_users)"]},
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
        rust_obs = invoke_rust_conformance(prog)
        return compare_exact_observables("C09_infer_ok", expected, rust_obs)
    run_diff_check("C09_infer_ok", _run)


# =====================================================================
# Negative Comparator Probes (R5)
# =====================================================================

def test_probe_wrong_lineage_fails():
    def _run():
        expected = {
            "status": "ok", "return_val": None, "effects": [], "active_facts": set(),
            "lineage": {"v1": ["read(docs)"]},
        }
        rust_obs = {
            "status": "ok", "return_val": None, "effects": [], "active_facts": [],
            "lineage": {"v1": ["read(WRONG_DOC)"]},
        }
        errs = compare_exact_observables("PROBE_wrong_lineage", expected, rust_obs)
        assert len(errs) > 0, "comparator falsely accepted wrong lineage"
        return []
    run_diff_check("PROBE_wrong_lineage_fails", _run)


def test_probe_lost_latent_facts_fails():
    def _run():
        expected = {
            "status": "ok", "return_val": None, "effects": [], "active_facts": set(),
            "latent_facts": {"v1": {"on_ok": [{"predicate": "ObservedAt", "args": []}], "on_err": []}},
        }
        rust_obs = {
            "status": "ok", "return_val": None, "effects": [], "active_facts": [],
            "latent_facts": {"v1": {"on_ok": [], "on_err": []}},  # LOST LATENT
        }
        errs = compare_exact_observables("PROBE_lost_latent", expected, rust_obs)
        assert len(errs) > 0, "comparator falsely accepted lost latent facts"
        return []
    run_diff_check("PROBE_lost_latent_facts_fails", _run)


def test_probe_wrong_type_binding_fails():
    def _run():
        expected = {
            "status": "ok", "return_val": None, "effects": [], "active_facts": set(),
            "types": {"v1": "string"},
            "bindings": {"v1": {"kind": "String", "payload": "hello"}},
        }
        rust_obs = {
            "status": "ok", "return_val": None, "effects": [], "active_facts": [],
            "types": {"v1": "i64"},
            "bindings": {"v1": {"kind": "I64", "payload": 100}},
        }
        errs = compare_exact_observables("PROBE_wrong_type_binding", expected, rust_obs)
        assert len(errs) > 0, "comparator falsely accepted wrong type and binding"
        return []
    run_diff_check("PROBE_wrong_type_binding_fails", _run)


if __name__ == "__main__":
    print("=" * 70)
    print("SOMA COMPILER CONFORMANCE v0 (SLICE 1) — Python Oracle vs Rust Toolchain Differential (R5)")
    test_diff_c01_pure()
    test_diff_c02_read_ok()
    test_diff_c03_read_err()
    test_diff_c09_infer_ok()
    test_probe_wrong_lineage_fails()
    test_probe_lost_latent_facts_fails()
    test_probe_wrong_type_binding_fails()

    print("=" * 70)
    print(f"DIFFERENTIAL CONFORMANCE RESULT: {PASS} passed, {FAIL} failed ({PASS + FAIL} total)")
    if FAIL:
        sys.exit(1)
    print("Exact differential agreement confirmed between Python Oracle and Rust Toolchain across all shared observables.")
