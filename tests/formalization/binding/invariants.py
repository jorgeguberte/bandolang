"""invariants.py — Normative Invariants B1–B12 for SOMA Binding Contract v0.

Validates that symbolic match evaluations strictly adhere to mathematical soundness rules.
"""
from __future__ import annotations

from typing import List, Optional
try:
    from .model import (
        BindingEvidence,
        BindingRequirement,
        BindingTerm,
        PathFactContext,
        SymbolicMatch,
        TermKind,
        match_binding,
        match_term,
        conservative_cfg_join,
        dynamic_gate_resolve,
    )
except ImportError:
    from model import (
        BindingEvidence,
        BindingRequirement,
        BindingTerm,
        PathFactContext,
        SymbolicMatch,
        TermKind,
        match_binding,
        match_term,
        conservative_cfg_join,
        dynamic_gate_resolve,
    )


def assert_b1_type_equality_not_binding_equality(
    term_a: BindingTerm,
    term_b: BindingTerm,
    ctx: PathFactContext,
    mutations: Optional[dict[str, bool]] = None,
):
    """B1: Same type must not imply subject match if values/identities differ."""
    assert term_a.val_type == term_b.val_type, "Precondition: terms must share type"
    assert not ctx.are_equal(term_a, term_b), "Precondition: terms must not be equal"
    
    match_res = match_term(term_a, term_b, ctx, mutations)
    assert not match_res.is_proved, (
        f"VIOLATION OF B1: Terms with different identities ({term_a.identity_key} vs {term_b.identity_key}) "
        f"were PROVED equal merely because they share type '{term_a.val_type}'!"
    )


def assert_b2_lineage_overlap_not_subject_identity(
    term_a: BindingTerm,
    term_b: BindingTerm,
    ctx: PathFactContext,
    mutations: Optional[dict[str, bool]] = None,
):
    """B2: Shared lineage dependencies must not prove subject identity."""
    assert bool(term_a.lineage_ids & term_b.lineage_ids), "Precondition: terms must share lineage"
    assert not ctx.are_equal(term_a, term_b), "Precondition: terms must not be equal"

    match_res = match_term(term_a, term_b, ctx, mutations)
    assert not match_res.is_proved, (
        f"VIOLATION OF B2: Terms with shared lineage {term_a.lineage_ids & term_b.lineage_ids} "
        f"were PROVED equal without identity proof!"
    )


def assert_b3_exact_known_mismatch_is_refuted(
    term_a: BindingTerm,
    term_b: BindingTerm,
    ctx: PathFactContext,
    mutations: Optional[dict[str, bool]] = None,
):
    """B3: Concrete known mismatch must be Refuted, never Deferred."""
    match_res = match_term(term_a, term_b, ctx, mutations)
    assert match_res.is_refuted, (
        f"VIOLATION OF B3: Concrete mismatch between {term_a.identity_key} and {term_b.identity_key} "
        f"must result in Refuted, got is_proved={match_res.is_proved}, deferred_checks={len(match_res.deferred_checks)}"
    )
    assert len(match_res.deferred_checks) == 0, "VIOLATION OF B3: Refuted match cannot carry deferred checks"


def assert_b4_lack_of_proof_is_not_refuted(
    term_a: BindingTerm,
    term_b: BindingTerm,
    ctx: PathFactContext,
    mutations: Optional[dict[str, bool]] = None,
):
    """B4: Opaque/unknown identity without proof must be Deferred, not Refuted."""
    match_res = match_term(term_a, term_b, ctx, mutations)
    assert not match_res.is_refuted, (
        f"VIOLATION OF B4: Opaque term without proof was prematurely Refuted!"
    )
    assert not match_res.is_proved, (
        f"VIOLATION OF B4: Opaque term without proof was prematurely Proved!"
    )
    assert len(match_res.deferred_checks) > 0, "VIOLATION OF B4: Deferred match must carry dynamic checks"


def assert_b5_base_state_independent_from_subject(
    req: BindingRequirement,
    ev: BindingEvidence,
    ctx: PathFactContext,
    mutations: Optional[dict[str, bool]] = None,
):
    """B5: Matching subject with mismatched/missing base state must NOT be Proved."""
    assert ctx.are_equal(req.subject, ev.subject_binding), "Precondition: subjects must match"
    assert req.base is not None, "Precondition: req must specify base state"

    match_res = match_binding(req, ev, ctx, mutations)
    assert not match_res.is_proved, (
        "VIOLATION OF B5: Binding was PROVED despite base state mismatch/omission!"
    )


def assert_b6_currentness_is_not_lexical_identity(
    req: BindingRequirement,
    ev: BindingEvidence,
    ctx: PathFactContext,
    mutations: Optional[dict[str, bool]] = None,
):
    """B6: Same StateRef name without CurrentnessWitness must not be Proved statically."""
    assert req.base is not None and ev.base_binding is not None
    assert req.base.kind == TermKind.STATE_REF and ev.base_binding.kind == TermKind.STATE_REF
    assert req.base.identity_key == ev.base_binding.identity_key

    match_res = match_binding(req, ev, ctx, mutations)
    if ev.currentness_witness is False:
        assert match_res.is_refuted, "VIOLATION OF B6: Stale base state witness must be Refuted"
    elif ev.currentness_witness is None:
        assert not match_res.is_proved, "VIOLATION OF B6: StateRef without currentness witness was Proved statically"
        assert any(c.check_type == "CheckCurrentBase" for c in match_res.deferred_checks), (
            "VIOLATION OF B6: StateRef without currentness witness must emit CheckCurrentBase"
        )


def assert_b7_static_success_requires_complete_proof(
    req: BindingRequirement,
    ev: BindingEvidence,
    ctx: PathFactContext,
    mutations: Optional[dict[str, bool]] = None,
):
    """B7: Proved is allowed ONLY if all required components are proved statically."""
    match_res = match_binding(req, ev, ctx, mutations)
    if match_res.is_proved:
        assert len(match_res.deferred_checks) == 0
        assert not match_res.is_refuted
    else:
        assert len(match_res.deferred_checks) > 0 or match_res.is_refuted


def assert_b8_refutation_dominates_deferred(
    req: BindingRequirement,
    ev: BindingEvidence,
    ctx: PathFactContext,
    mutations: Optional[dict[str, bool]] = None,
):
    """B8: If any required component is Refuted, the overall result MUST be Refuted."""
    match_res = match_binding(req, ev, ctx, mutations)
    assert match_res.is_refuted, (
        f"VIOLATION OF B8: Requirement containing a refuted component was not Refuted! "
        f"(is_proved={match_res.is_proved}, deferred={len(match_res.deferred_checks)})"
    )
    assert len(match_res.deferred_checks) == 0, "VIOLATION OF B8: Refuted result must not leak deferred checks"


def assert_b9_deferred_checks_are_explicit(
    match_res: SymbolicMatch,
):
    """B9: Deferred match must carry explicit, non-empty, actionable checks."""
    if not match_res.is_proved and not match_res.is_refuted:
        assert len(match_res.deferred_checks) > 0, "VIOLATION OF B9: Deferred match carries empty check list"
        for chk in match_res.deferred_checks:
            assert chk.check_type in ("CheckSubjectIdentity", "CheckCurrentBase", "CheckScopeConfinement", "CheckValidity"), (
                f"VIOLATION OF B9: Unknown check type '{chk.check_type}'"
            )
            assert bool(chk.details), "VIOLATION OF B9: Check must contain descriptive payload details"


def assert_b10_gate_cannot_widen_binding(
    req: BindingRequirement,
    ev: BindingEvidence,
    widened_subject: BindingTerm,
    ctx: PathFactContext,
    mutations: Optional[dict[str, Any]] = None,
):
    """B10 (R3): Dynamic gate evaluation cannot reinterpret or widen an attestation for a different subject."""
    muts = dict(mutations or {})
    muts["widened_subject"] = widened_subject

    # 1. Evaluate initial match -> should be Deferred (waiting on dynamic checks)
    initial_match = match_binding(req, ev, ctx)
    assert len(initial_match.deferred_checks) > 0, "Precondition: initial match must be Deferred"

    # 2. Perform dynamic gate resolution with witness proofs
    witness_proofs = {chk.check_type: True for chk in initial_match.deferred_checks}
    resolved_match, resolved_ev = dynamic_gate_resolve(req, ev, ctx, witness_proofs, muts)

    # 3. Prove that successful resolution validates the original binding without rebinding
    assert resolved_match.is_proved, "Dynamic resolution must prove the valid obligation"
    assert resolved_ev.subject_binding == ev.subject_binding, (
        f"VIOLATION OF B10: Dynamic resolution rebound subject to {resolved_ev.subject_binding.identity_key}!"
    )
    assert resolved_ev.subject_binding != widened_subject, (
        f"VIOLATION OF B10: Dynamic gate widened attestation subject to {widened_subject.identity_key}!"
    )


def assert_b11_attestation_predicate_exact(
    req: BindingRequirement,
    ev: BindingEvidence,
    ctx: PathFactContext,
    mutations: Optional[dict[str, bool]] = None,
):
    """B11: Predicate mismatch must be Refuted immediately."""
    assert req.predicate != ev.predicate
    match_res = match_binding(req, ev, ctx, mutations)
    assert match_res.is_refuted, f"VIOLATION OF B11: Predicate mismatch ({req.predicate} != {ev.predicate}) was not Refuted"


def assert_b12_cfg_joins_conservative(
    path_a: BindingEvidence,
    path_b: BindingEvidence,
    ctx: PathFactContext,
    mutations: Optional[dict[str, bool]] = None,
):
    """B12: Conflicting branch bindings must not be resolved by arbitrarily picking one."""
    assert not ctx.are_equal(path_a.subject_binding, path_b.subject_binding), "Precondition: branches must conflict"
    merged = conservative_cfg_join(path_a, path_b, ctx, mutations)
    assert merged is None, (
        f"VIOLATION OF B12: CFG join arbitrarily resolved conflicting subjects "
        f"({path_a.subject_binding.identity_key} vs {path_b.subject_binding.identity_key}) to {merged}!"
    )
