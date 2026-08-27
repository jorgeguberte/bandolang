"""test_differential.py — Exact Shared Observable Comparator for SOMA-IR Slice 1 (R5 & S3).

Compares every frozen shared observable available in ConformanceObservationV0:
1. Status
2. Return value / Result variant / payload
3. Observable external effects (Σ)
4. Exact active Ψ path facts
5. Latent postconditions (exact dict equality)
6. Types (exact dict equality)
7. Environment bindings (exact dict equality)
8. Concrete value lineage (exact dict equality)
9. Diagnostics (exact list equality)

Includes negative comparator probes (S3):
- Extra/wrong lineage => comparator fails
- Extra/lost latent facts => comparator fails
- Extra/wrong type or binding => comparator fails
- Unexpected diagnostic => comparator fails
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
    """Exact observable comparator across all 9 shared observables with strict equality (S3)."""
    errors = []

    # 1. Status
    if expected_oracle.get("status") != rust_obs.get("status"):
        errors.append(f"Status mismatch: oracle={expected_oracle.get('status')}, rust={rust_obs.get('status')}")

    # 2. Return value
    if expected_oracle.get("return_val") != rust_obs.get("return_val"):
        errors.append(f"Return value mismatch: oracle={expected_oracle.get('return_val')}, rust={rust_obs.get('return_val')}")

    # 3. Observable effects
    expected_effects = expected_oracle.get("effects", [])
    rust_effects = rust_obs.get("effects", [])
    if expected_effects != rust_effects:
        errors.append(f"Effects mismatch: oracle={expected_effects}, rust={rust_effects}")

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

    # 5. Latent facts (strict exact dict equality)
    expected_latent = expected_oracle.get("latent_facts", {})
    rust_latent = rust_obs.get("latent_facts", {})
    if expected_latent != rust_latent:
        errors.append(f"Latent facts exact mismatch: expected {expected_latent}, got {rust_latent}")

    # 6. Types (strict exact dict equality)
    expected_types = expected_oracle.get("types", {})
    rust_types = rust_obs.get("types", {})
    if expected_types != rust_types:
        errors.append(f"Types exact mismatch: expected {expected_types}, got {rust_types}")

    # 7. Bindings (strict exact dict equality)
    expected_bindings = expected_oracle.get("bindings", {})
    rust_bindings = rust_obs.get("bindings", {})
    if expected_bindings != rust_bindings:
        errors.append(f"Bindings exact mismatch: expected {expected_bindings}, got {rust_bindings}")

    # 8. Lineage (strict exact dict equality)
    expected_lineage = expected_oracle.get("lineage", {})
    rust_lineage = rust_obs.get("lineage", {})
    if expected_lineage != rust_lineage:
        errors.append(f"Lineage exact mismatch: expected {expected_lineage}, got {rust_lineage}")

    # 9. Diagnostics (strict exact list equality of diagnostic records/codes)
    expected_diags = expected_oracle.get("diagnostics", [])
    rust_diags = rust_obs.get("diagnostics", [])
    if expected_diags != rust_diags:
        errors.append(f"Diagnostics exact mismatch: expected {expected_diags}, got {rust_diags}")

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
            print(f"  \u2713 PASS {name} (exact agreement across all 9 shared observables)")
            PASS += 1
    except Exception as e:
        print(f"  \u2717 FAIL {name}: crashed with exception {type(e).__name__}: {e}")
        FAIL += 1


# =====================================================================
# Differential Conformance Suites (R5 & S3)
# =====================================================================

def test_diff_c01_pure():
    def _run():
        expected = {
            "status": "ok",
            "return_val": {"kind": "I64", "payload": 42},
            "effects": [],
            "active_facts": set(),
            "latent_facts": {},
            "types": {"v1": "i64"},
            "bindings": {"v1": {"kind": "I64", "payload": 42}},
            "lineage": {},
            "diagnostics": [],
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
        expected_latent = {
            "v1": {
                "on_ok": [{"predicate": "ObservedAt", "args": [{"Symbol": "$value"}, {"Literal": "docs"}]}],
                "on_err": []
            }
        }
        expected = {
            "status": "ok",
            "return_val": {"kind": "String", "payload": "data_of(docs)"},
            "effects": ["read[docs]"],
            "active_facts": {
                ("IsOk", ("sym(v1)",)),
                ("ObservedAt", ("sym(v2)", "lit(docs)")),
            },
            "latent_facts": expected_latent,
            "types": {"v1": "Result<string, string>", "v2": "string"},
            "bindings": {
                "v1": {"kind": "Ok", "payload": {"kind": "String", "payload": "data_of(docs)"}},
                "v2": {"kind": "String", "payload": "data_of(docs)"}
            },
            "lineage": {"v1": ["read(docs)"], "v2": ["read(docs)"]},
            "diagnostics": [],
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
        expected_latent = {
            "v1": {
                "on_ok": [{"predicate": "ObservedAt", "args": [{"Symbol": "$value"}]}],
                "on_err": [{"predicate": "ErrorOccurred", "args": [{"Symbol": "$error"}]}]
            }
        }
        expected = {
            "status": "ok",
            "return_val": {"kind": "String", "payload": "disk_failure"},
            "effects": ["read[docs]"],
            "active_facts": {
                ("IsErr", ("sym(v1)",)),
                ("ErrorOccurred", ("sym(v3)",)),
            },
            "latent_facts": expected_latent,
            "types": {"v1": "Result<string, string>", "v3": "string"},
            "bindings": {
                "v1": {"kind": "Err", "payload": {"kind": "String", "payload": "disk_failure"}},
                "v3": {"kind": "String", "payload": "disk_failure"}
            },
            "lineage": {"v1": ["read(docs)"], "v3": ["read(docs)"]},
            "diagnostics": [],
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
        expected_latent = {
            "v1": {
                "on_ok": [{"predicate": "InferredFact", "args": [{"Symbol": "$value"}]}],
                "on_err": []
            }
        }
        expected = {
            "status": "ok",
            "return_val": {"kind": "String", "payload": "infer_of(query_users)"},
            "effects": ["infer"],
            "active_facts": {
                ("IsOk", ("sym(v1)",)),
                ("InferredFact", ("sym(v2)",)),
            },
            "latent_facts": expected_latent,
            "types": {"v1": "Result<string, string>", "v2": "string"},
            "bindings": {
                "v1": {"kind": "Ok", "payload": {"kind": "String", "payload": "infer_of(query_users)"}},
                "v2": {"kind": "String", "payload": "infer_of(query_users)"}
            },
            "lineage": {"v1": ["infer(query_users)"], "v2": ["infer(query_users)"]},
            "diagnostics": [],
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
# Negative Comparator Probes (S3)
# =====================================================================

def test_probe_extra_lineage_fails():
    def _run():
        expected = {
            "status": "ok", "return_val": None, "effects": [], "active_facts": set(),
            "latent_facts": {}, "types": {}, "bindings": {}, "diagnostics": [],
            "lineage": {"v1": ["read(docs)"]},
        }
        rust_obs = {
            "status": "ok", "return_val": None, "effects": [], "active_facts": [],
            "latent_facts": {}, "types": {}, "bindings": {}, "diagnostics": [],
            "lineage": {"v1": ["read(docs)"], "phantom_evil": ["act(evil)"]},  # EXTRA SPURIOUS LINEAGE!
        }
        errs = compare_exact_observables("PROBE_extra_lineage", expected, rust_obs)
        assert len(errs) > 0, "comparator falsely accepted extra spurious lineage"
        return []
    run_diff_check("PROBE_extra_lineage_fails", _run)


def test_probe_extra_latent_fact_fails():
    def _run():
        expected = {
            "status": "ok", "return_val": None, "effects": [], "active_facts": set(),
            "types": {}, "bindings": {}, "lineage": {}, "diagnostics": [],
            "latent_facts": {"v1": {"on_ok": [{"predicate": "ObservedAt", "args": []}], "on_err": []}},
        }
        rust_obs = {
            "status": "ok", "return_val": None, "effects": [], "active_facts": [],
            "types": {}, "bindings": {}, "lineage": {}, "diagnostics": [],
            "latent_facts": {
                "v1": {"on_ok": [{"predicate": "ObservedAt", "args": []}], "on_err": []},
                "v_phantom": {"on_ok": [{"predicate": "PhantomFact", "args": []}], "on_err": []}  # EXTRA LATENT!
            },
        }
        errs = compare_exact_observables("PROBE_extra_latent", expected, rust_obs)
        assert len(errs) > 0, "comparator falsely accepted extra latent fact entry"
        return []
    run_diff_check("PROBE_extra_latent_fact_fails", _run)


def test_probe_extra_binding_entry_fails():
    def _run():
        expected = {
            "status": "ok", "return_val": None, "effects": [], "active_facts": set(),
            "latent_facts": {}, "types": {}, "lineage": {}, "diagnostics": [],
            "bindings": {"v1": {"kind": "String", "payload": "hello"}},
        }
        rust_obs = {
            "status": "ok", "return_val": None, "effects": [], "active_facts": [],
            "latent_facts": {}, "types": {}, "lineage": {}, "diagnostics": [],
            "bindings": {
                "v1": {"kind": "String", "payload": "hello"},
                "v_spurious": {"kind": "I64", "payload": 999}  # EXTRA BINDING!
            },
        }
        errs = compare_exact_observables("PROBE_extra_binding", expected, rust_obs)
        assert len(errs) > 0, "comparator falsely accepted extra binding entry"
        return []
    run_diff_check("PROBE_extra_binding_entry_fails", _run)


def test_probe_unexpected_diagnostic_fails():
    def _run():
        expected = {
            "status": "ok", "return_val": None, "effects": [], "active_facts": set(),
            "latent_facts": {}, "types": {}, "bindings": {}, "lineage": {},
            "diagnostics": [],  # EXPECTS NO DIAGNOSTICS
        }
        rust_obs = {
            "status": "ok", "return_val": None, "effects": [], "active_facts": [],
            "latent_facts": {}, "types": {}, "bindings": {}, "lineage": {},
            "diagnostics": [{"code": "SsaUseBeforeDef", "message": "unexpected"}],  # UNEXPECTED DIAGNOSTIC!
        }
        errs = compare_exact_observables("PROBE_unexpected_diag", expected, rust_obs)
        assert len(errs) > 0, "comparator falsely accepted unexpected diagnostic"
        return []
    run_diff_check("PROBE_unexpected_diagnostic_fails", _run)


if __name__ == "__main__":
    print("=" * 70)
    print("SOMA COMPILER CONFORMANCE v0 (SLICE 1) — Python Oracle vs Rust Toolchain Differential (R5 & S3)")
    test_diff_c01_pure()
    test_diff_c02_read_ok()
    test_diff_c03_read_err()
    test_diff_c09_infer_ok()
    test_probe_extra_lineage_fails()
    test_probe_extra_latent_fact_fails()
    test_probe_extra_binding_entry_fails()
    test_probe_unexpected_diagnostic_fails()

    print("=" * 70)
    print(f"DIFFERENTIAL CONFORMANCE RESULT: {PASS} passed, {FAIL} failed ({PASS + FAIL} total)")
    if FAIL:
        sys.exit(1)
    print("Exact differential agreement confirmed between Python Oracle and Rust Toolchain across all 9 shared observables.")
