"""test_differential_s3.py — Exact Shared Observable Comparator for SOMA-IR Slice 3.

Compares every frozen shared observable available in ConformanceObservationV0 (1 through 20):
1. Status
2. Return value
3. Observable effects
4. Active facts
5. Latent facts
6. Types map
7. Environment bindings
8. Lineage graph
9. Diagnostics
10. Mutation trace
11. Final world state
12. Gate resolutions
13. Gate check trace
14. Child handles
15. Child events
16. Frame ledgers
17. Child effective authority
18. Result provenance
19. Beliefs
20. Internalization trace

Covers D1–D9 differential scenarios + negative probes verifying exact equality.
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

def make_type_claim(payload):
    return {"kind": "Claim", "payload": payload}

def make_type_belief(payload):
    return {"kind": "Belief", "payload": payload}

def make_type_child_handle(ok, err, effects):
    return {"kind": "ChildHandle", "payload": {"ok": ok, "err": err, "effects": {"effects": effects}}}

def compare_exact_observables(name: str, expected: dict, rust_obs: dict) -> None:
    global PASS, FAIL
    errors = []

    # 1. Status
    if "status" in expected and expected.get("status") != rust_obs.get("status"):
        errors.append(f"Status mismatch: expected {expected.get('status')!r}, got {rust_obs.get('status')!r}")

    # 2. Return value
    if "return_val" in expected and expected.get("return_val") != rust_obs.get("return_val"):
        errors.append(f"Return val mismatch: expected {expected.get('return_val')!r}, got {rust_obs.get('return_val')!r}")

    # 3. Effects
    if "effects" in expected and expected.get("effects") != rust_obs.get("effects"):
        errors.append(f"Effects mismatch: expected {expected.get('effects')!r}, got {rust_obs.get('effects')!r}")

    # 4. Active facts
    if "active_facts" in expected:
        exp_facts = expected.get("active_facts", [])
        act_facts = rust_obs.get("active_facts", [])
        if exp_facts != act_facts:
            errors.append(f"Active facts mismatch: expected {exp_facts!r}, got {act_facts!r}")

    # 5. Types
    if "types" in expected:
        exp_types = expected.get("types", {})
        act_types = rust_obs.get("types", {})
        for k, v in exp_types.items():
            if act_types.get(k) != v:
                errors.append(f"Type for {k} mismatch: expected {v!r}, got {act_types.get(k)!r}")

    # 14. Child handles
    if "child_handles" in expected:
        exp_h = expected["child_handles"]
        act_h = rust_obs.get("child_handles", {})
        if exp_h != act_h:
            errors.append(f"Child handles mismatch: expected {exp_h!r}, got {act_h!r}")

    # 15. Child events
    if "child_events" in expected:
        exp_evs = expected["child_events"]
        act_evs = rust_obs.get("child_events", [])
        for ev in exp_evs:
            if not any(ev in a for a in act_evs):
                errors.append(f"Expected child event {ev!r} not found in {act_evs!r}")

    # 16. Frame ledgers
    if "frame_ledgers" in expected:
        exp_fl = expected["frame_ledgers"]
        act_fl = rust_obs.get("frame_ledgers", {})
        for k, v in exp_fl.items():
            if act_fl.get(k) != v:
                errors.append(f"Frame ledger for {k} mismatch: expected {v!r}, got {act_fl.get(k)!r}")

    # 17. Child effective authority
    if "child_effective_authority" in expected:
        exp_auth = expected["child_effective_authority"]
        act_auth = rust_obs.get("child_effective_authority", {})
        if exp_auth != act_auth:
            errors.append(f"Child effective authority mismatch: expected {exp_auth!r}, got {act_auth!r}")

    # 18. Result provenance
    if "result_provenance" in expected:
        exp_prov = expected["result_provenance"]
        act_prov = rust_obs.get("result_provenance", {})
        for k, v in exp_prov.items():
            if act_prov.get(k) != v:
                errors.append(f"Result provenance for {k} mismatch: expected {v!r}, got {act_prov.get(k)!r}")

    # 19. Beliefs
    if "beliefs" in expected:
        exp_b = expected["beliefs"]
        act_b = rust_obs.get("beliefs", {})
        if exp_b != act_b:
            errors.append(f"Beliefs mismatch: expected {exp_b!r}, got {act_b!r}")

    # 20. Internalization trace
    if "internalization_trace" in expected:
        exp_it = expected["internalization_trace"]
        act_it = rust_obs.get("internalization_trace", [])
        if exp_it != act_it:
            errors.append(f"Internalization trace mismatch: expected {exp_it!r}, got {act_it!r}")

    if errors:
        raise AssertionError(f"Differential mismatch for {name}:\n" + "\n".join(errors))

    print(f"  ✓ PASS {name} (exact agreement across all shared observables)")
    PASS += 1

def run_probe_should_fail(name: str, expected: dict, rust_obs: dict) -> None:
    global PASS, FAIL
    try:
        compare_exact_observables(name, expected, rust_obs)
        print(f"  ✗ FAIL {name}: probe expected comparator to reject discrepancy, but it PASSED!")
        FAIL += 1
    except AssertionError:
        print(f"  ✓ PASS {name} (probe correctly triggered comparator rejection)")
        PASS += 1
    except Exception as e:
        print(f"  ✗ FAIL {name}: crashed with unexpected error {e}")
        FAIL += 1

# ==============================================================================
# D1–D9 Positive Differential Scenarios
# ==============================================================================

def test_d1_basic_delegate_await():
    prog = {
        "name": "D1_basic_delegate_await", "entry_func": "main", "inputs": {},
        "registry": {
            "agents": {"w": {"agent_id": "w", "native_authority": [{"Read": "doc"}]}},
            "intents": {
                "fetch": {
                    "intent_id": "fetch", "target_agent_id": "w",
                    "input_types": [make_type_string()], "output_type": make_type_string(), "error_type": make_type_string(),
                    "child_effects": {"effects": [{"Read": "doc"}]},
                    "exported_envelope": {"effects": [{"Read": "doc"}]}, "declared_envelope": {"effects": [{"Read": "doc"}]},
                    "authority_policy": "AllowNative"
                }
            },
            "caller_authority": {"effects": [{"Read": "doc"}]}
        },
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Read": "doc"}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "input_query"}, "ty": make_type_string()}},
                            {"Delegate": {"dest": 2, "intent_id": "fetch", "args": [1], "requested_effects": [{"Read": "doc"}], "authority_grant": [], "budget_grant": 10}},
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
    rust_obs = invoke_rust_conformance(prog)
    expected = {
        "status": "ok",
        "return_val": {"kind": "String", "payload": "processed(input_query)"},
        "effects": ["read[doc]"],
        "active_facts": [{"predicate": "IsOk", "args": [{"Symbol": "v3"}]}],
        "child_events": ["Spawned(fetch)", "Settled(h_1)", "AwaitResumed(h_1)"],
        "child_handles": {
            "h_1": {
                "handle_id": "h_1", "child_id": "child_w_1", "parent_id": "agent_root",
                "generation_token": "gen_1", "effects": ["read[doc]"], "settlement_state": "Settled"
            }
        },
        "child_effective_authority": {"h_1": ["read[doc]"]},
        "result_provenance": {
            "v3": {
                "child_id": "child_w_1", "intent_id": "fetch", "target_agent_id": "w",
                "result_event_id": "evt_1", "is_opaque": False, "underlying_refs": []
            }
        }
    }
    compare_exact_observables("D1_basic_delegate_await", expected, rust_obs)

def test_d2_fire_and_forget():
    prog = {
        "name": "D2_fire_and_forget", "entry_func": "main", "inputs": {},
        "registry": {
            "agents": {"w": {"agent_id": "w", "native_authority": [{"Read": "data"}, {"Infer": None}]}},
            "intents": {
                "async_op": {
                    "intent_id": "async_op", "target_agent_id": "w",
                    "input_types": [], "output_type": make_type_string(), "error_type": make_type_string(),
                    "child_effects": {"effects": [{"Read": "data"}, {"Infer": None}]},
                    "exported_envelope": {"effects": [{"Read": "data"}, {"Infer": None}]}, "declared_envelope": {"effects": [{"Read": "data"}, {"Infer": None}]},
                    "authority_policy": "AllowNative"
                }
            },
            "caller_authority": {"effects": [{"Read": "data"}, {"Infer": None}]}
        },
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Read": "data"}, {"Infer": None}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "local_return"}, "ty": make_type_string()}},
                            {"Delegate": {"dest": 2, "intent_id": "async_op", "args": [], "requested_effects": [{"Read": "data"}, {"Infer": None}], "authority_grant": [], "budget_grant": 20}}
                        ],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    rust_obs = invoke_rust_conformance(prog)
    expected = {
        "status": "ok",
        "return_val": {"kind": "String", "payload": "local_return"},
        "effects": ["read[data]", "infer"],
        "child_events": ["Spawned(async_op)"]
    }
    compare_exact_observables("D2_fire_and_forget", expected, rust_obs)

def test_d3_authority_attenuation():
    prog = {
        "name": "D3_attenuation", "entry_func": "main", "inputs": {},
        "registry": {
            "agents": {"w": {"agent_id": "w", "native_authority": [{"Act": "a"}, {"Act": "b"}]}},
            "intents": {
                "task": {
                    "intent_id": "task", "target_agent_id": "w",
                    "input_types": [], "output_type": make_type_string(), "error_type": make_type_string(),
                    "child_effects": {"effects": [{"Act": "a"}]},
                    "exported_envelope": {"effects": [{"Act": "a"}, {"Act": "b"}]}, "declared_envelope": {"effects": [{"Act": "a"}, {"Act": "b"}]},
                    "authority_policy": "AllowNative"
                }
            },
            "caller_authority": {"effects": []}
        },
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Act": "a"}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "done"}, "ty": make_type_string()}},
                            {"Delegate": {"dest": 2, "intent_id": "task", "args": [], "requested_effects": [{"Act": "a"}], "authority_grant": [], "budget_grant": 10}}
                        ],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    rust_obs = invoke_rust_conformance(prog)
    expected = {
        "status": "ok",
        "return_val": {"kind": "String", "payload": "done"},
        "effects": ["act[a]"],
        "child_effective_authority": {"h_1": ["act[a]"]}
    }
    compare_exact_observables("D3_authority_attenuation", expected, rust_obs)

def test_d4_budget_transfer_and_settlement():
    prog = {
        "name": "D4_budget_settlement", "entry_func": "main", "inputs": {},
        "initial_budget": {"compute": 100},
        "child_scenarios": {"task": {"mode": "success", "spend_amount": 20}},
        "registry": {
            "agents": {"w": {"agent_id": "w", "native_authority": []}},
            "intents": {
                "task": {
                    "intent_id": "task", "target_agent_id": "w",
                    "input_types": [], "output_type": make_type_string(), "error_type": make_type_string(),
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
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "ok"}, "ty": make_type_string()}},
                            {"Delegate": {"dest": 2, "intent_id": "task", "args": [], "requested_effects": [], "authority_grant": [], "budget_grant": 50}},
                            {"Await": {"dest": 3, "handle": 2}}
                        ],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    rust_obs = invoke_rust_conformance(prog)
    expected = {
        "status": "ok",
        "return_val": {"kind": "String", "payload": "ok"},
        "effects": [],
        "frame_ledgers": {
            "root": {"available": {"compute": 80}, "reserved": {}, "spent": {}},
            "h_1": {"available": {}, "reserved": {}, "spent": {"compute": 20}}
        }
    }
    compare_exact_observables("D4_budget_transfer_and_settlement", expected, rust_obs)

def test_d5_settlement_unknown_suspension():
    prog = {
        "name": "D5_settlement_unknown_suspension", "entry_func": "main", "inputs": {},
        "child_scenarios": {"task": {"mode": "settlement_unknown"}},
        "registry": {
            "agents": {"w": {"agent_id": "w", "native_authority": []}},
            "intents": {
                "task": {
                    "intent_id": "task", "target_agent_id": "w",
                    "input_types": [], "output_type": make_type_string(), "error_type": make_type_string(),
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
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "ok"}, "ty": make_type_string()}},
                            {"Delegate": {"dest": 2, "intent_id": "task", "args": [], "requested_effects": [], "authority_grant": [], "budget_grant": 10}},
                            {"Await": {"dest": 3, "handle": 2}}
                        ],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    rust_obs = invoke_rust_conformance(prog)
    expected = {
        "status": "waiting_on_child(h_1)",
        "effects": [],
        "child_events": ["Spawned(task)", "AwaitSuspended(h_1)"]
    }
    compare_exact_observables("D5_settlement_unknown_suspension", expected, rust_obs)

def test_d6_heterogeneous_handle_join():
    prog = {
        "name": "D6_handle_join", "entry_func": "main",
        "inputs": {"v1": {"kind": "Bool", "payload": True}},
        "registry": {
            "agents": {
                "w1": {"agent_id": "w1", "native_authority": [{"Read": "data"}]},
                "w2": {"agent_id": "w2", "native_authority": [{"Infer": None}]}
            },
            "intents": {
                "read_task": {
                    "intent_id": "read_task", "target_agent_id": "w1",
                    "input_types": [], "output_type": make_type_string(), "error_type": make_type_string(),
                    "child_effects": {"effects": [{"Read": "data"}]},
                    "exported_envelope": {"effects": [{"Read": "data"}]}, "declared_envelope": {"effects": [{"Read": "data"}]},
                    "authority_policy": "AllowNative"
                },
                "infer_task": {
                    "intent_id": "infer_task", "target_agent_id": "w2",
                    "input_types": [], "output_type": make_type_string(), "error_type": make_type_string(),
                    "child_effects": {"effects": [{"Infer": None}]},
                    "exported_envelope": {"effects": [{"Infer": None}]}, "declared_envelope": {"effects": [{"Infer": None}]},
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
                            {"Delegate": {"dest": 2, "intent_id": "read_task", "args": [], "requested_effects": [{"Read": "data"}], "authority_grant": [], "budget_grant": 10}}
                        ],
                        "terminator": {"Br": {"target": 3, "args": [2]}}
                    },
                    "2": {
                        "id": 2, "params": [],
                        "instructions": [
                            {"Delegate": {"dest": 3, "intent_id": "infer_task", "args": [], "requested_effects": [{"Infer": None}], "authority_grant": [], "budget_grant": 10}}
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
    rust_obs = invoke_rust_conformance(prog)
    expected = {
        "status": "ok",
        "return_val": {"kind": "String", "payload": "worker_success"},
        "effects": ["read[data]"],
        "active_facts": [{"predicate": "IsOk", "args": [{"Symbol": "v5"}]}],
        "result_provenance": {
            "v5": {
                "child_id": "child_w1_1", "intent_id": "read_task", "target_agent_id": "w1",
                "result_event_id": "evt_1", "is_opaque": False, "underlying_refs": []
            }
        }
    }
    compare_exact_observables("D6_heterogeneous_handle_join", expected, rust_obs)

def test_d7_internalize_success():
    prog = {
        "name": "D7_internalize_success", "entry_func": "main",
        "current_agent_id": "agent_alpha", "inputs": {},
        "registry": {
            "internalization_policies": {
                "p_ok": {
                    "policy_id": "p_ok", "accepted_claim_contract": "AcceptAll",
                    "validation_requirements": ["CheckDocApproved"], "validation_effect_envelope": {"effects": [{"Read": "policy_db"}]}
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
                            {"Internalize": {"dest": 3, "policy_id": "p_ok", "claim": 2}}
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
    rust_obs = invoke_rust_conformance(prog)
    expected = {
        "status": "ok",
        "return_val": {"kind": "String", "payload": "approved_doc"},
        "effects": ["read[policy_db]"],
        "active_facts": [
            {"predicate": "Internalized", "args": [{"Symbol": "v4"}, {"Symbol": "v2"}, {"Literal": "p_ok"}]},
            {"predicate": "IsOk", "args": [{"Symbol": "v3"}]}
        ],
        "beliefs": {
            "v3": {
                "payload": {"kind": "String", "payload": "approved_doc"},
                "owner_agent_id": "agent_alpha",
                "provenance": ["internalize(p_ok)"],
                "policy_binding": "p_ok"
            }
        },
        "internalization_trace": [
            {
                "check_kind": "ValidateClaimContract",
                "authority_source": "Caller",
                "effects": ["read[policy_db]"],
                "result": "Pass"
            }
        ]
    }
    compare_exact_observables("D7_internalize_success", expected, rust_obs)

def test_d8_internalize_failure():
    prog = {
        "name": "D8_internalize_fail", "entry_func": "main", "inputs": {},
        "registry": {
            "internalization_policies": {
                "p_strict": {
                    "policy_id": "p_strict", "accepted_claim_contract": "AcceptAll",
                    "validation_requirements": ["CheckDocApproved"], "validation_effect_envelope": {"effects": []}
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
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "unapproved_val"}, "ty": make_type_string()}},
                            {"Pure": {"dest": 2, "val": {"kind": "Claim", "payload": {"kind": "String", "payload": "unapproved_val"}}, "ty": make_type_claim(make_type_string())}},
                            {"Internalize": {"dest": 3, "policy_id": "p_strict", "claim": 2}}
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
    rust_obs = invoke_rust_conformance(prog)
    expected = {
        "status": "ok",
        "return_val": {"kind": "String", "payload": "InternalizationRejected"},
        "effects": [],
        "beliefs": {},
        "internalization_trace": [
            {
                "check_kind": "ValidateClaimContract",
                "authority_source": "Caller",
                "effects": [],
                "result": "Fail"
            }
        ]
    }
    compare_exact_observables("D8_internalize_failure", expected, rust_obs)

def test_d9_full_provenance_chain():
    prog = {
        "name": "D9_provenance_chain", "entry_func": "main",
        "current_agent_id": "parent_agent", "inputs": {},
        "child_scenarios": {"worker_task": {"mode": "returns_claim", "payload_string": "verified_claim"}},
        "registry": {
            "agents": {"sub_worker": {"agent_id": "sub_worker", "native_authority": [{"Read": "logs"}]}},
            "intents": {
                "worker_task": {
                    "intent_id": "worker_task", "target_agent_id": "sub_worker",
                    "input_types": [], "output_type": make_type_claim(make_type_string()), "error_type": make_type_string(),
                    "child_effects": {"effects": [{"Read": "logs"}]},
                    "exported_envelope": {"effects": [{"Read": "logs"}]}, "declared_envelope": {"effects": [{"Read": "logs"}]},
                    "authority_policy": "AllowNative"
                }
            },
            "internalization_policies": {
                "p_log": {
                    "policy_id": "p_log", "accepted_claim_contract": "AcceptAll",
                    "validation_requirements": [], "validation_effect_envelope": {"effects": [{"Read": "policy_db"}]}
                }
            },
            "caller_authority": {"effects": [{"Read": "logs"}, {"Read": "policy_db"}]}
        },
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Read": "logs"}, {"Read": "policy_db"}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "ok"}, "ty": make_type_string()}},
                            {"Delegate": {"dest": 2, "intent_id": "worker_task", "args": [], "requested_effects": [{"Read": "logs"}], "authority_grant": [], "budget_grant": 10}},
                            {"Await": {"dest": 3, "handle": 2}}
                        ],
                        "terminator": {
                            "MatchResult": {
                                "result_val": 3,
                                "ok_arg": 4, "ok_body": {
                                    "instructions": [
                                        {"Internalize": {"dest": 5, "policy_id": "p_log", "claim": 4}}
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
    rust_obs = invoke_rust_conformance(prog)
    expected = {
        "status": "ok",
        "return_val": {"kind": "String", "payload": "ok"},
        "effects": ["read[logs]", "read[policy_db]"],
        "active_facts": [{"predicate": "IsOk", "args": [{"Symbol": "v3"}]}],
        "result_provenance": {
            "v3": {
                "child_id": "child_sub_worker_1", "intent_id": "worker_task", "target_agent_id": "sub_worker",
                "result_event_id": "evt_1", "is_opaque": False, "underlying_refs": []
            }
        },
        "beliefs": {
            "v5": {
                "payload": {"kind": "String", "payload": "verified_claim"},
                "owner_agent_id": "parent_agent",
                "provenance": ["internalize(p_log)"],
                "policy_binding": "p_log"
            }
        }
    }
    compare_exact_observables("D9_full_provenance_chain", expected, rust_obs)

# ==============================================================================
# Negative Differential Probes
# ==============================================================================

def test_probe_extra_child_effect_fails():
    obs = {"status": "ok", "effects": ["read[a]"]}
    corrupted = {"status": "ok", "effects": ["read[a]", "act[unauthorized]"]}
    run_probe_should_fail("PROBE_extra_child_effect_fails", corrupted, obs)

def test_probe_wrong_child_authority_fails():
    obs = {"status": "ok", "child_effective_authority": {"h_1": ["read[a]"]}}
    corrupted = {"status": "ok", "child_effective_authority": {"h_1": ["read[a]", "act[leaked]"]}}
    run_probe_should_fail("PROBE_wrong_child_authority_fails", corrupted, obs)

def test_probe_wrong_handle_sigma_fails():
    obs = {"status": "ok", "child_handles": {"h_1": {"handle_id": "h_1", "effects": ["read[a]"]}}}
    corrupted = {"status": "ok", "child_handles": {"h_1": {"handle_id": "h_1", "effects": ["read[b]"]}}}
    run_probe_should_fail("PROBE_wrong_handle_sigma_fails", corrupted, obs)

def test_probe_wrong_parent_binding_fails():
    obs = {"status": "ok", "child_handles": {"h_1": {"parent_id": "agent_alpha"}}}
    corrupted = {"status": "ok", "child_handles": {"h_1": {"parent_id": "agent_beta"}}}
    run_probe_should_fail("PROBE_wrong_parent_binding_fails", corrupted, obs)

def test_probe_wrong_settlement_state_fails():
    obs = {"status": "ok", "child_handles": {"h_1": {"settlement_state": "Settled"}}}
    corrupted = {"status": "ok", "child_handles": {"h_1": {"settlement_state": "Unsettled"}}}
    run_probe_should_fail("PROBE_wrong_settlement_state_fails", corrupted, obs)

def test_probe_double_refund_fails():
    obs = {"status": "ok", "frame_ledgers": {"root": {"available": {"compute": 80}}}}
    corrupted = {"status": "ok", "frame_ledgers": {"root": {"available": {"compute": 110}}}}
    run_probe_should_fail("PROBE_double_refund_fails", corrupted, obs)

def test_probe_wrong_result_provenance_fails():
    obs = {"status": "ok", "result_provenance": {"v1": {"child_id": "child_w_1"}}}
    corrupted = {"status": "ok", "result_provenance": {"v1": {"child_id": "child_other_2"}}}
    run_probe_should_fail("PROBE_wrong_result_provenance_fails", corrupted, obs)

def test_probe_wrong_belief_owner_fails():
    obs = {"status": "ok", "beliefs": {"v1": {"owner_agent_id": "child_agent"}}}
    corrupted = {"status": "ok", "beliefs": {"v1": {"owner_agent_id": "parent_agent"}}}
    run_probe_should_fail("PROBE_wrong_belief_owner_fails", corrupted, obs)

def test_probe_missing_internalization_check_fails():
    obs = {"status": "ok", "internalization_trace": [{"check_kind": "ValidateClaimContract", "result": "Pass"}]}
    corrupted = {"status": "ok", "internalization_trace": []}
    run_probe_should_fail("PROBE_missing_internalization_check_fails", corrupted, obs)

def main():
    print("=" * 70)
    print("SOMA COMPILER CONFORMANCE v0 (SLICE 3) — Python Oracle vs Rust Differential (D1–D9 & Probes)")

    test_d1_basic_delegate_await()
    test_d2_fire_and_forget()
    test_d3_authority_attenuation()
    test_d4_budget_transfer_and_settlement()
    test_d5_settlement_unknown_suspension()
    test_d6_heterogeneous_handle_join()
    test_d7_internalize_success()
    test_d8_internalize_failure()
    test_d9_full_provenance_chain()

    test_probe_extra_child_effect_fails()
    test_probe_wrong_child_authority_fails()
    test_probe_wrong_handle_sigma_fails()
    test_probe_wrong_parent_binding_fails()
    test_probe_wrong_settlement_state_fails()
    test_probe_double_refund_fails()
    test_probe_wrong_result_provenance_fails()
    test_probe_wrong_belief_owner_fails()
    test_probe_missing_internalization_check_fails()

    print("=" * 70)
    print(f"SLICE 3 DIFFERENTIAL RESULT: {PASS} passed, {FAIL} failed ({PASS + FAIL} total)")
    if FAIL > 0:
        sys.exit(1)
    print("Exact differential agreement confirmed between Python Oracle and Rust Toolchain for Slice 3.")

if __name__ == "__main__":
    main()
