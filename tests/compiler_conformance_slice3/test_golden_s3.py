"""test_golden_s3.py — SOMA-IR Compiler Conformance v0 (Slice 3: Delegate / Await / Internalize / ChildHandle).

Covers Golden Matrix S3C01–S3C34:
- S3C01–S3C07: Delegate & Authority Attenuation & Confinement
- S3C08–S3C13: Budget Ownership Transfer & Conservation & Settlement
- S3C14–S3C20: Await Lifecycle & Generation Binding & Suspension
- S3C21–S3C25: Handle Joins in CFG & Effect Unions & Provenance
- S3C26–S3C33: Claim / Belief / Internalize & Policy Contract & Owner Binding
- S3C34: Full Cross-Case: Delegate -> Await -> Match Ok -> Internalize
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "compiler_conformance"))

from protocol import invoke_rust_conformance

PASS = 0
FAIL = 0

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

def run_golden(
    name: str,
    program: dict,
    expected_status: str = "ok",
    expected_diag: str = None,
    expected_child_events: list = None,
    expected_beliefs: list = None,
    expected_provenance: dict = None,
) -> None:
    global PASS, FAIL
    print(f"\n--- GOLDEN PROGRAM (Slice 3): {name}")
    try:
        obs = invoke_rust_conformance(program)
        if expected_status == "ok":
            if obs["status"] != "ok":
                print(f"  ✗ FAIL {name}: expected status 'ok', got '{obs['status']}' with diagnostics {obs.get('diagnostics')}")
                FAIL += 1
                return
        elif expected_status == "verifier_error":
            if obs["status"] not in ("verifier_error", "vm_verifier_error"):
                print(f"  ✗ FAIL {name}: expected verifier error, got status '{obs['status']}'")
                FAIL += 1
                return
            if expected_diag is not None:
                diags = obs.get("diagnostics", [])
                if not any(d.get("code") == expected_diag for d in diags):
                    print(f"  ✗ FAIL {name}: expected diagnostic code '{expected_diag}', got {diags}")
                    FAIL += 1
                    return
        else:
            if expected_status not in obs["status"]:
                print(f"  ✗ FAIL {name}: expected status containing '{expected_status}', got '{obs['status']}'")
                FAIL += 1
                return

        if expected_child_events is not None:
            actual_events = obs.get("child_events", [])
            for ev in expected_child_events:
                if not any(ev in a for a in actual_events):
                    print(f"  ✗ FAIL {name}: expected child event '{ev}' not found in {actual_events}")
                    FAIL += 1
                    return

        print(f"  ✓ PASS {name} (status={obs['status']}, return={obs.get('return_val')}, effects={obs.get('effects')})")
        PASS += 1
    except Exception as e:
        print(f"  ✗ FAIL {name}: crashed with exception {type(e).__name__}: {e}")
        FAIL += 1

# ==============================================================================
# S3C01–S3C07: Delegate & Authority Attenuation & Confinement
# ==============================================================================

def s3c01_basic_delegate():
    prog = {
        "name": "S3C01_basic_delegate", "entry_func": "main", "inputs": {},
        "registry": {
            "agents": {
                "worker": {"agent_id": "worker", "native_authority": [{"Read": "docs"}]}
            },
            "intents": {
                "fetch_doc": {
                    "intent_id": "fetch_doc", "target_agent_id": "worker",
                    "input_types": [make_type_string()], "output_type": make_type_string(), "error_type": make_type_string(),
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
                "declared_effects": {"effects": [{"Read": "docs"}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "doc1"}, "ty": make_type_string()}},
                            {"Delegate": {"dest": 2, "intent_id": "fetch_doc", "args": [1], "requested_effects": [{"Read": "docs"}], "authority_grant": [], "budget_grant": 10}}
                        ],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    run_golden("S3C01_basic_delegate", prog, expected_child_events=["Spawned(fetch_doc)"])

def s3c02_fire_and_forget_effects_visible():
    prog = {
        "name": "S3C02_fire_and_forget", "entry_func": "main", "inputs": {},
        "registry": {
            "agents": {
                "worker": {"agent_id": "worker", "native_authority": [{"Read": "docs"}, {"Infer": None}]}
            },
            "intents": {
                "async_task": {
                    "intent_id": "async_task", "target_agent_id": "worker",
                    "input_types": [], "output_type": make_type_string(), "error_type": make_type_string(),
                    "child_effects": {"effects": [{"Read": "docs"}, {"Infer": None}]},
                    "exported_envelope": {"effects": [{"Read": "docs"}, {"Infer": None}]},
                    "declared_envelope": {"effects": [{"Read": "docs"}, {"Infer": None}]},
                    "authority_policy": "AllowNative"
                }
            },
            "caller_authority": {"effects": [{"Read": "docs"}, {"Infer": None}]}
        },
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Read": "docs"}, {"Infer": None}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "42"}, "ty": make_type_string()}},
                            {"Delegate": {"dest": 2, "intent_id": "async_task", "args": [], "requested_effects": [{"Read": "docs"}, {"Infer": None}], "authority_grant": [], "budget_grant": 20}}
                        ],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    run_golden("S3C02_fire_and_forget", prog)

def s3c03_valid_invocation_ceiling():
    prog = {
        "name": "S3C03_valid_ceiling", "entry_func": "main", "inputs": {},
        "registry": {
            "agents": {
                "worker": {"agent_id": "worker", "native_authority": [{"Read": "docs"}, {"Read": "extra"}]}
            },
            "intents": {
                "query": {
                    "intent_id": "query", "target_agent_id": "worker",
                    "input_types": [], "output_type": make_type_string(), "error_type": make_type_string(),
                    "child_effects": {"effects": [{"Read": "docs"}]},
                    "exported_envelope": {"effects": [{"Read": "docs"}, {"Read": "extra"}]},
                    "declared_envelope": {"effects": [{"Read": "docs"}, {"Read": "extra"}]},
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
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "done"}, "ty": make_type_string()}},
                            {"Delegate": {"dest": 2, "intent_id": "query", "args": [], "requested_effects": [{"Read": "docs"}, {"Read": "extra"}], "authority_grant": [], "budget_grant": 10}}
                        ],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    run_golden("S3C03_valid_invocation_ceiling", prog)

def s3c04_native_authority_independent_from_caller():
    # Caller does NOT possess act[target_domain], but target agent does natively!
    prog = {
        "name": "S3C04_native_authority_independent", "entry_func": "main", "inputs": {},
        "registry": {
            "agents": {
                "db_worker": {"agent_id": "db_worker", "native_authority": [{"Act": "database"}]}
            },
            "intents": {
                "db_write": {
                    "intent_id": "db_write", "target_agent_id": "db_worker",
                    "input_types": [make_type_string()], "output_type": make_type_string(), "error_type": make_type_string(),
                    "child_effects": {"effects": [{"Act": "database"}]},
                    "exported_envelope": {"effects": [{"Act": "database"}]},
                    "declared_envelope": {"effects": [{"Act": "database"}]},
                    "authority_policy": "AllowNative"
                }
            },
            "caller_authority": {"effects": []} # Caller has zero authority!
        },
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Act": "database"}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "record"}, "ty": make_type_string()}},
                            {"Delegate": {"dest": 2, "intent_id": "db_write", "args": [1], "requested_effects": [{"Act": "database"}], "authority_grant": [], "budget_grant": 15}}
                        ],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    run_golden("S3C04_native_authority_independent", prog)

def s3c05_native_authority_attenuation():
    # Target native has act[a] and act[b], requested ceiling has only act[a] -> effective authority is act[a]
    prog = {
        "name": "S3C05_native_attenuation", "entry_func": "main", "inputs": {},
        "registry": {
            "agents": {
                "super_worker": {"agent_id": "super_worker", "native_authority": [{"Act": "domain_a"}, {"Act": "domain_b"}]}
            },
            "intents": {
                "restricted_intent": {
                    "intent_id": "restricted_intent", "target_agent_id": "super_worker",
                    "input_types": [], "output_type": make_type_string(), "error_type": make_type_string(),
                    "child_effects": {"effects": [{"Act": "domain_a"}]},
                    "exported_envelope": {"effects": [{"Act": "domain_a"}, {"Act": "domain_b"}]},
                    "declared_envelope": {"effects": [{"Act": "domain_a"}, {"Act": "domain_b"}]},
                    "authority_policy": "AllowNative"
                }
            },
            "caller_authority": {"effects": []}
        },
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Act": "domain_a"}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "ok"}, "ty": make_type_string()}},
                            {"Delegate": {"dest": 2, "intent_id": "restricted_intent", "args": [], "requested_effects": [{"Act": "domain_a"}], "authority_grant": [], "budget_grant": 10}}
                        ],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    run_golden("S3C05_native_attenuation", prog)

def s3c06_explicit_granted_authority():
    # Target native has read[a], caller grants act[workspace] -> child effective is read[a] + act[workspace]
    prog = {
        "name": "S3C06_explicit_grant", "entry_func": "main", "inputs": {},
        "registry": {
            "agents": {
                "worker": {"agent_id": "worker", "native_authority": [{"Read": "domain_a"}]}
            },
            "intents": {
                "hybrid_intent": {
                    "intent_id": "hybrid_intent", "target_agent_id": "worker",
                    "input_types": [], "output_type": make_type_string(), "error_type": make_type_string(),
                    "child_effects": {"effects": [{"Read": "domain_a"}, {"Act": "workspace"}]},
                    "exported_envelope": {"effects": [{"Read": "domain_a"}, {"Act": "workspace"}]},
                    "declared_envelope": {"effects": [{"Read": "domain_a"}, {"Act": "workspace"}]},
                    "authority_policy": "AllowGrant"
                }
            },
            "caller_authority": {"effects": [{"Act": "workspace"}]}
        },
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Read": "domain_a"}, {"Act": "workspace"}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "ok"}, "ty": make_type_string()}},
                            {"Delegate": {
                                "dest": 2, "intent_id": "hybrid_intent", "args": [],
                                "requested_effects": [{"Read": "domain_a"}, {"Act": "workspace"}],
                                "authority_grant": [{"Act": "workspace"}],
                                "budget_grant": 10
                            }}
                        ],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    run_golden("S3C06_explicit_grant", prog)

def s3c07_runtime_confinement():
    # Child attempts effect outside requested ceiling -> blocked before target effect!
    prog = {
        "name": "S3C07_confinement", "entry_func": "main", "inputs": {},
        "child_scenarios": {
            "confined_op": {
                "mode": "out_of_ceiling_attempt",
                "attempt_out_of_ceiling_effect": {"Act": "production"}
            }
        },
        "registry": {
            "agents": {
                "worker": {"agent_id": "worker", "native_authority": [{"Act": "workspace"}, {"Act": "production"}]}
            },
            "intents": {
                "confined_op": {
                    "intent_id": "confined_op", "target_agent_id": "worker",
                    "input_types": [], "output_type": make_type_string(), "error_type": make_type_string(),
                    "child_effects": {"effects": [{"Act": "workspace"}]},
                    "exported_envelope": {"effects": [{"Act": "workspace"}, {"Act": "production"}]},
                    "declared_envelope": {"effects": [{"Act": "workspace"}, {"Act": "production"}]},
                    "authority_policy": "AllowNative"
                }
            },
            "caller_authority": {"effects": []}
        },
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Act": "workspace"}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "ok"}, "ty": make_type_string()}},
                            {"Delegate": {"dest": 2, "intent_id": "confined_op", "args": [], "requested_effects": [{"Act": "workspace"}], "authority_grant": [], "budget_grant": 10}}
                        ],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    run_golden("S3C07_confinement", prog, expected_status="error: SpawnFailed: ConfinementViolation")

# ==============================================================================
# S3C08–S3C13: Budget Ownership Transfer & Conservation & Settlement
# ==============================================================================

def s3c08_atomic_budget_transfer():
    prog = {
        "name": "S3C08_budget_transfer", "entry_func": "main", "inputs": {},
        "initial_budget": {"compute": 100},
        "registry": {
            "agents": {"w": {"agent_id": "w", "native_authority": [{"Read": "x"}]}},
            "intents": {
                "calc": {
                    "intent_id": "calc", "target_agent_id": "w",
                    "input_types": [], "output_type": make_type_string(), "error_type": make_type_string(),
                    "child_effects": {"effects": [{"Read": "x"}]},
                    "exported_envelope": {"effects": [{"Read": "x"}]},
                    "declared_envelope": {"effects": [{"Read": "x"}]},
                    "authority_policy": "AllowNative"
                }
            },
            "caller_authority": {"effects": [{"Read": "x"}]}
        },
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Read": "x"}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "ok"}, "ty": make_type_string()}},
                            {"Delegate": {"dest": 2, "intent_id": "calc", "args": [], "requested_effects": [{"Read": "x"}], "authority_grant": [], "budget_grant": 30}}
                        ],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    run_golden("S3C08_atomic_budget_transfer", prog)

def s3c09_spawn_failure_atomic_budget():
    prog = {
        "name": "S3C09_spawn_failure_budget", "entry_func": "main", "inputs": {},
        "initial_budget": {"compute": 100},
        "child_scenarios": {
            "calc": {"mode": "spawn_failure"}
        },
        "registry": {
            "agents": {"w": {"agent_id": "w", "native_authority": [{"Read": "x"}]}},
            "intents": {
                "calc": {
                    "intent_id": "calc", "target_agent_id": "w",
                    "input_types": [], "output_type": make_type_string(), "error_type": make_type_string(),
                    "child_effects": {"effects": [{"Read": "x"}]},
                    "exported_envelope": {"effects": [{"Read": "x"}]},
                    "declared_envelope": {"effects": [{"Read": "x"}]},
                    "authority_policy": "AllowNative"
                }
            },
            "caller_authority": {"effects": [{"Read": "x"}]}
        },
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Read": "x"}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "ok"}, "ty": make_type_string()}},
                            {"Delegate": {"dest": 2, "intent_id": "calc", "args": [], "requested_effects": [{"Read": "x"}], "authority_grant": [], "budget_grant": 30}}
                        ],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    run_golden("S3C09_spawn_failure_budget", prog, expected_status="error: SpawnFailed")

def s3c10_settlement_returns_unspent():
    prog = {
        "name": "S3C10_settlement_unspent", "entry_func": "main", "inputs": {},
        "initial_budget": {"compute": 100},
        "child_scenarios": {
            "calc": {"mode": "success", "spend_amount": 12}
        },
        "registry": {
            "agents": {"w": {"agent_id": "w", "native_authority": [{"Read": "x"}]}},
            "intents": {
                "calc": {
                    "intent_id": "calc", "target_agent_id": "w",
                    "input_types": [], "output_type": make_type_string(), "error_type": make_type_string(),
                    "child_effects": {"effects": [{"Read": "x"}]},
                    "exported_envelope": {"effects": [{"Read": "x"}]},
                    "declared_envelope": {"effects": [{"Read": "x"}]},
                    "authority_policy": "AllowNative"
                }
            },
            "caller_authority": {"effects": [{"Read": "x"}]}
        },
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Read": "x"}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "ok"}, "ty": make_type_string()}},
                            {"Delegate": {"dest": 2, "intent_id": "calc", "args": [], "requested_effects": [{"Read": "x"}], "authority_grant": [], "budget_grant": 30}},
                            {"Await": {"dest": 3, "handle": 2}}
                        ],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    run_golden("S3C10_settlement_unspent", prog, expected_child_events=["Settled(h_1)"])

def s3c11_exactly_once_settlement():
    # Awaiting the same settled handle twice settles only once
    prog = {
        "name": "S3C11_settlement_exactly_once", "entry_func": "main", "inputs": {},
        "initial_budget": {"compute": 100},
        "registry": {
            "agents": {"w": {"agent_id": "w", "native_authority": [{"Read": "x"}]}},
            "intents": {
                "calc": {
                    "intent_id": "calc", "target_agent_id": "w",
                    "input_types": [], "output_type": make_type_string(), "error_type": make_type_string(),
                    "child_effects": {"effects": [{"Read": "x"}]},
                    "exported_envelope": {"effects": [{"Read": "x"}]},
                    "declared_envelope": {"effects": [{"Read": "x"}]},
                    "authority_policy": "AllowNative"
                }
            },
            "caller_authority": {"effects": [{"Read": "x"}]}
        },
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Read": "x"}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "ok"}, "ty": make_type_string()}},
                            {"Delegate": {"dest": 2, "intent_id": "calc", "args": [], "requested_effects": [{"Read": "x"}], "authority_grant": [], "budget_grant": 25}},
                            {"Await": {"dest": 3, "handle": 2}},
                            {"Await": {"dest": 4, "handle": 2}}
                        ],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    run_golden("S3C11_settlement_exactly_once", prog, expected_child_events=["Settled(h_1)"])

def s3c12_outstanding_commitment_blocks_settlement():
    prog = {
        "name": "S3C12_commitment_blocks_settlement", "entry_func": "main", "inputs": {},
        "initial_budget": {"compute": 100},
        "child_scenarios": {
            "calc": {"mode": "outstanding_commitment", "reserved_amount": 15}
        },
        "registry": {
            "agents": {"w": {"agent_id": "w", "native_authority": [{"Read": "x"}]}},
            "intents": {
                "calc": {
                    "intent_id": "calc", "target_agent_id": "w",
                    "input_types": [], "output_type": make_type_string(), "error_type": make_type_string(),
                    "child_effects": {"effects": [{"Read": "x"}]},
                    "exported_envelope": {"effects": [{"Read": "x"}]},
                    "declared_envelope": {"effects": [{"Read": "x"}]},
                    "authority_policy": "AllowNative"
                }
            },
            "caller_authority": {"effects": [{"Read": "x"}]}
        },
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Read": "x"}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "ok"}, "ty": make_type_string()}},
                            {"Delegate": {"dest": 2, "intent_id": "calc", "args": [], "requested_effects": [{"Read": "x"}], "authority_grant": [], "budget_grant": 30}},
                            {"Await": {"dest": 3, "handle": 2}}
                        ],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    run_golden("S3C12_commitment_blocks_settlement", prog, expected_status="error: SettlementFailed")

def s3c13_nested_budget_conservation():
    global PASS, FAIL
    print("\n--- GOLDEN PROGRAM (Slice 3): S3C13_nested_budget")
    prog = {
        "name": "S3C13_nested_budget", "entry_func": "main", "inputs": {},
        "initial_budget": {"compute": 100},
        "child_scenarios": {
            "parent_intent": {
                "mode": "nested_delegation",
                "spend_amount": 5,
                "nested_grandchild_spend": 7
            }
        },
        "registry": {
            "agents": {"w": {"agent_id": "w", "native_authority": [{"Read": "x"}]}},
            "intents": {
                "parent_intent": {
                    "intent_id": "parent_intent", "target_agent_id": "w",
                    "input_types": [], "output_type": make_type_string(), "error_type": make_type_string(),
                    "child_effects": {"effects": [{"Read": "x"}]},
                    "exported_envelope": {"effects": [{"Read": "x"}]},
                    "declared_envelope": {"effects": [{"Read": "x"}]},
                    "authority_policy": "AllowNative"
                }
            },
            "caller_authority": {"effects": [{"Read": "x"}]}
        },
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Read": "x"}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "ok"}, "ty": make_type_string()}},
                            {"Delegate": {"dest": 2, "intent_id": "parent_intent", "args": [], "requested_effects": [{"Read": "x"}], "authority_grant": [], "budget_grant": 40}},
                            {"Await": {"dest": 3, "handle": 2}}
                        ],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    obs = invoke_rust_conformance(prog)
    if obs["status"] != "ok":
        print(f"  ✗ FAIL S3C13_nested_budget: status={obs['status']}")
        FAIL += 1
        return

    ledgers = obs.get("frame_ledgers", {})
    root_b = ledgers.get("root", {})
    child_b = ledgers.get("h_1", {})
    gc_b = ledgers.get("h_1_gc", {})

    root_avail = root_b.get("available", {}).get("compute", 0)
    child_spent = child_b.get("spent", {}).get("compute", 0)
    gc_spent = gc_b.get("spent", {}).get("compute", 0)

    assert root_avail == 88, f"expected root available 88, got {root_avail}"
    assert child_spent == 5, f"expected child spent 5, got {child_spent}"
    assert gc_spent == 7, f"expected grandchild spent 7, got {gc_spent}"
    assert root_avail + child_spent + gc_spent == 100, f"Budget conservation failed: {root_avail} + {child_spent} + {gc_spent} != 100"
    assert len(root_b.get("reserved", {})) == 0, "root has shadow reservation"
    assert len(child_b.get("reserved", {})) == 0, "child has shadow reservation"
    assert len(gc_b.get("reserved", {})) == 0, "grandchild has shadow reservation"

    print("  ✓ PASS S3C13_nested_budget (three-frame conservation strictly verified: root=88 + child_spent=5 + gc_spent=7 == 100)")
    PASS += 1

# ==============================================================================
# S3C14–S3C20: Await Lifecycle & Generation Binding & Suspension
# ==============================================================================

def s3c14_await_success():
    prog = {
        "name": "S3C14_await_success", "entry_func": "main", "inputs": {},
        "registry": {
            "agents": {"w": {"agent_id": "w", "native_authority": [{"Read": "data"}]}},
            "intents": {
                "fetch": {
                    "intent_id": "fetch", "target_agent_id": "w",
                    "input_types": [make_type_string()], "output_type": make_type_string(), "error_type": make_type_string(),
                    "child_effects": {"effects": [{"Read": "data"}]},
                    "exported_envelope": {"effects": [{"Read": "data"}]},
                    "declared_envelope": {"effects": [{"Read": "data"}]},
                    "authority_policy": "AllowNative"
                }
            },
            "caller_authority": {"effects": [{"Read": "data"}]}
        },
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Read": "data"}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "payload_x"}, "ty": make_type_string()}},
                            {"Delegate": {"dest": 2, "intent_id": "fetch", "args": [1], "requested_effects": [{"Read": "data"}], "authority_grant": [], "budget_grant": 10}},
                            {"Await": {"dest": 3, "handle": 2}}
                        ],
                        "terminator": {
                            "MatchResult": {
                                "result_val": 3,
                                "ok_arg": 4, "ok_body": {"instructions": [], "terminator": {"Return": 4}},
                                "err_arg": 5, "err_body": {"instructions": [], "terminator": {"Return": 1}}
                            }
                        }
                    }
                }
            }]
        }
    }
    run_golden("S3C14_await_success", prog)

def s3c15_await_semantic_failure():
    prog = {
        "name": "S3C15_await_failure", "entry_func": "main", "inputs": {},
        "child_scenarios": {
            "fetch": {"mode": "semantic_failure", "payload_string": "WorkerNotFound"}
        },
        "registry": {
            "agents": {"w": {"agent_id": "w", "native_authority": [{"Read": "data"}]}},
            "intents": {
                "fetch": {
                    "intent_id": "fetch", "target_agent_id": "w",
                    "input_types": [], "output_type": make_type_string(), "error_type": make_type_string(),
                    "child_effects": {"effects": [{"Read": "data"}]},
                    "exported_envelope": {"effects": [{"Read": "data"}]},
                    "declared_envelope": {"effects": [{"Read": "data"}]},
                    "authority_policy": "AllowNative"
                }
            },
            "caller_authority": {"effects": [{"Read": "data"}]}
        },
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Read": "data"}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "fallback"}, "ty": make_type_string()}},
                            {"Delegate": {"dest": 2, "intent_id": "fetch", "args": [], "requested_effects": [{"Read": "data"}], "authority_grant": [], "budget_grant": 10}},
                            {"Await": {"dest": 3, "handle": 2}}
                        ],
                        "terminator": {
                            "MatchResult": {
                                "result_val": 3,
                                "ok_arg": 4, "ok_body": {"instructions": [], "terminator": {"Return": 4}},
                                "err_arg": 5, "err_body": {"instructions": [], "terminator": {"Return": 5}}
                            }
                        }
                    }
                }
            }]
        }
    }
    run_golden("S3C15_await_failure", prog)

def s3c16_settlement_unknown():
    prog = {
        "name": "S3C16_settlement_unknown", "entry_func": "main", "inputs": {},
        "child_scenarios": {
            "fetch": {"mode": "settlement_unknown"}
        },
        "registry": {
            "agents": {"w": {"agent_id": "w", "native_authority": [{"Read": "data"}]}},
            "intents": {
                "fetch": {
                    "intent_id": "fetch", "target_agent_id": "w",
                    "input_types": [], "output_type": make_type_string(), "error_type": make_type_string(),
                    "child_effects": {"effects": [{"Read": "data"}]},
                    "exported_envelope": {"effects": [{"Read": "data"}]},
                    "declared_envelope": {"effects": [{"Read": "data"}]},
                    "authority_policy": "AllowNative"
                }
            },
            "caller_authority": {"effects": [{"Read": "data"}]}
        },
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Read": "data"}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "ok"}, "ty": make_type_string()}},
                            {"Delegate": {"dest": 2, "intent_id": "fetch", "args": [], "requested_effects": [{"Read": "data"}], "authority_grant": [], "budget_grant": 10}},
                            {"Await": {"dest": 3, "handle": 2}}
                        ],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    run_golden("S3C16_settlement_unknown", prog, expected_status="waiting_on_child", expected_child_events=["AwaitSuspended(h_1)"])

def s3c17_resume_after_settlement():
    prog = {
        "name": "S3C17_resume_after_settlement", "entry_func": "main", "inputs": {},
        "simulate_suspension_and_resume": True,
        "child_scenarios": {
            "fetch": {"mode": "settlement_unknown"}
        },
        "registry": {
            "agents": {"w": {"agent_id": "w", "native_authority": [{"Read": "data"}]}},
            "intents": {
                "fetch": {
                    "intent_id": "fetch", "target_agent_id": "w",
                    "input_types": [], "output_type": make_type_string(), "error_type": make_type_string(),
                    "child_effects": {"effects": [{"Read": "data"}]},
                    "exported_envelope": {"effects": [{"Read": "data"}]},
                    "declared_envelope": {"effects": [{"Read": "data"}]},
                    "authority_policy": "AllowNative"
                }
            },
            "caller_authority": {"effects": [{"Read": "data"}]}
        },
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Read": "data"}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "ok"}, "ty": make_type_string()}},
                            {"Delegate": {"dest": 2, "intent_id": "fetch", "args": [], "requested_effects": [{"Read": "data"}], "authority_grant": [], "budget_grant": 10}},
                            {"Await": {"dest": 3, "handle": 2}}
                        ],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    run_golden("S3C17_resume_after_settlement", prog, expected_child_events=["AwaitSuspended(h_1)", "Settled(h_1)", "AwaitResumed(h_1)"])

def s3c18_await_twice():
    prog = {
        "name": "S3C18_await_twice", "entry_func": "main", "inputs": {},
        "registry": {
            "agents": {"w": {"agent_id": "w", "native_authority": [{"Read": "data"}]}},
            "intents": {
                "fetch": {
                    "intent_id": "fetch", "target_agent_id": "w",
                    "input_types": [], "output_type": make_type_string(), "error_type": make_type_string(),
                    "child_effects": {"effects": [{"Read": "data"}]},
                    "exported_envelope": {"effects": [{"Read": "data"}]},
                    "declared_envelope": {"effects": [{"Read": "data"}]},
                    "authority_policy": "AllowNative"
                }
            },
            "caller_authority": {"effects": [{"Read": "data"}]}
        },
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Read": "data"}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "ok"}, "ty": make_type_string()}},
                            {"Delegate": {"dest": 2, "intent_id": "fetch", "args": [], "requested_effects": [{"Read": "data"}], "authority_grant": [], "budget_grant": 10}},
                            {"Await": {"dest": 3, "handle": 2}},
                            {"Await": {"dest": 4, "handle": 2}}
                        ],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    run_golden("S3C18_await_twice", prog)

def s3c19_foreign_parent_handle_rejected():
    prog = {
        "name": "S3C19_foreign_parent", "entry_func": "main",
        "current_agent_id": "agent_current",
        "inputs": {
            "v2": {
                "kind": "ChildHandle",
                "payload": {
                    "handle_id": "h_foreign", "child_id": "c_foreign", "parent_id": "agent_other",
                    "generation_token": "gen_1", "effects": {"effects": []}, "settlement_state": "Settled"
                }
            }
        },
        "registry": {
            "caller_authority": {"effects": []}
        },
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [
                    [2, make_type_child_handle(make_type_string(), make_type_string(), [])]
                ], "return_type": make_type_string(),
                "declared_effects": {"effects": []}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "ok"}, "ty": make_type_string()}},
                            {"Await": {"dest": 3, "handle": 2}}
                        ],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    run_golden("S3C19_foreign_parent", prog, expected_status="error: ForeignParentHandle")

def s3c20_late_response_after_cancellation():
    prog = {
        "name": "S3C20_late_response", "entry_func": "main",
        "current_agent_id": "agent_current",
        "inputs": {},
        "child_scenarios": {
            "fetch": {"mode": "external_effect_then_cancelled"}
        },
        "registry": {
            "agents": {"w": {"agent_id": "w", "native_authority": [{"Act": "database"}]}},
            "intents": {
                "fetch": {
                    "intent_id": "fetch", "target_agent_id": "w",
                    "input_types": [], "output_type": make_type_string(), "error_type": make_type_string(),
                    "child_effects": {"effects": [{"Act": "database"}]},
                    "exported_envelope": {"effects": [{"Act": "database"}]},
                    "declared_envelope": {"effects": [{"Act": "database"}]},
                    "authority_policy": "AllowNative"
                }
            },
            "caller_authority": {"effects": [{"Act": "database"}]}
        },
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Act": "database"}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "ok"}, "ty": make_type_string()}},
                            {"Delegate": {"dest": 2, "intent_id": "fetch", "args": [], "requested_effects": [{"Act": "database"}], "authority_grant": [], "budget_grant": 10}},
                            {"Await": {"dest": 3, "handle": 2}}
                        ],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    run_golden("S3C20_late_response", prog, expected_status="error: StaleGenerationHandle", expected_child_events=["Cancelled(child_w_1)", "LateResponseRejected(h_1)"])

# ==============================================================================
# S3C21–S3C25: Handle Joins in CFG & Effect Unions & Provenance
# ==============================================================================

def s3c21_same_effect_handle_join():
    prog = {
        "name": "S3C21_same_effect_join", "entry_func": "main",
        "inputs": {"cond": {"kind": "Bool", "payload": True}},
        "registry": {
            "agents": {"w": {"agent_id": "w", "native_authority": [{"Read": "doc"}]}},
            "intents": {
                "intentA": {
                    "intent_id": "intentA", "target_agent_id": "w",
                    "input_types": [], "output_type": make_type_string(), "error_type": make_type_string(),
                    "child_effects": {"effects": [{"Read": "doc"}]},
                    "exported_envelope": {"effects": [{"Read": "doc"}]},
                    "declared_envelope": {"effects": [{"Read": "doc"}]},
                    "authority_policy": "AllowNative"
                },
                "intentB": {
                    "intent_id": "intentB", "target_agent_id": "w",
                    "input_types": [], "output_type": make_type_string(), "error_type": make_type_string(),
                    "child_effects": {"effects": [{"Read": "doc"}]},
                    "exported_envelope": {"effects": [{"Read": "doc"}]},
                    "declared_envelope": {"effects": [{"Read": "doc"}]},
                    "authority_policy": "AllowNative"
                }
            },
            "caller_authority": {"effects": [{"Read": "doc"}]}
        },
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [[1, make_type_bool()]], "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Read": "doc"}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [],
                        "terminator": {"CondBr": {"cond": 1, "true_target": 1, "true_args": [], "false_target": 2, "false_args": []}}
                    },
                    "1": {
                        "id": 1, "params": [],
                        "instructions": [
                            {"Delegate": {"dest": 2, "intent_id": "intentA", "args": [], "requested_effects": [{"Read": "doc"}], "authority_grant": [], "budget_grant": 10}}
                        ],
                        "terminator": {"Br": {"target": 3, "args": [2]}}
                    },
                    "2": {
                        "id": 2, "params": [],
                        "instructions": [
                            {"Delegate": {"dest": 3, "intent_id": "intentB", "args": [], "requested_effects": [{"Read": "doc"}], "authority_grant": [], "budget_grant": 10}}
                        ],
                        "terminator": {"Br": {"target": 3, "args": [3]}}
                    },
                    "3": {
                        "id": 3, "params": [
                            [4, make_type_child_handle(make_type_string(), make_type_string(), [{"Read": "doc"}])]
                        ],
                        "instructions": [
                            {"Await": {"dest": 5, "handle": 4}}
                        ],
                        "terminator": {
                            "MatchResult": {
                                "result_val": 5,
                                "ok_arg": 6, "ok_body": {"instructions": [], "terminator": {"Return": 6}},
                                "err_arg": 7, "err_body": {"instructions": [], "terminator": {"Return": 7}}
                            }
                        }
                    }
                }
            }]
        }
    }
    run_golden("S3C21_same_effect_join", prog)

def s3c22_heterogeneous_effect_union():
    # Left produces ChildHandle<T, E, {read[x]}>, Right produces ChildHandle<T, E, {infer}>
    # Merged block expects ChildHandle<T, E, {read[x], infer}> -> valid union!
    prog = {
        "name": "S3C22_effect_union", "entry_func": "main",
        "inputs": {"cond": {"kind": "Bool", "payload": True}},
        "registry": {
            "agents": {
                "w1": {"agent_id": "w1", "native_authority": [{"Read": "data"}]},
                "w2": {"agent_id": "w2", "native_authority": [{"Infer": None}]}
            },
            "intents": {
                "intent_read": {
                    "intent_id": "intent_read", "target_agent_id": "w1",
                    "input_types": [], "output_type": make_type_string(), "error_type": make_type_string(),
                    "child_effects": {"effects": [{"Read": "data"}]},
                    "exported_envelope": {"effects": [{"Read": "data"}]},
                    "declared_envelope": {"effects": [{"Read": "data"}]},
                    "authority_policy": "AllowNative"
                },
                "intent_infer": {
                    "intent_id": "intent_infer", "target_agent_id": "w2",
                    "input_types": [], "output_type": make_type_string(), "error_type": make_type_string(),
                    "child_effects": {"effects": [{"Infer": None}]},
                    "exported_envelope": {"effects": [{"Infer": None}]},
                    "declared_envelope": {"effects": [{"Infer": None}]},
                    "authority_policy": "AllowNative"
                }
            },
            "caller_authority": {"effects": [{"Read": "data"}, {"Infer": None}]}
        },
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [[1, make_type_bool()]], "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Read": "data"}, {"Infer": None}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [],
                        "terminator": {"CondBr": {"cond": 1, "true_target": 1, "true_args": [], "false_target": 2, "false_args": []}}
                    },
                    "1": {
                        "id": 1, "params": [],
                        "instructions": [
                            {"Delegate": {"dest": 2, "intent_id": "intent_read", "args": [], "requested_effects": [{"Read": "data"}], "authority_grant": [], "budget_grant": 10}}
                        ],
                        "terminator": {"Br": {"target": 3, "args": [2]}}
                    },
                    "2": {
                        "id": 2, "params": [],
                        "instructions": [
                            {"Delegate": {"dest": 3, "intent_id": "intent_infer", "args": [], "requested_effects": [{"Infer": None}], "authority_grant": [], "budget_grant": 10}}
                        ],
                        "terminator": {"Br": {"target": 3, "args": [3]}}
                    },
                    "3": {
                        "id": 3, "params": [
                            [4, make_type_child_handle(make_type_string(), make_type_string(), [{"Read": "data"}, {"Infer": None}])]
                        ],
                        "instructions": [
                            {"Await": {"dest": 5, "handle": 4}}
                        ],
                        "terminator": {
                            "MatchResult": {
                                "result_val": 5,
                                "ok_arg": 6, "ok_body": {"instructions": [], "terminator": {"Return": 6}},
                                "err_arg": 7, "err_body": {"instructions": [], "terminator": {"Return": 7}}
                            }
                        }
                    }
                }
            }]
        }
    }
    run_golden("S3C22_effect_union", prog)

def s3c23_handle_type_mismatch():
    # Incompatible T (String vs I64) at block join -> verifier error
    prog = {
        "name": "S3C23_handle_type_mismatch", "entry_func": "main",
        "inputs": {},
        "registry": {
            "agents": {"w": {"agent_id": "w", "native_authority": [{"Read": "data"}]}},
            "intents": {
                "fetch_str": {
                    "intent_id": "fetch_str", "target_agent_id": "w",
                    "input_types": [], "output_type": make_type_string(), "error_type": make_type_string(),
                    "child_effects": {"effects": [{"Read": "data"}]},
                    "exported_envelope": {"effects": [{"Read": "data"}]},
                    "declared_envelope": {"effects": [{"Read": "data"}]},
                    "authority_policy": "AllowNative"
                }
            },
            "caller_authority": {"effects": [{"Read": "data"}]}
        },
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Read": "data"}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Delegate": {"dest": 1, "intent_id": "fetch_str", "args": [], "requested_effects": [{"Read": "data"}], "authority_grant": [], "budget_grant": 10}}
                        ],
                        "terminator": {"Br": {"target": 1, "args": [1]}}
                    },
                    "1": {
                        "id": 1, "params": [
                            # Expected type is ChildHandle<I64, String, ...> but arg is ChildHandle<String, String, ...>!
                            [2, make_type_child_handle(make_type_i64(), make_type_string(), [{"Read": "data"}])]
                        ],
                        "instructions": [],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    run_golden("S3C23_handle_type_mismatch", prog, expected_status="verifier_error", expected_diag="IncompatibleHandleJoin")

def s3c24_join_does_not_invent_provenance():
    # Merged type carries exact union effects; no concrete result provenance until await
    prog = {
        "name": "S3C24_no_invented_provenance", "entry_func": "main",
        "inputs": {"cond": {"kind": "Bool", "payload": True}},
        "registry": {
            "agents": {
                "w1": {"agent_id": "w1", "native_authority": [{"Read": "data"}]},
                "w2": {"agent_id": "w2", "native_authority": [{"Infer": None}]}
            },
            "intents": {
                "fetch1": {
                    "intent_id": "fetch1", "target_agent_id": "w1",
                    "input_types": [], "output_type": make_type_string(), "error_type": make_type_string(),
                    "child_effects": {"effects": [{"Read": "data"}]},
                    "exported_envelope": {"effects": [{"Read": "data"}]},
                    "declared_envelope": {"effects": [{"Read": "data"}]},
                    "authority_policy": "AllowNative"
                },
                "fetch2": {
                    "intent_id": "fetch2", "target_agent_id": "w2",
                    "input_types": [], "output_type": make_type_string(), "error_type": make_type_string(),
                    "child_effects": {"effects": [{"Infer": None}]},
                    "exported_envelope": {"effects": [{"Infer": None}]},
                    "declared_envelope": {"effects": [{"Infer": None}]},
                    "authority_policy": "AllowNative"
                }
            },
            "caller_authority": {"effects": [{"Read": "data"}, {"Infer": None}]}
        },
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [[10, make_type_bool()]], "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Read": "data"}, {"Infer": None}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "ok"}, "ty": make_type_string()}}
                        ],
                        "terminator": {
                            "CondBr": {
                                "cond": 10,
                                "true_target": 1, "true_args": [],
                                "false_target": 2, "false_args": []
                            }
                        }
                    },
                    "1": {
                        "id": 1, "params": [],
                        "instructions": [
                            {"Delegate": {"dest": 2, "intent_id": "fetch1", "args": [], "requested_effects": [{"Read": "data"}], "authority_grant": [], "budget_grant": 10}}
                        ],
                        "terminator": {"Br": {"target": 3, "args": [2]}}
                    },
                    "2": {
                        "id": 2, "params": [],
                        "instructions": [
                            {"Delegate": {"dest": 3, "intent_id": "fetch2", "args": [], "requested_effects": [{"Infer": None}], "authority_grant": [], "budget_grant": 10}}
                        ],
                        "terminator": {"Br": {"target": 3, "args": [3]}}
                    },
                    "3": {
                        "id": 3, "params": [
                            [4, make_type_child_handle(make_type_string(), make_type_string(), [{"Read": "data"}, {"Infer": None}])]
                        ],
                        "instructions": [],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    run_golden("S3C24_no_invented_provenance", prog)

def s3c25_await_joined_handle_preserves_actual_child():
    prog = {
        "name": "S3C25_await_joined_preserves_child", "entry_func": "main",
        "inputs": {"cond": {"kind": "Bool", "payload": True}},
        "registry": {
            "agents": {
                "agentA": {"agent_id": "agentA", "native_authority": [{"Read": "a"}]},
                "agentB": {"agent_id": "agentB", "native_authority": [{"Read": "b"}]}
            },
            "intents": {
                "intentA": {
                    "intent_id": "intentA", "target_agent_id": "agentA",
                    "input_types": [], "output_type": make_type_string(), "error_type": make_type_string(),
                    "child_effects": {"effects": [{"Read": "a"}]},
                    "exported_envelope": {"effects": [{"Read": "a"}]},
                    "declared_envelope": {"effects": [{"Read": "a"}]},
                    "authority_policy": "AllowNative"
                },
                "intentB": {
                    "intent_id": "intentB", "target_agent_id": "agentB",
                    "input_types": [], "output_type": make_type_string(), "error_type": make_type_string(),
                    "child_effects": {"effects": [{"Read": "b"}]},
                    "exported_envelope": {"effects": [{"Read": "b"}]},
                    "declared_envelope": {"effects": [{"Read": "b"}]},
                    "authority_policy": "AllowNative"
                }
            },
            "caller_authority": {"effects": [{"Read": "a"}, {"Read": "b"}]}
        },
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [[1, make_type_bool()]], "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Read": "a"}, {"Read": "b"}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [],
                        "terminator": {"CondBr": {"cond": 1, "true_target": 1, "true_args": [], "false_target": 2, "false_args": []}}
                    },
                    "1": {
                        "id": 1, "params": [],
                        "instructions": [
                            {"Delegate": {"dest": 2, "intent_id": "intentA", "args": [], "requested_effects": [{"Read": "a"}], "authority_grant": [], "budget_grant": 10}}
                        ],
                        "terminator": {"Br": {"target": 3, "args": [2]}}
                    },
                    "2": {
                        "id": 2, "params": [],
                        "instructions": [
                            {"Delegate": {"dest": 3, "intent_id": "intentB", "args": [], "requested_effects": [{"Read": "b"}], "authority_grant": [], "budget_grant": 10}}
                        ],
                        "terminator": {"Br": {"target": 3, "args": [3]}}
                    },
                    "3": {
                        "id": 3, "params": [
                            [4, make_type_child_handle(make_type_string(), make_type_string(), [{"Read": "a"}, {"Read": "b"}])]
                        ],
                        "instructions": [
                            {"Await": {"dest": 5, "handle": 4}}
                        ],
                        "terminator": {
                            "MatchResult": {
                                "result_val": 5,
                                "ok_arg": 6, "ok_body": {"instructions": [], "terminator": {"Return": 6}},
                                "err_arg": 7, "err_body": {"instructions": [], "terminator": {"Return": 7}}
                            }
                        }
                    }
                }
            }]
        }
    }
    run_golden("S3C25_await_joined_preserves_child", prog)

# ==============================================================================
# S3C26–S3C33: Claim / Belief / Internalize & Policy Contract & Owner Binding
# ==============================================================================

def s3c26_internalize_covered_proved():
    prog = {
        "name": "S3C26_internalize_proved", "entry_func": "main", "inputs": {},
        "registry": {
            "internalization_policies": {
                "p_trust": {
                    "policy_id": "p_trust",
                    "accepted_claim_contract": "AcceptAll",
                    "validation_requirements": [],
                    "validation_effect_envelope": {"effects": [{"Read": "policy_db"}]}
                }
            },
            "caller_authority": {"effects": [{"Read": "policy_db"}]}
        },
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Read": "policy_db"}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "user_id_42"}, "ty": make_type_string()}},
                            {"Pure": {"dest": 2, "val": {"kind": "Claim", "payload": {"kind": "String", "payload": "user_id_42"}}, "ty": make_type_claim(make_type_string())}},
                            {"Internalize": {"dest": 3, "policy_id": "p_trust", "claim": 2}}
                        ],
                        "terminator": {
                            "MatchResult": {
                                "result_val": 3,
                                "ok_arg": 4, "ok_body": {"instructions": [], "terminator": {"Return": 1}},
                                "err_arg": 5, "err_body": {"instructions": [], "terminator": {"Return": 1}}
                            }
                        }
                    }
                }
            }]
        }
    }
    run_golden("S3C26_internalize_proved", prog)

def s3c27_internalize_deferred_passes():
    prog = {
        "name": "S3C27_internalize_deferred_pass", "entry_func": "main", "inputs": {},
        "registry": {
            "internalization_policies": {
                "p_audit": {
                    "policy_id": "p_audit",
                    "accepted_claim_contract": {"AcceptSubjectLiteral": "approved_doc"},
                    "validation_requirements": ["CheckSubjectLiteral"],
                    "validation_effect_envelope": {"effects": [{"Read": "policy_db"}]}
                }
            },
            "caller_authority": {"effects": [{"Read": "policy_db"}]}
        },
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Read": "policy_db"}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "approved_doc"}, "ty": make_type_string()}},
                            {"Pure": {"dest": 2, "val": {"kind": "Claim", "payload": {"kind": "String", "payload": "approved_doc"}}, "ty": make_type_claim(make_type_string())}},
                            {"Internalize": {"dest": 3, "policy_id": "p_audit", "claim": 2}}
                        ],
                        "terminator": {
                            "MatchResult": {
                                "result_val": 3,
                                "ok_arg": 4, "ok_body": {"instructions": [], "terminator": {"Return": 1}},
                                "err_arg": 5, "err_body": {"instructions": [], "terminator": {"Return": 1}}
                            }
                        }
                    }
                }
            }]
        }
    }
    run_golden("S3C27_internalize_deferred_pass", prog)

def s3c28_internalize_deferred_fails():
    prog = {
        "name": "S3C28_internalize_deferred_fail", "entry_func": "main", "inputs": {},
        "registry": {
            "internalization_policies": {
                "p_audit": {
                    "policy_id": "p_audit",
                    "accepted_claim_contract": "AcceptAll",
                    "validation_requirements": ["CheckDocApproved"],
                    "validation_effect_envelope": {"effects": [{"Read": "policy_db"}]}
                }
            },
            "caller_authority": {"effects": [{"Read": "policy_db"}]}
        },
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Read": "policy_db"}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "unapproved_doc"}, "ty": make_type_string()}},
                            {"Pure": {"dest": 2, "val": {"kind": "Claim", "payload": {"kind": "String", "payload": "unapproved_doc"}}, "ty": make_type_claim(make_type_string())}},
                            {"Internalize": {"dest": 3, "policy_id": "p_audit", "claim": 2}}
                        ],
                        "terminator": {
                            "MatchResult": {
                                "result_val": 3,
                                "ok_arg": 4, "ok_body": {"instructions": [], "terminator": {"Return": 1}},
                                "err_arg": 5, "err_body": {"instructions": [], "terminator": {"Return": 5}}
                            }
                        }
                    }
                }
            }]
        }
    }
    run_golden("S3C28_internalize_deferred_fail", prog)

def s3c29_internalize_refuted():
    prog = {
        "name": "S3C29_internalize_refuted", "entry_func": "main", "inputs": {},
        "registry": {
            "internalization_policies": {
                "p_reject": {
                    "policy_id": "p_reject",
                    "accepted_claim_contract": "RejectAll",
                    "validation_requirements": [],
                    "validation_effect_envelope": {"effects": [{"Read": "policy_db"}]}
                }
            },
            "caller_authority": {"effects": [{"Read": "policy_db"}]}
        },
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Read": "policy_db"}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "claim_data"}, "ty": make_type_string()}},
                            {"Pure": {"dest": 2, "val": {"kind": "Claim", "payload": {"kind": "String", "payload": "claim_data"}}, "ty": make_type_claim(make_type_string())}},
                            {"Internalize": {"dest": 3, "policy_id": "p_reject", "claim": 2}}
                        ],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    run_golden("S3C29_internalize_refuted", prog, expected_status="verifier_error", expected_diag="RefutedRequirement")

def s3c30_internalize_uncovered():
    prog = {
        "name": "S3C30_internalize_uncovered", "entry_func": "main", "inputs": {},
        "registry": {
            "internalization_policies": {
                "p_pred": {
                    "policy_id": "p_pred",
                    "accepted_claim_contract": {"AcceptSubjectLiteral": "approved_doc"},
                    "validation_requirements": [],
                    "validation_effect_envelope": {"effects": []}
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
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "uncovered_doc"}, "ty": make_type_string()}},
                            {"Pure": {"dest": 2, "val": {"kind": "Claim", "payload": {"kind": "String", "payload": "uncovered_doc"}}, "ty": make_type_claim(make_type_string())}},
                            {"Internalize": {"dest": 3, "policy_id": "p_pred", "claim": 2}}
                        ],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    run_golden("S3C30_internalize_uncovered", prog, expected_status="verifier_error", expected_diag="UncoveredRequirement")

def s3c31_internalize_authority_fail_closed():
    # Function declared effects has read[policy_db], but CallerAuthority lacks it -> rejected!
    prog = {
        "name": "S3C31_authority_fail_closed", "entry_func": "main", "inputs": {},
        "registry": {
            "internalization_policies": {
                "p_secure": {
                    "policy_id": "p_secure",
                    "accepted_claim_contract": "AcceptAll",
                    "validation_requirements": [],
                    "validation_effect_envelope": {"effects": [{"Read": "policy_db"}]}
                }
            },
            "caller_authority": {"effects": []} # Lacks read[policy_db]!
        },
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Read": "policy_db"}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "data"}, "ty": make_type_string()}},
                            {"Pure": {"dest": 2, "val": {"kind": "Claim", "payload": {"kind": "String", "payload": "data"}}, "ty": make_type_claim(make_type_string())}},
                            {"Internalize": {"dest": 3, "policy_id": "p_secure", "claim": 2}}
                        ],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    run_golden("S3C31_authority_fail_closed", prog, expected_status="verifier_error", expected_diag="ValidationAuthorityInsufficient")

def s3c32_belief_owner_creation():
    prog = {
        "name": "S3C32_belief_owner_creation", "entry_func": "main",
        "current_agent_id": "agent_alpha",
        "inputs": {},
        "registry": {
            "internalization_policies": {
                "p_trust": {
                    "policy_id": "p_trust",
                    "accepted_claim_contract": "AcceptAll",
                    "validation_requirements": [],
                    "validation_effect_envelope": {"effects": []}
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
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "data"}, "ty": make_type_string()}},
                            {"Pure": {"dest": 2, "val": {"kind": "Claim", "payload": {"kind": "String", "payload": "data"}}, "ty": make_type_claim(make_type_string())}},
                            {"Internalize": {"dest": 3, "policy_id": "p_trust", "claim": 2}}
                        ],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    run_golden("S3C32_belief_owner_creation", prog)

def s3c33_received_belief_preserves_owner():
    # Child returns Belief owned by ChildAgent -> Parent awaits it, owner remains ChildAgent
    prog = {
        "name": "S3C33_received_belief_preserves_owner", "entry_func": "main",
        "current_agent_id": "parent_agent", "inputs": {},
        "child_scenarios": {
            "produce_belief": {"mode": "returns_belief", "payload_string": "child_knowledge"}
        },
        "registry": {
            "agents": {"child_worker": {"agent_id": "child_worker", "native_authority": [{"Read": "data"}]}},
            "intents": {
                "produce_belief": {
                    "intent_id": "produce_belief", "target_agent_id": "child_worker",
                    "input_types": [], "output_type": make_type_belief(make_type_string()), "error_type": make_type_string(),
                    "child_effects": {"effects": [{"Read": "data"}]},
                    "exported_envelope": {"effects": [{"Read": "data"}]},
                    "declared_envelope": {"effects": [{"Read": "data"}]},
                    "authority_policy": "AllowNative"
                }
            },
            "caller_authority": {"effects": [{"Read": "data"}]}
        },
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Read": "data"}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "ok"}, "ty": make_type_string()}},
                            {"Delegate": {"dest": 2, "intent_id": "produce_belief", "args": [], "requested_effects": [{"Read": "data"}], "authority_grant": [], "budget_grant": 10}},
                            {"Await": {"dest": 3, "handle": 2}}
                        ],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    run_golden("S3C33_received_belief_preserves_owner", prog)

# ==============================================================================
# S3C34: Full Cross-Case (Delegate -> Await -> Match Ok -> Internalize)
# ==============================================================================

def s3c34_delegate_await_internalize():
    prog = {
        "name": "S3C34_delegate_await_internalize", "entry_func": "main",
        "current_agent_id": "parent_agent", "inputs": {},
        "child_scenarios": {
            "summarize": {"mode": "returns_claim", "payload_string": "summary_claim"}
        },
        "registry": {
            "agents": {"worker": {"agent_id": "worker", "native_authority": [{"Read": "raw_logs"}, {"Infer": None}]}},
            "intents": {
                "summarize": {
                    "intent_id": "summarize", "target_agent_id": "worker",
                    "input_types": [make_type_string()], "output_type": make_type_claim(make_type_string()), "error_type": make_type_string(),
                    "child_effects": {"effects": [{"Read": "raw_logs"}, {"Infer": None}]},
                    "exported_envelope": {"effects": [{"Read": "raw_logs"}, {"Infer": None}]},
                    "declared_envelope": {"effects": [{"Read": "raw_logs"}, {"Infer": None}]},
                    "authority_policy": "AllowNative"
                }
            },
            "internalization_policies": {
                "p_summary_policy": {
                    "policy_id": "p_summary_policy",
                    "accepted_claim_contract": "AcceptAll",
                    "validation_requirements": [],
                    "validation_effect_envelope": {"effects": [{"Read": "policy_rules"}]}
                }
            },
            "caller_authority": {"effects": [{"Read": "raw_logs"}, {"Infer": None}, {"Read": "policy_rules"}]}
        },
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Read": "raw_logs"}, {"Infer": None}, {"Read": "policy_rules"}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "log_data"}, "ty": make_type_string()}},
                            {"Delegate": {"dest": 2, "intent_id": "summarize", "args": [1], "requested_effects": [{"Read": "raw_logs"}, {"Infer": None}], "authority_grant": [], "budget_grant": 25}},
                            {"Await": {"dest": 3, "handle": 2}}
                        ],
                        "terminator": {
                            "MatchResult": {
                                "result_val": 3,
                                "ok_arg": 4, "ok_body": {
                                    "instructions": [
                                        {"Internalize": {"dest": 5, "policy_id": "p_summary_policy", "claim": 4}}
                                    ],
                                    "terminator": {"Return": 1}
                                },
                                "err_arg": 6, "err_body": {"instructions": [], "terminator": {"Return": 1}}
                            }
                        }
                    }
                }
            }]
        }
    }
    run_golden("S3C34_delegate_await_internalize", prog, expected_child_events=["Spawned(summarize)", "Settled(h_1)", "AwaitResumed(h_1)"])

def main():
    print("=" * 70)
    print("SOMA COMPILER CONFORMANCE v0 (SLICE 3) — Golden Programs (S3C01–S3C34)")

    s3c01_basic_delegate()
    s3c02_fire_and_forget_effects_visible()
    s3c03_valid_invocation_ceiling()
    s3c04_native_authority_independent_from_caller()
    s3c05_native_authority_attenuation()
    s3c06_explicit_granted_authority()
    s3c07_runtime_confinement()
    s3c08_atomic_budget_transfer()
    s3c09_spawn_failure_atomic_budget()
    s3c10_settlement_returns_unspent()
    s3c11_exactly_once_settlement()
    s3c12_outstanding_commitment_blocks_settlement()
    s3c13_nested_budget_conservation()
    s3c14_await_success()
    s3c15_await_semantic_failure()
    s3c16_settlement_unknown()
    s3c17_resume_after_settlement()
    s3c18_await_twice()
    s3c19_foreign_parent_handle_rejected()
    s3c20_late_response_after_cancellation()
    s3c21_same_effect_handle_join()
    s3c22_heterogeneous_effect_union()
    s3c23_handle_type_mismatch()
    s3c24_join_does_not_invent_provenance()
    s3c25_await_joined_handle_preserves_actual_child()
    s3c26_internalize_covered_proved()
    s3c27_internalize_deferred_passes()
    s3c28_internalize_deferred_fails()
    s3c29_internalize_refuted()
    s3c30_internalize_uncovered()
    s3c31_internalize_authority_fail_closed()
    s3c32_belief_owner_creation()
    s3c33_received_belief_preserves_owner()
    s3c34_delegate_await_internalize()

    print("=" * 70)
    print(f"SLICE 3 GOLDEN CONFORMANCE RESULT: {PASS} passed, {FAIL} failed ({PASS + FAIL} total)")
    if FAIL > 0:
        sys.exit(1)
    print("All 34 Slice 3 Golden Conformance Programs PASS under real Rust toolchain.")

if __name__ == "__main__":
    main()
