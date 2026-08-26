"""semantic_model.py — High-Level Semantic Reference Model (WHAT) for SOMA-IR Item 3.

Direct mathematical execution of:
- Track A: Result<T,E> and LatentPostconditions
- Track B: Definite Success/Failure vs DeliveryUnknown / SettlementUnknown
- Track C: ActOutcome (Success, Failure, PartialEffectReport)
- Track D: ChildHandle, May-Effect Unions, and Concrete Provenance Tracing
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from model import (
    ActFailureVal, ActOutcomeType, ActPartialVal, ActSuccessVal,
    ChildHandleType, ChildHandleVal, DeliveryUnknownVal, ErrVal, Fact,
    LatentPostconditions, OkVal, PartialEffectReport, ResultType,
    SettlementUnknownVal, Type,
)


@dataclass
class SemanticContext:
    """High-level semantic execution context."""
    psi: frozenset[Fact] = field(default_factory=frozenset)
    effects: list[str] = field(default_factory=list)
    lineage: dict[str, tuple[str, ...]] = field(default_factory=dict)
    status: str = "Active"
    protocol_violations: list[str] = field(default_factory=list)


class HighLevelSemanticEngine:
    """Direct reference evaluator for SOMA-IR semantics."""
    def __init__(self):
        self.ctx = SemanticContext()

    def read_op(self, target: str, latent: LatentPostconditions) -> OkVal:
        val = OkVal(f"data_of({target})", Type(), latent)
        # Latent postconditions do NOT enter Ψ until refined!
        return val

    def infer_op(self, query: str, latent: LatentPostconditions) -> OkVal:
        val = OkVal(f"infer_of({query})", Type(), latent)
        return val

    def verify_op(self, target: str, latent: LatentPostconditions) -> OkVal:
        val = OkVal(True, Type(), latent)
        return val

    def act_op(self, op_id: str, is_atomic: bool, latent: LatentPostconditions,
               outcome_kind: str = "success", report: Optional[PartialEffectReport] = None,
               error: Optional[str] = None) -> Any:
        self.ctx.effects.append(f"act({op_id})")

        if is_atomic and outcome_kind == "partial":
            self.ctx.protocol_violations.append(f"TransactionalAdapterYieldedPartial({op_id})")
            self.ctx.status = "ProtocolViolation"
            return None

        if outcome_kind == "success":
            return ActSuccessVal("action_ok", Type(), latent)
        elif outcome_kind == "failure":
            return ActFailureVal(error or "action_failed", Type(), latent)
        elif outcome_kind == "partial":
            return ActPartialVal(report or PartialEffectReport(op_id, ("step1",), ("step2",), "rcpt-1", error), latent)
        elif outcome_kind == "delivery_unknown":
            return DeliveryUnknownVal("req-1", op_id)
        elif outcome_kind == "settlement_unknown":
            return SettlementUnknownVal("req-1", op_id)
        else:
            raise ValueError(f"Unknown outcome kind: {outcome_kind}")

    def spawn_child_op(self, child_id: str, may_effects: frozenset[str],
                       ok_type: Type, err_type: Type,
                       actual_effects_executed: tuple[str, ...] = ()) -> ChildHandleVal:
        return ChildHandleVal(
            handle_id=f"handle:{child_id}",
            ok_type=ok_type,
            err_type=err_type,
            may_effects=may_effects,
            actual_provenance=actual_effects_executed or (f"exec({child_id})",),
            result_val=OkVal("child_success", ok_type),
        )

    def join_handles(self, h1: ChildHandleVal, h2: ChildHandleVal) -> ChildHandleType:
        """Handle effect join (Track D): produces may-effects union Σ1 ∪ Σ2."""
        t1 = ChildHandleType(h1.ok_type, h1.err_type, h1.may_effects)
        t2 = ChildHandleType(h2.ok_type, h2.err_type, h2.may_effects)
        return t1.join(t2)

    def await_handle(self, h: ChildHandleVal) -> tuple[Optional[OkVal | ErrVal], frozenset[Fact]]:
        """Await execution: effect neutral (Σ_await = ∅); returns child result & provenance."""
        if h.settlement_state == "SettlementUnknown":
            self.ctx.status = "SuspendedWaiting"
            return None, frozenset()

        # Await itself adds NO observable effects to self.ctx.effects!
        res = h.result_val or OkVal("await_ok", h.ok_type)
        return res, frozenset()

    def refine_result(self, res: OkVal | ErrVal, var_name: str, payload_sym: str) -> frozenset[Fact]:
        """Refine Result (Track A): instantiates latent postconditions for proven variant."""
        if isinstance(res, OkVal):
            facts = frozenset([Fact("IsOk", (var_name,))]) | res.latent.instantiate_ok(payload_sym)
            self.ctx.psi = self.ctx.psi | facts
            return facts
        elif isinstance(res, ErrVal):
            facts = frozenset([Fact("IsErr", (var_name,))]) | res.latent.instantiate_err(payload_sym)
            self.ctx.psi = self.ctx.psi | facts
            return facts
        return frozenset()

    def refine_act_outcome(self, outcome: Any, var_name: str, payload_sym: str) -> frozenset[Fact]:
        """Refine ActOutcome (Tracks B & C)."""
        if isinstance(outcome, ActSuccessVal):
            facts = frozenset([Fact("IsSuccess", (var_name,))]) | outcome.latent.instantiate_ok(payload_sym)
            self.ctx.psi = self.ctx.psi | facts
            return facts
        elif isinstance(outcome, ActFailureVal):
            facts = frozenset([Fact("IsFailure", (var_name,))]) | outcome.latent.instantiate_err(payload_sym)
            self.ctx.psi = self.ctx.psi | facts
            return facts
        elif isinstance(outcome, ActPartialVal):
            facts = frozenset([Fact("IsPartial", (var_name,))]) | outcome.latent.instantiate_partial(payload_sym)
            self.ctx.psi = self.ctx.psi | facts
            return facts
        elif isinstance(outcome, (DeliveryUnknownVal, SettlementUnknownVal)):
            facts = frozenset([Fact("IsUnknown", (var_name,))])
            self.ctx.psi = self.ctx.psi | facts
            return facts
        return frozenset()
