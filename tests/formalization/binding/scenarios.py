"""scenarios.py — Canonical Test Scenarios for SOMA Binding Contract v0.

Covers the complete minimal scenario matrix for formal verification and falsification.
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

    # 6. opaque_delegated_subject -> Deferred (B4)
    term_opaque_child = BindingTerm.opaque_ref("child_agent_1", "handle_xyz", "Diff")
    req6 = BindingRequirement(predicate="TestsPassed", subject=term_diff1)
    ev6 = BindingEvidence(predicate="TestsPassed", subject_binding=term_opaque_child, provenance="Delegated")
    scenarios.append({
        "name": "opaque_delegated_subject",
        "req": req6,
        "ev": ev6,
        "ctx": PathFactContext(),
        "expected_proved": False,
        "expected_refuted": False,
        "expected_checks_count": 1,
    })

    # 7. opaque_base_identity -> Deferred (B4, B5)
    term_opaque_base = BindingTerm.opaque_ref("external_vcs", "repo_token_99", "Commit")
    req7 = BindingRequirement(predicate="TestsPassed", subject=term_diff1, base=term_repo1)
    ev7 = BindingEvidence(predicate="TestsPassed", subject_binding=term_diff1, base_binding=term_opaque_base)
    scenarios.append({
        "name": "opaque_base_identity",
        "req": req7,
        "ev": ev7,
        "ctx": PathFactContext(),
        "expected_proved": False,
        "expected_refuted": False,
        "expected_checks_count": 1,
    })

    # 8. currentness_witness_success -> Proved (B6)
    term_state = BindingTerm.state_ref("database", "table_users")
    req8 = BindingRequirement(predicate="SchemaValidated", subject=term_diff1, base=term_state)
    ev8 = BindingEvidence(predicate="SchemaValidated", subject_binding=term_diff1, base_binding=term_state, currentness_witness=True)
    scenarios.append({
        "name": "currentness_witness_success",
        "req": req8,
        "ev": ev8,
        "ctx": PathFactContext(),
        "expected_proved": True,
        "expected_refuted": False,
        "expected_checks_count": 0,
    })

    # 9. currentness_witness_stale -> Refuted (B6)
    ev9 = BindingEvidence(predicate="SchemaValidated", subject_binding=term_diff1, base_binding=term_state, currentness_witness=False)
    scenarios.append({
        "name": "currentness_witness_stale",
        "req": req8,
        "ev": ev9,
        "ctx": PathFactContext(),
        "expected_proved": False,
        "expected_refuted": True,
        "expected_checks_count": 0,
    })

    # 10. currentness_witness_missing -> Deferred (B6)
    ev10 = BindingEvidence(predicate="SchemaValidated", subject_binding=term_diff1, base_binding=term_state, currentness_witness=None)
    scenarios.append({
        "name": "currentness_witness_missing",
        "req": req8,
        "ev": ev10,
        "ctx": PathFactContext(),
        "expected_proved": False,
        "expected_refuted": False,
        "expected_checks_count": 1,
    })

    # 11. alias_proven_equal -> Proved
    term_val_x = BindingTerm.value_ref("vx", "Diff")
    term_val_y = BindingTerm.value_ref("vy", "Diff")
    ctx_alias = PathFactContext(known_aliases={"vx": "vy"})
    req11 = BindingRequirement(predicate="TestsPassed", subject=term_val_x)
    ev11 = BindingEvidence(predicate="TestsPassed", subject_binding=term_val_y)
    scenarios.append({
        "name": "alias_proven_equal",
        "req": req11,
        "ev": ev11,
        "ctx": ctx_alias,
        "expected_proved": True,
        "expected_refuted": False,
        "expected_checks_count": 0,
    })

    # 12. alias_not_proven_equal -> Deferred
    req12 = BindingRequirement(predicate="TestsPassed", subject=term_val_x)
    ev12 = BindingEvidence(predicate="TestsPassed", subject_binding=term_val_y)
    scenarios.append({
        "name": "alias_not_proven_equal",
        "req": req12,
        "ev": ev12,
        "ctx": PathFactContext(),
        "expected_proved": False,
        "expected_refuted": False,
        "expected_checks_count": 1,
    })

    # 13. predicate_mismatch -> Refuted (B11)
    req13 = BindingRequirement(predicate="SafeToDeploy", subject=term_diff1)
    ev13 = BindingEvidence(predicate="TestsPassed", subject_binding=term_diff1)
    scenarios.append({
        "name": "predicate_mismatch",
        "req": req13,
        "ev": ev13,
        "ctx": PathFactContext(),
        "expected_proved": False,
        "expected_refuted": True,
        "expected_checks_count": 0,
    })

    # 14. scope_mismatch -> Refuted
    term_scope1 = BindingTerm.literal("prod", "string")
    term_scope2 = BindingTerm.literal("staging", "string")
    req14 = BindingRequirement(predicate="TestsPassed", subject=term_diff1, scope=term_scope1)
    ev14 = BindingEvidence(predicate="TestsPassed", subject_binding=term_diff1, scope_binding=term_scope2)
    scenarios.append({
        "name": "scope_mismatch",
        "req": req14,
        "ev": ev14,
        "ctx": PathFactContext(),
        "expected_proved": False,
        "expected_refuted": True,
        "expected_checks_count": 0,
    })

    # 15. multiple_deferred_checks -> Deferred with count >= 2 (B7, B9)
    req15 = BindingRequirement(predicate="TestsPassed", subject=term_opaque_child, base=term_opaque_base)
    ev15 = BindingEvidence(predicate="TestsPassed", subject_binding=term_diff1, base_binding=term_repo1)
    scenarios.append({
        "name": "multiple_deferred_checks",
        "req": req15,
        "ev": ev15,
        "ctx": PathFactContext(),
        "expected_proved": False,
        "expected_refuted": False,
        "expected_checks_count": 2,
    })

    # 16. refuted_and_deferred_composition -> Refuted (B8)
    req16 = BindingRequirement(predicate="TestsPassed", subject=term_diff1, base=term_opaque_base)
    ev16 = BindingEvidence(predicate="TestsPassed", subject_binding=term_diff2, base_binding=term_repo1)
    scenarios.append({
        "name": "refuted_and_deferred_composition",
        "req": req16,
        "ev": ev16,
        "ctx": PathFactContext(),
        "expected_proved": False,
        "expected_refuted": True,
        "expected_checks_count": 0,
    })

    return scenarios
