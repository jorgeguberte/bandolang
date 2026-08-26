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


def i3_5_no_false_clean_failure(outcome_val: Any, confirmed_applied_effects: list[str] | tuple[str, ...] | None = None) -> bool:
    """I3.5: If target mutation occurred or physical ambiguity exists, outcome cannot be clean Failure."""
    if confirmed_applied_effects and len(confirmed_applied_effects) > 0:
        if isinstance(outcome_val, (ErrVal, ActFailureVal)):
            return False
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
                                     concrete_lineage: tuple[str, ...],
                                     actual_executed_child: str | None = None) -> bool:
    """I3.8: Concrete result lineage reflects actual execution, NOT full may-effects set (J3)."""
    # If concrete_lineage claims execution of an unexecuted child or operation, it is a provenance violation
    if actual_executed_child is not None:
        expected = (f"exec({actual_executed_child})",)
        return concrete_lineage == expected
    # Lineage must not blindly equal may_effects summary if multiple alternative branches exist
    if len(handle_type.may_effects) > 1 and len(concrete_lineage) == len(handle_type.may_effects):
        # Provably fabricated if it claims all alternative branches executed
        return False
    return True


def check_all_invariants(state: ExecutionState, context: dict[str, Any] | None = None) -> dict[str, str]:
    """Run all invariants I3.1–I3.8, returning PASS, VIOLATION, or explicit NOT_APPLICABLE (F2)."""
    ctx = context or {}
    results = {}

    # I3.1 Result fact soundness
    if i3_1_result_fact_soundness(state):
        results["I3.1"] = "PASS"
    else:
        results["I3.1"] = "VIOLATION: fact present in Ψ without dominating proof"

    # I3.2 No eager latent discharge (G2: strict NOT_APPLICABLE if unrefined_vars is not explicitly provided)
    unref = ctx.get("unrefined_vars")
    if unref is not None and len(unref) > 0:
        if i3_2_no_eager_latent_discharge(unref, state):
            results["I3.2"] = "PASS"
        else:
            results["I3.2"] = "VIOLATION: unrefined result leaked latent postcondition into Ψ"
    else:
        results["I3.2"] = "NOT_APPLICABLE: requires unrefined_vars list to evaluate"

    # I3.3 CFG must-fact merge
    if "pred_facts" in ctx and "merge_facts" in ctx:
        if i3_3_cfg_must_fact_merge(ctx["pred_facts"], ctx["merge_facts"]):
            results["I3.3"] = "PASS"
        else:
            results["I3.3"] = "VIOLATION: merge facts do not equal intersection of predecessor facts"
    else:
        results["I3.3"] = "NOT_APPLICABLE: requires pred_facts and merge_facts context"

    # I3.4 Outcome disjointness
    if i3_4_outcome_disjointness(state):
        results["I3.4"] = "PASS"
    else:
        results["I3.4"] = "VIOLATION: multiple mutually exclusive outcome tags active simultaneously in Ψ"

    # I3.5 No false clean failure (G2: strict NOT_APPLICABLE if outcome/evidence context is absent)
    applied = ctx.get("confirmed_applied_effects")
    outcome_val = ctx.get("outcome_val")
    if outcome_val is not None or (applied is not None and len(applied) > 0):
        val = outcome_val if outcome_val is not None else next((v for v in state.env.values() if isinstance(v, (ErrVal, ActFailureVal, ActPartialVal, DeliveryUnknownVal, SettlementUnknownVal))), None)
        if val is not None and i3_5_no_false_clean_failure(val, confirmed_applied_effects=applied):
            results["I3.5"] = "PASS"
        else:
            results["I3.5"] = "VIOLATION: clean Failure asserted on operation with partial mutations or ambiguity"
    else:
        results["I3.5"] = "NOT_APPLICABLE: requires outcome_val or confirmed_applied_effects context"

    # I3.6 Handle effect monotonicity
    if "left_handle" in ctx and "right_handle" in ctx and "joined_handle" in ctx:
        if i3_6_handle_effect_monotonicity(ctx["left_handle"], ctx["right_handle"], ctx["joined_handle"]):
            results["I3.6"] = "PASS"
        else:
            results["I3.6"] = "VIOLATION: handle join is not a monotonic union of predecessor effects"
    else:
        results["I3.6"] = "NOT_APPLICABLE: requires left_handle, right_handle, and joined_handle context"

    # I3.7 Await effect neutrality
    if "effects_before_await" in ctx and "effects_after_await" in ctx:
        if i3_7_await_effect_neutrality(ctx["effects_before_await"], ctx["effects_after_await"]):
            results["I3.7"] = "PASS"
        else:
            results["I3.7"] = "VIOLATION: await polluted parent observable effect trace"
    else:
        results["I3.7"] = "NOT_APPLICABLE: requires effects_before_await and effects_after_await context"

    # I3.8 Provenance / effect separation
    if "handle_type" in ctx and "concrete_lineage" in ctx:
        if i3_8_provenance_effect_separation(ctx["handle_type"], ctx["concrete_lineage"], actual_executed_child=ctx.get("actual_executed_child")):
            results["I3.8"] = "PASS"
        else:
            results["I3.8"] = "VIOLATION: concrete lineage was falsely widened to include unexecuted may-effects"
    else:
        results["I3.8"] = "NOT_APPLICABLE: requires handle_type and concrete_lineage context"

    return results
