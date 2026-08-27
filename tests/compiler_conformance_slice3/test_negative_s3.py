"""test_negative_s3.py — Negative Verifier Tests S3V01–S3V16 for Compiler Conformance v0 (Slice 3).

Verifies fail-closed static enforcement of delegate, ceilings, authority grants,
await handle constraints, handle join type/effect invariants, and internalization policies.
Asserts exact DiagnosticCode values.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "compiler_conformance"))

from protocol import invoke_rust_conformance

PASS, FAIL = 0, 0

def make_type_string():
    return {"kind": "String"}

def make_type_i64():
    return {"kind": "I64"}

def make_type_bool():
    return {"kind": "Bool"}

def make_type_unit():
    return {"kind": "Unit"}

def make_type_result(ok, err):
    return {"kind": "Result", "payload": {"ok": ok, "err": err}}

def make_type_claim(payload):
    return {"kind": "Claim", "payload": payload}

def make_type_belief(payload):
    return {"kind": "Belief", "payload": payload}

def make_type_child_handle(ok, err, effects):
    return {"kind": "ChildHandle", "payload": {"ok": ok, "err": err, "effects": {"effects": effects}}}

def run_negative(name: str, program: dict, expected_code: str) -> None:
    global PASS, FAIL
    print(f"\n--- NEGATIVE VERIFIER TEST (Slice 3): {name}")
    try:
        obs = invoke_rust_conformance(program)
        if obs["status"] not in ("verifier_error", "vm_verifier_error"):
            print(f"  ✗ FAIL {name}: expected verifier error, got '{obs['status']}'")
            FAIL += 1
            return
        diags = obs.get("diagnostics", [])
        codes = [d.get("code") for d in diags]
        if expected_code not in codes:
            print(f"  ✗ FAIL {name}: expected diagnostic code '{expected_code}', got {codes}")
            FAIL += 1
            return
        print(f"  ✓ PASS {name} (correctly rejected with {expected_code})")
        PASS += 1
    except Exception as e:
        print(f"  ✗ FAIL {name}: crashed with exception {type(e).__name__}: {e}")
        FAIL += 1

def s3v01_unknown_intent():
    prog = {
        "name": "S3V01_unknown_intent", "entry_func": "main", "inputs": {},
        "registry": {"intents": {}, "caller_authority": {"effects": []}},
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": []}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Delegate": {"dest": 1, "intent_id": "nonexistent_intent", "args": [], "requested_effects": [], "authority_grant": [], "budget_grant": 0}}
                        ],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    run_negative("S3V01_unknown_intent", prog, "UnknownIntent")

def s3v02_delegate_input_type_mismatch():
    prog = {
        "name": "S3V02_input_type_mismatch", "entry_func": "main", "inputs": {},
        "registry": {
            "agents": {"w": {"agent_id": "w", "native_authority": []}},
            "intents": {
                "fetch": {
                    "intent_id": "fetch", "target_agent_id": "w",
                    "input_types": [make_type_string()], "output_type": make_type_string(), "error_type": make_type_string(),
                    "child_effects": {"effects": []}, "exported_envelope": {"effects": []}, "declared_envelope": {"effects": []},
                    "authority_policy": "AllowNative"
                }
            },
            "caller_authority": {"effects": []}
        },
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": []}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "I64", "payload": 42}, "ty": make_type_i64()}},
                            {"Delegate": {"dest": 2, "intent_id": "fetch", "args": [1], "requested_effects": [], "authority_grant": [], "budget_grant": 0}}
                        ],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    run_negative("S3V02_delegate_input_type_mismatch", prog, "DelegateInputTypeMismatch")

def s3v03_requested_below_child():
    # Child needs read[docs], but requested ceiling is empty
    prog = {
        "name": "S3V03_ceiling_below_child", "entry_func": "main", "inputs": {},
        "registry": {
            "agents": {"w": {"agent_id": "w", "native_authority": [{"Read": "docs"}]}},
            "intents": {
                "fetch": {
                    "intent_id": "fetch", "target_agent_id": "w",
                    "input_types": [], "output_type": make_type_string(), "error_type": make_type_string(),
                    "child_effects": {"effects": [{"Read": "docs"}]},
                    "exported_envelope": {"effects": [{"Read": "docs"}]}, "declared_envelope": {"effects": [{"Read": "docs"}]},
                    "authority_policy": "AllowNative"
                }
            },
            "caller_authority": {"effects": [{"Read": "docs"}]}
        },
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Read": "docs"}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "ok"}, "ty": make_type_string()}},
                            {"Delegate": {"dest": 2, "intent_id": "fetch", "args": [], "requested_effects": [], "authority_grant": [], "budget_grant": 0}}
                        ],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    run_negative("S3V03_requested_below_child", prog, "InvocationCeilingBelowChild")

def s3v04_requested_above_exported():
    # Exported envelope is read[docs], but requested ceiling is read[docs] + act[production]
    prog = {
        "name": "S3V04_ceiling_above_exported", "entry_func": "main", "inputs": {},
        "registry": {
            "agents": {"w": {"agent_id": "w", "native_authority": [{"Read": "docs"}]}},
            "intents": {
                "fetch": {
                    "intent_id": "fetch", "target_agent_id": "w",
                    "input_types": [], "output_type": make_type_string(), "error_type": make_type_string(),
                    "child_effects": {"effects": [{"Read": "docs"}]},
                    "exported_envelope": {"effects": [{"Read": "docs"}]}, "declared_envelope": {"effects": [{"Read": "docs"}]},
                    "authority_policy": "AllowNative"
                }
            },
            "caller_authority": {"effects": [{"Read": "docs"}]}
        },
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Read": "docs"}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "ok"}, "ty": make_type_string()}},
                            {"Delegate": {"dest": 2, "intent_id": "fetch", "args": [], "requested_effects": [{"Read": "docs"}, {"Act": "production"}], "authority_grant": [], "budget_grant": 0}}
                        ],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    run_negative("S3V04_requested_above_exported", prog, "InvocationCeilingAboveExported")

def s3v05_grant_exceeds_caller_authority():
    # Caller authority has read[docs], but grants act[workspace]
    prog = {
        "name": "S3V05_grant_exceeds_caller", "entry_func": "main", "inputs": {},
        "registry": {
            "agents": {"w": {"agent_id": "w", "native_authority": [{"Read": "docs"}]}},
            "intents": {
                "task": {
                    "intent_id": "task", "target_agent_id": "w",
                    "input_types": [], "output_type": make_type_string(), "error_type": make_type_string(),
                    "child_effects": {"effects": [{"Read": "docs"}]},
                    "exported_envelope": {"effects": [{"Read": "docs"}, {"Act": "workspace"}]},
                    "declared_envelope": {"effects": [{"Read": "docs"}, {"Act": "workspace"}]},
                    "authority_policy": "AllowGrant"
                }
            },
            "caller_authority": {"effects": [{"Read": "docs"}]} # Lacks act[workspace]!
        },
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Read": "docs"}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "ok"}, "ty": make_type_string()}},
                            {"Delegate": {"dest": 2, "intent_id": "task", "args": [], "requested_effects": [{"Read": "docs"}, {"Act": "workspace"}], "authority_grant": [{"Act": "workspace"}], "budget_grant": 0}}
                        ],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    run_negative("S3V05_grant_exceeds_caller_authority", prog, "GrantExceedsCallerAuthority")

def s3v06_grant_exceeds_requested_ceiling():
    # Caller has act[production], but requested ceiling is only read[docs] -> grant of act[production] rejected
    prog = {
        "name": "S3V06_grant_exceeds_ceiling", "entry_func": "main", "inputs": {},
        "registry": {
            "agents": {"w": {"agent_id": "w", "native_authority": [{"Read": "docs"}]}},
            "intents": {
                "task": {
                    "intent_id": "task", "target_agent_id": "w",
                    "input_types": [], "output_type": make_type_string(), "error_type": make_type_string(),
                    "child_effects": {"effects": [{"Read": "docs"}]},
                    "exported_envelope": {"effects": [{"Read": "docs"}, {"Act": "production"}]},
                    "declared_envelope": {"effects": [{"Read": "docs"}, {"Act": "production"}]},
                    "authority_policy": "AllowGrant"
                }
            },
            "caller_authority": {"effects": [{"Read": "docs"}, {"Act": "production"}]}
        },
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Read": "docs"}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "ok"}, "ty": make_type_string()}},
                            {"Delegate": {"dest": 2, "intent_id": "task", "args": [], "requested_effects": [{"Read": "docs"}], "authority_grant": [{"Act": "production"}], "budget_grant": 0}}
                        ],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    run_negative("S3V06_grant_exceeds_requested_ceiling", prog, "GrantExceedsRequestedCeiling")

def s3v07_function_omits_child_effect():
    # Child carries read[docs], but function declared_effects is empty
    prog = {
        "name": "S3V07_function_omits_child_effect", "entry_func": "main", "inputs": {},
        "registry": {
            "agents": {"w": {"agent_id": "w", "native_authority": [{"Read": "docs"}]}},
            "intents": {
                "task": {
                    "intent_id": "task", "target_agent_id": "w",
                    "input_types": [], "output_type": make_type_string(), "error_type": make_type_string(),
                    "child_effects": {"effects": [{"Read": "docs"}]},
                    "exported_envelope": {"effects": [{"Read": "docs"}]},
                    "declared_envelope": {"effects": [{"Read": "docs"}]},
                    "authority_policy": "AllowNative"
                }
            },
            "caller_authority": {"effects": [{"Read": "docs"}]}
        },
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": []}, # Omits read[docs]!
                "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "ok"}, "ty": make_type_string()}},
                            {"Delegate": {"dest": 2, "intent_id": "task", "args": [], "requested_effects": [{"Read": "docs"}], "authority_grant": [], "budget_grant": 0}}
                        ],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    run_negative("S3V07_function_omits_child_effect", prog, "EffectUndeclared")

def s3v08_await_non_child_handle():
    prog = {
        "name": "S3V08_await_non_handle", "entry_func": "main", "inputs": {},
        "registry": {"caller_authority": {"effects": []}},
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": []}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "not_a_handle"}, "ty": make_type_string()}},
                            {"Await": {"dest": 2, "handle": 1}}
                        ],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    run_negative("S3V08_await_non_child_handle", prog, "AwaitNonChildHandle")

def s3v09_incompatible_handle_join_t():
    prog = {
        "name": "S3V09_incompatible_join_t", "entry_func": "main", "inputs": {},
        "registry": {
            "agents": {"w": {"agent_id": "w", "native_authority": []}},
            "intents": {
                "fetch_i64": {
                    "intent_id": "fetch_i64", "target_agent_id": "w",
                    "input_types": [], "output_type": make_type_i64(), "error_type": make_type_string(),
                    "child_effects": {"effects": []}, "exported_envelope": {"effects": []}, "declared_envelope": {"effects": []},
                    "authority_policy": "AllowNative"
                }
            },
            "caller_authority": {"effects": []}
        },
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": []}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Delegate": {"dest": 1, "intent_id": "fetch_i64", "args": [], "requested_effects": [], "authority_grant": [], "budget_grant": 0}}
                        ],
                        "terminator": {"Br": {"target": 1, "args": [1]}}
                    },
                    "1": {
                        "id": 1, "params": [
                            # Expected type has T=String, incoming has T=I64
                            [2, make_type_child_handle(make_type_string(), make_type_string(), [])]
                        ],
                        "instructions": [],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    run_negative("S3V09_incompatible_handle_join_t", prog, "IncompatibleHandleJoin")

def s3v10_incompatible_handle_join_e():
    prog = {
        "name": "S3V10_incompatible_join_e", "entry_func": "main", "inputs": {},
        "registry": {
            "agents": {"w": {"agent_id": "w", "native_authority": []}},
            "intents": {
                "fetch_err_i64": {
                    "intent_id": "fetch_err_i64", "target_agent_id": "w",
                    "input_types": [], "output_type": make_type_string(), "error_type": make_type_i64(),
                    "child_effects": {"effects": []}, "exported_envelope": {"effects": []}, "declared_envelope": {"effects": []},
                    "authority_policy": "AllowNative"
                }
            },
            "caller_authority": {"effects": []}
        },
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": []}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Delegate": {"dest": 1, "intent_id": "fetch_err_i64", "args": [], "requested_effects": [], "authority_grant": [], "budget_grant": 0}}
                        ],
                        "terminator": {"Br": {"target": 1, "args": [1]}}
                    },
                    "1": {
                        "id": 1, "params": [
                            # Expected type has E=String, incoming has E=I64
                            [2, make_type_child_handle(make_type_string(), make_type_string(), [])]
                        ],
                        "instructions": [],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    run_negative("S3V10_incompatible_handle_join_e", prog, "IncompatibleHandleJoin")

def s3v11_region_local_leak_after_match():
    prog = {
        "name": "S3V11_region_local_leak", "entry_func": "main", "inputs": {},
        "registry": {"caller_authority": {"effects": []}},
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": []}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "Ok", "payload": {"kind": "String", "payload": "ok"}}, "ty": make_type_result(make_type_string(), make_type_string())}}
                        ],
                        "terminator": {
                            "MatchResult": {
                                "result_val": 1,
                                "ok_arg": 2, "ok_body": {
                                    "instructions": [
                                        {"Pure": {"dest": 4, "val": {"kind": "String", "payload": "leak"}, "ty": make_type_string()}}
                                    ],
                                    "terminator": {"Br": {"target": 1, "args": []}}
                                },
                                "err_arg": 3, "err_body": {
                                    "instructions": [],
                                    "terminator": {"Br": {"target": 1, "args": []}}
                                }
                            }
                        }
                    },
                    "1": {
                        "id": 1, "params": [],
                        "instructions": [],
                        # Uses %4 which was defined only inside ok_body!
                        "terminator": {"Return": 4}
                    }
                }
            }]
        }
    }
    run_negative("S3V11_region_local_leak_after_match", prog, "SsaUseBeforeDef")

def s3v12_cross_branch_ssa_use():
    prog = {
        "name": "S3V12_cross_branch_use", "entry_func": "main", "inputs": {},
        "registry": {"caller_authority": {"effects": []}},
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": []}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "Ok", "payload": {"kind": "String", "payload": "ok"}}, "ty": make_type_result(make_type_string(), make_type_string())}}
                        ],
                        "terminator": {
                            "MatchResult": {
                                "result_val": 1,
                                "ok_arg": 2, "ok_body": {
                                    "instructions": [
                                        {"Pure": {"dest": 4, "val": {"kind": "String", "payload": "local"}, "ty": make_type_string()}}
                                    ],
                                    "terminator": {"Return": 4}
                                },
                                "err_arg": 3, "err_body": {
                                    # err_body attempts to use %4 from ok_body!
                                    "instructions": [],
                                    "terminator": {"Return": 4}
                                }
                            }
                        }
                    }
                }
            }]
        }
    }
    run_negative("S3V12_cross_branch_ssa_use", prog, "SsaUseBeforeDef")

def s3v13_unknown_internalization_policy():
    prog = {
        "name": "S3V13_unknown_policy", "entry_func": "main", "inputs": {},
        "registry": {"internalization_policies": {}, "caller_authority": {"effects": []}},
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": []}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "Claim", "payload": {"kind": "String", "payload": "x"}}, "ty": make_type_claim(make_type_string())}},
                            {"Internalize": {"dest": 2, "policy_id": "nonexistent_policy", "claim": 1}}
                        ],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    run_negative("S3V13_unknown_internalization_policy", prog, "UnknownInternalizationPolicy")

def s3v14_internalize_non_claim_value():
    prog = {
        "name": "S3V14_internalize_non_claim", "entry_func": "main", "inputs": {},
        "registry": {
            "internalization_policies": {
                "p": {"policy_id": "p", "accepted_claim_contract": "AcceptAll", "validation_requirements": [], "validation_effect_envelope": {"effects": []}}
            },
            "caller_authority": {"effects": []}
        },
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": []}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "not_a_claim"}, "ty": make_type_string()}},
                            {"Internalize": {"dest": 2, "policy_id": "p", "claim": 1}}
                        ],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    run_negative("S3V14_internalize_non_claim_value", prog, "InternalizeNonClaim")

def s3v15_function_omits_validation_effect():
    # Policy has read[policy_store], function declared_effects is empty
    prog = {
        "name": "S3V15_function_omits_val_eff", "entry_func": "main", "inputs": {},
        "registry": {
            "internalization_policies": {
                "p": {
                    "policy_id": "p", "accepted_claim_contract": "AcceptAll", "validation_requirements": [],
                    "validation_effect_envelope": {"effects": [{"Read": "policy_store"}]}
                }
            },
            "caller_authority": {"effects": [{"Read": "policy_store"}]}
        },
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": []}, # Omits read[policy_store]!
                "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "Claim", "payload": {"kind": "String", "payload": "x"}}, "ty": make_type_claim(make_type_string())}},
                            {"Internalize": {"dest": 2, "policy_id": "p", "claim": 1}}
                        ],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    run_negative("S3V15_function_omits_validation_effect", prog, "EffectUndeclared")

def s3v16_caller_lacks_validation_authority():
    # Policy has read[policy_store], caller authority lacks it
    prog = {
        "name": "S3V16_caller_lacks_val_auth", "entry_func": "main", "inputs": {},
        "registry": {
            "internalization_policies": {
                "p": {
                    "policy_id": "p", "accepted_claim_contract": "AcceptAll", "validation_requirements": [],
                    "validation_effect_envelope": {"effects": [{"Read": "policy_store"}]}
                }
            },
            "caller_authority": {"effects": []} # Lacks read[policy_store]!
        },
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Read": "policy_store"}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "Claim", "payload": {"kind": "String", "payload": "x"}}, "ty": make_type_claim(make_type_string())}},
                            {"Internalize": {"dest": 2, "policy_id": "p", "claim": 1}}
                        ],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    run_negative("S3V16_caller_lacks_validation_authority", prog, "ValidationAuthorityInsufficient")

def main():
    print("=" * 70)
    print("SOMA COMPILER CONFORMANCE v0 (SLICE 3) — Negative Verifier Tests (S3V01–S3V16)")

    s3v01_unknown_intent()
    s3v02_delegate_input_type_mismatch()
    s3v03_requested_below_child()
    s3v04_requested_above_exported()
    s3v05_grant_exceeds_caller_authority()
    s3v06_grant_exceeds_requested_ceiling()
    s3v07_function_omits_child_effect()
    s3v08_await_non_child_handle()
    s3v09_incompatible_handle_join_t()
    s3v10_incompatible_handle_join_e()
    s3v11_region_local_leak_after_match()
    s3v12_cross_branch_ssa_use()
    s3v13_unknown_internalization_policy()
    s3v14_internalize_non_claim_value()
    s3v15_function_omits_validation_effect()
    s3v16_caller_lacks_validation_authority()

    print("=" * 70)
    print(f"SLICE 3 NEGATIVE VERIFIER RESULT: {PASS} passed, {FAIL} failed ({PASS + FAIL} total)")
    if FAIL > 0:
        sys.exit(1)
    print("All 16 Slice 3 Negative Verifier Tests correctly rejected by Rust Verifier.")

if __name__ == "__main__":
    main()
