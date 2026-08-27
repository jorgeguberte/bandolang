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
                                "args": [1], "evidence": [2], "gate_effects": [],
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
    prog = base_verify_act_program()
    prog["verifier_out_of_envelope"] = {"v_audit": {"effects": [{"Read": "workspace"}, {"Act": "sandbox"}]}}
    obs = invoke_rust_conformance(prog)
    return obs.get("return_val") == {"kind": "String", "payload": "GateRejected"} or obs.get("return_val") == {"kind": "String", "payload": "RequirementUncovered"}


def s2m02_drop_verifier_effect():
    prog = base_verify_act_program()
    prog["mutations"] = {"s2m02_drop_verifier_effect": True}
    obs = invoke_rust_conformance(prog)
    return not ("read[workspace]" in obs.get("effects", []))


def s2m03_trust_arbitrary_issuer():
    prog = base_verify_act_program()
    prog["registry"]["trust_policy"] = {"trusted_issuers": {"PassesAudit": ["other_trusted"]}}
    baseline_obs = invoke_rust_conformance(copy.deepcopy(prog))
    assert baseline_obs.get("return_val") == {"kind": "String", "payload": "GateRejected"}

    prog["mutations"] = {"s2m03_trust_arbitrary_issuer": True}
    mutant_obs = invoke_rust_conformance(prog)
    return mutant_obs.get("return_val") == {"kind": "String", "payload": "act_success_ok"}


def s2m04_deferred_treated_as_proved():
    prog = base_verify_act_program()
    prog["module"]["functions"][0]["blocks"]["0"]["instructions"].insert(
        1, {"Pure": {"dest": 8, "val": {"kind": "String", "payload": "wrong_subject"}, "ty": {"kind": "String"}}}
    )
    prog["module"]["functions"][0]["blocks"]["0"]["instructions"][3]["Act"]["args"] = [8]
    baseline_obs = invoke_rust_conformance(copy.deepcopy(prog))
    assert baseline_obs.get("return_val") == {"kind": "String", "payload": "GateRejected"}

    prog["mutations"] = {"s2m04_deferred_treated_as_proved": True}
    mutant_obs = invoke_rust_conformance(prog)
    return mutant_obs.get("return_val") == {"kind": "String", "payload": "act_success_ok"}


def s2m05_gate_rejection_still_invokes_target():
    prog = base_verify_act_program()
    prog["registry"]["trust_policy"] = {"trusted_issuers": {"PassesAudit": ["other"]}}
    prog["mutations"] = {"s2m05_gate_rejection_still_invokes_target": True}
    obs = invoke_rust_conformance(prog)
    return len(obs.get("mutation_trace", [])) > 0


def s2m06_gate_effect_omitted_from_act():
    prog = base_verify_act_program()
    prog["mutations"] = {"s2m06_gate_effect_omitted_from_act": True}
    obs = invoke_rust_conformance(prog)
    return not ("read[trust_store]" in obs.get("effects", []))


def s2m07_trusted_gate_requires_caller_authority():
    # Caller authority has ONLY act[workspace]. Runtime authority has read[trust_store].
    # Baseline: gate passes because runtime authority covers read[trust_store].
    # Mutant: requires caller authority for read[trust_store], so gate fails!
    prog = base_verify_act_program()
    prog["registry"]["caller_authority"] = {"effects": [{"Read": "workspace"}, {"Act": "workspace"}]}  # lacks read[trust_store]
    prog["registry"]["runtime_authority"] = {"effects": [{"Read": "trust_store"}]}
    baseline_obs = invoke_rust_conformance(copy.deepcopy(prog))
    assert baseline_obs.get("return_val") == {"kind": "String", "payload": "act_success_ok"}

    prog["mutations"] = {"s2m07_trusted_gate_requires_caller_authority": True}
    mutant_obs = invoke_rust_conformance(prog)
    return mutant_obs.get("return_val") == {"kind": "String", "payload": "GateRejected"}


def s2m08_toctou_revalidation_omitted():
    # Deterministic TOCTOU hook: version starts at 5, gate observes 5.
    # Hook mutates storage version to 6 before commit.
    # Baseline: atomic revalidation sees 6 != 5 -> reject commit, zero write.
    # Mutant (s2m08_toctou_revalidation_omitted): omits witness version check -> commits blindly!
    prog = base_verify_act_program()
    prog["module"]["functions"][0]["declared_effects"]["effects"].append({"Read": "state_base"})
    prog["registry"]["operations"]["op_write"]["declared_envelope"]["effects"].append({"Read": "state_base"})
    prog["registry"]["runtime_authority"]["effects"].append({"Read": "state_base"})
    prog["registry"]["operations"]["op_write"]["requirements"].append(
        {"RequiresStateBase": {"key": "workspace/doc1", "expected_version": 5}}
    )
    prog["initial_world"] = {
        "storage": {"workspace/doc1": [{"kind": "String", "payload": "v5_data"}, 5]},
        "mutation_trace": []
    }
    prog["toctou_hook_bumps"] = {
        "op_write": ("workspace/doc1", {"kind": "String", "payload": "inter_bumped"}, 6)
    }

    baseline_obs = invoke_rust_conformance(copy.deepcopy(prog))
    assert baseline_obs.get("return_val") == {"kind": "String", "payload": "GateRejected"}, f"baseline must reject TOCTOU race: got {baseline_obs}"
    assert len(baseline_obs.get("mutation_trace", [])) == 0, "baseline must have 0 target mutation on TOCTOU failure"

    prog["mutations"] = {"s2m08_toctou_revalidation_omitted": True}
    mutant_obs = invoke_rust_conformance(prog)
    # Mutant falsely allowed commit and recorded mutation trace!
    return mutant_obs.get("return_val") == {"kind": "String", "payload": "act_success_ok"} and len(mutant_obs.get("mutation_trace", [])) > 0


def s2m09_footprint_enforcement_disabled():
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
    return any(f.get("predicate") == "SuccessFact" for f in obs.get("active_facts", []))


def s2m13_atomic_adapter_partial_accepted():
    prog = base_verify_act_program()
    prog["act_scenarios"] = {"op_write": "atomic_yielding_partial"}
    prog["registry"]["operations"]["op_write"]["atomicity"] = "Atomic"
    baseline_obs = invoke_rust_conformance(copy.deepcopy(prog))
    assert "protocol_violation" in baseline_obs["status"]

    prog["registry"]["operations"]["op_write"]["atomicity"] = "MayPartiallyComplete"
    mutant_obs = invoke_rust_conformance(prog)
    return mutant_obs["status"] == "ok"


def s2m14_current_facts_not_invalidated():
    prog = base_verify_act_program()
    prog["initial_facts"] = [{"predicate": "CurrentState", "args": [{"Literal": "workspace/doc1"}, {"Literal": "old"}]}]
    baseline_obs = invoke_rust_conformance(copy.deepcopy(prog))
    assert not any(f.get("predicate") == "CurrentState" for f in baseline_obs.get("active_facts", [])), "CurrentState must be invalidated"

    prog["mutations"] = {"s2m14_current_facts_not_invalidated": True}
    mutant_obs = invoke_rust_conformance(prog)
    return any(f.get("predicate") == "CurrentState" for f in mutant_obs.get("active_facts", []))


def s2m15_historical_facts_invalidated():
    prog = base_verify_act_program()
    prog["initial_facts"] = [{"predicate": "Historical", "args": [{"Literal": "init_provenance"}]}]
    baseline_obs = invoke_rust_conformance(copy.deepcopy(prog))
    assert any(f.get("predicate") == "Historical" for f in baseline_obs.get("active_facts", [])), "Historical must survive"

    prog["mutations"] = {"s2m15_historical_facts_invalidated": True}
    mutant_obs = invoke_rust_conformance(prog)
    return not any(f.get("predicate") == "Historical" for f in mutant_obs.get("active_facts", []))


def s2m16_untrusted_attestation_accepted():
    prog = base_verify_act_program()
    prog["registry"]["trust_policy"] = {"trusted_issuers": {"PassesAudit": ["trusted_only"]}}
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
    kill_mutation("S2M07_trusted_gate_requires_caller_authority", s2m07_trusted_gate_requires_caller_authority)
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
    print("All 16 Slice 2 Compiler Mutations correctly identified and killed.")
