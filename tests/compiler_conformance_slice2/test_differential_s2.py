"""test_differential_s2.py — Exact Shared Observable Comparator for SOMA-IR Slice 2.

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
10. Mutation trace (exact list of writes)
11. Final world state (exact storage key-value map)
12. Gate resolutions (exact list of operation resolution outcomes)
13. Gate check trace (exact list of dynamic gate checks executed with authority source)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "compiler_conformance"))

from protocol import invoke_rust_conformance

PASS, FAIL = 0, 0


def compare_exact_observables(name: str, expected_oracle: dict, rust_obs: dict) -> list[str]:
    """Exact observable comparator across all shared observables with strict equality."""
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

    # 5. Latent facts
    expected_latent = expected_oracle.get("latent_facts", {})
    rust_latent = rust_obs.get("latent_facts", {})
    if expected_latent != rust_latent:
        errors.append(f"Latent facts exact mismatch: expected {expected_latent}, got {rust_latent}")

    # 6. Types
    expected_types = expected_oracle.get("types", {})
    rust_types = rust_obs.get("types", {})
    if expected_types != rust_types:
        errors.append(f"Types exact mismatch: expected {expected_types}, got {rust_types}")

    # 7. Bindings
    expected_bindings = expected_oracle.get("bindings", {})
    rust_bindings = rust_obs.get("bindings", {})
    if expected_bindings != rust_bindings:
        errors.append(f"Bindings exact mismatch: expected {expected_bindings}, got {rust_bindings}")

    # 8. Lineage
    expected_lineage = expected_oracle.get("lineage", {})
    rust_lineage = rust_obs.get("lineage", {})
    if expected_lineage != rust_lineage:
        errors.append(f"Lineage exact mismatch: expected {expected_lineage}, got {rust_lineage}")

    # 9. Diagnostics
    expected_diags = expected_oracle.get("diagnostics", [])
    rust_diags = rust_obs.get("diagnostics", [])
    if expected_diags != rust_diags:
        errors.append(f"Diagnostics exact mismatch: expected {expected_diags}, got {rust_diags}")

    # 10. Mutation trace
    expected_trace = expected_oracle.get("mutation_trace", [])
    rust_trace = rust_obs.get("mutation_trace", [])
    if expected_trace != rust_trace:
        errors.append(f"Mutation trace exact mismatch: expected {expected_trace}, got {rust_trace}")

    # 11. Final world state
    expected_world = expected_oracle.get("final_world", {})
    rust_world = rust_obs.get("final_world", {})
    if expected_world != rust_world:
        errors.append(f"Final world exact mismatch: expected {expected_world}, got {rust_world}")

    # 12. Gate resolutions
    expected_res = expected_oracle.get("gate_resolutions", [])
    rust_res = rust_obs.get("gate_resolutions", [])
    if expected_res != rust_res:
        errors.append(f"Gate resolutions exact mismatch: expected {expected_res}, got {rust_res}")

    # 13. Gate check trace
    expected_gate_trace = expected_oracle.get("gate_trace", [])
    rust_gate_trace = rust_obs.get("gate_trace", [])
    if expected_gate_trace != rust_gate_trace:
        errors.append(f"Gate trace exact mismatch: expected {expected_gate_trace}, got {rust_gate_trace}")

    return errors


def run_diff_check(name: str, fn) -> None:
    global PASS, FAIL
    print(f"\n--- CONFORMANCE DIFFERENTIAL (Slice 2): {name}")
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
# Differential Conformance Suites (Slice 2)
# =====================================================================

def test_diff_verify_success():
    def _run():
        expected = {
            "status": "ok",
            "return_val": {"kind": "String", "payload": "sub_A"},
            "effects": ["read[workspace]"],
            "active_facts": {("IsOk", ("sym(v2)",))},
            "latent_facts": {},
            "types": {
                "v1": "string",
                "v2": "Result<Attestation<PassesAudit, string>, string>",
                "v3": "Attestation<PassesAudit, string>",
            },
            "bindings": {
                "v1": {"kind": "String", "payload": "sub_A"},
                "v2": {"kind": "Ok", "payload": {
                    "kind": "Attestation",
                    "payload": {
                        "predicate": "PassesAudit",
                        "subject": {"kind": "String", "payload": "sub_A"},
                        "issuer": "v_audit",
                        "verifier_build": "1.0.0",
                        "token": "tok_valid"
                    }
                }},
                "v3": {
                    "kind": "Attestation",
                    "payload": {
                        "predicate": "PassesAudit",
                        "subject": {"kind": "String", "payload": "sub_A"},
                        "issuer": "v_audit",
                        "verifier_build": "1.0.0",
                        "token": "tok_valid"
                    }
                }
            },
            "lineage": {},
            "diagnostics": [],
            "mutation_trace": [],
            "final_world": {},
            "gate_resolutions": [],
            "gate_trace": [],
        }
        prog = {
            "name": "Diff_Verify_Success", "entry_func": "main", "inputs": {},
            "registry": {
                "caller_authority": {"effects": [{"Read": "workspace"}]},
                "runtime_authority": {"effects": []},
                "verifiers": {
                    "v_audit": {
                        "verifier_id": "v_audit", "version": "1.0.0",
                        "effect_envelope": {"effects": [{"Read": "workspace"}]},
                        "output_predicate": "PassesAudit", "subject_type": {"kind": "String"}
                    }
                },
                "operations": {}, "trust_policy": {"trusted_issuers": {}}
            },
            "module": {
                "name": "m", "functions": [{
                    "name": "main", "params": [], "return_type": {"kind": "String"},
                    "declared_effects": {"effects": [{"Read": "workspace"}]}, "entry": 0,
                    "blocks": {
                        "0": {
                            "id": 0, "params": [],
                            "instructions": [
                                {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "sub_A"}, "ty": {"kind": "String"}}},
                                {"Verify": {"dest": 2, "verifier_id": "v_audit", "subject": 1}}
                            ],
                            "terminator": {
                                "MatchResult": {
                                    "result_val": 2,
                                    "ok_arg": 3, "ok_body": {"instructions": [], "terminator": {"Return": 1}},
                                    "err_arg": 4, "err_body": {"instructions": [], "terminator": {"Return": 4}}
                                }
                            }
                        }
                    }
                }]
            }
        }
        rust_obs = invoke_rust_conformance(prog)
        return compare_exact_observables("Diff_Verify_Success", expected, rust_obs)
    run_diff_check("Diff_Verify_Success", _run)


def test_diff_gated_act_success():
    def _run():
        expected = {
            "status": "ok",
            "return_val": {"kind": "String", "payload": "act_success_ok"},
            "effects": ["read[workspace]", "read[trust_store]", "act[workspace]"],
            "active_facts": {
                ("IsSuccess", ("sym(v3)",)),
                ("SuccessFact", ("sym(v4)",)),
            },
            "latent_facts": {},
            "types": {
                "v1": "string",
                "v2": "Result<Attestation<PassesAudit, string>, string>",
                "v3": "ActOutcome<string, string>",
                "v4": "string",
            },
            "bindings": {
                "v1": {"kind": "String", "payload": "sub_A"},
                "v2": {"kind": "Ok", "payload": {
                    "kind": "Attestation",
                    "payload": {
                        "predicate": "PassesAudit",
                        "subject": {"kind": "String", "payload": "sub_A"},
                        "issuer": "v_audit",
                        "verifier_build": "1.0.0",
                        "token": "tok_valid"
                    }
                }},
                "v3": {"kind": "ActSuccess", "payload": {"kind": "String", "payload": "act_success_ok"}},
                "v4": {"kind": "String", "payload": "act_success_ok"}
            },
            "lineage": {},
            "diagnostics": [],
            "mutation_trace": [
                ["workspace/doc1", {"kind": "String", "payload": "updated_data"}, 1]
            ],
            "final_world": {
                "workspace/doc1": [{"kind": "String", "payload": "updated_data"}, 1]
            },
            "gate_resolutions": [
                {"op_id": "op_write", "resolution": "Deferred"}
            ],
            "gate_trace": [
                {
                    "check_kind": "CheckTrustPolicy",
                    "authority_source": "TrustedRuntime",
                    "effects": ["read[trust_store]"],
                    "result": "Pass"
                }
            ],
        }
        prog = {
            "name": "Diff_Gated_Act_Success", "entry_func": "main", "inputs": {},
            "registry": {
                "caller_authority": {"effects": [{"Read": "workspace"}, {"Act": "workspace"}]},
                "runtime_authority": {"effects": [{"Read": "trust_store"}]},
                "verifiers": {
                    "v_audit": {
                        "verifier_id": "v_audit", "version": "1.0.0",
                        "effect_envelope": {"effects": [{"Read": "workspace"}]},
                        "output_predicate": "PassesAudit", "subject_type": {"kind": "String"}
                    }
                },
                "operations": {
                    "op_write": {
                        "op_id": "op_write", "target_domain": "workspace",
                        "declared_envelope": {"effects": [{"Act": "workspace"}, {"Read": "workspace"}, {"Read": "trust_store"}]},
                        "declared_footprint": {"Exact": ["workspace/doc1"]},
                        "atomicity": "Atomic",
                        "requirements": [{"RequiresAttestation": {"predicate": "PassesAudit", "subject_arg_idx": 0}}]
                    }
                },
                "trust_policy": {"trusted_issuers": {"PassesAudit": ["v_audit"]}}
            },
            "module": {
                "name": "m", "functions": [{
                    "name": "main", "params": [], "return_type": {"kind": "String"},
                    "declared_effects": {"effects": [{"Read": "workspace"}, {"Read": "trust_store"}, {"Act": "workspace"}]},
                    "entry": 0,
                    "blocks": {
                        "0": {
                            "id": 0, "params": [],
                            "instructions": [
                                {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "sub_A"}, "ty": {"kind": "String"}}},
                                {"Verify": {"dest": 2, "verifier_id": "v_audit", "subject": 1}},
                                {"Act": {
                                    "dest": 3, "op_id": "op_write",
                                    "success_type": {"kind": "String"}, "failure_type": {"kind": "String"},
                                    "args": [1], "evidence": [2],
                                    "latent": {
                                        "on_success": [{"predicate": "SuccessFact", "args": [{"Symbol": "$value"}]}],
                                        "on_failure": [], "on_partial": []
                                    }
                                }}
                            ],
                            "terminator": {
                                "MatchActOutcome": {
                                    "outcome_val": 3,
                                    "success_arg": 4, "success_body": {"instructions": [], "terminator": {"Return": 4}},
                                    "failure_arg": 5, "failure_body": {"instructions": [], "terminator": {"Return": 5}},
                                    "partial_arg": 6, "partial_body": {"instructions": [], "terminator": {"Return": 1}},
                                    "unknown_arg": 7, "unknown_body": {"instructions": [], "terminator": {"Return": 1}}
                                }
                            }
                        }
                    }
                }]
            }
        }
        rust_obs = invoke_rust_conformance(prog)
        return compare_exact_observables("Diff_Gated_Act_Success", expected, rust_obs)
    run_diff_check("Diff_Gated_Act_Success", _run)


# =====================================================================
# Negative Comparator Probes (Slice 2)
# =====================================================================

def test_probe_extra_lineage_fails():
    def _run():
        expected = {
            "status": "ok", "return_val": None, "effects": [], "active_facts": set(),
            "latent_facts": {}, "types": {}, "bindings": {}, "diagnostics": [],
            "lineage": {"v1": ["verify(auditor)"]}, "mutation_trace": [], "final_world": {},
            "gate_resolutions": [], "gate_trace": []
        }
        rust_obs = {
            "status": "ok", "return_val": None, "effects": [], "active_facts": [],
            "latent_facts": {}, "types": {}, "bindings": {}, "diagnostics": [],
            "lineage": {"v1": ["verify(auditor)"], "phantom_unauthorized": ["act(evil)"]},
            "mutation_trace": [], "final_world": {}, "gate_resolutions": [], "gate_trace": []
        }
        errs = compare_exact_observables("PROBE_extra_lineage", expected, rust_obs)
        assert len(errs) > 0, "comparator falsely accepted extra spurious lineage"
        return []
    run_diff_check("PROBE_extra_lineage_fails", _run)


def test_probe_extra_target_mutation_fails():
    def _run():
        expected = {
            "status": "ok", "return_val": None, "effects": [], "active_facts": set(),
            "latent_facts": {}, "types": {}, "bindings": {}, "lineage": {}, "diagnostics": [],
            "mutation_trace": [], "final_world": {}, "gate_resolutions": [], "gate_trace": []
        }
        rust_obs = {
            "status": "ok", "return_val": None, "effects": [], "active_facts": [],
            "latent_facts": {}, "types": {}, "bindings": {}, "lineage": {}, "diagnostics": [],
            "mutation_trace": [["workspace/doc1", {"kind": "String", "payload": "unauthorized"}, 1]],
            "final_world": {}, "gate_resolutions": [], "gate_trace": []
        }
        errs = compare_exact_observables("PROBE_extra_mutation", expected, rust_obs)
        assert len(errs) > 0, "comparator falsely accepted unauthorized target mutation"
        return []
    run_diff_check("PROBE_extra_target_mutation_fails", _run)


def test_probe_wrong_final_world_fails():
    def _run():
        expected = {
            "status": "ok", "return_val": None, "effects": [], "active_facts": set(),
            "latent_facts": {}, "types": {}, "bindings": {}, "lineage": {}, "diagnostics": [],
            "mutation_trace": [], "final_world": {"workspace/doc1": [{"kind": "String", "payload": "correct"}, 1]},
            "gate_resolutions": [], "gate_trace": []
        }
        rust_obs = {
            "status": "ok", "return_val": None, "effects": [], "active_facts": [],
            "latent_facts": {}, "types": {}, "bindings": {}, "lineage": {}, "diagnostics": [],
            "mutation_trace": [], "final_world": {"workspace/doc1": [{"kind": "String", "payload": "corrupted"}, 1]},
            "gate_resolutions": [], "gate_trace": []
        }
        errs = compare_exact_observables("PROBE_wrong_world", expected, rust_obs)
        assert len(errs) > 0, "comparator falsely accepted corrupted final world state"
        return []
    run_diff_check("PROBE_wrong_final_world_fails", _run)


def test_probe_omitted_gate_effect_fails():
    def _run():
        expected = {
            "status": "ok", "return_val": None, "effects": ["read[trust_store]", "act[workspace]"],
            "active_facts": set(), "latent_facts": {}, "types": {}, "bindings": {}, "lineage": {},
            "diagnostics": [], "mutation_trace": [], "final_world": {},
            "gate_resolutions": [], "gate_trace": []
        }
        rust_obs = {
            "status": "ok", "return_val": None, "effects": ["act[workspace]"],
            "active_facts": [], "latent_facts": {}, "types": {}, "bindings": {}, "lineage": {},
            "diagnostics": [], "mutation_trace": [], "final_world": {},
            "gate_resolutions": [], "gate_trace": []
        }
        errs = compare_exact_observables("PROBE_omitted_gate_effect", expected, rust_obs)
        assert len(errs) > 0, "comparator falsely accepted omitted gate effect"
        return []
    run_diff_check("PROBE_omitted_gate_effect_fails", _run)


def test_probe_stale_current_fact_fails():
    def _run():
        expected = {
            "status": "ok", "return_val": None, "effects": [],
            "active_facts": {("Historical", ("lit(provenance)",))},
            "latent_facts": {}, "types": {}, "bindings": {}, "lineage": {},
            "diagnostics": [], "mutation_trace": [], "final_world": {},
            "gate_resolutions": [], "gate_trace": []
        }
        rust_obs = {
            "status": "ok", "return_val": None, "effects": [],
            "active_facts": [
                {"predicate": "Historical", "args": [{"Literal": "provenance"}]},
                {"predicate": "CurrentState", "args": [{"Literal": "workspace/doc1"}, {"Literal": "stale"}]}
            ],
            "latent_facts": {}, "types": {}, "bindings": {}, "lineage": {},
            "diagnostics": [], "mutation_trace": [], "final_world": {},
            "gate_resolutions": [], "gate_trace": []
        }
        errs = compare_exact_observables("PROBE_stale_current_fact", expected, rust_obs)
        assert len(errs) > 0, "comparator falsely accepted stale CurrentState fact after mutation"
        return []
    run_diff_check("PROBE_stale_current_fact_fails", _run)


def test_probe_wrong_gate_resolution_fails():
    def _run():
        expected = {
            "status": "ok", "return_val": None, "effects": [], "active_facts": set(),
            "latent_facts": {}, "types": {}, "bindings": {}, "lineage": {}, "diagnostics": [],
            "mutation_trace": [], "final_world": {},
            "gate_resolutions": [{"op_id": "op_write", "resolution": "Deferred"}],
            "gate_trace": []
        }
        rust_obs = {
            "status": "ok", "return_val": None, "effects": [], "active_facts": [],
            "latent_facts": {}, "types": {}, "bindings": {}, "lineage": {}, "diagnostics": [],
            "mutation_trace": [], "final_world": {},
            "gate_resolutions": [{"op_id": "op_write", "resolution": "Proved"}],  # WRONG!
            "gate_trace": []
        }
        errs = compare_exact_observables("PROBE_wrong_gate_resolution", expected, rust_obs)
        assert len(errs) > 0, "comparator falsely accepted wrong gate resolution outcome"
        return []
    run_diff_check("PROBE_wrong_gate_resolution_fails", _run)


def test_probe_wrong_authority_source_fails():
    def _run():
        expected = {
            "status": "ok", "return_val": None, "effects": [], "active_facts": set(),
            "latent_facts": {}, "types": {}, "bindings": {}, "lineage": {}, "diagnostics": [],
            "mutation_trace": [], "final_world": {}, "gate_resolutions": [],
            "gate_trace": [{
                "check_kind": "CheckTrustPolicy",
                "authority_source": "TrustedRuntime",
                "effects": ["read[trust_store]"],
                "result": "Pass"
            }]
        }
        rust_obs = {
            "status": "ok", "return_val": None, "effects": [], "active_facts": [],
            "latent_facts": {}, "types": {}, "bindings": {}, "lineage": {}, "diagnostics": [],
            "mutation_trace": [], "final_world": {}, "gate_resolutions": [],
            "gate_trace": [{
                "check_kind": "CheckTrustPolicy",
                "authority_source": "Caller",  # WRONG AUTHORITY SOURCE!
                "effects": ["read[trust_store]"],
                "result": "Pass"
            }]
        }
        errs = compare_exact_observables("PROBE_wrong_authority_source", expected, rust_obs)
        assert len(errs) > 0, "comparator falsely accepted forged/wrong authority source in gate trace"
        return []
    run_diff_check("PROBE_wrong_authority_source_fails", _run)


if __name__ == "__main__":
    print("=" * 70)
    print("SOMA COMPILER CONFORMANCE v0 (SLICE 2) — Python Oracle vs Rust Differential")
    test_diff_verify_success()
    test_diff_gated_act_success()
    test_probe_extra_lineage_fails()
    test_probe_extra_target_mutation_fails()
    test_probe_wrong_final_world_fails()
    test_probe_omitted_gate_effect_fails()
    test_probe_stale_current_fact_fails()
    test_probe_wrong_gate_resolution_fails()
    test_probe_wrong_authority_source_fails()

    print("=" * 70)
    print(f"SLICE 2 DIFFERENTIAL RESULT: {PASS} passed, {FAIL} failed ({PASS + FAIL} total)")
    if FAIL:
        sys.exit(1)
    print("Exact differential agreement confirmed between Python Oracle and Rust Toolchain for Slice 2.")
