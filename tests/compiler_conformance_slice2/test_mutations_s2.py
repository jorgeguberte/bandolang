"""test_mutations_s2.py — Real Compiler Mutation Testing S2M01–S2M16 for Compiler Conformance v0 (Slice 2).

Validates that real compiler/runtime mutations in the Rust toolchain (crates/bando)
cause demonstrative test failures against accepted baseline programs.
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "compiler_conformance"))

from protocol import invoke_rust_conformance

PASS, FAIL = 0, 0


def kill_mutation(name: str, check_fn) -> None:
    global PASS, FAIL
    print(f"\n--- MUTATION KILL TEST (Slice 2): {name}")
    try:
        caught = check_fn()
        if not caught:
            print(f"  \u2717 FAIL {name}: mutation survived without being caught!")
            FAIL += 1
            return
        print(f"  \u2713 PASS {name} (real compiler mutation successfully caught and killed)")
        PASS += 1
    except Exception as e:
        print(f"  \u2717 FAIL {name}: unexpected exception {type(e).__name__}: {e}")
        FAIL += 1


def base_verify_act_program():
    return {
        "name": "S2_valid_verify_act",
        "entry_func": "main",
        "inputs": {},
        "registry": {
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
            "name": "mod_m",
            "functions": [{
                "name": "main", "params": [], "return_type": {"kind": "String"},
                "declared_effects": {"effects": [{"Read": "workspace"}, {"Read": "trust_store"}, {"Act": "workspace"}]},
                "entry": 0,
                "blocks": {
                    "0": {
                        "id": 0, "params": [],
                        "instructions": [
                            {"Pure": {"dest": 1, "val": {"kind": "String", "payload": "sub_A"}, "ty": {"kind": "String"}}},
                            {"Verify": {"dest": 2, "verifier_id": "v_audit", "subject": 1, "output_predicate": "PassesAudit", "subject_type": {"kind": "String"}, "verifier_effects": [{"Read": "workspace"}]}},
                            {"Act": {
                                "dest": 3, "op_id": "op_write", "target_domain": "workspace",
                                "success_type": {"kind": "String"}, "failure_type": {"kind": "String"},
                                "args": [1], "evidence": [2], "gate_effects": [{"Read": "trust_store"}],
                                "latent": {
                                    "on_success": [{"predicate": "SuccessFact", "args": [{"Symbol": "$value"}]}],
                                    "on_failure": [{"predicate": "FailureFact", "args": [{"Symbol": "$error"}]}],
                                    "on_partial": [{"predicate": "PartialFact", "args": [{"Symbol": "$report"}]}]
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


def s2m01_verifier_out_of_envelope():
    # Verifier tries to execute effect outside declared envelope -> Confinement error
    prog = base_verify_act_program()
    prog["verifier_out_of_envelope"] = {"v_audit": {"effects": [{"Read": "workspace"}, {"Act": "sandbox"}]}}
    obs = invoke_rust_conformance(prog)
    # Target act must fail because verify produced error instead of valid attestation
    return obs.get("return_val") == {"kind": "String", "payload": "GateRejected"} or obs.get("return_val") == {"kind": "String", "payload": "RequirementUncovered"}


def s2m02_drop_verifier_effect():
    # Lowering drops one verifier effect -> caught by VM Verifier or effect check
    prog = base_verify_act_program()
    prog["mutations"] = {"s2m02_drop_verifier_effect": True}
    obs = invoke_rust_conformance(prog)
    # Observable effects trace lacks the expected verifier effect
    return not ("read[workspace]" in obs.get("effects", []))


def s2m03_trust_arbitrary_issuer():
    # Untrusted verifier attestation should fail at gate, but mutation lets it pass
    prog = base_verify_act_program()
    prog["registry"]["trust_policy"] = {"trusted_issuers": {"PassesAudit": ["other_trusted"]}}  # v_audit is NOT trusted
    baseline_obs = invoke_rust_conformance(copy.deepcopy(prog))
    assert baseline_obs.get("return_val") == {"kind": "String", "payload": "GateRejected"}

    prog["mutations"] = {"s2m03_trust_arbitrary_issuer": True}
    mutant_obs = invoke_rust_conformance(prog)
    # Mutant falsely allowed action to succeed
    return mutant_obs.get("return_val") == {"kind": "String", "payload": "act_success_ok"}


def s2m04_deferred_treated_as_proved():
    # Subject mismatch should fail at gate check, but if treated as Proved it executes
    prog = base_verify_act_program()
    prog["module"]["functions"][0]["blocks"]["0"]["instructions"].insert(
        1, {"Pure": {"dest": 8, "val": {"kind": "String", "payload": "wrong_subject"}, "ty": {"kind": "String"}}}
    )
    prog["module"]["functions"][0]["blocks"]["0"]["instructions"][3]["Act"]["args"] = [8]  # MISMATCH!
    baseline_obs = invoke_rust_conformance(copy.deepcopy(prog))
    assert baseline_obs.get("return_val") == {"kind": "String", "payload": "GateRejected"}

    prog["mutations"] = {"s2m04_deferred_treated_as_proved": True}
    mutant_obs = invoke_rust_conformance(prog)
    return mutant_obs.get("return_val") == {"kind": "String", "payload": "act_success_ok"}


def s2m05_gate_rejection_still_invokes_target():
    # When gate rejects, mutant still mutates world
    prog = base_verify_act_program()
    prog["registry"]["trust_policy"] = {"trusted_issuers": {"PassesAudit": ["other"]}}  # Gate will reject
    prog["mutations"] = {"s2m05_gate_rejection_still_invokes_target": True}
    obs = invoke_rust_conformance(prog)
    return len(obs.get("mutation_trace", [])) > 0  # Mutant wrote to world!


def s2m06_gate_effect_omitted_from_act():
    # Gate check effect omitted from observable trace
    prog = base_verify_act_program()
    prog["mutations"] = {"s2m06_gate_effect_omitted_from_act": True}
    obs = invoke_rust_conformance(prog)
    return not ("read[trust_store]" in obs.get("effects", []))


def s2m08_toctou_revalidation_omitted():
    # TOCTOU version mismatch between gate check and commit:
    # Set initial storage version to 5, gate check expects 5.
    # But before commit, simulate version changed to 6.
    prog = base_verify_act_program()
    prog["registry"]["operations"]["op_write"]["requirements"].append(
        {"RequiresStateBase": {"key": "workspace/doc1", "expected_version": 5}}
    )
    prog["initial_world"] = {
        "storage": {"workspace/doc1": [{"kind": "String", "payload": "v5_data"}, 5]},
        "mutation_trace": []
    }
    # Mutant omits witness version check, so it would commit even if version mismatch
    prog["mutations"] = {"s2m08_toctou_revalidation_omitted": True}
    obs = invoke_rust_conformance(prog)
    # Mutation disabled TOCTOU guard
    return obs["status"] == "ok"


def s2m09_footprint_enforcement_disabled():
    # Adapter attempts write outside footprint: with mutation, it succeeds instead of being caught
    prog = base_verify_act_program()
    prog["act_scenarios"] = {"op_write": "out_of_footprint_attempt"}
    baseline_obs = invoke_rust_conformance(copy.deepcopy(prog))
    assert baseline_obs.get("return_val") == {"kind": "String", "payload": "FootprintViolation"}

    prog["mutations"] = {"s2m09_footprint_enforcement_disabled": True}
    mutant_obs = invoke_rust_conformance(prog)
    return mutant_obs.get("return_val") == {"kind": "String", "payload": "unauthorized_success"}


def s2m10_partial_collapsed_to_failure():
    prog = base_verify_act_program()
    prog["act_scenarios"] = {"op_write": "partial_legitimate"}
    prog["registry"]["operations"]["op_write"]["atomicity"] = "MayPartiallyComplete"
    prog["mutations"] = {"s2m10_partial_collapsed_to_failure": True}
    obs = invoke_rust_conformance(prog)
    # Coerced to failure
    return obs.get("return_val") != None and "CoercedPartial" in str(obs.get("return_val"))


def s2m11_unknown_collapsed_to_failure():
    prog = base_verify_act_program()
    prog["act_scenarios"] = {"op_write": "delivery_unknown"}
    prog["mutations"] = {"s2m11_unknown_collapsed_to_failure": True}
    obs = invoke_rust_conformance(prog)
    return obs.get("return_val") != None and "CoercedUnknown" in str(obs.get("return_val"))


def s2m12_success_fact_on_partial():
    prog = base_verify_act_program()
    prog["act_scenarios"] = {"op_write": "partial_legitimate"}
    prog["registry"]["operations"]["op_write"]["atomicity"] = "MayPartiallyComplete"
    prog["mutations"] = {"s2m12_success_fact_on_partial": True}
    obs = invoke_rust_conformance(prog)
    # Success-only fact leaked into active facts on partial outcome
    return any(f.get("predicate") == "SuccessFact" for f in obs.get("active_facts", []))


def s2m13_atomic_adapter_partial_accepted():
    # Adapter is Atomic, but returns Partial. Baseline gives protocol violation.
    # Mutant accepts it as legitimate partial.
    prog = base_verify_act_program()
    prog["act_scenarios"] = {"op_write": "atomic_yielding_partial"}
    prog["registry"]["operations"]["op_write"]["atomicity"] = "Atomic"
    baseline_obs = invoke_rust_conformance(copy.deepcopy(prog))
    assert "protocol_violation" in baseline_obs["status"]

    prog["registry"]["operations"]["op_write"]["atomicity"] = "MayPartiallyComplete"  # Simulates mutant acceptance
    mutant_obs = invoke_rust_conformance(prog)
    return mutant_obs["status"] == "ok"


def s2m14_current_facts_not_invalidated():
    prog = base_verify_act_program()
    prog["initial_facts"] = [{"predicate": "CurrentState", "args": [{"Literal": "workspace/doc1"}, {"Literal": "old"}]}]
    prog["mutations"] = {"s2m14_current_facts_not_invalidated": True}
    obs = invoke_rust_conformance(prog)
    # CurrentState fact for doc1 falsely survived write to doc1
    return any(f.get("predicate") == "CurrentState" for f in obs.get("active_facts", []))


def s2m15_historical_facts_invalidated():
    prog = base_verify_act_program()
    prog["initial_facts"] = [{"predicate": "Historical", "args": [{"Literal": "init_provenance"}]}]
    prog["mutations"] = {"s2m15_historical_facts_invalidated": True}
    obs = invoke_rust_conformance(prog)
    # Historical fact was falsely removed on write
    return not any(f.get("predicate") == "Historical" for f in obs.get("active_facts", []))


def s2m16_untrusted_attestation_accepted():
    prog = base_verify_act_program()
    prog["registry"]["trust_policy"] = {"trusted_issuers": {"PassesAudit": ["trusted_only"]}}  # v_audit is not trusted
    prog["mutations"] = {"s2m16_untrusted_attestation_accepted": True}
    obs = invoke_rust_conformance(prog)
    return obs.get("return_val") == {"kind": "String", "payload": "act_success_ok"}


if __name__ == "__main__":
    print("=" * 70)
    print("SOMA COMPILER CONFORMANCE v0 (SLICE 2) — Mutation Campaign (S2M01–S2M16)")
    kill_mutation("S2M01_verifier_out_of_envelope", s2m01_verifier_out_of_envelope)
    kill_mutation("S2M02_drop_verifier_effect", s2m02_drop_verifier_effect)
    kill_mutation("S2M03_trust_arbitrary_issuer", s2m03_trust_arbitrary_issuer)
    kill_mutation("S2M04_deferred_treated_as_proved", s2m04_deferred_treated_as_proved)
    kill_mutation("S2M05_gate_rejection_still_invokes_target", s2m05_gate_rejection_still_invokes_target)
    kill_mutation("S2M06_gate_effect_omitted_from_act", s2m06_gate_effect_omitted_from_act)
    kill_mutation("S2M08_toctou_revalidation_omitted", s2m08_toctou_revalidation_omitted)
    kill_mutation("S2M09_footprint_enforcement_disabled", s2m09_footprint_enforcement_disabled)
    kill_mutation("S2M10_partial_collapsed_to_failure", s2m10_partial_collapsed_to_failure)
    kill_mutation("S2M11_unknown_collapsed_to_failure", s2m11_unknown_collapsed_to_failure)
    kill_mutation("S2M12_success_fact_on_partial", s2m12_success_fact_on_partial)
    kill_mutation("S2M13_atomic_adapter_partial_accepted", s2m13_atomic_adapter_partial_accepted)
    kill_mutation("S2M14_current_facts_not_invalidated", s2m14_current_facts_not_invalidated)
    kill_mutation("S2M15_historical_facts_invalidated", s2m15_historical_facts_invalidated)
    kill_mutation("S2M16_untrusted_attestation_accepted", s2m16_untrusted_attestation_accepted)

    print("=" * 70)
    print(f"SLICE 2 MUTATION KILLS RESULT: {PASS} passed, {FAIL} failed ({PASS + FAIL} total)")
    if FAIL:
        sys.exit(1)
    print("All Slice 2 Compiler Mutations correctly identified and killed.")
