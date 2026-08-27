"""scenarios.py — Canonical Test Scenarios for SOMA Binding Contract v0.

Covers the complete minimal scenario matrix for formal verification and falsification (R1 & R2).
"""
from __future__ import annotations

from typing import Any, Dict, List
try:
    from .model import (
        BindingEvidence,
        BindingRequirement,
        BindingTerm,
        PathFactContext,
        SymbolicMatch,
        match_binding,
        match_term,
        conservative_cfg_join,
    )
except ImportError:
    from model import (
        BindingEvidence,
        BindingRequirement,
        BindingTerm,
        PathFactContext,
        SymbolicMatch,
        match_binding,
        match_term,
        conservative_cfg_join,
    )


def get_all_scenarios() -> List[Dict[str, Any]]:
    scenarios = []

    # 1. same_subject_same_base -> Proved
    term_diff1 = BindingTerm.stable_digest("sha256", "aabbcc112233", "Diff")
    term_repo1 = BindingTerm.stable_digest("sha256", "commit_0001", "Commit")
    req1 = BindingRequirement(predicate="TestsPassed", subject=term_diff1, base=term_repo1)
    ev1 = BindingEvidence(predicate="TestsPassed", subject_binding=term_diff1, base_binding=term_repo1)
    scenarios.append({
        "name": "same_subject_same_base",
        "req": req1,
        "ev": ev1,
        "ctx": PathFactContext(),
        "expected_proved": True,
        "expected_refuted": False,
        "expected_checks_count": 0,
    })

    # 2. same_subject_different_base -> Refuted
    term_repo2 = BindingTerm.stable_digest("sha256", "commit_0002", "Commit")
    req2 = BindingRequirement(predicate="TestsPassed", subject=term_diff1, base=term_repo1)
    ev2 = BindingEvidence(predicate="TestsPassed", subject_binding=term_diff1, base_binding=term_repo2)
    scenarios.append({
        "name": "same_subject_different_base",
        "req": req2,
        "ev": ev2,
        "ctx": PathFactContext(),
        "expected_proved": False,
        "expected_refuted": True,
        "expected_checks_count": 0,
    })

    # 3. different_subject_same_type -> Refuted (B1)
    term_diff2 = BindingTerm.stable_digest("sha256", "ddeeff445566", "Diff")
    req3 = BindingRequirement(predicate="TestsPassed", subject=term_diff1)
    ev3 = BindingEvidence(predicate="TestsPassed", subject_binding=term_diff2)
    scenarios.append({
        "name": "different_subject_same_type",
        "req": req3,
        "ev": ev3,
        "ctx": PathFactContext(),
        "expected_proved": False,
        "expected_refuted": True,
        "expected_checks_count": 0,
    })

    # 4. different_subject_shared_lineage -> Refuted (B2)
    term_v1 = BindingTerm.value_ref("v1", "Diff", lineage_ids={"agent_A", "intent_1"})
    term_v2 = BindingTerm.value_ref("v2", "Diff", lineage_ids={"agent_A", "intent_1"})
    term_v1_digest = BindingTerm(term_v1.kind, "Diff", "v1", digest="hash_1", lineage_ids=term_v1.lineage_ids)
    term_v2_digest = BindingTerm(term_v2.kind, "Diff", "v2", digest="hash_2", lineage_ids=term_v2.lineage_ids)
    req4 = BindingRequirement(predicate="TestsPassed", subject=term_v1_digest)
    ev4 = BindingEvidence(predicate="TestsPassed", subject_binding=term_v2_digest)
    scenarios.append({
        "name": "different_subject_shared_lineage",
        "req": req4,
        "ev": ev4,
        "ctx": PathFactContext(),
        "expected_proved": False,
        "expected_refuted": True,
        "expected_checks_count": 0,
    })

    # 5. concrete_digest_mismatch -> Refuted (B3)
    term_d1 = BindingTerm.stable_digest("sha256", "111111111111")
    term_d2 = BindingTerm.stable_digest("sha256", "222222222222")
    req5 = BindingRequirement(predicate="LintClean", subject=term_d1)
    ev5 = BindingEvidence(predicate="LintClean", subject_binding=term_d2)
    scenarios.append({
        "name": "concrete_digest_mismatch",
        "req": req5,
        "ev": ev5,
        "ctx": PathFactContext(),
        "expected_proved": False,
        "expected_refuted": True,
        "expected_checks_count": 0,
    })

    # 6. same_artifact_conflicting_digest -> Refuted (R1)
    art1 = BindingTerm.artifact_identity("file", "src/main.rs", digest="sha256:aaaa")
    art2 = BindingTerm.artifact_identity("file", "src/main.rs", digest="sha256:bbbb")
    req6 = BindingRequirement(predicate="Compiled", subject=art1)
    ev6 = BindingEvidence(predicate="Compiled", subject_binding=art2)
    scenarios.append({
        "name": "same_artifact_conflicting_digest",
        "req": req6,
        "ev": ev6,
        "ctx": PathFactContext(),
        "expected_proved": False,
        "expected_refuted": True,
        "expected_checks_count": 0,
    })

    # 7. same_digest_different_algorithm -> Refuted (R1)
    dig_sha256 = BindingTerm.stable_digest("sha256", "deadbeef0011")
    dig_sha512 = BindingTerm.stable_digest("sha512", "deadbeef0011")
    req7 = BindingRequirement(predicate="Verified", subject=dig_sha256)
    ev7 = BindingEvidence(predicate="Verified", subject_binding=dig_sha512)
    scenarios.append({
        "name": "same_digest_different_algorithm",
        "req": req7,
        "ev": ev7,
        "ctx": PathFactContext(),
        "expected_proved": False,
        "expected_refuted": True,
        "expected_checks_count": 0,
    })

    # 8. alias_cannot_override_concrete_mismatch -> Refuted (R1, R4)
    v_alias1 = BindingTerm.value_ref("v1", "Diff", digest="hash_alpha")
    v_alias2 = BindingTerm.value_ref("v2", "Diff", digest="hash_beta")
    ctx_contradictory_alias = PathFactContext(known_aliases={"v1": "v2"})
    req8 = BindingRequirement(predicate="TestsPassed", subject=v_alias1)
    ev8 = BindingEvidence(predicate="TestsPassed", subject_binding=v_alias2)
    scenarios.append({
        "name": "alias_cannot_override_concrete_mismatch",
        "req": req8,
        "ev": ev8,
        "ctx": ctx_contradictory_alias,
        "expected_proved": False,
        "expected_refuted": True,
        "expected_checks_count": 0,
    })

    # 9. opaque_delegated_subject -> Deferred (B4)
    term_opaque_child = BindingTerm.opaque_ref("child_agent_1", "handle_xyz", "Diff")
    req9 = BindingRequirement(predicate="TestsPassed", subject=term_diff1)
    ev9 = BindingEvidence(predicate="TestsPassed", subject_binding=term_opaque_child, provenance="Delegated")
    scenarios.append({
        "name": "opaque_delegated_subject",
        "req": req9,
        "ev": ev9,
        "ctx": PathFactContext(),
        "expected_proved": False,
        "expected_refuted": False,
        "expected_checks_count": 1,
    })

    # 10. opaque_base_identity -> Deferred (B4, B5)
    term_opaque_base = BindingTerm.opaque_ref("external_vcs", "repo_token_99", "Commit")
    req10 = BindingRequirement(predicate="TestsPassed", subject=term_diff1, base=term_repo1)
    ev10 = BindingEvidence(predicate="TestsPassed", subject_binding=term_diff1, base_binding=term_opaque_base)
    scenarios.append({
        "name": "opaque_base_identity",
        "req": req10,
        "ev": ev10,
        "ctx": PathFactContext(),
        "expected_proved": False,
        "expected_refuted": False,
        "expected_checks_count": 1,
    })

    # 11. currentness_witness_success -> Proved (B6)
    term_state = BindingTerm.state_ref("database", "table_users")
    req11 = BindingRequirement(predicate="SchemaValidated", subject=term_diff1, base=term_state)
    ev11 = BindingEvidence(predicate="SchemaValidated", subject_binding=term_diff1, base_binding=term_state, currentness_witness=True)
    scenarios.append({
        "name": "currentness_witness_success",
        "req": req11,
        "ev": ev11,
        "ctx": PathFactContext(),
        "expected_proved": True,
        "expected_refuted": False,
        "expected_checks_count": 0,
    })

    # 12. currentness_witness_stale -> Refuted (B6)
    ev12 = BindingEvidence(predicate="SchemaValidated", subject_binding=term_diff1, base_binding=term_state, currentness_witness=False)
    scenarios.append({
        "name": "currentness_witness_stale",
        "req": req11,
        "ev": ev12,
        "ctx": PathFactContext(),
        "expected_proved": False,
        "expected_refuted": True,
        "expected_checks_count": 0,
    })

    # 13. currentness_witness_missing -> Deferred (B6)
    ev13 = BindingEvidence(predicate="SchemaValidated", subject_binding=term_diff1, base_binding=term_state, currentness_witness=None)
    scenarios.append({
        "name": "currentness_witness_missing",
        "req": req11,
        "ev": ev13,
        "ctx": PathFactContext(),
        "expected_proved": False,
        "expected_refuted": False,
        "expected_checks_count": 1,
    })

    # 14. expired_validity -> Refuted (R2)
    term_validity = BindingTerm.literal("2026-08-27T00:00:00Z", "Timestamp")
    req14 = BindingRequirement(predicate="Certified", subject=term_diff1, validity=term_validity)
    ev14 = BindingEvidence(predicate="Certified", subject_binding=term_diff1, validity_binding=term_validity, validity_witness=False)
    scenarios.append({
        "name": "expired_validity",
        "req": req14,
        "ev": ev14,
        "ctx": PathFactContext(),
        "expected_proved": False,
        "expected_refuted": True,
        "expected_checks_count": 0,
    })

    # 15. unknown_validity -> Deferred (R2)
    ev15 = BindingEvidence(predicate="Certified", subject_binding=term_diff1, validity_binding=term_validity, validity_witness=None)
    scenarios.append({
        "name": "unknown_validity",
        "req": req14,
        "ev": ev15,
        "ctx": PathFactContext(),
        "expected_proved": False,
        "expected_refuted": False,
        "expected_checks_count": 1,
    })

    # 16. valid_validity -> Proved (R2)
    ev16 = BindingEvidence(predicate="Certified", subject_binding=term_diff1, validity_binding=term_validity, validity_witness=True)
    scenarios.append({
        "name": "valid_validity",
        "req": req14,
        "ev": ev16,
        "ctx": PathFactContext(),
        "expected_proved": True,
        "expected_refuted": False,
        "expected_checks_count": 0,
    })

    # 17. alias_proven_equal -> Proved
    term_val_x = BindingTerm.value_ref("vx", "Diff")
    term_val_y = BindingTerm.value_ref("vy", "Diff")
    ctx_alias = PathFactContext(known_aliases={"vx": "vy"})
    req17 = BindingRequirement(predicate="TestsPassed", subject=term_val_x)
    ev17 = BindingEvidence(predicate="TestsPassed", subject_binding=term_val_y)
    scenarios.append({
        "name": "alias_proven_equal",
        "req": req17,
        "ev": ev17,
        "ctx": ctx_alias,
        "expected_proved": True,
        "expected_refuted": False,
        "expected_checks_count": 0,
    })

    # 18. alias_not_proven_equal -> Deferred
    req18 = BindingRequirement(predicate="TestsPassed", subject=term_val_x)
    ev18 = BindingEvidence(predicate="TestsPassed", subject_binding=term_val_y)
    scenarios.append({
        "name": "alias_not_proven_equal",
        "req": req18,
        "ev": ev18,
        "ctx": PathFactContext(),
        "expected_proved": False,
        "expected_refuted": False,
        "expected_checks_count": 1,
    })

    # 19. predicate_mismatch -> Refuted (B11)
    req19 = BindingRequirement(predicate="SafeToDeploy", subject=term_diff1)
    ev19 = BindingEvidence(predicate="TestsPassed", subject_binding=term_diff1)
    scenarios.append({
        "name": "predicate_mismatch",
        "req": req19,
        "ev": ev19,
        "ctx": PathFactContext(),
        "expected_proved": False,
        "expected_refuted": True,
        "expected_checks_count": 0,
    })

    # 20. scope_mismatch -> Refuted
    term_scope1 = BindingTerm.literal("prod", "string")
    term_scope2 = BindingTerm.literal("staging", "string")
    req20 = BindingRequirement(predicate="TestsPassed", subject=term_diff1, scope=term_scope1)
    ev20 = BindingEvidence(predicate="TestsPassed", subject_binding=term_diff1, scope_binding=term_scope2)
    scenarios.append({
        "name": "scope_mismatch",
        "req": req20,
        "ev": ev20,
        "ctx": PathFactContext(),
        "expected_proved": False,
        "expected_refuted": True,
        "expected_checks_count": 0,
    })

    # 21. multiple_deferred_checks -> Deferred with count >= 2 (B7, B9)
    req21 = BindingRequirement(predicate="TestsPassed", subject=term_opaque_child, base=term_opaque_base)
    ev21 = BindingEvidence(predicate="TestsPassed", subject_binding=term_diff1, base_binding=term_repo1)
    scenarios.append({
        "name": "multiple_deferred_checks",
        "req": req21,
        "ev": ev21,
        "ctx": PathFactContext(),
        "expected_proved": False,
        "expected_refuted": False,
        "expected_checks_count": 2,
    })

    # 22. refuted_and_deferred_composition -> Refuted (B8)
    req22 = BindingRequirement(predicate="TestsPassed", subject=term_diff1, base=term_opaque_base)
    ev22 = BindingEvidence(predicate="TestsPassed", subject_binding=term_diff2, base_binding=term_repo1)
    scenarios.append({
        "name": "refuted_and_deferred_composition",
        "req": req22,
        "ev": ev22,
        "ctx": PathFactContext(),
        "expected_proved": False,
        "expected_refuted": True,
        "expected_checks_count": 0,
    })

    return scenarios
