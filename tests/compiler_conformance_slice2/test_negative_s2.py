"""test_negative_s2.py — Negative Verifier Tests S2V01–S2V14 for Compiler Conformance v0 (Slice 2).

Validates that the Rust High-Level Verifier and VM Verifier correctly reject invalid programs
with structured DiagnosticCode.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "compiler_conformance"))

from protocol import invoke_rust_conformance

PASS, FAIL = 0, 0


def expect_verifier_error(name: str, program: dict, expected_code: str) -> None:
    global PASS, FAIL
    print(f"\n--- NEGATIVE VERIFIER TEST (Slice 2): {name}")
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


def make_type_string(): return {"kind": "String"}
def make_type_bool(): return {"kind": "Bool"}
def make_type_i64(): return {"kind": "I64"}
def make_type_attestation(p, s): return {"kind": "Attestation", "payload": {"predicate": p, "subject_ty": s}}
def make_type_result(ok, err): return {"kind": "Result", "payload": {"ok": ok, "err": err}}
def make_type_act_outcome(s, f): return {"kind": "ActOutcome", "payload": {"success": s, "failure": f}}


def s2v01_verify_subject_type_mismatch():
    prog = {
        "name": "S2V01_subject_type_mismatch",
        "entry_func": "main", "inputs": {},
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Read": "workspace"}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "I64", "payload": 42}, "ty": make_type_i64()}},  # I64 SUBJECT
                            {"Verify": {"dest": 2, "verifier_id": "auditor_v1", "subject": 1, "output_predicate": "PassesAudit", "subject_type": make_type_string(), "verifier_effects": [{"Read": "workspace"}]}}  # EXPECTS STRING
                        ],
                        "terminator": {"Return": None}
                    }
                }
            }]
        }
    }
    expect_verifier_error("S2V01_verify_subject_type_mismatch", prog, "TypeMismatch")


def s2v02_verify_caller_authority_missing_verifier_effect():
    # Rule #5: Caller authority must cover verifier effect envelope
    prog = {
        "name": "S2V02_verify_authority_missing",
        "entry_func": "main", "inputs": {},
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Read": "workspace"}]}, "entry": 0,  # LACKS act[sandbox]
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "sub"}, "ty": make_type_string()}},
                            {"Verify": {"dest": 2, "verifier_id": "heavy_v", "subject": 1, "output_predicate": "PassesAudit", "subject_type": make_type_string(), "verifier_effects": [{"Read": "workspace"}, {"Act": "sandbox"}]}}
                        ],
                        "terminator": {"Return": None}
                    }
                }
            }]
        }
    }
    expect_verifier_error("S2V02_verify_caller_authority_missing_verifier_effect", prog, "EffectUndeclared")


def s2v03_act_caller_capability_missing():
    # Caller lacks act[workspace]
    prog = {
        "name": "S2V03_act_capability_missing",
        "entry_func": "main", "inputs": {},
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Read": "workspace"}]}, "entry": 0,  # LACKS act[workspace]
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "sub"}, "ty": make_type_string()}},
                            {"Act": {
                                "dest": 2, "op_id": "op_write", "target_domain": "workspace",
                                "success_type": make_type_string(), "failure_type": make_type_string(),
                                "args": [1], "evidence": [], "gate_effects": [],
                                "latent": {"on_success": [], "on_failure": [], "on_partial": []}
                            }}
                        ],
                        "terminator": {"Return": None}
                    }
                }
            }]
        }
    }
    expect_verifier_error("S2V03_act_caller_capability_missing", prog, "EffectUndeclared")


def s2v04_region_local_leak_after_match_act_outcome():
    # Definition in success_body used in merge without block argument
    prog = {
        "name": "S2V04_act_region_leak",
        "entry_func": "main", "inputs": {},
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [], "return_type": make_type_i64(),
                "declared_effects": {"effects": [{"Act": "workspace"}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "sub"}, "ty": make_type_string()}},
                            {"Act": {
                                "dest": 2, "op_id": "op_write", "target_domain": "workspace",
                                "success_type": make_type_string(), "failure_type": make_type_string(),
                                "args": [1], "evidence": [], "gate_effects": [],
                                "latent": {"on_success": [], "on_failure": [], "on_partial": []}
                            }}
                        ],
                        "terminator": {
                            "MatchActOutcome": {
                                "outcome_val": 2,
                                "success_arg": 3, "success_body": {
                                    "instructions": [{"Pure": {"dest": 7, "val": {"kind": "I64", "payload": 100}, "ty": make_type_i64()}}],
                                    "terminator": {"Br": {"target": 1, "args": []}}  # DID NOT TRANSPORT 7!
                                },
                                "failure_arg": 4, "failure_body": {"instructions": [], "terminator": {"Br": {"target": 1, "args": []}}},
                                "partial_arg": 5, "partial_body": {"instructions": [], "terminator": {"Br": {"target": 1, "args": []}}},
                                "unknown_arg": 6, "unknown_body": {"instructions": [], "terminator": {"Br": {"target": 1, "args": []}}}
                            }
                        }
                    },
                    "1": {
                        "id": 1, "name": "merge", "params": [], "instructions": [],
                        "terminator": {"Return": 7}  # ILLEGAL USE OF 7!
                    }
                }
            }]
        }
    }
    expect_verifier_error("S2V04_region_local_leak_after_match_act_outcome", prog, "SsaUseBeforeDef")


def s2v05_cross_region_act_outcome_use():
    # Value defined in failure_body used in success_body
    prog = {
        "name": "S2V05_cross_act_region",
        "entry_func": "main", "inputs": {},
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [], "return_type": make_type_i64(),
                "declared_effects": {"effects": [{"Act": "workspace"}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "sub"}, "ty": make_type_string()}},
                            {"Act": {
                                "dest": 2, "op_id": "op_write", "target_domain": "workspace",
                                "success_type": make_type_string(), "failure_type": make_type_string(),
                                "args": [1], "evidence": [], "gate_effects": [],
                                "latent": {"on_success": [], "on_failure": [], "on_partial": []}
                            }}
                        ],
                        "terminator": {
                            "MatchActOutcome": {
                                "outcome_val": 2,
                                "success_arg": 3, "success_body": {
                                    "instructions": [],
                                    "terminator": {"Return": 8}  # USES 8 DEFINED ONLY IN FAILURE BODY!
                                },
                                "failure_arg": 4, "failure_body": {
                                    "instructions": [{"Pure": {"dest": 8, "val": {"kind": "I64", "payload": 88}, "ty": make_type_i64()}}],
                                    "terminator": {"Return": 8}
                                },
                                "partial_arg": 5, "partial_body": {"instructions": [], "terminator": {"Return": None}},
                                "unknown_arg": 6, "unknown_body": {"instructions": [], "terminator": {"Return": None}}
                            }
                        }
                    }
                }
            }]
        }
    }
    expect_verifier_error("S2V05_cross_region_act_outcome_use", prog, "SsaUseBeforeDef")


if __name__ == "__main__":
    print("=" * 70)
    print("SOMA COMPILER CONFORMANCE v0 (SLICE 2) — Negative Verifier Tests (S2V01–S2V05)")
    s2v01_verify_subject_type_mismatch()
    s2v02_verify_caller_authority_missing_verifier_effect()
    s2v03_act_caller_capability_missing()
    s2v04_region_local_leak_after_match_act_outcome()
    s2v05_cross_region_act_outcome_use()

    print("=" * 70)
    print(f"SLICE 2 NEGATIVE VERIFIER RESULT: {PASS} passed, {FAIL} failed ({PASS + FAIL} total)")
    if FAIL:
        sys.exit(1)
    print("All Slice 2 Negative Verifier Tests correctly rejected by Rust Verifier.")
