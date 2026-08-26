"""differential.py — observation comparison between semantic and lowered models.

Compares semantic observables only. Administrative differences (outbox,
CompletionRecord, SettlementRecord, StageLocal) are NORMALIZED, never treated
as divergence by themselves.
"""
from __future__ import annotations

from dataclasses import dataclass

from model import ConvergeTransactionDomain
from semantic_model import SemanticFrame


@dataclass
class Divergence:
    scenario: str
    field: str
    semantic: object
    lowered: object

    def render(self) -> str:
        return (f"DIFFERENTIAL FAIL [{self.scenario}] field={self.field}\n"
                f"  semantic: {self.semantic!r}\n  lowered:  {self.lowered!r}")


def lowered_observation(d: ConvergeTransactionDomain, bk: HarnessBookkeeping | None = None,
                        initial_available: int = 100) -> dict:
    """Extract the SEMANTICALLY RELEVANT observation from the lowered domain,
    including ledger and obligation observables (R12/R14/R17)."""
    status = d.frame_status
    error = None
    if d.closing_reason is not None:
        error = d.closing_reason.error or d.closing_reason.kind

    curr_avail = d.intent_available.get("usd", initial_available)
    avail_consumed = initial_available - curr_avail

    # R17 (audit): attributable reservations belong specifically to this CF via bookkeeping
    attributable = sum(bk.reservations_created_by_cf.values()) if bk else sum(d.intent_reserved.values())

    return {
        "status": status,
        "value": getattr(d, "satisfied_value", None),
        "error": error if status in ("Failed", "Closing") else None,
        "step_count": d.step_count,
        "satisfaction_attempts": d.satisfaction_attempts,
        "visited": [v.node_id for v in d.visited],
        "frontier": [n for n in d.frontier],
        "budget_spent": sum(d.scope_spent.values()),
        "outstanding_scope_commitment": sum(d.scope_committed.values()),
        "unsettled_request_count": sum(1 for s in d.handles.values() if s.settlement is None and s.state != "Aborted"),
        "attributable_owner_reserved": attributable,
        "intent_available_consumed": avail_consumed,
        "effects": sorted(
            f"external({rec.op_id})" for rec in d.outbox.values()
            if d.first_emission_flags.get(rec.request_id) and not rec.local_only
        ),
    }


def compare(scenario: str, semantic_obs: dict, lowered_obs: dict) -> list[Divergence]:
    """Field-by-field comparison of normalized observations.
    R6 (audit): exact T-value comparison.
    R14/R17 (audit): compares obligations, commitments, and available consumption."""
    divergences = []
    for key in ("status", "value", "error", "step_count",
                "satisfaction_attempts", "visited", "frontier",
                "budget_spent", "outstanding_scope_commitment",
                "unsettled_request_count", "attributable_owner_reserved",
                "intent_available_consumed", "effects"):
        s, l = semantic_obs.get(key), lowered_obs.get(key)
        if s != l:
            divergences.append(Divergence(scenario, key, s, l))
    return divergences


def classify(divergence: Divergence, field_hint: str | None = None) -> str:
    """Mandatory classification BEFORE any fix. Conservative defaults."""
    f = field_hint or divergence.field
    if f in ("step_count", "satisfaction_attempts"):
        # fuel semantics live in the frozen normative principles → candidate counterexample
        return "LOWERING_COUNTEREXAMPLE_CANDIDATE"
    if f in ("status", "value", "error", "effects"):
        return "LOWERED_MODEL_BUG_OR_COUNTEREXAMPLE"   # needs manual triage
    if f in ("visited", "frontier", "budget_spent"):
        return "OBSERVATION/NORMALIZATION_BUG_OR_LOWERED_BUG"  # manual triage
    return "SEMANTIC_MODEL_BUG"
