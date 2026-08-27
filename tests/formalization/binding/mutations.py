"""mutations.py — Causal Mutation Suite for SOMA Binding Contract v0.

Defines deliberate semantic shortcuts (M1–M10) to verify that the formal invariant
battery strictly catches and kills each unsound implementation variant.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List
try:
    from .invariants import (
        assert_b1_type_equality_not_binding_equality,
        assert_b2_lineage_overlap_not_subject_identity,
        assert_b3_exact_known_mismatch_is_refuted,
        assert_b4_lack_of_proof_is_not_refuted,
        assert_b5_base_state_independent_from_subject,
        assert_b6_currentness_is_not_lexical_identity,
        assert_b7_static_success_requires_complete_proof,
        assert_b8_refutation_dominates_deferred,
        assert_b9_deferred_checks_are_explicit,
        assert_b11_attestation_predicate_exact,
        assert_b12_cfg_joins_conservative,
    )
    from .model import (
        BindingEvidence,
        BindingRequirement,
        BindingTerm,
        PathFactContext,
        SymbolicMatch,
        match_binding,
        match_term,
    )
except ImportError:
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
        assert_b11_attestation_predicate_exact,
        assert_b12_cfg_joins_conservative,
    )
    from model import (
        BindingEvidence,
        BindingRequirement,
        BindingTerm,
        PathFactContext,
        SymbolicMatch,
        match_binding,
        match_term,
    )


@dataclass(frozen=True)
class MutantDescriptor:
    mutant_id: str
    description: str
    target_invariant: str
    run_killer: Callable[[], None]


def get_all_mutants() -> List[MutantDescriptor]:
    mutants = []

    # M1: type equality => subject equality shortcut (Killed by B1)
    def kill_m1():
        t1 = BindingTerm.value_ref("diff_a", "Diff")
        t2 = BindingTerm.value_ref("diff_b", "Diff")
        ctx = PathFactContext()
        assert_b1_type_equality_not_binding_equality(t1, t2, ctx, {"m1_type_equality_shortcut": True})

    mutants.append(MutantDescriptor(
        mutant_id="M1",
        description="Type equality automatically satisfies subject requirement",
        target_invariant="B1",
        run_killer=kill_m1,
    ))

    # M2: lineage overlap => subject equality shortcut (Killed by B2)
    def kill_m2():
        t1 = BindingTerm.value_ref("diff_a", "Diff", lineage_ids={"agent_1"})
        t2 = BindingTerm.value_ref("diff_b", "Diff", lineage_ids={"agent_1"})
        ctx = PathFactContext()
        assert_b2_lineage_overlap_not_subject_identity(t1, t2, ctx, {"m2_lineage_overlap_shortcut": True})

    mutants.append(MutantDescriptor(
        mutant_id="M2",
        description="Shared lineage dependency automatically proves subject identity",
        target_invariant="B2",
        run_killer=kill_m2,
    ))

    # M3: concrete mismatch => Deferred (Killed by B3)
    def kill_m3():
        t1 = BindingTerm.stable_digest("sha256", "hash_a")
        t2 = BindingTerm.stable_digest("sha256", "hash_b")
        ctx = PathFactContext()
        assert_b3_exact_known_mismatch_is_refuted(t1, t2, ctx, {"m3_concrete_mismatch_deferred": True})

    mutants.append(MutantDescriptor(
        mutant_id="M3",
        description="Concrete digest mismatch is downgraded to Deferred instead of Refuted",
        target_invariant="B3",
        run_killer=kill_m3,
    ))

    # M4: opaque unknown => Refuted (Killed by B4)
    def kill_m4():
        t1 = BindingTerm.stable_digest("sha256", "hash_target")
        t_opaque = BindingTerm.opaque_ref("child_agent", "token_123")
        ctx = PathFactContext()
        assert_b4_lack_of_proof_is_not_refuted(t1, t_opaque, ctx, {"m4_opaque_unknown_refuted": True})

    mutants.append(MutantDescriptor(
        mutant_id="M4",
        description="Opaque delegated term without static proof is prematurely Refuted instead of Deferred",
        target_invariant="B4",
        run_killer=kill_m4,
    ))

    # M5: ignore base binding (Killed by B5)
    def kill_m5():
        subj = BindingTerm.stable_digest("sha256", "diff_hash")
        base1 = BindingTerm.stable_digest("sha256", "repo_base_1")
        base2 = BindingTerm.stable_digest("sha256", "repo_base_2")
        req = BindingRequirement(predicate="TestsPassed", subject=subj, base=base1)
        ev = BindingEvidence(predicate="TestsPassed", subject_binding=subj, base_binding=base2)
        ctx = PathFactContext()
        assert_b5_base_state_independent_from_subject(req, ev, ctx, {"m5_ignore_base_binding": True})

    mutants.append(MutantDescriptor(
        mutant_id="M5",
        description="Base state binding is ignored when subject matches",
        target_invariant="B5",
        run_killer=kill_m5,
    ))

    # M6: lexical StateRef => current (Killed by B6)
    def kill_m6():
        subj = BindingTerm.stable_digest("sha256", "diff_hash")
        state_term = BindingTerm.state_ref("db", "users")
        req = BindingRequirement(predicate="SchemaValidated", subject=subj, base=state_term)
        ev = BindingEvidence(predicate="SchemaValidated", subject_binding=subj, base_binding=state_term, currentness_witness=None)
        ctx = PathFactContext()
        assert_b6_currentness_is_not_lexical_identity(req, ev, ctx, {"m6_lexical_state_current_shortcut": True})

    mutants.append(MutantDescriptor(
        mutant_id="M6",
        description="Lexical StateRef match assumed current without CurrentnessWitness",
        target_invariant="B6",
        run_killer=kill_m6,
    ))

    # M7: drop Deferred checks (Killed by B7 / B9)
    def kill_m7():
        subj = BindingTerm.opaque_ref("agent_a", "tok_1")
        req = BindingRequirement(predicate="TestsPassed", subject=subj)
        ev = BindingEvidence(predicate="TestsPassed", subject_binding=BindingTerm.stable_digest("sha256", "d1"))
        ctx = PathFactContext()
        res = match_binding(req, ev, ctx, {"m7_drop_deferred_checks": True})
        assert not res.is_proved, "VIOLATION: Dropping deferred checks caused bogus Proved!"
        assert_b9_deferred_checks_are_explicit(res)

    mutants.append(MutantDescriptor(
        mutant_id="M7",
        description="Deferred checks list dropped/empty on dynamic matching",
        target_invariant="B7/B9",
        run_killer=kill_m7,
    ))

    # M8: Deferred overrides Refuted (Killed by B8)
    def kill_m8():
        diff1 = BindingTerm.stable_digest("sha256", "d1")
        diff2 = BindingTerm.stable_digest("sha256", "d2")  # Concrete mismatch -> Refuted
        opaque_base = BindingTerm.opaque_ref("ext", "tok")  # Opaque -> Deferred
        req = BindingRequirement(predicate="TestsPassed", subject=diff1, base=opaque_base)
        ev = BindingEvidence(predicate="TestsPassed", subject_binding=diff2, base_binding=BindingTerm.stable_digest("sha256", "b1"))
        ctx = PathFactContext()
        assert_b8_refutation_dominates_deferred(req, ev, ctx, {"m8_deferred_overrides_refuted": True})

    mutants.append(MutantDescriptor(
        mutant_id="M8",
        description="Deferred check overrides a concrete Refuted component",
        target_invariant="B8",
        run_killer=kill_m8,
    ))

    # M9: predicate mismatch ignored (Killed by B11)
    def kill_m9():
        subj = BindingTerm.stable_digest("sha256", "d1")
        req = BindingRequirement(predicate="SafeToDeploy", subject=subj)
        ev = BindingEvidence(predicate="TestsPassed", subject_binding=subj)
        ctx = PathFactContext()
        assert_b11_attestation_predicate_exact(req, ev, ctx, {"m9_predicate_mismatch_ignored": True})

    mutants.append(MutantDescriptor(
        mutant_id="M9",
        description="Predicate mismatch ignored or promoted without policy",
        target_invariant="B11",
        run_killer=kill_m9,
    ))

    # M10: conflicting CFG join picks one branch (Killed by B12)
    def kill_m10():
        diff1 = BindingTerm.stable_digest("sha256", "d1")
        diff2 = BindingTerm.stable_digest("sha256", "d2")
        ev1 = BindingEvidence(predicate="TestsPassed", subject_binding=diff1)
        ev2 = BindingEvidence(predicate="TestsPassed", subject_binding=diff2)
        ctx = PathFactContext()
        assert_b12_cfg_joins_conservative(ev1, ev2, ctx, {"m10_cfg_join_picks_branch": True})

    mutants.append(MutantDescriptor(
        mutant_id="M10",
        description="Conflicting CFG join arbitrarily picks branch A instead of conservative join",
        target_invariant="B12",
        run_killer=kill_m10,
    ))

    return mutants
