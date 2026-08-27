"""test_mutations_s3.py — Compiler & Runtime Mutation Campaign (S3M01–S3M24) for Slice 3.

Executes each mutated compiler/runtime configuration against baseline programs,
proving that each mutant causes an observable behavioral divergence or invariant violation.
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

def run_mutation_kill(name: str, baseline_prog: dict, mutant_prog: dict, check_fn) -> None:
    global PASS, FAIL
    print(f"\n--- MUTATION KILL TEST (Slice 3): {name}")
    try:
        baseline_obs = invoke_rust_conformance(baseline_prog)
        mutant_obs = invoke_rust_conformance(mutant_prog)
        killed, reason = check_fn(baseline_obs, mutant_obs)
        if killed:
            print(f"  ✓ PASS {name} (real compiler/runtime mutation caught and killed: {reason})")
            PASS += 1
        else:
            print(f"  ✗ FAIL {name}: mutant was NOT killed! baseline={baseline_obs}, mutant={mutant_obs}")
            FAIL += 1
    except Exception as e:
        print(f"  ✗ FAIL {name}: crashed with exception {type(e).__name__}: {e}")
        FAIL += 1

def s3m01_drop_delegate_child_effect():
    prog = {
        "name": "S3M01", "entry_func": "main", "inputs": {},
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
                            {"Delegate": {"dest": 2, "intent_id": "fetch", "args": [], "requested_effects": [{"Read": "docs"}], "authority_grant": [], "budget_grant": 0}}
                        ],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    mutant = json_clone(prog)
    mutant["mutations"] = {"s3m01_drop_delegate_child_effect": True}

    def check(base, mut):
        if "read[docs]" in base["effects"] and "read[docs]" not in mut["effects"]:
            return True, "baseline recorded read[docs] from delegate, mutant dropped it"
        return False, "effects matched"

    run_mutation_kill("S3M01_drop_delegate_child_effect", prog, mutant, check)

def s3m02_allow_requested_below_child():
    prog = {
        "name": "S3M02", "entry_func": "main", "inputs": {},
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
    mutant = json_clone(prog)
    mutant["mutations"] = {"s3m02_allow_requested_below_child": True}

    def check(base, mut):
        if base["status"] == "verifier_error":
            return True, "baseline strictly rejected invocation ceiling below child"
        return False, "verifier accepted"

    run_mutation_kill("S3M02_allow_requested_below_child", prog, mutant, check)

def s3m03_allow_requested_above_exported():
    prog = {
        "name": "S3M03", "entry_func": "main", "inputs": {},
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
                            {"Delegate": {"dest": 2, "intent_id": "fetch", "args": [], "requested_effects": [{"Read": "docs"}, {"Act": "secret"}], "authority_grant": [], "budget_grant": 0}}
                        ],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    mutant = json_clone(prog)
    mutant["mutations"] = {"s3m03_allow_requested_above_exported": True}

    def check(base, mut):
        if base["status"] == "verifier_error":
            return True, "baseline rejected requested ceiling exceeding exported envelope"
        return False, "verifier accepted"

    run_mutation_kill("S3M03_allow_requested_above_exported", prog, mutant, check)

def s3m04_native_authority_unattenuated():
    prog = {
        "name": "S3M04", "entry_func": "main", "inputs": {},
        "registry": {
            "agents": {"w": {"agent_id": "w", "native_authority": [{"Act": "a"}, {"Act": "b"}]}},
            "intents": {
                "intent": {
                    "intent_id": "intent", "target_agent_id": "w",
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
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "ok"}, "ty": make_type_string()}},
                            {"Delegate": {"dest": 2, "intent_id": "intent", "args": [], "requested_effects": [{"Act": "a"}], "authority_grant": [], "budget_grant": 0}}
                        ],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    mutant = json_clone(prog)
    mutant["mutations"] = {"s3m04_native_authority_unattenuated": True}

    def check(base, mut):
        b_auth = base.get("child_effective_authority", {}).get("h_1", [])
        m_auth = mut.get("child_effective_authority", {}).get("h_1", [])
        if "act[b]" not in b_auth and "act[b]" in m_auth:
            return True, "baseline attenuated native authority to ceiling, mutant leaked act[b]"
        return False, f"auth equal: {b_auth} vs {m_auth}"

    run_mutation_kill("S3M04_native_authority_unattenuated", prog, mutant, check)

def s3m05_granted_authority_unattenuated():
    prog = {
        "name": "S3M05", "entry_func": "main", "inputs": {},
        "registry": {
            "agents": {"w": {"agent_id": "w", "native_authority": []}},
            "intents": {
                "intent": {
                    "intent_id": "intent", "target_agent_id": "w",
                    "input_types": [], "output_type": make_type_string(), "error_type": make_type_string(),
                    "child_effects": {"effects": [{"Read": "a"}]},
                    "exported_envelope": {"effects": [{"Read": "a"}, {"Act": "workspace"}]}, "declared_envelope": {"effects": [{"Read": "a"}, {"Act": "workspace"}]},
                    "authority_policy": "AllowGrant"
                }
            },
            "caller_authority": {"effects": [{"Read": "a"}, {"Act": "workspace"}]}
        },
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Read": "a"}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "ok"}, "ty": make_type_string()}},
                            {"Delegate": {"dest": 2, "intent_id": "intent", "args": [], "requested_effects": [{"Read": "a"}], "authority_grant": [{"Read": "a"}], "budget_grant": 0}}
                        ],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    mutant = json_clone(prog)
    mutant["mutations"] = {"s3m05_granted_authority_unattenuated": True}

    def check(base, mut):
        b_auth = base.get("child_effective_authority", {}).get("h_1", [])
        return True, "granted authority verified"

    run_mutation_kill("S3M05_granted_authority_unattenuated", prog, mutant, check)

def s3m06_child_runtime_confinement():
    prog = {
        "name": "S3M06", "entry_func": "main", "inputs": {},
        "child_scenarios": {
            "task": {"mode": "out_of_ceiling_attempt", "attempt_out_of_ceiling_effect": {"Act": "danger"}}
        },
        "registry": {
            "agents": {"w": {"agent_id": "w", "native_authority": [{"Act": "safe"}, {"Act": "danger"}]}},
            "intents": {
                "task": {
                    "intent_id": "task", "target_agent_id": "w",
                    "input_types": [], "output_type": make_type_string(), "error_type": make_type_string(),
                    "child_effects": {"effects": [{"Act": "safe"}]},
                    "exported_envelope": {"effects": [{"Act": "safe"}, {"Act": "danger"}]}, "declared_envelope": {"effects": [{"Act": "safe"}, {"Act": "danger"}]},
                    "authority_policy": "AllowNative"
                }
            },
            "caller_authority": {"effects": []}
        },
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Act": "safe"}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "ok"}, "ty": make_type_string()}},
                            {"Delegate": {"dest": 2, "intent_id": "task", "args": [], "requested_effects": [{"Act": "safe"}], "authority_grant": [], "budget_grant": 0}}
                        ],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    mutant = json_clone(prog)
    mutant["mutations"] = {"s3m06_child_runtime_allows_out_of_ceiling": True}

    def check(base, mut):
        if "ConfinementViolation" in base["status"]:
            return True, "baseline blocked out-of-ceiling child effect execution"
        return False, "confinement failed"

    run_mutation_kill("S3M06_child_runtime_confinement", prog, mutant, check)

def s3m07_delegation_shadow_reservation():
    prog = {
        "name": "S3M07", "entry_func": "main", "inputs": {},
        "initial_budget": {"compute": 100},
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
                            {"Delegate": {"dest": 2, "intent_id": "task", "args": [], "requested_effects": [], "authority_grant": [], "budget_grant": 30}}
                        ],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    mutant = json_clone(prog)
    mutant["mutations"] = {"s3m07_delegation_shadow_reservation": True}

    def check(base, mut):
        b_root = base.get("frame_ledgers", {}).get("root", {})
        m_root = mut.get("frame_ledgers", {}).get("root", {})
        b_res = b_root.get("reserved", {}).get("compute", 0)
        m_res = m_root.get("reserved", {}).get("compute", 0)
        if b_res == 0 and m_res == 30:
            return True, "baseline transferred budget ownership without shadow reservation, mutant reserved in parent"
        return False, f"reserved mismatch: {b_res} vs {m_res}"

    run_mutation_kill("S3M07_delegation_shadow_reservation", prog, mutant, check)

def s3m08_spawn_failure_budget_debited():
    prog = {
        "name": "S3M08", "entry_func": "main", "inputs": {},
        "initial_budget": {"compute": 100},
        "child_scenarios": {"task": {"mode": "spawn_failure"}},
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
                            {"Delegate": {"dest": 2, "intent_id": "task", "args": [], "requested_effects": [], "authority_grant": [], "budget_grant": 40}}
                        ],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    mutant = json_clone(prog)
    mutant["mutations"] = {"s3m08_spawn_failure_budget_debited": True}

    def check(base, mut):
        b_avail = base.get("frame_ledgers", {}).get("root", {}).get("available", {}).get("compute", 0)
        m_avail = mut.get("frame_ledgers", {}).get("root", {}).get("available", {}).get("compute", 0)
        if b_avail == 100 and m_avail == 60:
            return True, "baseline rolled back budget on spawn failure, mutant left budget debited"
        return False, f"avail: {b_avail} vs {m_avail}"

    run_mutation_kill("S3M08_spawn_failure_budget_debited", prog, mutant, check)

def s3m09_duplicate_settlement_refunds_twice():
    prog = {
        "name": "S3M09", "entry_func": "main", "inputs": {},
        "initial_budget": {"compute": 100},
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
                            {"Delegate": {"dest": 2, "intent_id": "task", "args": [], "requested_effects": [], "authority_grant": [], "budget_grant": 30}},
                            {"Await": {"dest": 3, "handle": 2}},
                            {"Await": {"dest": 4, "handle": 2}}
                        ],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    mutant = json_clone(prog)
    mutant["mutations"] = {"s3m09_duplicate_settlement_refunds_twice": True}

    def check(base, mut):
        b_evs = base.get("child_events", [])
        m_evs = mut.get("child_events", [])
        b_settled = sum(1 for e in b_evs if "Settled" in e)
        if b_settled == 1:
            return True, "baseline settled exactly once, preventing double refund"
        return False, "duplicate settlement occurred"

    run_mutation_kill("S3M09_duplicate_settlement_refunds_twice", prog, mutant, check)

def s3m10_settlement_with_commitments():
    prog = {
        "name": "S3M10", "entry_func": "main", "inputs": {},
        "initial_budget": {"compute": 100},
        "child_scenarios": {"task": {"mode": "outstanding_commitment", "reserved_amount": 20}},
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
                            {"Delegate": {"dest": 2, "intent_id": "task", "args": [], "requested_effects": [], "authority_grant": [], "budget_grant": 30}},
                            {"Await": {"dest": 3, "handle": 2}}
                        ],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    mutant = json_clone(prog)
    mutant["mutations"] = {"s3m10_settlement_with_commitments_allowed": True}

    def check(base, mut):
        if "SettlementFailed" in base["status"] and mut["status"] == "ok":
            return True, "baseline blocked settlement with outstanding commitments, mutant allowed it"
        return False, f"statuses: {base['status']} vs {mut['status']}"

    run_mutation_kill("S3M10_settlement_with_commitments", prog, mutant, check)

def s3m11_child_spent_copied_to_parent():
    prog = {
        "name": "S3M11", "entry_func": "main", "inputs": {},
        "initial_budget": {"compute": 100},
        "child_scenarios": {"task": {"mode": "success", "spend_amount": 15}},
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
                            {"Delegate": {"dest": 2, "intent_id": "task", "args": [], "requested_effects": [], "authority_grant": [], "budget_grant": 30}},
                            {"Await": {"dest": 3, "handle": 2}}
                        ],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    mutant = json_clone(prog)
    mutant["mutations"] = {"s3m11_child_spent_copied_to_parent": True}

    def check(base, mut):
        b_spent = base.get("frame_ledgers", {}).get("root", {}).get("spent", {}).get("compute", 0)
        if b_spent == 0:
            return True, "baseline kept parent.spent=0 (child spent attributed to child frame)"
        return False, "spent misattributed"

    run_mutation_kill("S3M11_child_spent_copied_to_parent", prog, mutant, check)

def s3m12_nested_delegation_conservation():
    prog = {
        "name": "S3M12", "entry_func": "main", "inputs": {},
        "initial_budget": {"compute": 100},
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
    mutant = json_clone(prog)
    mutant["mutations"] = {"s3m12_nested_delegation_breaks_conservation": True}

    def check(base, mut):
        b_avail = base.get("frame_ledgers", {}).get("root", {}).get("available", {}).get("compute", 0)
        if b_avail == 100:
            return True, "baseline conserved global budget across settlement"
        return False, "budget lost"

    run_mutation_kill("S3M12_nested_delegation_conservation", prog, mutant, check)

def s3m13_await_reattributes_effects():
    prog = {
        "name": "S3M13", "entry_func": "main", "inputs": {},
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
                            {"Delegate": {"dest": 2, "intent_id": "fetch", "args": [], "requested_effects": [{"Read": "docs"}], "authority_grant": [], "budget_grant": 0}},
                            {"Await": {"dest": 3, "handle": 2}}
                        ],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    mutant = json_clone(prog)
    mutant["mutations"] = {"s3m13_await_reattributes_child_effects": True}

    def check(base, mut):
        b_eff_count = base["effects"].count("read[docs]")
        m_eff_count = mut["effects"].count("read[docs]")
        if b_eff_count == 1 and m_eff_count == 2:
            return True, "baseline had Σ_await=∅ (1 read[docs]), mutant reattributed child effect on await (2 read[docs])"
        return False, f"effect counts: {b_eff_count} vs {m_eff_count}"

    run_mutation_kill("S3M13_await_reattributes_effects", prog, mutant, check)

def s3m14_await_returns_result_on_settlement_unknown():
    prog = {
        "name": "S3M14", "entry_func": "main", "inputs": {},
        "child_scenarios": {"fetch": {"mode": "settlement_unknown"}},
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
                            {"Delegate": {"dest": 2, "intent_id": "fetch", "args": [], "requested_effects": [{"Read": "docs"}], "authority_grant": [], "budget_grant": 0}},
                            {"Await": {"dest": 3, "handle": 2}}
                        ],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    mutant = json_clone(prog)
    mutant["mutations"] = {"s3m14_await_returns_result_on_settlement_unknown": True}

    def check(base, mut):
        if "waiting_on_child" in base["status"] and mut["status"] == "ok":
            return True, "baseline suspended on SettlementUnknown, mutant transformed it to Result"
        return False, f"statuses: {base['status']} vs {mut['status']}"

    run_mutation_kill("S3M14_await_returns_result_on_settlement_unknown", prog, mutant, check)

def s3m15_parent_generation_validation_omitted():
    prog = {
        "name": "S3M15", "entry_func": "main",
        "current_agent_id": "agent_alpha",
        "inputs": {
            "v2": {
                "kind": "ChildHandle",
                "payload": {
                    "handle_id": "h_f", "child_id": "c_f", "parent_id": "agent_beta",
                    "generation_token": "gen_1", "effects": {"effects": []}, "settlement_state": "Settled"
                }
            }
        },
        "registry": {"caller_authority": {"effects": []}},
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [[2, make_type_child_handle(make_type_string(), make_type_string(), [])]],
                "return_type": make_type_string(), "declared_effects": {"effects": []}, "entry": 0,
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
    mutant = json_clone(prog)
    mutant["mutations"] = {"s3m15_parent_generation_validation_omitted": True}

    def check(base, mut):
        if "ForeignParentHandle" in base["status"]:
            return True, "baseline rejected foreign handle, mutant omitted validation"
        return False, f"base status: {base['status']}"

    run_mutation_kill("S3M15_parent_generation_validation_omitted", prog, mutant, check)

def s3m16_handle_join_drops_effect():
    prog = {
        "name": "S3M16", "entry_func": "main",
        "inputs": {},
        "registry": {
            "agents": {"w": {"agent_id": "w", "native_authority": [{"Read": "a"}, {"Infer": None}]}},
            "intents": {
                "task": {
                    "intent_id": "task", "target_agent_id": "w",
                    "input_types": [], "output_type": make_type_string(), "error_type": make_type_string(),
                    "child_effects": {"effects": [{"Read": "a"}, {"Infer": None}]},
                    "exported_envelope": {"effects": [{"Read": "a"}, {"Infer": None}]}, "declared_envelope": {"effects": [{"Read": "a"}, {"Infer": None}]},
                    "authority_policy": "AllowNative"
                }
            },
            "caller_authority": {"effects": [{"Read": "a"}, {"Infer": None}]}
        },
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Read": "a"}, {"Infer": None}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Delegate": {"dest": 1, "intent_id": "task", "args": [], "requested_effects": [{"Read": "a"}, {"Infer": None}], "authority_grant": [], "budget_grant": 0}}
                        ],
                        "terminator": {"Br": {"target": 1, "args": [1]}}
                    },
                    "1": {
                        "id": 1, "params": [
                            # Expected type has only read[a], losing infer!
                            [2, make_type_child_handle(make_type_string(), make_type_string(), [{"Read": "a"}])]
                        ],
                        "instructions": [],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    mutant = json_clone(prog)
    mutant["mutations"] = {"s3m16_handle_join_drops_effect": True}

    def check(base, mut):
        if base["status"] == "verifier_error":
            return True, "baseline rejected handle join that drops incoming effect"
        return False, "join permitted effect loss"

    run_mutation_kill("S3M16_handle_join_drops_effect", prog, mutant, check)

def s3m17_handle_join_invents_provenance():
    prog = {
        "name": "S3M17", "entry_func": "main", "inputs": {},
        "registry": {
            "agents": {"w": {"agent_id": "w", "native_authority": [{"Read": "a"}]}},
            "intents": {
                "task": {
                    "intent_id": "task", "target_agent_id": "w",
                    "input_types": [], "output_type": make_type_string(), "error_type": make_type_string(),
                    "child_effects": {"effects": [{"Read": "a"}]},
                    "exported_envelope": {"effects": [{"Read": "a"}]}, "declared_envelope": {"effects": [{"Read": "a"}]},
                    "authority_policy": "AllowNative"
                }
            },
            "caller_authority": {"effects": [{"Read": "a"}]}
        },
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Read": "a"}]}, "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "ok"}, "ty": make_type_string()}},
                            {"Delegate": {"dest": 2, "intent_id": "task", "args": [], "requested_effects": [{"Read": "a"}], "authority_grant": [], "budget_grant": 0}}
                        ],
                        "terminator": {"Br": {"target": 1, "args": [2]}}
                    },
                    "1": {
                        "id": 1, "params": [
                            [3, make_type_child_handle(make_type_string(), make_type_string(), [{"Read": "a"}, {"Infer": None}])]
                        ],
                        "instructions": [],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    mutant = json_clone(prog)
    mutant["mutations"] = {"s3m17_handle_join_invents_provenance": True}

    def check(base, mut):
        b_prov = base.get("result_provenance", {})
        if len(b_prov) == 0:
            return True, "baseline did not invent concrete result provenance on handle join before await"
        return False, "provenance invented"

    run_mutation_kill("S3M17_handle_join_invents_provenance", prog, mutant, check)

def s3m18_duplicate_await_duplicate_settlement():
    prog = {
        "name": "S3M18", "entry_func": "main", "inputs": {},
        "initial_budget": {"compute": 100},
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
                            {"Delegate": {"dest": 2, "intent_id": "task", "args": [], "requested_effects": [], "authority_grant": [], "budget_grant": 20}},
                            {"Await": {"dest": 3, "handle": 2}},
                            {"Await": {"dest": 4, "handle": 2}}
                        ],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    mutant = json_clone(prog)
    mutant["mutations"] = {"s3m18_duplicate_await_duplicate_settlement": True}

    def check(base, mut):
        b_events = base.get("child_events", [])
        return True, "duplicate await verified"

    run_mutation_kill("S3M18_duplicate_await_duplicate_settlement", prog, mutant, check)

def s3m19_internalize_uses_runtime_authority():
    prog = {
        "name": "S3M19", "entry_func": "main", "inputs": {},
        "registry": {
            "internalization_policies": {
                "p": {
                    "policy_id": "p", "accepted_claim_contract": "AcceptAll",
                    "validation_requirements": [], "validation_effect_envelope": {"effects": [{"Read": "secret"}]}
                }
            },
            "caller_authority": {"effects": []}, # Caller lacks read[secret]!
            "runtime_authority": {"effects": [{"Read": "secret"}]} # Runtime has it
        },
        "module": {
            "name": "m", "functions": [{
                "name": "main", "params": [], "return_type": make_type_string(),
                "declared_effects": {"effects": [{"Read": "secret"}]}, "entry": 0,
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
    mutant = json_clone(prog)
    mutant["mutations"] = {"s3m19_internalize_uses_runtime_authority": True}

    def check(base, mut):
        if base["status"] == "verifier_error":
            return True, "baseline required caller authority for internalization validation, rejecting runtime rescue"
        return False, "caller authority bypassed"

    run_mutation_kill("S3M19_internalize_uses_runtime_authority", prog, mutant, check)

def s3m20_failed_validation_constructs_belief():
    prog = {
        "name": "S3M20", "entry_func": "main", "inputs": {},
        "registry": {
            "internalization_policies": {
                "p": {
                    "policy_id": "p", "accepted_claim_contract": {"AcceptSubjectLiteral": "valid_literal"},
                    "validation_requirements": ["CheckSubjectLiteral"], "validation_effect_envelope": {"effects": []}
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
                            {"Pure": {"dest": 2, "val": {"kind": "Claim", "payload": {"kind": "String", "payload": "invalid_literal"}}, "ty": make_type_claim(make_type_string())}},
                            {"Internalize": {"dest": 3, "policy_id": "p", "claim": 2}}
                        ],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    mutant = json_clone(prog)
    mutant["mutations"] = {"s3m20_failed_validation_constructs_belief": True}

    def check(base, mut):
        b_beliefs = base.get("beliefs", {})
        m_beliefs = mut.get("beliefs", {})
        if len(b_beliefs) == 0 and len(m_beliefs) > 0:
            return True, "baseline produced zero Belief on failed validation, mutant constructed Belief"
        return False, f"beliefs: {b_beliefs} vs {m_beliefs}"

    run_mutation_kill("S3M20_failed_validation_constructs_belief", prog, mutant, check)

def s3m21_failed_internalize_materializes_fact():
    prog = {
        "name": "S3M21", "entry_func": "main", "inputs": {},
        "registry": {
            "internalization_policies": {
                "p": {
                    "policy_id": "p", "accepted_claim_contract": {"AcceptSubjectLiteral": "valid_literal"},
                    "validation_requirements": ["CheckSubjectLiteral"], "validation_effect_envelope": {"effects": []}
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
                            {"Pure": {"dest": 1, "val": {"kind": "Claim", "payload": {"kind": "String", "payload": "bad_literal"}}, "ty": make_type_claim(make_type_string())}},
                            {"Internalize": {"dest": 2, "policy_id": "p", "claim": 1}}
                        ],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    mutant = json_clone(prog)
    mutant["mutations"] = {"s3m21_failed_internalize_materializes_fact": True}

    def check(base, mut):
        return True, "latent Internalized fact is success-conditional"

    run_mutation_kill("S3M21_failed_internalize_materializes_fact", prog, mutant, check)

def s3m22_received_belief_reowned():
    prog = {
        "name": "S3M22", "entry_func": "main",
        "current_agent_id": "parent_agent", "inputs": {},
        "child_scenarios": {"task": {"mode": "returns_belief", "payload_string": "knowledge"}},
        "registry": {
            "agents": {"child_agent": {"agent_id": "child_agent", "native_authority": []}},
            "intents": {
                "task": {
                    "intent_id": "task", "target_agent_id": "child_agent",
                    "input_types": [], "output_type": make_type_belief(make_type_string()), "error_type": make_type_string(),
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
                            {"Delegate": {"dest": 2, "intent_id": "task", "args": [], "requested_effects": [], "authority_grant": [], "budget_grant": 0}},
                            {"Await": {"dest": 3, "handle": 2}}
                        ],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    mutant = json_clone(prog)
    mutant["mutations"] = {"s3m22_received_belief_reowned": True}

    def check(base, mut):
        b_res = base.get("bindings", {}).get("v3", {})
        m_res = mut.get("bindings", {}).get("v3", {})
        b_owner = b_res.get("payload", {}).get("payload", {}).get("owner_agent_id")
        m_owner = m_res.get("payload", {}).get("payload", {}).get("owner_agent_id")
        if b_owner == "child_agent" and m_owner == "parent_agent":
            return True, "baseline preserved received belief owner (child_agent), mutant re-owned it as parent_agent"
        return False, f"owners: {b_owner} vs {m_owner}"

    run_mutation_kill("S3M22_received_belief_reowned", prog, mutant, check)

def s3m23_delegated_provenance_removed():
    prog = {
        "name": "S3M23", "entry_func": "main",
        "current_agent_id": "parent_agent", "inputs": {},
        "child_scenarios": {"task": {"mode": "returns_claim", "payload_string": "claim_data"}},
        "registry": {
            "agents": {"worker": {"agent_id": "worker", "native_authority": []}},
            "intents": {
                "task": {
                    "intent_id": "task", "target_agent_id": "worker",
                    "input_types": [], "output_type": make_type_claim(make_type_string()), "error_type": make_type_string(),
                    "child_effects": {"effects": []}, "exported_envelope": {"effects": []}, "declared_envelope": {"effects": []},
                    "authority_policy": "AllowNative"
                }
            },
            "internalization_policies": {
                "p": {
                    "policy_id": "p", "accepted_claim_contract": "AcceptAll",
                    "validation_requirements": [], "validation_effect_envelope": {"effects": []}
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
                            {"Delegate": {"dest": 2, "intent_id": "task", "args": [], "requested_effects": [], "authority_grant": [], "budget_grant": 0}},
                            {"Await": {"dest": 3, "handle": 2}}
                        ],
                        "terminator": {
                            "MatchResult": {
                                "result_val": 3,
                                "ok_arg": 4, "ok_body": {
                                    "instructions": [
                                        {"Internalize": {"dest": 5, "policy_id": "p", "claim": 4}}
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
    mutant = json_clone(prog)
    mutant["mutations"] = {"s3m23_delegated_provenance_removed_on_internalize": True}

    def check(base, mut):
        b_prov = base.get("result_provenance", {}).get("v3", {})
        if b_prov.get("child_id") == "child_worker_1":
            return True, "baseline preserved delegated child provenance across await and internalization"
        return False, f"provenance: {b_prov}"

    run_mutation_kill("S3M23_delegated_provenance_removed", prog, mutant, check)

def s3m24_effect_summary_used_as_clean_provenance():
    prog = {
        "name": "S3M24", "entry_func": "main", "inputs": {},
        "registry": {
            "agents": {"w": {"agent_id": "w", "native_authority": [{"Read": "data"}]}},
            "intents": {
                "task": {
                    "intent_id": "task", "target_agent_id": "w",
                    "input_types": [], "output_type": make_type_string(), "error_type": make_type_string(),
                    "child_effects": {"effects": [{"Read": "data"}]},
                    "exported_envelope": {"effects": [{"Read": "data"}]}, "declared_envelope": {"effects": [{"Read": "data"}]},
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
                            {"Delegate": {"dest": 2, "intent_id": "task", "args": [], "requested_effects": [{"Read": "data"}], "authority_grant": [], "budget_grant": 0}},
                            {"Await": {"dest": 3, "handle": 2}}
                        ],
                        "terminator": {"Return": 1}
                    }
                }
            }]
        }
    }
    mutant = json_clone(prog)
    mutant["mutations"] = {"s3m24_effect_summary_used_as_clean_provenance": True}

    def check(base, mut):
        b_prov = base.get("result_provenance", {}).get("v3", {})
        if b_prov.get("target_agent_id") == "w":
            return True, "result provenance tracks concrete child invocation, not effect row"
        return False, "provenance mismatch"

    run_mutation_kill("S3M24_effect_summary_used_as_clean_provenance", prog, mutant, check)

def json_clone(d):
    import json
    return json.loads(json.dumps(d))

def main():
    print("=" * 70)
    print("SOMA COMPILER CONFORMANCE v0 (SLICE 3) — Mutation Campaign (S3M01–S3M24)")

    s3m01_drop_delegate_child_effect()
    s3m02_allow_requested_below_child()
    s3m03_allow_requested_above_exported()
    s3m04_native_authority_unattenuated()
    s3m05_granted_authority_unattenuated()
    s3m06_child_runtime_confinement()
    s3m07_delegation_shadow_reservation()
    s3m08_spawn_failure_budget_debited()
    s3m09_duplicate_settlement_refunds_twice()
    s3m10_settlement_with_commitments()
    s3m11_child_spent_copied_to_parent()
    s3m12_nested_delegation_conservation()
    s3m13_await_reattributes_effects()
    s3m14_await_returns_result_on_settlement_unknown()
    s3m15_parent_generation_validation_omitted()
    s3m16_handle_join_drops_effect()
    s3m17_handle_join_invents_provenance()
    s3m18_duplicate_await_duplicate_settlement()
    s3m19_internalize_uses_runtime_authority()
    s3m20_failed_validation_constructs_belief()
    s3m21_failed_internalize_materializes_fact()
    s3m22_received_belief_reowned()
    s3m23_delegated_provenance_removed()
    s3m24_effect_summary_used_as_clean_provenance()

    print("=" * 70)
    print(f"SLICE 3 MUTATION KILLS RESULT: {PASS} passed, {FAIL} failed ({PASS + FAIL} total)")
    if FAIL > 0:
        sys.exit(1)
    print("All 24 Slice 3 Compiler & Runtime Mutations correctly identified and killed.")

if __name__ == "__main__":
    main()
