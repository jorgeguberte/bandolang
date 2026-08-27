"""test_scenarios.py — SOMA Binding Contract v0 Baseline Scenario Suite.

Verifies that the clean baseline formalization satisfies all 16 canonical scenarios
and passes all normative invariants B1–B12.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Add package directory to path
sys.path.insert(0, str(Path(__file__).parent))

from invariants import (
    assert_b1_type_equality_not_binding_equality,
    assert_b2_lineage_overlap_not_subject_identity,
    assert_b3_exact_known_mismatch_is_refuted,
    assert_b4_lack_of_proof_is_not_refuted,
    assert_b5_base_state_independent_from_subject,
    assert_b6_currentness_is_not_lexical_identity,
    assert_b7_static_success_requires_complete_proof,
    assert_b8_refutation_dominates_deferred,
    assert_b9_deferred_checks_are_explicit,
    assert_b10_gate_cannot_widen_binding,
    assert_b11_attestation_predicate_exact,
    assert_b12_cfg_joins_conservative,
)
from model import (
    BindingEvidence,
    BindingRequirement,
    BindingTerm,
    PathFactContext,
    match_binding,
    match_term,
    conservative_cfg_join,
)
from scenarios import get_all_scenarios


def main():
    print("=" * 70)
    print("SOMA BINDING CONTRACT v0 — Canonical Scenario Verification Suite")
    print("=" * 70)

    scenarios = get_all_scenarios()
    passed = 0
    total = len(scenarios)

    for sc in scenarios:
        name = sc["name"]
        req = sc["req"]
        ev = sc["ev"]
        ctx = sc["ctx"]
        exp_proved = sc["expected_proved"]
        exp_refuted = sc["expected_refuted"]
        exp_checks = sc["expected_checks_count"]

        res = match_binding(req, ev, ctx)

        assert res.is_proved == exp_proved, (
            f"Scenario '{name}' failed: expected is_proved={exp_proved}, got {res.is_proved}"
        )
        assert res.is_refuted == exp_refuted, (
            f"Scenario '{name}' failed: expected is_refuted={exp_refuted}, got {res.is_refuted}"
        )
        assert len(res.deferred_checks) == exp_checks, (
            f"Scenario '{name}' failed: expected {exp_checks} deferred checks, got {len(res.deferred_checks)}"
        )

        # Validate explicit checks if deferred
        assert_b9_deferred_checks_are_explicit(res)

        print(f"  ✓ PASS scenario: {name:<36} (proved={res.is_proved}, refuted={res.is_refuted}, checks={len(res.deferred_checks)})")
        passed += 1

    # Invariants verification on baseline
    print("\n--- NORMATIVE INVARIANTS VERIFICATION (B1–B12) ---")
    ctx = PathFactContext()

    # B1
    t_diff_a = BindingTerm.value_ref("diff_a", "Diff")
    t_diff_b = BindingTerm.value_ref("diff_b", "Diff")
    assert_b1_type_equality_not_binding_equality(t_diff_a, t_diff_b, ctx)
    print("  ✓ PASS B1: Type equality is not binding equality")

    # B2
    t_lin_a = BindingTerm.value_ref("diff_a", "Diff", lineage_ids={"agent_1", "step_0"})
    t_lin_b = BindingTerm.value_ref("diff_b", "Diff", lineage_ids={"agent_1", "step_0"})
    assert_b2_lineage_overlap_not_subject_identity(t_lin_a, t_lin_b, ctx)
    print("  ✓ PASS B2: Lineage overlap is not subject identity")

    # B3
    t_dig_a = BindingTerm.stable_digest("sha256", "hash_1")
    t_dig_b = BindingTerm.stable_digest("sha256", "hash_2")
    assert_b3_exact_known_mismatch_is_refuted(t_dig_a, t_dig_b, ctx)
    print("  ✓ PASS B3: Exact known mismatch is Refuted")

    # B4
    t_opaque = BindingTerm.opaque_ref("child", "handle_123")
    assert_b4_lack_of_proof_is_not_refuted(t_dig_a, t_opaque, ctx)
    print("  ✓ PASS B4: Lack of proof is not Refuted (Deferred)")

    # B5
    t_repo_a = BindingTerm.stable_digest("sha256", "repo_a")
    t_repo_b = BindingTerm.stable_digest("sha256", "repo_b")
    req_b5 = BindingRequirement(predicate="TestsPassed", subject=t_dig_a, base=t_repo_a)
    ev_b5 = BindingEvidence(predicate="TestsPassed", subject_binding=t_dig_a, base_binding=t_repo_b)
    assert_b5_base_state_independent_from_subject(req_b5, ev_b5, ctx)
    print("  ✓ PASS B5: Base-state binding is independent from subject binding")

    # B6
    t_state = BindingTerm.state_ref("db", "users")
    req_b6 = BindingRequirement(predicate="SchemaValidated", subject=t_dig_a, base=t_state)
    ev_b6_stale = BindingEvidence(predicate="SchemaValidated", subject_binding=t_dig_a, base_binding=t_state, currentness_witness=False)
    ev_b6_missing = BindingEvidence(predicate="SchemaValidated", subject_binding=t_dig_a, base_binding=t_state, currentness_witness=None)
    assert_b6_currentness_is_not_lexical_identity(req_b6, ev_b6_stale, ctx)
    assert_b6_currentness_is_not_lexical_identity(req_b6, ev_b6_missing, ctx)
    print("  ✓ PASS B6: Currentness is not lexical identity")

    # B7
    assert_b7_static_success_requires_complete_proof(req_b5, ev_b5, ctx)
    print("  ✓ PASS B7: Static success requires complete static proof")

    # B8
    req_b8 = BindingRequirement(predicate="TestsPassed", subject=t_dig_a, base=t_opaque)
    ev_b8 = BindingEvidence(predicate="TestsPassed", subject_binding=t_dig_b, base_binding=t_repo_a)
    assert_b8_refutation_dominates_deferred(req_b8, ev_b8, ctx)
    print("  ✓ PASS B8: Refutation dominates Deferred")

    # B9
    res_b9 = match_binding(req_b8, BindingEvidence(predicate="TestsPassed", subject_binding=t_opaque, base_binding=t_repo_a), ctx)
    assert_b9_deferred_checks_are_explicit(res_b9)
    print("  ✓ PASS B9: Deferred checks are explicit obligations")

    # B10
    ev_b10 = BindingEvidence(predicate="TestsPassed", subject_binding=t_dig_a)
    assert_b10_gate_cannot_widen_binding(ev_b10, t_dig_b, ctx)
    print("  ✓ PASS B10: Gate cannot widen a binding")

    # B11
    req_b11 = BindingRequirement(predicate="SafeToDeploy", subject=t_dig_a)
    ev_b11 = BindingEvidence(predicate="TestsPassed", subject_binding=t_dig_a)
    assert_b11_attestation_predicate_exact(req_b11, ev_b11, ctx)
    print("  ✓ PASS B11: Attestation predicate remains exact")

    # B12
    ev_b12_a = BindingEvidence(predicate="TestsPassed", subject_binding=t_dig_a)
    ev_b12_b = BindingEvidence(predicate="TestsPassed", subject_binding=t_dig_b)
    assert_b12_cfg_joins_conservative(ev_b12_a, ev_b12_b, ctx)
    print("  ✓ PASS B12: Joins of CFG remain conservative")

    print("=" * 70)
    print(f"BINDING CONTRACT v0 SCENARIOS RESULT: {passed}/{total} passed (100% GREEN).")
    print("=" * 70)


if __name__ == "__main__":
    main()
