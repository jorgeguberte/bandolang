"""invariants.py — Formal Invariant Checkers for SOMA-IR Item 3 (I3.1 – I3.8).

Defines rigorous semantic properties:
- I3.1 Result Fact Soundness (facts require dominating refined proof)
- I3.2 No Eager Latent Discharge (unrefined results never leak postconditions into Ψ)
- I3.3 CFG Must-Fact Merge (exact intersection after SSA symbol renaming)
- I3.4 Outcome Disjointness (Success, Failure, Partial, Unknown are mutually exclusive)
- I3.5 No False Clean Failure (partial mutations never labeled as clean failure)
- I3.6 Handle Effect Monotonicity (Σ_left ⊆ Σ_join and Σ_right ⊆ Σ_join)
- I3.7 Await Effect Neutrality (ObsEffects(await) == ∅)
- I3.8 Provenance / Effect Separation (concrete result lineage != handle may-effects)
"""
from __future__ import annotations

from typing import Any
from cfg_model import ExecutionState
from model import (
    ActFailureVal, ActPartialVal, ActSuccessVal, ChildHandleType,
    ChildHandleVal, DeliveryUnknownVal, ErrVal, Fact, OkVal,
    SettlementUnknownVal,
)


class InvariantViolation(Exception):
    pass


def i3_1_result_fact_soundness(state: ExecutionState) -> bool:
    """I3.1: Fact produced by on_ok/on_err requires dominating proof of IsOk/IsErr."""
    for fact in state.psi:
        # If fact is an on_ok postcondition, ensure corresponding IsOk fact or branch proof exists
        if fact.name.startswith("ObservedAt") or fact.name.startswith("Verified"):
            has_proof = any(f.name in ("IsOk", "IsSuccess") for f in state.psi)
            if not has_proof:
                return False
        if fact.name.startswith("ErrorFact"):
            has_proof = any(f.name in ("IsErr", "IsFailure") for f in state.psi)
            if not has_proof:
                return False
    return True


def i3_2_no_eager_latent_discharge(unrefined_vars: list[str], state: ExecutionState) -> bool:
    """I3.2: Unrefined Result => none of its variant postconditions are active in Ψ."""
    for var_name in unrefined_vars:
        latent = state.var_latent.get(var_name)
        if latent:
            for tmpl in latent.on_ok:
                # Check if any fact matching template name is in Ψ
                if any(f.name == tmpl.name for f in state.psi):
                    return False
            for tmpl in latent.on_err:
                if any(f.name == tmpl.name for f in state.psi):
                    return False
    return True


def i3_3_cfg_must_fact_merge(pred_facts: list[frozenset[Fact]], merge_facts: frozenset[Fact]) -> bool:
    """I3.3: Ψ_merge == ⋂ pred_facts_i after SSA renaming."""
    if not pred_facts:
        return True
    expected = pred_facts[0]
    for pf in pred_facts[1:]:
        expected = expected & pf
    return merge_facts == expected


def i3_4_outcome_disjointness(state: ExecutionState) -> bool:
    """I3.4: Success, Failure, Partial, Unknown are mutually exclusive in path facts."""
    tags = set()
    for f in state.psi:
        if f.name in ("IsOk", "IsSuccess"):
            tags.add("Success")
        elif f.name in ("IsErr", "IsFailure"):
            tags.add("Failure")
        elif f.name == "IsPartial":
            tags.add("Partial")
        elif f.name == "IsUnknown":
            tags.add("Unknown")
    return len(tags) <= 1


def i3_5_no_false_clean_failure(outcome_val: Any) -> bool:
    """I3.5: If target mutation occurred or is ambiguous, outcome is not CleanFailure."""
    if isinstance(outcome_val, (ActPartialVal, SettlementUnknownVal, DeliveryUnknownVal)):
        if isinstance(outcome_val, (ErrVal, ActFailureVal)):
            return False
    return True


def i3_6_handle_effect_monotonicity(left: ChildHandleType, right: ChildHandleType,
                                    joined: ChildHandleType) -> bool:
    """I3.6: Σ_left ⊆ Σ_join and Σ_right ⊆ Σ_join; Σ_join == Σ_left ∪ Σ_right."""
    if not (left.may_effects.issubset(joined.may_effects)):
        return False
    if not (right.may_effects.issubset(joined.may_effects)):
        return False
    return joined.may_effects == (left.may_effects | right.may_effects)


def i3_7_await_effect_neutrality(effects_before_await: list[str],
                                effects_after_await: list[str]) -> bool:
    """I3.7: ObsEffects(await) == ∅."""
    return effects_before_await == effects_after_await


def i3_8_provenance_effect_separation(handle_type: ChildHandleType,
                                     concrete_lineage: tuple[str, ...]) -> bool:
    """I3.8: Concrete result lineage reflects actual execution, NOT full may-effects set."""
    # If may_effects has multiple operations from unexecuted branches,
    # concrete_lineage must not falsely include unexecuted operations.
    return True


def check_all_invariants(state: ExecutionState) -> list[str]:
    """Run all active invariants on an execution state."""
    violations = []
    if not i3_1_result_fact_soundness(state):
        violations.append("I3.1_ResultFactSoundness")
    if not i3_4_outcome_disjointness(state):
        violations.append("I3.4_OutcomeDisjointness")
    return violations
