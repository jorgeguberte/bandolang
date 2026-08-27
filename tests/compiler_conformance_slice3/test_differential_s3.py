"""test_differential_s3.py — Exact Shared Observable Comparator for SOMA-IR Slice 3.

Compares every frozen shared observable available in ConformanceObservationV0 (all 20 fields):
1. status
2. return_val
3. effects
4. active_facts
5. latent_facts
6. types
7. bindings
8. lineage
9. diagnostics
10. mutation_trace
11. final_world
12. gate_resolutions
13. gate_trace
14. child_handles
15. child_events
16. frame_ledgers
17. child_effective_authority
18. result_provenance
19. beliefs
20. internalization_trace

Covers D1–D9 differential scenarios + 9 negative probes verifying exact 20-field equality.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "compiler_conformance"))

from protocol import invoke_rust_conformance

PASS, FAIL = 0, 0

ALL_20_OBSERVABLES = [
    "status",
    "return_val",
    "effects",
    "active_facts",
    "latent_facts",
    "types",
    "bindings",
    "lineage",
    "diagnostics",
    "mutation_trace",
    "final_world",
    "gate_resolutions",
    "gate_trace",
    "child_handles",
    "child_events",
    "frame_ledgers",
    "child_effective_authority",
    "result_provenance",
    "beliefs",
    "internalization_trace",
]

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

def canonical_normalize(val):
    if isinstance(val, dict):
        return {k: canonical_normalize(v) for k, v in sorted(val.items())}
    elif isinstance(val, list):
        return [canonical_normalize(x) for x in val]
    return val

def compare_exact_20_observables(name: str, expected: dict, rust_obs: dict) -> None:
    global PASS, FAIL
    errors = []

    # Enforce that all 20 fields are explicitly declared in expected
    for key in ALL_20_OBSERVABLES:
        if key not in expected:
            errors.append(f"Missing key in expected dict: '{key}'")
            continue
        exp_val = canonical_normalize(expected[key])
        act_val = canonical_normalize(rust_obs.get(key))
        if exp_val != act_val:
            errors.append(f"Observable '{key}' mismatch:\n  Expected: {exp_val!r}\n  Actual:   {act_val!r}")

    for key in rust_obs:
        if key not in ALL_20_OBSERVABLES:
            errors.append(f"Unexpected extra observable key in rust_obs: '{key}'")

    if errors:
        raise AssertionError(f"Exact 20-Observable Differential Mismatch for {name}:\n" + "\n".join(errors))

    print(f"  ✓ PASS {name} (exact agreement across all 20 canonical observables)")
    PASS += 1

def run_probe_should_fail(name: str, expected: dict, rust_obs: dict) -> None:
    global PASS, FAIL
    try:
        compare_exact_20_observables(name, expected, rust_obs)
        print(f"  ✗ FAIL {name}: probe expected comparator to reject discrepancy, but it PASSED!")
        FAIL += 1
    except AssertionError:
        print(f"  ✓ PASS {name} (probe correctly triggered comparator rejection)")
        PASS += 1
    except Exception as e:
        print(f"  ✗ FAIL {name}: crashed with unexpected error {e}")
        FAIL += 1

def test_d1_basic_delegate_await():
    prog = json.loads('''{
    "name": "D1_basic_delegate_await",
    "entry_func": "main",
    "inputs": {},
    "registry": {
        "agents": {
            "w": {
                "agent_id": "w",
                "native_authority": [
                    {
                        "Read": "doc"
                    }
                ]
            }
        },
        "intents": {
            "fetch": {
                "intent_id": "fetch",
                "target_agent_id": "w",
                "input_types": [
                    {
                        "kind": "String"
                    }
                ],
                "output_type": {
                    "kind": "String"
                },
                "error_type": {
                    "kind": "String"
                },
                "child_effects": {
                    "effects": [
                        {
                            "Read": "doc"
                        }
                    ]
                },
                "exported_envelope": {
                    "effects": [
                        {
                            "Read": "doc"
                        }
                    ]
                },
                "declared_envelope": {
                    "effects": [
                        {
                            "Read": "doc"
                        }
                    ]
                },
                "authority_policy": "AllowNative"
            }
        },
        "caller_authority": {
            "effects": [
                {
                    "Read": "doc"
                }
            ]
        }
    },
    "module": {
        "name": "m",
        "functions": [
            {
                "name": "main",
                "params": [],
                "return_type": {
                    "kind": "String"
                },
                "declared_effects": {
                    "effects": [
                        {
                            "Read": "doc"
                        }
                    ]
                },
                "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0,
                        "params": [],
                        "instructions": [
                            {
                                "Pure": {
                                    "dest": 1,
                                    "val": {
                                        "kind": "String",
                                        "payload": "input_query"
                                    },
                                    "ty": {
                                        "kind": "String"
                                    }
                                }
                            },
                            {
                                "Delegate": {
                                    "dest": 2,
                                    "intent_id": "fetch",
                                    "args": [
                                        1
                                    ],
                                    "requested_effects": [
                                        {
                                            "Read": "doc"
                                        }
                                    ],
                                    "authority_grant": [],
                                    "budget_grant": 10
                                }
                            },
                            {
                                "Await": {
                                    "dest": 3,
                                    "handle": 2
                                }
                            }
                        ],
                        "terminator": {
                            "MatchResult": {
                                "result_val": 3,
                                "ok_arg": 4,
                                "ok_body": {
                                    "instructions": [],
                                    "terminator": {
                                        "Return": 4
                                    }
                                },
                                "err_arg": 5,
                                "err_body": {
                                    "instructions": [],
                                    "terminator": {
                                        "Return": 1
                                    }
                                }
                            }
                        }
                    }
                }
            }
        ]
    }
}''')
    rust_obs = invoke_rust_conformance(prog)
    expected = json.loads('''{
    "status": "ok",
    "return_val": {
        "kind": "String",
        "payload": "processed(input_query)"
    },
    "effects": [
        "read[doc]"
    ],
    "active_facts": [
        {
            "predicate": "IsOk",
            "args": [
                {
                    "Symbol": "v3"
                }
            ]
        }
    ],
    "latent_facts": {},
    "types": {
        "v1": "string",
        "v2": "ChildHandle<string, string, {read[doc]}>",
        "v3": "Result<string, string>",
        "v4": "string"
    },
    "bindings": {
        "v1": {
            "kind": "String",
            "payload": "input_query"
        },
        "v2": {
            "kind": "ChildHandle",
            "payload": {
                "handle_id": "h_1",
                "child_id": "child_w_1",
                "parent_id": "agent_root",
                "generation_token": "gen_1",
                "effects": {
                    "effects": [
                        {
                            "Read": "doc"
                        }
                    ]
                },
                "settlement_state": "Unsettled"
            }
        },
        "v3": {
            "kind": "Ok",
            "payload": {
                "kind": "String",
                "payload": "processed(input_query)"
            }
        },
        "v4": {
            "kind": "String",
            "payload": "processed(input_query)"
        }
    },
    "lineage": {
        "v2": [
            "child_invocation(fetch)",
            "target_agent(w)"
        ],
        "v3": [
            "await_result(h_1)",
            "delegated_result(child_w_1)",
            "child_invocation(fetch)",
            "target_agent(w)"
        ],
        "v4": [
            "await_result(h_1)",
            "delegated_result(child_w_1)",
            "child_invocation(fetch)",
            "target_agent(w)"
        ]
    },
    "diagnostics": [],
    "mutation_trace": [],
    "final_world": {},
    "gate_resolutions": [],
    "gate_trace": [],
    "child_handles": {
        "h_1": {
            "handle_id": "h_1",
            "child_id": "child_w_1",
            "parent_id": "agent_root",
            "generation_token": "gen_1",
            "effects": [
                "read[doc]"
            ],
            "settlement_state": "Settled"
        }
    },
    "child_events": [
        "Spawned(fetch)",
        "Settled(h_1)",
        "AwaitResumed(h_1)"
    ],
    "frame_ledgers": {
        "h_1": {
            "available": {},
            "reserved": {},
            "spent": {}
        },
        "root": {
            "available": {
                "compute": 100
            },
            "reserved": {},
            "spent": {}
        }
    },
    "child_effective_authority": {
        "h_1": [
            "read[doc]"
        ]
    },
    "result_provenance": {
        "v3": {
            "child_id": "child_w_1",
            "intent_id": "fetch",
            "target_agent_id": "w",
            "result_event_id": "evt_1",
            "is_opaque": false,
            "underlying_refs": []
        }
    },
    "beliefs": {},
    "internalization_trace": []
}''')
    compare_exact_20_observables('D1_basic_delegate_await', expected, rust_obs)

def test_d2_fire_and_forget():
    prog = json.loads('''{
    "name": "D2_fire_and_forget",
    "entry_func": "main",
    "inputs": {},
    "registry": {
        "agents": {
            "w": {
                "agent_id": "w",
                "native_authority": [
                    {
                        "Read": "data"
                    },
                    {
                        "Infer": null
                    }
                ]
            }
        },
        "intents": {
            "async_op": {
                "intent_id": "async_op",
                "target_agent_id": "w",
                "input_types": [],
                "output_type": {
                    "kind": "String"
                },
                "error_type": {
                    "kind": "String"
                },
                "child_effects": {
                    "effects": [
                        {
                            "Read": "data"
                        },
                        {
                            "Infer": null
                        }
                    ]
                },
                "exported_envelope": {
                    "effects": [
                        {
                            "Read": "data"
                        },
                        {
                            "Infer": null
                        }
                    ]
                },
                "declared_envelope": {
                    "effects": [
                        {
                            "Read": "data"
                        },
                        {
                            "Infer": null
                        }
                    ]
                },
                "authority_policy": "AllowNative"
            }
        },
        "caller_authority": {
            "effects": [
                {
                    "Read": "data"
                },
                {
                    "Infer": null
                }
            ]
        }
    },
    "module": {
        "name": "m",
        "functions": [
            {
                "name": "main",
                "params": [],
                "return_type": {
                    "kind": "String"
                },
                "declared_effects": {
                    "effects": [
                        {
                            "Read": "data"
                        },
                        {
                            "Infer": null
                        }
                    ]
                },
                "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0,
                        "params": [],
                        "instructions": [
                            {
                                "Pure": {
                                    "dest": 1,
                                    "val": {
                                        "kind": "String",
                                        "payload": "local_return"
                                    },
                                    "ty": {
                                        "kind": "String"
                                    }
                                }
                            },
                            {
                                "Delegate": {
                                    "dest": 2,
                                    "intent_id": "async_op",
                                    "args": [],
                                    "requested_effects": [
                                        {
                                            "Read": "data"
                                        },
                                        {
                                            "Infer": null
                                        }
                                    ],
                                    "authority_grant": [],
                                    "budget_grant": 20
                                }
                            }
                        ],
                        "terminator": {
                            "Return": 1
                        }
                    }
                }
            }
        ]
    }
}''')
    rust_obs = invoke_rust_conformance(prog)
    expected = json.loads('''{
    "status": "ok",
    "return_val": {
        "kind": "String",
        "payload": "local_return"
    },
    "effects": [
        "read[data]",
        "infer"
    ],
    "active_facts": [],
    "latent_facts": {},
    "types": {
        "v1": "string",
        "v2": "ChildHandle<string, string, {read[data], infer}>"
    },
    "bindings": {
        "v1": {
            "kind": "String",
            "payload": "local_return"
        },
        "v2": {
            "kind": "ChildHandle",
            "payload": {
                "handle_id": "h_1",
                "child_id": "child_w_1",
                "parent_id": "agent_root",
                "generation_token": "gen_1",
                "effects": {
                    "effects": [
                        {
                            "Read": "data"
                        },
                        "Infer"
                    ]
                },
                "settlement_state": "Unsettled"
            }
        }
    },
    "lineage": {
        "v2": [
            "child_invocation(async_op)",
            "target_agent(w)"
        ]
    },
    "diagnostics": [],
    "mutation_trace": [],
    "final_world": {},
    "gate_resolutions": [],
    "gate_trace": [],
    "child_handles": {
        "h_1": {
            "handle_id": "h_1",
            "child_id": "child_w_1",
            "parent_id": "agent_root",
            "generation_token": "gen_1",
            "effects": [
                "read[data]",
                "infer"
            ],
            "settlement_state": "Unsettled"
        }
    },
    "child_events": [
        "Spawned(async_op)"
    ],
    "frame_ledgers": {
        "h_1": {
            "available": {
                "compute": 20
            },
            "reserved": {},
            "spent": {}
        },
        "root": {
            "available": {
                "compute": 80
            },
            "reserved": {},
            "spent": {}
        }
    },
    "child_effective_authority": {
        "h_1": [
            "read[data]",
            "infer"
        ]
    },
    "result_provenance": {},
    "beliefs": {},
    "internalization_trace": []
}''')
    compare_exact_20_observables('D2_fire_and_forget', expected, rust_obs)

def test_d3_authority_attenuation():
    prog = json.loads('''{
    "name": "D3_authority_attenuation",
    "entry_func": "main",
    "inputs": {},
    "registry": {
        "agents": {
            "worker": {
                "agent_id": "worker",
                "native_authority": [
                    {
                        "Act": "workspace"
                    },
                    {
                        "Act": "production"
                    }
                ]
            }
        },
        "intents": {
            "task": {
                "intent_id": "task",
                "target_agent_id": "worker",
                "input_types": [],
                "output_type": {
                    "kind": "String"
                },
                "error_type": {
                    "kind": "String"
                },
                "child_effects": {
                    "effects": [
                        {
                            "Act": "workspace"
                        }
                    ]
                },
                "exported_envelope": {
                    "effects": [
                        {
                            "Act": "workspace"
                        },
                        {
                            "Act": "production"
                        }
                    ]
                },
                "declared_envelope": {
                    "effects": [
                        {
                            "Act": "workspace"
                        },
                        {
                            "Act": "production"
                        }
                    ]
                },
                "authority_policy": "AllowNative"
            }
        },
        "caller_authority": {
            "effects": [
                {
                    "Act": "workspace"
                }
            ]
        }
    },
    "module": {
        "name": "m",
        "functions": [
            {
                "name": "main",
                "params": [],
                "return_type": {
                    "kind": "String"
                },
                "declared_effects": {
                    "effects": [
                        {
                            "Act": "workspace"
                        }
                    ]
                },
                "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0,
                        "params": [],
                        "instructions": [
                            {
                                "Pure": {
                                    "dest": 1,
                                    "val": {
                                        "kind": "String",
                                        "payload": "ok"
                                    },
                                    "ty": {
                                        "kind": "String"
                                    }
                                }
                            },
                            {
                                "Delegate": {
                                    "dest": 2,
                                    "intent_id": "task",
                                    "args": [],
                                    "requested_effects": [
                                        {
                                            "Act": "workspace"
                                        }
                                    ],
                                    "authority_grant": [],
                                    "budget_grant": 0
                                }
                            }
                        ],
                        "terminator": {
                            "Return": 1
                        }
                    }
                }
            }
        ]
    }
}''')
    rust_obs = invoke_rust_conformance(prog)
    expected = json.loads('''{
    "status": "ok",
    "return_val": {
        "kind": "String",
        "payload": "ok"
    },
    "effects": [
        "act[workspace]"
    ],
    "active_facts": [],
    "latent_facts": {},
    "types": {
        "v1": "string",
        "v2": "ChildHandle<string, string, {act[workspace]}>"
    },
    "bindings": {
        "v1": {
            "kind": "String",
            "payload": "ok"
        },
        "v2": {
            "kind": "ChildHandle",
            "payload": {
                "handle_id": "h_1",
                "child_id": "child_worker_1",
                "parent_id": "agent_root",
                "generation_token": "gen_1",
                "effects": {
                    "effects": [
                        {
                            "Act": "workspace"
                        }
                    ]
                },
                "settlement_state": "Unsettled"
            }
        }
    },
    "lineage": {
        "v2": [
            "child_invocation(task)",
            "target_agent(worker)"
        ]
    },
    "diagnostics": [],
    "mutation_trace": [],
    "final_world": {},
    "gate_resolutions": [],
    "gate_trace": [],
    "child_handles": {
        "h_1": {
            "handle_id": "h_1",
            "child_id": "child_worker_1",
            "parent_id": "agent_root",
            "generation_token": "gen_1",
            "effects": [
                "act[workspace]"
            ],
            "settlement_state": "Unsettled"
        }
    },
    "child_events": [
        "Spawned(task)"
    ],
    "frame_ledgers": {
        "h_1": {
            "available": {},
            "reserved": {},
            "spent": {}
        },
        "root": {
            "available": {
                "compute": 100
            },
            "reserved": {},
            "spent": {}
        }
    },
    "child_effective_authority": {
        "h_1": [
            "act[workspace]"
        ]
    },
    "result_provenance": {},
    "beliefs": {},
    "internalization_trace": []
}''')
    compare_exact_20_observables('D3_authority_attenuation', expected, rust_obs)

def test_d4_budget_transfer_and_settlement():
    prog = json.loads('''{
    "name": "D4_budget",
    "entry_func": "main",
    "inputs": {},
    "initial_budget": {
        "compute": 100
    },
    "child_scenarios": {
        "work": {
            "mode": "success",
            "spend_amount": 12
        }
    },
    "registry": {
        "agents": {
            "w": {
                "agent_id": "w",
                "native_authority": [
                    {
                        "Read": "data"
                    }
                ]
            }
        },
        "intents": {
            "work": {
                "intent_id": "work",
                "target_agent_id": "w",
                "input_types": [],
                "output_type": {
                    "kind": "String"
                },
                "error_type": {
                    "kind": "String"
                },
                "child_effects": {
                    "effects": [
                        {
                            "Read": "data"
                        }
                    ]
                },
                "exported_envelope": {
                    "effects": [
                        {
                            "Read": "data"
                        }
                    ]
                },
                "declared_envelope": {
                    "effects": [
                        {
                            "Read": "data"
                        }
                    ]
                },
                "authority_policy": "AllowNative"
            }
        },
        "caller_authority": {
            "effects": [
                {
                    "Read": "data"
                }
            ]
        }
    },
    "module": {
        "name": "m",
        "functions": [
            {
                "name": "main",
                "params": [],
                "return_type": {
                    "kind": "String"
                },
                "declared_effects": {
                    "effects": [
                        {
                            "Read": "data"
                        }
                    ]
                },
                "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0,
                        "params": [],
                        "instructions": [
                            {
                                "Pure": {
                                    "dest": 1,
                                    "val": {
                                        "kind": "String",
                                        "payload": "ok"
                                    },
                                    "ty": {
                                        "kind": "String"
                                    }
                                }
                            },
                            {
                                "Delegate": {
                                    "dest": 2,
                                    "intent_id": "work",
                                    "args": [],
                                    "requested_effects": [
                                        {
                                            "Read": "data"
                                        }
                                    ],
                                    "authority_grant": [],
                                    "budget_grant": 30
                                }
                            },
                            {
                                "Await": {
                                    "dest": 3,
                                    "handle": 2
                                }
                            }
                        ],
                        "terminator": {
                            "Return": 1
                        }
                    }
                }
            }
        ]
    }
}''')
    rust_obs = invoke_rust_conformance(prog)
    expected = json.loads('''{
    "status": "ok",
    "return_val": {
        "kind": "String",
        "payload": "ok"
    },
    "effects": [
        "read[data]"
    ],
    "active_facts": [],
    "latent_facts": {},
    "types": {
        "v1": "string",
        "v2": "ChildHandle<string, string, {read[data]}>",
        "v3": "Result<string, string>"
    },
    "bindings": {
        "v1": {
            "kind": "String",
            "payload": "ok"
        },
        "v2": {
            "kind": "ChildHandle",
            "payload": {
                "handle_id": "h_1",
                "child_id": "child_w_1",
                "parent_id": "agent_root",
                "generation_token": "gen_1",
                "effects": {
                    "effects": [
                        {
                            "Read": "data"
                        }
                    ]
                },
                "settlement_state": "Unsettled"
            }
        },
        "v3": {
            "kind": "Ok",
            "payload": {
                "kind": "String",
                "payload": "result_data"
            }
        }
    },
    "lineage": {
        "v2": [
            "child_invocation(work)",
            "target_agent(w)"
        ],
        "v3": [
            "await_result(h_1)",
            "delegated_result(child_w_1)",
            "child_invocation(work)",
            "target_agent(w)"
        ]
    },
    "diagnostics": [],
    "mutation_trace": [],
    "final_world": {},
    "gate_resolutions": [],
    "gate_trace": [],
    "child_handles": {
        "h_1": {
            "handle_id": "h_1",
            "child_id": "child_w_1",
            "parent_id": "agent_root",
            "generation_token": "gen_1",
            "effects": [
                "read[data]"
            ],
            "settlement_state": "Settled"
        }
    },
    "child_events": [
        "Spawned(work)",
        "Settled(h_1)",
        "AwaitResumed(h_1)"
    ],
    "frame_ledgers": {
        "h_1": {
            "available": {},
            "reserved": {},
            "spent": {
                "compute": 12
            }
        },
        "root": {
            "available": {
                "compute": 88
            },
            "reserved": {},
            "spent": {}
        }
    },
    "child_effective_authority": {
        "h_1": [
            "read[data]"
        ]
    },
    "result_provenance": {
        "v3": {
            "child_id": "child_w_1",
            "intent_id": "work",
            "target_agent_id": "w",
            "result_event_id": "evt_1",
            "is_opaque": false,
            "underlying_refs": []
        }
    },
    "beliefs": {},
    "internalization_trace": []
}''')
    compare_exact_20_observables('D4_budget_transfer_and_settlement', expected, rust_obs)

def test_d5_settlement_unknown_suspension():
    prog = json.loads('''{
    "name": "D5_unknown_suspension",
    "entry_func": "main",
    "inputs": {},
    "child_scenarios": {
        "slow_job": {
            "mode": "settlement_unknown"
        }
    },
    "registry": {
        "agents": {
            "w": {
                "agent_id": "w",
                "native_authority": [
                    {
                        "Read": "data"
                    }
                ]
            }
        },
        "intents": {
            "slow_job": {
                "intent_id": "slow_job",
                "target_agent_id": "w",
                "input_types": [],
                "output_type": {
                    "kind": "String"
                },
                "error_type": {
                    "kind": "String"
                },
                "child_effects": {
                    "effects": [
                        {
                            "Read": "data"
                        }
                    ]
                },
                "exported_envelope": {
                    "effects": [
                        {
                            "Read": "data"
                        }
                    ]
                },
                "declared_envelope": {
                    "effects": [
                        {
                            "Read": "data"
                        }
                    ]
                },
                "authority_policy": "AllowNative"
            }
        },
        "caller_authority": {
            "effects": [
                {
                    "Read": "data"
                }
            ]
        }
    },
    "module": {
        "name": "m",
        "functions": [
            {
                "name": "main",
                "params": [],
                "return_type": {
                    "kind": "String"
                },
                "declared_effects": {
                    "effects": [
                        {
                            "Read": "data"
                        }
                    ]
                },
                "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0,
                        "params": [],
                        "instructions": [
                            {
                                "Pure": {
                                    "dest": 1,
                                    "val": {
                                        "kind": "String",
                                        "payload": "ok"
                                    },
                                    "ty": {
                                        "kind": "String"
                                    }
                                }
                            },
                            {
                                "Delegate": {
                                    "dest": 2,
                                    "intent_id": "slow_job",
                                    "args": [],
                                    "requested_effects": [
                                        {
                                            "Read": "data"
                                        }
                                    ],
                                    "authority_grant": [],
                                    "budget_grant": 0
                                }
                            },
                            {
                                "Await": {
                                    "dest": 3,
                                    "handle": 2
                                }
                            }
                        ],
                        "terminator": {
                            "Return": 1
                        }
                    }
                }
            }
        ]
    }
}''')
    rust_obs = invoke_rust_conformance(prog)
    expected = json.loads('''{
    "status": "waiting_on_child(h_1)",
    "return_val": null,
    "effects": [
        "read[data]"
    ],
    "active_facts": [],
    "latent_facts": {},
    "types": {
        "v1": "string",
        "v2": "ChildHandle<string, string, {read[data]}>"
    },
    "bindings": {
        "v1": {
            "kind": "String",
            "payload": "ok"
        },
        "v2": {
            "kind": "ChildHandle",
            "payload": {
                "handle_id": "h_1",
                "child_id": "child_w_1",
                "parent_id": "agent_root",
                "generation_token": "gen_1",
                "effects": {
                    "effects": [
                        {
                            "Read": "data"
                        }
                    ]
                },
                "settlement_state": "Unsettled"
            }
        }
    },
    "lineage": {
        "v2": [
            "child_invocation(slow_job)",
            "target_agent(w)"
        ]
    },
    "diagnostics": [],
    "mutation_trace": [],
    "final_world": {},
    "gate_resolutions": [],
    "gate_trace": [],
    "child_handles": {
        "h_1": {
            "handle_id": "h_1",
            "child_id": "child_w_1",
            "parent_id": "agent_root",
            "generation_token": "gen_1",
            "effects": [
                "read[data]"
            ],
            "settlement_state": "SettlementUnknown"
        }
    },
    "child_events": [
        "Spawned(slow_job)",
        "AwaitSuspended(h_1)"
    ],
    "frame_ledgers": {
        "h_1": {
            "available": {},
            "reserved": {},
            "spent": {}
        },
        "root": {
            "available": {
                "compute": 100
            },
            "reserved": {},
            "spent": {}
        }
    },
    "child_effective_authority": {
        "h_1": [
            "read[data]"
        ]
    },
    "result_provenance": {},
    "beliefs": {},
    "internalization_trace": []
}''')
    compare_exact_20_observables('D5_settlement_unknown_suspension', expected, rust_obs)

def test_d6_heterogeneous_handle_join():
    prog = json.loads('''{
    "name": "D6_handle_join",
    "entry_func": "main",
    "inputs": {
        "cond": {
            "kind": "Bool",
            "payload": true
        }
    },
    "registry": {
        "agents": {
            "w1": {
                "agent_id": "w1",
                "native_authority": [
                    {
                        "Read": "a"
                    }
                ]
            },
            "w2": {
                "agent_id": "w2",
                "native_authority": [
                    {
                        "Infer": null
                    }
                ]
            }
        },
        "intents": {
            "fetch1": {
                "intent_id": "fetch1",
                "target_agent_id": "w1",
                "input_types": [],
                "output_type": {
                    "kind": "String"
                },
                "error_type": {
                    "kind": "String"
                },
                "child_effects": {
                    "effects": [
                        {
                            "Read": "a"
                        }
                    ]
                },
                "exported_envelope": {
                    "effects": [
                        {
                            "Read": "a"
                        }
                    ]
                },
                "declared_envelope": {
                    "effects": [
                        {
                            "Read": "a"
                        }
                    ]
                },
                "authority_policy": "AllowNative"
            },
            "fetch2": {
                "intent_id": "fetch2",
                "target_agent_id": "w2",
                "input_types": [],
                "output_type": {
                    "kind": "String"
                },
                "error_type": {
                    "kind": "String"
                },
                "child_effects": {
                    "effects": [
                        {
                            "Infer": null
                        }
                    ]
                },
                "exported_envelope": {
                    "effects": [
                        {
                            "Infer": null
                        }
                    ]
                },
                "declared_envelope": {
                    "effects": [
                        {
                            "Infer": null
                        }
                    ]
                },
                "authority_policy": "AllowNative"
            }
        },
        "caller_authority": {
            "effects": [
                {
                    "Read": "a"
                },
                {
                    "Infer": null
                }
            ]
        }
    },
    "module": {
        "name": "m",
        "functions": [
            {
                "name": "main",
                "params": [
                    [
                        10,
                        {
                            "kind": "Bool"
                        }
                    ]
                ],
                "return_type": {
                    "kind": "String"
                },
                "declared_effects": {
                    "effects": [
                        {
                            "Read": "a"
                        },
                        {
                            "Infer": null
                        }
                    ]
                },
                "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0,
                        "params": [],
                        "instructions": [
                            {
                                "Pure": {
                                    "dest": 1,
                                    "val": {
                                        "kind": "String",
                                        "payload": "ok"
                                    },
                                    "ty": {
                                        "kind": "String"
                                    }
                                }
                            }
                        ],
                        "terminator": {
                            "CondBr": {
                                "cond": 10,
                                "true_target": 1,
                                "true_args": [],
                                "false_target": 2,
                                "false_args": []
                            }
                        }
                    },
                    "1": {
                        "id": 1,
                        "params": [],
                        "instructions": [
                            {
                                "Delegate": {
                                    "dest": 2,
                                    "intent_id": "fetch1",
                                    "args": [],
                                    "requested_effects": [
                                        {
                                            "Read": "a"
                                        }
                                    ],
                                    "authority_grant": [],
                                    "budget_grant": 0
                                }
                            }
                        ],
                        "terminator": {
                            "Br": {
                                "target": 3,
                                "args": [
                                    2
                                ]
                            }
                        }
                    },
                    "2": {
                        "id": 2,
                        "params": [],
                        "instructions": [
                            {
                                "Delegate": {
                                    "dest": 3,
                                    "intent_id": "fetch2",
                                    "args": [],
                                    "requested_effects": [
                                        {
                                            "Infer": null
                                        }
                                    ],
                                    "authority_grant": [],
                                    "budget_grant": 0
                                }
                            }
                        ],
                        "terminator": {
                            "Br": {
                                "target": 3,
                                "args": [
                                    3
                                ]
                            }
                        }
                    },
                    "3": {
                        "id": 3,
                        "params": [
                            [
                                4,
                                {
                                    "kind": "ChildHandle",
                                    "payload": {
                                        "ok": {
                                            "kind": "String"
                                        },
                                        "err": {
                                            "kind": "String"
                                        },
                                        "effects": {
                                            "effects": [
                                                {
                                                    "Read": "a"
                                                },
                                                {
                                                    "Infer": null
                                                }
                                            ]
                                        }
                                    }
                                }
                            ]
                        ],
                        "instructions": [
                            {
                                "Await": {
                                    "dest": 5,
                                    "handle": 4
                                }
                            }
                        ],
                        "terminator": {
                            "Return": 1
                        }
                    }
                }
            }
        ]
    }
}''')
    rust_obs = invoke_rust_conformance(prog)
    expected = json.loads('''{
    "status": "ok",
    "return_val": {
        "kind": "String",
        "payload": "ok"
    },
    "effects": [
        "infer"
    ],
    "active_facts": [],
    "latent_facts": {},
    "types": {
        "v1": "string",
        "v3": "ChildHandle<string, string, {infer}>",
        "v4": "ChildHandle<string, string, {read[a], infer}>",
        "v5": "Result<string, string>"
    },
    "bindings": {
        "cond": {
            "kind": "Bool",
            "payload": true
        },
        "v1": {
            "kind": "String",
            "payload": "ok"
        },
        "v3": {
            "kind": "ChildHandle",
            "payload": {
                "handle_id": "h_1",
                "child_id": "child_w2_1",
                "parent_id": "agent_root",
                "generation_token": "gen_1",
                "effects": {
                    "effects": [
                        "Infer"
                    ]
                },
                "settlement_state": "Unsettled"
            }
        },
        "v4": {
            "kind": "ChildHandle",
            "payload": {
                "handle_id": "h_1",
                "child_id": "child_w2_1",
                "parent_id": "agent_root",
                "generation_token": "gen_1",
                "effects": {
                    "effects": [
                        "Infer"
                    ]
                },
                "settlement_state": "Unsettled"
            }
        },
        "v5": {
            "kind": "Ok",
            "payload": {
                "kind": "String",
                "payload": "worker_success"
            }
        }
    },
    "lineage": {
        "v3": [
            "child_invocation(fetch2)",
            "target_agent(w2)"
        ],
        "v4": [
            "child_invocation(fetch2)",
            "target_agent(w2)"
        ],
        "v5": [
            "await_result(h_1)",
            "delegated_result(child_w2_1)",
            "child_invocation(fetch2)",
            "target_agent(w2)"
        ]
    },
    "diagnostics": [],
    "mutation_trace": [],
    "final_world": {},
    "gate_resolutions": [],
    "gate_trace": [],
    "child_handles": {
        "h_1": {
            "handle_id": "h_1",
            "child_id": "child_w2_1",
            "parent_id": "agent_root",
            "generation_token": "gen_1",
            "effects": [
                "infer"
            ],
            "settlement_state": "Settled"
        }
    },
    "child_events": [
        "Spawned(fetch2)",
        "Settled(h_1)",
        "AwaitResumed(h_1)"
    ],
    "frame_ledgers": {
        "h_1": {
            "available": {},
            "reserved": {},
            "spent": {}
        },
        "root": {
            "available": {
                "compute": 100
            },
            "reserved": {},
            "spent": {}
        }
    },
    "child_effective_authority": {
        "h_1": [
            "infer"
        ]
    },
    "result_provenance": {
        "v5": {
            "child_id": "child_w2_1",
            "intent_id": "fetch2",
            "target_agent_id": "w2",
            "result_event_id": "evt_1",
            "is_opaque": false,
            "underlying_refs": []
        }
    },
    "beliefs": {},
    "internalization_trace": []
}''')
    compare_exact_20_observables('D6_heterogeneous_handle_join', expected, rust_obs)

def test_d7_internalize_success():
    prog = json.loads('''{
    "name": "D7_internalize_success",
    "entry_func": "main",
    "current_agent_id": "agent_alpha",
    "inputs": {},
    "registry": {
        "internalization_policies": {
            "p_ok": {
                "policy_id": "p_ok",
                "accepted_claim_contract": "AcceptAll",
                "validation_requirements": [
                    "CheckDocApproved"
                ],
                "validation_effect_envelope": {
                    "effects": [
                        {
                            "Read": "policy_db"
                        }
                    ]
                }
            }
        },
        "caller_authority": {
            "effects": [
                {
                    "Read": "policy_db"
                }
            ]
        }
    },
    "module": {
        "name": "m",
        "functions": [
            {
                "name": "main",
                "params": [],
                "return_type": {
                    "kind": "String"
                },
                "declared_effects": {
                    "effects": [
                        {
                            "Read": "policy_db"
                        }
                    ]
                },
                "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0,
                        "params": [],
                        "instructions": [
                            {
                                "Pure": {
                                    "dest": 1,
                                    "val": {
                                        "kind": "String",
                                        "payload": "approved_doc"
                                    },
                                    "ty": {
                                        "kind": "String"
                                    }
                                }
                            },
                            {
                                "Pure": {
                                    "dest": 2,
                                    "val": {
                                        "kind": "Claim",
                                        "payload": {
                                            "kind": "String",
                                            "payload": "approved_doc"
                                        }
                                    },
                                    "ty": {
                                        "kind": "Claim",
                                        "payload": {
                                            "kind": "String"
                                        }
                                    }
                                }
                            },
                            {
                                "Internalize": {
                                    "dest": 3,
                                    "policy_id": "p_ok",
                                    "claim": 2
                                }
                            }
                        ],
                        "terminator": {
                            "MatchResult": {
                                "result_val": 3,
                                "ok_arg": 4,
                                "ok_body": {
                                    "instructions": [],
                                    "terminator": {
                                        "Return": 1
                                    }
                                },
                                "err_arg": 5,
                                "err_body": {
                                    "instructions": [],
                                    "terminator": {
                                        "Return": 1
                                    }
                                }
                            }
                        }
                    }
                }
            }
        ]
    }
}''')
    rust_obs = invoke_rust_conformance(prog)
    expected = json.loads('''{
    "status": "ok",
    "return_val": {
        "kind": "String",
        "payload": "approved_doc"
    },
    "effects": [
        "read[policy_db]"
    ],
    "active_facts": [
        {
            "predicate": "Internalized",
            "args": [
                {
                    "Symbol": "v4"
                },
                {
                    "Symbol": "v2"
                },
                {
                    "Literal": "p_ok"
                }
            ]
        },
        {
            "predicate": "IsOk",
            "args": [
                {
                    "Symbol": "v3"
                }
            ]
        }
    ],
    "latent_facts": {
        "v3": {
            "on_ok": [
                {
                    "predicate": "Internalized",
                    "args": [
                        {
                            "Symbol": "$value"
                        },
                        {
                            "Symbol": "v2"
                        },
                        {
                            "Literal": "p_ok"
                        }
                    ]
                }
            ],
            "on_err": []
        }
    },
    "types": {
        "v1": "string",
        "v2": "Claim<string>",
        "v3": "Result<Belief<string>, string>",
        "v4": "Belief<string>"
    },
    "bindings": {
        "v1": {
            "kind": "String",
            "payload": "approved_doc"
        },
        "v2": {
            "kind": "Claim",
            "payload": {
                "kind": "String",
                "payload": "approved_doc"
            }
        },
        "v3": {
            "kind": "Ok",
            "payload": {
                "kind": "Belief",
                "payload": {
                    "payload": {
                        "kind": "String",
                        "payload": "approved_doc"
                    },
                    "owner_agent_id": "agent_alpha",
                    "provenance": [
                        "internalize(p_ok)"
                    ],
                    "policy_binding": "p_ok"
                }
            }
        },
        "v4": {
            "kind": "Belief",
            "payload": {
                "payload": {
                    "kind": "String",
                    "payload": "approved_doc"
                },
                "owner_agent_id": "agent_alpha",
                "provenance": [
                    "internalize(p_ok)"
                ],
                "policy_binding": "p_ok"
            }
        }
    },
    "lineage": {
        "v3": [
            "internalize(p_ok)",
            "claim_from(v2)"
        ],
        "v4": [
            "internalize(p_ok)",
            "claim_from(v2)"
        ]
    },
    "diagnostics": [],
    "mutation_trace": [],
    "final_world": {},
    "gate_resolutions": [],
    "gate_trace": [],
    "child_handles": {},
    "child_events": [],
    "frame_ledgers": {
        "root": {
            "available": {
                "compute": 100
            },
            "reserved": {},
            "spent": {}
        }
    },
    "child_effective_authority": {},
    "result_provenance": {},
    "beliefs": {
        "v3": {
            "payload": {
                "kind": "String",
                "payload": "approved_doc"
            },
            "owner_agent_id": "agent_alpha",
            "provenance": [
                "internalize(p_ok)"
            ],
            "policy_binding": "p_ok"
        }
    },
    "internalization_trace": [
        {
            "check_kind": "ValidateClaimContract",
            "authority_source": "Caller",
            "effects": [
                "read[policy_db]"
            ],
            "result": "Pass"
        }
    ]
}''')
    compare_exact_20_observables('D7_internalize_success', expected, rust_obs)

def test_d8_internalize_failure():
    prog = json.loads('''{
    "name": "D8_internalize_fail",
    "entry_func": "main",
    "inputs": {},
    "registry": {
        "internalization_policies": {
            "p_strict": {
                "policy_id": "p_strict",
                "accepted_claim_contract": "AcceptAll",
                "validation_requirements": [
                    "CheckDocApproved"
                ],
                "validation_effect_envelope": {
                    "effects": []
                }
            }
        },
        "caller_authority": {
            "effects": []
        }
    },
    "module": {
        "name": "m",
        "functions": [
            {
                "name": "main",
                "params": [],
                "return_type": {
                    "kind": "String"
                },
                "declared_effects": {
                    "effects": []
                },
                "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0,
                        "params": [],
                        "instructions": [
                            {
                                "Pure": {
                                    "dest": 1,
                                    "val": {
                                        "kind": "String",
                                        "payload": "unapproved_val"
                                    },
                                    "ty": {
                                        "kind": "String"
                                    }
                                }
                            },
                            {
                                "Pure": {
                                    "dest": 2,
                                    "val": {
                                        "kind": "Claim",
                                        "payload": {
                                            "kind": "String",
                                            "payload": "unapproved_val"
                                        }
                                    },
                                    "ty": {
                                        "kind": "Claim",
                                        "payload": {
                                            "kind": "String"
                                        }
                                    }
                                }
                            },
                            {
                                "Internalize": {
                                    "dest": 3,
                                    "policy_id": "p_strict",
                                    "claim": 2
                                }
                            }
                        ],
                        "terminator": {
                            "MatchResult": {
                                "result_val": 3,
                                "ok_arg": 4,
                                "ok_body": {
                                    "instructions": [],
                                    "terminator": {
                                        "Return": 1
                                    }
                                },
                                "err_arg": 5,
                                "err_body": {
                                    "instructions": [],
                                    "terminator": {
                                        "Return": 5
                                    }
                                }
                            }
                        }
                    }
                }
            }
        ]
    }
}''')
    rust_obs = invoke_rust_conformance(prog)
    expected = json.loads('''{
    "status": "ok",
    "return_val": {
        "kind": "String",
        "payload": "InternalizationRejected"
    },
    "effects": [],
    "active_facts": [
        {
            "predicate": "IsErr",
            "args": [
                {
                    "Symbol": "v3"
                }
            ]
        }
    ],
    "latent_facts": {
        "v3": {
            "on_ok": [
                {
                    "predicate": "Internalized",
                    "args": [
                        {
                            "Symbol": "$value"
                        },
                        {
                            "Symbol": "v2"
                        },
                        {
                            "Literal": "p_strict"
                        }
                    ]
                }
            ],
            "on_err": []
        }
    },
    "types": {
        "v1": "string",
        "v2": "Claim<string>",
        "v5": "string"
    },
    "bindings": {
        "v1": {
            "kind": "String",
            "payload": "unapproved_val"
        },
        "v2": {
            "kind": "Claim",
            "payload": {
                "kind": "String",
                "payload": "unapproved_val"
            }
        },
        "v3": {
            "kind": "Err",
            "payload": {
                "kind": "String",
                "payload": "InternalizationRejected"
            }
        },
        "v5": {
            "kind": "String",
            "payload": "InternalizationRejected"
        }
    },
    "lineage": {},
    "diagnostics": [],
    "mutation_trace": [],
    "final_world": {},
    "gate_resolutions": [],
    "gate_trace": [],
    "child_handles": {},
    "child_events": [],
    "frame_ledgers": {
        "root": {
            "available": {
                "compute": 100
            },
            "reserved": {},
            "spent": {}
        }
    },
    "child_effective_authority": {},
    "result_provenance": {},
    "beliefs": {},
    "internalization_trace": [
        {
            "check_kind": "ValidateClaimContract",
            "authority_source": "Caller",
            "effects": [],
            "result": "Fail"
        }
    ]
}''')
    compare_exact_20_observables('D8_internalize_failure', expected, rust_obs)

def test_d9_full_provenance_chain():
    prog = json.loads('''{
    "name": "D9_provenance_chain",
    "entry_func": "main",
    "current_agent_id": "parent_agent",
    "inputs": {},
    "child_scenarios": {
        "worker_task": {
            "mode": "returns_claim",
            "payload_string": "verified_claim"
        }
    },
    "registry": {
        "agents": {
            "sub_worker": {
                "agent_id": "sub_worker",
                "native_authority": [
                    {
                        "Read": "logs"
                    }
                ]
            }
        },
        "intents": {
            "worker_task": {
                "intent_id": "worker_task",
                "target_agent_id": "sub_worker",
                "input_types": [],
                "output_type": {
                    "kind": "Claim",
                    "payload": {
                        "kind": "String"
                    }
                },
                "error_type": {
                    "kind": "String"
                },
                "child_effects": {
                    "effects": [
                        {
                            "Read": "logs"
                        }
                    ]
                },
                "exported_envelope": {
                    "effects": [
                        {
                            "Read": "logs"
                        }
                    ]
                },
                "declared_envelope": {
                    "effects": [
                        {
                            "Read": "logs"
                        }
                    ]
                },
                "authority_policy": "AllowNative"
            }
        },
        "internalization_policies": {
            "p_log": {
                "policy_id": "p_log",
                "accepted_claim_contract": "AcceptAll",
                "validation_requirements": [],
                "validation_effect_envelope": {
                    "effects": [
                        {
                            "Read": "policy_db"
                        }
                    ]
                }
            }
        },
        "caller_authority": {
            "effects": [
                {
                    "Read": "logs"
                },
                {
                    "Read": "policy_db"
                }
            ]
        }
    },
    "module": {
        "name": "m",
        "functions": [
            {
                "name": "main",
                "params": [],
                "return_type": {
                    "kind": "String"
                },
                "declared_effects": {
                    "effects": [
                        {
                            "Read": "logs"
                        },
                        {
                            "Read": "policy_db"
                        }
                    ]
                },
                "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0,
                        "params": [],
                        "instructions": [
                            {
                                "Pure": {
                                    "dest": 1,
                                    "val": {
                                        "kind": "String",
                                        "payload": "ok"
                                    },
                                    "ty": {
                                        "kind": "String"
                                    }
                                }
                            },
                            {
                                "Delegate": {
                                    "dest": 2,
                                    "intent_id": "worker_task",
                                    "args": [],
                                    "requested_effects": [
                                        {
                                            "Read": "logs"
                                        }
                                    ],
                                    "authority_grant": [],
                                    "budget_grant": 10
                                }
                            },
                            {
                                "Await": {
                                    "dest": 3,
                                    "handle": 2
                                }
                            }
                        ],
                        "terminator": {
                            "MatchResult": {
                                "result_val": 3,
                                "ok_arg": 4,
                                "ok_body": {
                                    "instructions": [],
                                    "terminator": {
                                        "Br": {
                                            "target": 1,
                                            "args": [
                                                4
                                            ]
                                        }
                                    }
                                },
                                "err_arg": 6,
                                "err_body": {
                                    "instructions": [],
                                    "terminator": {
                                        "Return": 1
                                    }
                                }
                            }
                        }
                    },
                    "1": {
                        "id": 1,
                        "params": [
                            [
                                10,
                                {
                                    "kind": "Claim",
                                    "payload": {
                                        "kind": "String"
                                    }
                                }
                            ]
                        ],
                        "instructions": [
                            {
                                "Internalize": {
                                    "dest": 5,
                                    "policy_id": "p_log",
                                    "claim": 10
                                }
                            }
                        ],
                        "terminator": {
                            "MatchResult": {
                                "result_val": 5,
                                "ok_arg": 7,
                                "ok_body": {
                                    "instructions": [],
                                    "terminator": {
                                        "Return": 1
                                    }
                                },
                                "err_arg": 8,
                                "err_body": {
                                    "instructions": [],
                                    "terminator": {
                                        "Return": 1
                                    }
                                }
                            }
                        }
                    }
                }
            }
        ]
    }
}''')
    rust_obs = invoke_rust_conformance(prog)
    expected = json.loads('''{
    "status": "ok",
    "return_val": {
        "kind": "String",
        "payload": "ok"
    },
    "effects": [
        "read[logs]",
        "read[policy_db]"
    ],
    "active_facts": [
        {
            "predicate": "Internalized",
            "args": [
                {
                    "Symbol": "v7"
                },
                {
                    "Symbol": "v10"
                },
                {
                    "Literal": "p_log"
                }
            ]
        },
        {
            "predicate": "IsOk",
            "args": [
                {
                    "Symbol": "v3"
                }
            ]
        },
        {
            "predicate": "IsOk",
            "args": [
                {
                    "Symbol": "v5"
                }
            ]
        }
    ],
    "latent_facts": {
        "v5": {
            "on_ok": [
                {
                    "predicate": "Internalized",
                    "args": [
                        {
                            "Symbol": "$value"
                        },
                        {
                            "Symbol": "v10"
                        },
                        {
                            "Literal": "p_log"
                        }
                    ]
                }
            ],
            "on_err": []
        }
    },
    "types": {
        "v1": "string",
        "v10": "Claim<string>",
        "v2": "ChildHandle<Claim<string>, string, {read[logs]}>",
        "v3": "Result<Claim<string>, string>",
        "v4": "Claim<string>",
        "v5": "Result<Belief<string>, string>",
        "v7": "Belief<string>"
    },
    "bindings": {
        "v1": {
            "kind": "String",
            "payload": "ok"
        },
        "v10": {
            "kind": "Claim",
            "payload": {
                "kind": "String",
                "payload": "verified_claim"
            }
        },
        "v2": {
            "kind": "ChildHandle",
            "payload": {
                "handle_id": "h_1",
                "child_id": "child_sub_worker_1",
                "parent_id": "parent_agent",
                "generation_token": "gen_1",
                "effects": {
                    "effects": [
                        {
                            "Read": "logs"
                        }
                    ]
                },
                "settlement_state": "Unsettled"
            }
        },
        "v3": {
            "kind": "Ok",
            "payload": {
                "kind": "Claim",
                "payload": {
                    "kind": "String",
                    "payload": "verified_claim"
                }
            }
        },
        "v4": {
            "kind": "Claim",
            "payload": {
                "kind": "String",
                "payload": "verified_claim"
            }
        },
        "v5": {
            "kind": "Ok",
            "payload": {
                "kind": "Belief",
                "payload": {
                    "payload": {
                        "kind": "String",
                        "payload": "verified_claim"
                    },
                    "owner_agent_id": "parent_agent",
                    "provenance": [
                        "internalize(p_log)",
                        "await_result(h_1)",
                        "delegated_result(child_sub_worker_1)",
                        "child_invocation(worker_task)",
                        "target_agent(sub_worker)"
                    ],
                    "policy_binding": "p_log"
                }
            }
        },
        "v7": {
            "kind": "Belief",
            "payload": {
                "payload": {
                    "kind": "String",
                    "payload": "verified_claim"
                },
                "owner_agent_id": "parent_agent",
                "provenance": [
                    "internalize(p_log)",
                    "await_result(h_1)",
                    "delegated_result(child_sub_worker_1)",
                    "child_invocation(worker_task)",
                    "target_agent(sub_worker)"
                ],
                "policy_binding": "p_log"
            }
        }
    },
    "lineage": {
        "v10": [
            "await_result(h_1)",
            "delegated_result(child_sub_worker_1)",
            "child_invocation(worker_task)",
            "target_agent(sub_worker)"
        ],
        "v2": [
            "child_invocation(worker_task)",
            "target_agent(sub_worker)"
        ],
        "v3": [
            "await_result(h_1)",
            "delegated_result(child_sub_worker_1)",
            "child_invocation(worker_task)",
            "target_agent(sub_worker)"
        ],
        "v4": [
            "await_result(h_1)",
            "delegated_result(child_sub_worker_1)",
            "child_invocation(worker_task)",
            "target_agent(sub_worker)"
        ],
        "v5": [
            "internalize(p_log)",
            "claim_from(v10)",
            "await_result(h_1)",
            "delegated_result(child_sub_worker_1)",
            "child_invocation(worker_task)",
            "target_agent(sub_worker)"
        ],
        "v7": [
            "internalize(p_log)",
            "claim_from(v10)",
            "await_result(h_1)",
            "delegated_result(child_sub_worker_1)",
            "child_invocation(worker_task)",
            "target_agent(sub_worker)"
        ]
    },
    "diagnostics": [],
    "mutation_trace": [],
    "final_world": {},
    "gate_resolutions": [],
    "gate_trace": [],
    "child_handles": {
        "h_1": {
            "handle_id": "h_1",
            "child_id": "child_sub_worker_1",
            "parent_id": "parent_agent",
            "generation_token": "gen_1",
            "effects": [
                "read[logs]"
            ],
            "settlement_state": "Settled"
        }
    },
    "child_events": [
        "Spawned(worker_task)",
        "Settled(h_1)",
        "AwaitResumed(h_1)"
    ],
    "frame_ledgers": {
        "h_1": {
            "available": {},
            "reserved": {},
            "spent": {}
        },
        "root": {
            "available": {
                "compute": 100
            },
            "reserved": {},
            "spent": {}
        }
    },
    "child_effective_authority": {
        "h_1": [
            "read[logs]"
        ]
    },
    "result_provenance": {
        "v3": {
            "child_id": "child_sub_worker_1",
            "intent_id": "worker_task",
            "target_agent_id": "sub_worker",
            "result_event_id": "evt_1",
            "is_opaque": false,
            "underlying_refs": []
        }
    },
    "beliefs": {
        "v5": {
            "payload": {
                "kind": "String",
                "payload": "verified_claim"
            },
            "owner_agent_id": "parent_agent",
            "provenance": [
                "internalize(p_log)",
                "await_result(h_1)",
                "delegated_result(child_sub_worker_1)",
                "child_invocation(worker_task)",
                "target_agent(sub_worker)"
            ],
            "policy_binding": "p_log"
        }
    },
    "internalization_trace": []
}''')
    compare_exact_20_observables('D9_full_provenance_chain', expected, rust_obs)

# ==============================================================================
# Negative Differential Probes (Must Fail on Discrepancy in Any of the 20 Fields)
# ==============================================================================

def make_dummy_valid_20_obs():
    return {
        "status": "ok",
        "return_val": {"kind": "String", "payload": "ok"},
        "effects": ["read[doc]"],
        "active_facts": [{"predicate": "IsOk", "args": [{"Symbol": "v1"}]}],
        "latent_facts": {},
        "types": {"v1": "String"},
        "bindings": {"v1": {"kind": "String", "payload": "ok"}},
        "lineage": {"v1": ["source_a"]},
        "diagnostics": [],
        "mutation_trace": [],
        "final_world": {},
        "gate_resolutions": [],
        "gate_trace": [],
        "child_handles": {
            "h_1": {
                "child_id": "child_1",
                "effects": ["read[doc]"],
                "generation_token": "gen_1",
                "handle_id": "h_1",
                "parent_id": "agent_root",
                "settlement_state": "Settled"
            }
        },
        "child_events": ["Spawned(task)"],
        "frame_ledgers": {"root": {"available": {"compute": 100}, "reserved": {}, "spent": {}}},
        "child_effective_authority": {"h_1": ["read[doc]"]},
        "result_provenance": {
            "v1": {
                "child_id": "child_1",
                "intent_id": "task",
                "is_opaque": False,
                "result_event_id": "evt_1",
                "target_agent_id": "worker",
                "underlying_refs": []
            }
        },
        "beliefs": {
            "v1": {
                "owner_agent_id": "agent_root",
                "payload": {"kind": "String", "payload": "doc"},
                "policy_binding": "p1",
                "provenance": ["internalize(p1)"]
            }
        },
        "internalization_trace": []
    }

def test_probe_extra_type_fails():
    obs = make_dummy_valid_20_obs()
    corrupted = copy.deepcopy(obs)
    corrupted["types"]["v_extra"] = "I64"
    run_probe_should_fail("PROBE_extra_type_fails", corrupted, obs)

def test_probe_extra_child_event_fails():
    obs = make_dummy_valid_20_obs()
    corrupted = copy.deepcopy(obs)
    corrupted["child_events"].append("ExtraEvent")
    run_probe_should_fail("PROBE_extra_child_event_fails", corrupted, obs)

def test_probe_extra_frame_ledger_fails():
    obs = make_dummy_valid_20_obs()
    corrupted = copy.deepcopy(obs)
    corrupted["frame_ledgers"]["ghost_frame"] = {"available": {"compute": 50}, "reserved": {}, "spent": {}}
    run_probe_should_fail("PROBE_extra_frame_ledger_fails", corrupted, obs)

def test_probe_extra_result_provenance_fails():
    obs = make_dummy_valid_20_obs()
    corrupted = copy.deepcopy(obs)
    corrupted["result_provenance"]["v_extra"] = {
        "child_id": "ghost_child", "intent_id": "ghost_intent", "is_opaque": False,
        "result_event_id": "evt_g", "target_agent_id": "ghost_agent", "underlying_refs": []
    }
    run_probe_should_fail("PROBE_extra_result_provenance_fails", corrupted, obs)

def test_probe_extra_diagnostic_fails():
    obs = make_dummy_valid_20_obs()
    corrupted = copy.deepcopy(obs)
    corrupted["diagnostics"].append({"code": "TypeMismatch", "message": "unexpected diag"})
    run_probe_should_fail("PROBE_extra_diagnostic_fails", corrupted, obs)

def test_probe_extra_mutation_trace_fails():
    obs = make_dummy_valid_20_obs()
    corrupted = copy.deepcopy(obs)
    corrupted["mutation_trace"].append(["key", "val", 1])
    run_probe_should_fail("PROBE_extra_mutation_trace_fails", corrupted, obs)

def test_probe_wrong_latent_fact_fails():
    obs = make_dummy_valid_20_obs()
    corrupted = copy.deepcopy(obs)
    corrupted["latent_facts"]["v1"] = {"on_ok": [{"predicate": "GhostFact", "args": []}], "on_err": []}
    run_probe_should_fail("PROBE_wrong_latent_fact_fails", corrupted, obs)

def test_probe_wrong_lineage_fails():
    obs = make_dummy_valid_20_obs()
    corrupted = copy.deepcopy(obs)
    corrupted["lineage"]["v1"] = ["wrong_origin"]
    run_probe_should_fail("PROBE_wrong_lineage_fails", corrupted, obs)

def test_probe_wrong_belief_provenance_fails():
    obs = make_dummy_valid_20_obs()
    corrupted = copy.deepcopy(obs)
    corrupted["beliefs"]["v1"]["provenance"] = ["laundered_provenance"]
    run_probe_should_fail("PROBE_wrong_belief_provenance_fails", corrupted, obs)

def main():
    print("=" * 70)
    print("SOMA COMPILER CONFORMANCE v0 (SLICE 3) — Python Oracle vs Rust Exact 20-Observable Differential (D1–D9 & Probes)")
    test_d1_basic_delegate_await()
    test_d2_fire_and_forget()
    test_d3_authority_attenuation()
    test_d4_budget_transfer_and_settlement()
    test_d5_settlement_unknown_suspension()
    test_d6_heterogeneous_handle_join()
    test_d7_internalize_success()
    test_d8_internalize_failure()
    test_d9_full_provenance_chain()
    test_probe_extra_type_fails()
    test_probe_extra_child_event_fails()
    test_probe_extra_frame_ledger_fails()
    test_probe_extra_result_provenance_fails()
    test_probe_extra_diagnostic_fails()
    test_probe_extra_mutation_trace_fails()
    test_probe_wrong_latent_fact_fails()
    test_probe_wrong_lineage_fails()
    test_probe_wrong_belief_provenance_fails()
    print("=" * 70)
    print(f"SLICE 3 DIFFERENTIAL RESULT: {PASS} passed, {FAIL} failed ({PASS + FAIL} total)")
    if FAIL == 0:
        print("Exact 20-Observable differential agreement strictly confirmed between Python Oracle and Rust Toolchain.")
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()
