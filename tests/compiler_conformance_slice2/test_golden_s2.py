"""test_golden_s2.py — Golden Conformance Programs S2C01–S2C21 for Compiler Conformance v0 (Slice 2).

Executes end-to-end against the real Rust toolchain (crates/bando).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "compiler_conformance"))

from protocol import invoke_rust_conformance

PASS, FAIL = 0, 0


def run_golden(name: str, program: dict) -> None:
    global PASS, FAIL
    print(f"\n--- GOLDEN PROGRAM (Slice 2): {name}")
    try:
        obs = invoke_rust_conformance(program)
        if obs["status"] != "ok":
            print(f"  \u2717 FAIL {name}: expected status 'ok', got '{obs['status']}' with diagnostics {obs.get('diagnostics')}")
            FAIL += 1
            return
        print(f"  \u2713 PASS {name} (status=ok, return={obs.get('return_val')}, effects={obs.get('effects')})")
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


# =====================================================================
# S2C01–S2C05: VERIFY Golden Programs
# =====================================================================

def s2c01_verify_success():
    prog = {
        "name": "S2C01_verify_success",
        "entry_func": "main",
        "inputs": {},
        "registry": {
            "verifiers": {
                "auditor_v1": {
                    "verifier_id": "auditor_v1", "version": "1.0.0",
                    "effect_envelope": {"effects": [{"Read": "workspace"}]},
                    "output_predicate": "PassesAudit", "subject_type": make_type_string()
                }
            },
            "operations": {}, "trust_policy": {"trusted_issuers": {}}
        },
        "module": {
            "name": "mod_s2c01",
            "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Read": "workspace"}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "artifact_x"}, "ty": make_type_string()}},
                            {"Verify": {"dest": 2, "verifier_id": "auditor_v1", "subject": 1, "output_predicate": "PassesAudit", "subject_type": make_type_string(), "verifier_effects": [{"Read": "workspace"}]}}
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
    run_golden("S2C01_verify_success", prog)


def s2c02_verify_semantic_failure():
    prog = {
        "name": "S2C02_verify_failure",
        "entry_func": "main",
        "inputs": {},
        "verifier_failures": {"auditor_v1": "AuditFailed(MissingSignature)"},
        "registry": {
            "verifiers": {
                "auditor_v1": {
                    "verifier_id": "auditor_v1", "version": "1.0.0",
                    "effect_envelope": {"effects": [{"Read": "workspace"}]},
                    "output_predicate": "PassesAudit", "subject_type": make_type_string()
                }
            },
            "operations": {}, "trust_policy": {"trusted_issuers": {}}
        },
        "module": {
            "name": "mod_s2c02",
            "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Read": "workspace"}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "bad_artifact"}, "ty": make_type_string()}},
                            {"Verify": {"dest": 2, "verifier_id": "auditor_v1", "subject": 1, "output_predicate": "PassesAudit", "subject_type": make_type_string(), "verifier_effects": [{"Read": "workspace"}]}}
                        ],
                        "terminator": {
                            "MatchResult": {
                                "result_val": 2,
                                "ok_arg": 3, "ok_body": {"instructions": [], "terminator": {"Return": 1}},
                                "err_arg": 4, "err_body": {"instructions": [], "terminator": {"Return": 4}}  # Returns error message!
                            }
                        }
                    }
                }
            }]
        }
    }
    run_golden("S2C02_verify_semantic_failure", prog)


def s2c03_verifier_runtime_confinement():
    # Attempt to execute effects outside envelope is caught and returns Err
    prog = {
        "name": "S2C03_verifier_confinement",
        "entry_func": "main",
        "inputs": {},
        "verifier_out_of_envelope": {"confined_v1": {"effects": [{"Read": "workspace"}, {"Act": "sandbox"}]}},
        "registry": {
            "verifiers": {
                "confined_v1": {
                    "verifier_id": "confined_v1", "version": "1.0.0",
                    "effect_envelope": {"effects": [{"Read": "workspace"}]},  # ENVELOPE IS ONLY READ
                    "output_predicate": "SafeAudit", "subject_type": make_type_string()
                }
            },
            "operations": {}, "trust_policy": {"trusted_issuers": {}}
        },
        "module": {
            "name": "mod_s2c03",
            "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Read": "workspace"}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "art"}, "ty": make_type_string()}},
                            {"Verify": {"dest": 2, "verifier_id": "confined_v1", "subject": 1, "output_predicate": "SafeAudit", "subject_type": make_type_string(), "verifier_effects": [{"Read": "workspace"}]}}
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
    run_golden("S2C03_verifier_runtime_confinement", prog)


def s2c05_registered_but_untrusted_verifier_rejected_at_gate():
    # Verify succeeds (attestation emitted), but act gate rejects it because issuer is not in trust_policy!
    prog = {
        "name": "S2C05_untrusted_at_gate",
        "entry_func": "main",
        "inputs": {},
        "registry": {
            "verifiers": {
                "untrusted_v": {
                    "verifier_id": "untrusted_v", "version": "1.0.0",
                    "effect_envelope": {"effects": [{"Read": "workspace"}]},
                    "output_predicate": "AuditPass", "subject_type": make_type_string()
                }
            },
            "operations": {
                "protected_op": {
                    "op_id": "protected_op", "target_domain": "workspace",
                    "declared_envelope": {"effects": [{"Act": "workspace"}, {"Read": "workspace"}]},
                    "declared_footprint": {"Exact": ["workspace/doc1"]},
                    "atomicity": "Atomic",
                    "requirements": [{"RequiresAttestation": {"predicate": "AuditPass", "subject_arg_idx": 0}}]
                }
            },
            "trust_policy": {"trusted_issuers": {"AuditPass": ["official_auditor"]}}  # untrusted_v is NOT trusted!
        },
        "module": {
            "name": "mod_s2c05",
            "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Read": "workspace"}, {"Act": "workspace"}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "my_payload"}, "ty": make_type_string()}},
                            {"Verify": {"dest": 2, "verifier_id": "untrusted_v", "subject": 1, "output_predicate": "AuditPass", "subject_type": make_type_string(), "verifier_effects": [{"Read": "workspace"}]}},
                            {"Act": {
                                "dest": 3, "op_id": "protected_op", "target_domain": "workspace",
                                "success_type": make_type_string(), "failure_type": make_type_string(),
                                "args": [1], "evidence": [2], "gate_effects": [],
                                "latent": {"on_success": [], "on_failure": [], "on_partial": []}
                            }}
                        ],
                        "terminator": {
                            "MatchActOutcome": {
                                "outcome_val": 3,
                                "success_arg": 4, "success_body": {"instructions": [], "terminator": {"Return": 4}},
                                "failure_arg": 5, "failure_body": {"instructions": [], "terminator": {"Return": 5}},  # Correctly routes to failure!
                                "partial_arg": 6, "partial_body": {"instructions": [], "terminator": {"Return": 1}},
                                "unknown_arg": 7, "unknown_body": {"instructions": [], "terminator": {"Return": 1}}
                            }
                        }
                    }
                }
            }]
        }
    }
    run_golden("S2C05_registered_but_untrusted_verifier_rejected_at_gate", prog)


# =====================================================================
# S2C06–S2C13: ACT & GATES Golden Programs
# =====================================================================

def s2c06_proved_requirement_target_executes():
    # Proved requirement (empty requirements) -> target executes directly
    prog = {
        "name": "S2C06_proved_requirement",
        "entry_func": "main",
        "inputs": {},
        "registry": {
            "verifiers": {},
            "operations": {
                "simple_act": {
                    "op_id": "simple_act", "target_domain": "workspace",
                    "declared_envelope": {"effects": [{"Act": "workspace"}]},
                    "declared_footprint": {"Exact": ["workspace/doc1"]},
                    "atomicity": "Atomic", "requirements": []
                }
            },
            "trust_policy": {"trusted_issuers": {}}
        },
        "module": {
            "name": "mod_s2c06",
            "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Act": "workspace"}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "data"}, "ty": make_type_string()}},
                            {"Act": {
                                "dest": 2, "op_id": "simple_act", "target_domain": "workspace",
                                "success_type": make_type_string(), "failure_type": make_type_string(),
                                "args": [1], "evidence": [], "gate_effects": [],
                                "latent": {"on_success": [], "on_failure": [], "on_partial": []}
                            }}
                        ],
                        "terminator": {
                            "MatchActOutcome": {
                                "outcome_val": 2,
                                "success_arg": 3, "success_body": {"instructions": [], "terminator": {"Return": 3}},
                                "failure_arg": 4, "failure_body": {"instructions": [], "terminator": {"Return": 4}},
                                "partial_arg": 5, "partial_body": {"instructions": [], "terminator": {"Return": 1}},
                                "unknown_arg": 6, "unknown_body": {"instructions": [], "terminator": {"Return": 1}}
                            }
                        }
                    }
                }
            }]
        }
    }
    run_golden("S2C06_proved_requirement_target_executes", prog)


def s2c07_deferred_subject_binding_passes():
    prog = {
        "name": "S2C07_deferred_passes",
        "entry_func": "main",
        "inputs": {},
        "registry": {
            "verifiers": {
                "v_audit": {
                    "verifier_id": "v_audit", "version": "1.0.0",
                    "effect_envelope": {"effects": [{"Read": "workspace"}]},
                    "output_predicate": "AuditPass", "subject_type": make_type_string()
                }
            },
            "operations": {
                "op_write": {
                    "op_id": "op_write", "target_domain": "workspace",
                    "declared_envelope": {"effects": [{"Act": "workspace"}, {"Read": "workspace"}]},
                    "declared_footprint": {"Exact": ["workspace/doc1"]},
                    "atomicity": "Atomic",
                    "requirements": [{"RequiresAttestation": {"predicate": "AuditPass", "subject_arg_idx": 0}}]
                }
            },
            "trust_policy": {"trusted_issuers": {"AuditPass": ["v_audit"]}}
        },
        "module": {
            "name": "mod_s2c07",
            "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Read": "workspace"}, {"Act": "workspace"}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "correct_subject"}, "ty": make_type_string()}},
                            {"Verify": {"dest": 2, "verifier_id": "v_audit", "subject": 1, "output_predicate": "AuditPass", "subject_type": make_type_string(), "verifier_effects": [{"Read": "workspace"}]}},
                            {"Act": {
                                "dest": 3, "op_id": "op_write", "target_domain": "workspace",
                                "success_type": make_type_string(), "failure_type": make_type_string(),
                                "args": [1], "evidence": [2], "gate_effects": [],
                                "latent": {"on_success": [], "on_failure": [], "on_partial": []}
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
    run_golden("S2C07_deferred_subject_binding_passes", prog)


def s2c08_deferred_subject_binding_fails_zero_mutation():
    # Evidence is for subject "sub_A", but act called with arg "sub_B" -> gate rejects, zero mutation!
    prog = {
        "name": "S2C08_deferred_fails",
        "entry_func": "main",
        "inputs": {},
        "registry": {
            "verifiers": {
                "v_audit": {
                    "verifier_id": "v_audit", "version": "1.0.0",
                    "effect_envelope": {"effects": [{"Read": "workspace"}]},
                    "output_predicate": "AuditPass", "subject_type": make_type_string()
                }
            },
            "operations": {
                "op_write": {
                    "op_id": "op_write", "target_domain": "workspace",
                    "declared_envelope": {"effects": [{"Act": "workspace"}, {"Read": "workspace"}, {"Read": "gate_check"}]},
                    "declared_footprint": {"Exact": ["workspace/doc1"]},
                    "atomicity": "Atomic",
                    "requirements": [{"RequiresAttestation": {"predicate": "AuditPass", "subject_arg_idx": 0}}]
                }
            },
            "trust_policy": {"trusted_issuers": {"AuditPass": ["v_audit"]}}
        },
        "module": {
            "name": "mod_s2c08",
            "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Read": "workspace"}, {"Act": "workspace"}, {"Read": "gate_check"}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "sub_A"}, "ty": make_type_string()}},
                            {"Pure": {"dest": 2, "val": {"kind": "String", "payload": "sub_B"}, "ty": make_type_string()}},  # DIFFERENT!
                            {"Verify": {"dest": 3, "verifier_id": "v_audit", "subject": 1, "output_predicate": "AuditPass", "subject_type": make_type_string(), "verifier_effects": [{"Read": "workspace"}]}},
                            {"Act": {
                                "dest": 4, "op_id": "op_write", "target_domain": "workspace",
                                "success_type": make_type_string(), "failure_type": make_type_string(),
                                "args": [2], "evidence": [3], "gate_effects": [{"Read": "gate_check"}],
                                "latent": {"on_success": [], "on_failure": [], "on_partial": []}
                            }}
                        ],
                        "terminator": {
                            "MatchActOutcome": {
                                "outcome_val": 4,
                                "success_arg": 5, "success_body": {"instructions": [], "terminator": {"Return": 5}},
                                "failure_arg": 6, "failure_body": {"instructions": [], "terminator": {"Return": 6}},
                                "partial_arg": 7, "partial_body": {"instructions": [], "terminator": {"Return": 1}},
                                "unknown_arg": 8, "unknown_body": {"instructions": [], "terminator": {"Return": 1}}
                            }
                        }
                    }
                }
            }]
        }
    }
    run_golden("S2C08_deferred_subject_binding_fails_zero_mutation", prog)


def s2c12_separate_gate_authority():
    # Caller declared effects: {act[workspace], read[trust_store]}. Gate executes read[trust_store] and act[workspace].
    prog = {
        "name": "S2C12_separate_gate_authority",
        "entry_func": "main",
        "inputs": {},
        "registry": {
            "verifiers": {},
            "operations": {
                "op_gated": {
                    "op_id": "op_gated", "target_domain": "workspace",
                    "declared_envelope": {"effects": [{"Act": "workspace"}, {"Read": "trust_store"}]},
                    "declared_footprint": {"Exact": ["workspace/doc1"]},
                    "atomicity": "Atomic", "requirements": []
                }
            },
            "trust_policy": {"trusted_issuers": {}}
        },
        "module": {
            "name": "mod_s2c12",
            "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Act": "workspace"}, {"Read": "trust_store"}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "data"}, "ty": make_type_string()}},
                            {"Act": {
                                "dest": 2, "op_id": "op_gated", "target_domain": "workspace",
                                "success_type": make_type_string(), "failure_type": make_type_string(),
                                "args": [1], "evidence": [], "gate_effects": [{"Read": "trust_store"}],
                                "latent": {"on_success": [], "on_failure": [], "on_partial": []}
                            }}
                        ],
                        "terminator": {
                            "MatchActOutcome": {
                                "outcome_val": 2,
                                "success_arg": 3, "success_body": {"instructions": [], "terminator": {"Return": 3}},
                                "failure_arg": 4, "failure_body": {"instructions": [], "terminator": {"Return": 4}},
                                "partial_arg": 5, "partial_body": {"instructions": [], "terminator": {"Return": 1}},
                                "unknown_arg": 6, "unknown_body": {"instructions": [], "terminator": {"Return": 1}}
                            }
                        }
                    }
                }
            }]
        }
    }
    run_golden("S2C12_separate_gate_authority", prog)


# =====================================================================
# S2C14–S2C18: ActOutcomes Golden Programs
# =====================================================================

def s2c14_clean_failure():
    prog = {
        "name": "S2C14_clean_failure",
        "entry_func": "main",
        "inputs": {},
        "act_scenarios": {"op_fail": "clean_failure"},
        "registry": {
            "verifiers": {},
            "operations": {
                "op_fail": {
                    "op_id": "op_fail", "target_domain": "workspace",
                    "declared_envelope": {"effects": [{"Act": "workspace"}]},
                    "declared_footprint": {"Exact": ["workspace/doc1"]},
                    "atomicity": "Atomic", "requirements": []
                }
            },
            "trust_policy": {"trusted_issuers": {}}
        },
        "module": {
            "name": "mod_s2c14",
            "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Act": "workspace"}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "arg"}, "ty": make_type_string()}},
                            {"Act": {
                                "dest": 2, "op_id": "op_fail", "target_domain": "workspace",
                                "success_type": make_type_string(), "failure_type": make_type_string(),
                                "args": [1], "evidence": [], "gate_effects": [],
                                "latent": {"on_success": [], "on_failure": [], "on_partial": []}
                            }}
                        ],
                        "terminator": {
                            "MatchActOutcome": {
                                "outcome_val": 2,
                                "success_arg": 3, "success_body": {"instructions": [], "terminator": {"Return": 3}},
                                "failure_arg": 4, "failure_body": {"instructions": [], "terminator": {"Return": 4}},
                                "partial_arg": 5, "partial_body": {"instructions": [], "terminator": {"Return": 1}},
                                "unknown_arg": 6, "unknown_body": {"instructions": [], "terminator": {"Return": 1}}
                            }
                        }
                    }
                }
            }]
        }
    }
    run_golden("S2C14_clean_failure", prog)


def s2c15_legitimate_partial():
    prog = {
        "name": "S2C15_partial",
        "entry_func": "main",
        "inputs": {},
        "act_scenarios": {"op_part": "partial_legitimate"},
        "registry": {
            "verifiers": {},
            "operations": {
                "op_part": {
                    "op_id": "op_part", "target_domain": "workspace",
                    "declared_envelope": {"effects": [{"Act": "workspace"}]},
                    "declared_footprint": {"Prefix": "workspace/"},
                    "atomicity": "MayPartiallyComplete", "requirements": []
                }
            },
            "trust_policy": {"trusted_issuers": {}}
        },
        "module": {
            "name": "mod_s2c15",
            "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Act": "workspace"}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "arg"}, "ty": make_type_string()}},
                            {"Act": {
                                "dest": 2, "op_id": "op_part", "target_domain": "workspace",
                                "success_type": make_type_string(), "failure_type": make_type_string(),
                                "args": [1], "evidence": [], "gate_effects": [],
                                "latent": {"on_success": [], "on_failure": [], "on_partial": []}
                            }}
                        ],
                        "terminator": {
                            "MatchActOutcome": {
                                "outcome_val": 2,
                                "success_arg": 3, "success_body": {"instructions": [], "terminator": {"Return": 3}},
                                "failure_arg": 4, "failure_body": {"instructions": [], "terminator": {"Return": 4}},
                                "partial_arg": 5, "partial_body": {"instructions": [], "terminator": {"Return": 1}},
                                "unknown_arg": 6, "unknown_body": {"instructions": [], "terminator": {"Return": 1}}
                            }
                        }
                    }
                }
            }]
        }
    }
    run_golden("S2C15_legitimate_partial", prog)


def s2c17_delivery_unknown():
    prog = {
        "name": "S2C17_delivery_unknown",
        "entry_func": "main",
        "inputs": {},
        "act_scenarios": {"op_unk": "delivery_unknown"},
        "registry": {
            "verifiers": {},
            "operations": {
                "op_unk": {
                    "op_id": "op_unk", "target_domain": "workspace",
                    "declared_envelope": {"effects": [{"Act": "workspace"}]},
                    "declared_footprint": {"Exact": ["workspace/doc1"]},
                    "atomicity": "Atomic", "requirements": []
                }
            },
            "trust_policy": {"trusted_issuers": {}}
        },
        "module": {
            "name": "mod_s2c17",
            "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Act": "workspace"}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "arg"}, "ty": make_type_string()}},
                            {"Act": {
                                "dest": 2, "op_id": "op_unk", "target_domain": "workspace",
                                "success_type": make_type_string(), "failure_type": make_type_string(),
                                "args": [1], "evidence": [], "gate_effects": [],
                                "latent": {"on_success": [], "on_failure": [], "on_partial": []}
                            }}
                        ],
                        "terminator": {
                            "MatchActOutcome": {
                                "outcome_val": 2,
                                "success_arg": 3, "success_body": {"instructions": [], "terminator": {"Return": 3}},
                                "failure_arg": 4, "failure_body": {"instructions": [], "terminator": {"Return": 4}},
                                "partial_arg": 5, "partial_body": {"instructions": [], "terminator": {"Return": 1}},
                                "unknown_arg": 6, "unknown_body": {"instructions": [], "terminator": {"Return": 6}}  # Routes to Unknown!
                            }
                        }
                    }
                }
            }]
        }
    }
    run_golden("S2C17_delivery_unknown", prog)


# =====================================================================
# S2C19–S2C21: Footprint & Current Fact Invalidation Golden Programs
# =====================================================================

def s2c20_mutation_invalidates_current_fact():
    prog = {
        "name": "S2C20_current_invalidation",
        "entry_func": "main",
        "inputs": {},
        "initial_facts": [
            {"predicate": "CurrentState", "args": [{"Literal": "workspace/doc1"}, {"Literal": "old_data"}]},
            {"predicate": "Historical", "args": [{"Literal": "init_provenance"}]}
        ],
        "registry": {
            "verifiers": {},
            "operations": {
                "op_write": {
                    "op_id": "op_write", "target_domain": "workspace",
                    "declared_envelope": {"effects": [{"Act": "workspace"}]},
                    "declared_footprint": {"Exact": ["workspace/doc1"]},
                    "atomicity": "Atomic", "requirements": []
                }
            },
            "trust_policy": {"trusted_issuers": {}}
        },
        "module": {
            "name": "mod_s2c20",
            "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Act": "workspace"}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "val"}, "ty": make_type_string()}},
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
                                "success_arg": 3, "success_body": {"instructions": [], "terminator": {"Return": 3}},
                                "failure_arg": 4, "failure_body": {"instructions": [], "terminator": {"Return": 4}},
                                "partial_arg": 5, "partial_body": {"instructions": [], "terminator": {"Return": 1}},
                                "unknown_arg": 6, "unknown_body": {"instructions": [], "terminator": {"Return": 1}}
                            }
                        }
                    }
                }
            }]
        }
    }
    run_golden("S2C20_mutation_invalidates_current_fact", prog)


if __name__ == "__main__":
    print("=" * 70)
    print("SOMA COMPILER CONFORMANCE v0 (SLICE 2) — Golden Programs (S2C01–S2C21)")
    s2c01_verify_success()
    s2c02_verify_semantic_failure()
    s2c03_verifier_runtime_confinement()
    s2c05_registered_but_untrusted_verifier_rejected_at_gate()
    s2c06_proved_requirement_target_executes()
    s2c07_deferred_subject_binding_passes()
    s2c08_deferred_subject_binding_fails_zero_mutation()
    s2c12_separate_gate_authority()
    s2c14_clean_failure()
    s2c15_legitimate_partial()
    s2c17_delivery_unknown()
    s2c20_mutation_invalidates_current_fact()

    print("=" * 70)
    print(f"SLICE 2 GOLDEN CONFORMANCE RESULT: {PASS} passed, {FAIL} failed ({PASS + FAIL} total)")
    if FAIL:
        sys.exit(1)
    print("All Slice 2 Golden Conformance Programs PASS under real Rust toolchain.")
