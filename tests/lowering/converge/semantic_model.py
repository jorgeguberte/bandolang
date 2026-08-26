"""semantic_model.py — minimal semantic model of ConvergeFrame v0.

Models the WHAT (ConvergeFrame v0 semantics), not the soma.vm.* HOW.
Deliberately more direct than the lowered model in model.py/transitions.py:
no outbox, no CompletionRecord, no StageLocal, no settlement records.

R9 (audit): SemanticFrame executes ScenarioProgram autonomously using ONLY
its own internal methods. Drivers NEVER poke internal status or counters.

Deterministic stubs only: 0 LLM calls, 0 network, 0 randomness.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from scenarios import OpDef, ScenarioProgram


class Status:
    SEARCHING = "Searching"
    SATISFIED = "Satisfied"
    EXHAUSTED = "Exhausted"
    FAILED = "Failed"
    CANCELLED = "Cancelled"   # R2 (audit): owner cancellation ≠ exhaustion


@dataclass(frozen=True)
class Visit:
    node_id: str


@dataclass(frozen=True)
class SemanticOutcome:
    status: str                 # Satisfied / Exhausted / Failed / Cancelled / Searching
    value: Any = None           # the T in Ok(Some(T))
    error: Optional[str] = None


@dataclass
class SemanticFrame:
    """Direct representation of a converge search over an explicit space."""
    max_steps: int = 6
    budget_limit: int = 100

    nodes: dict[str, str] = field(default_factory=dict)   # node_id -> status ("Frontier"|"Expanding")
    frontier: list[str] = field(default_factory=list)
    visited: list[Visit] = field(default_factory=list)
    step_count: int = 0
    satisfaction_attempts: int = 0
    budget_spent: int = 0
    effects: list[str] = field(default_factory=list)      # observable external actions Σ
    status: str = Status.SEARCHING
    outcome: Optional[SemanticOutcome] = None

    # ---- core methods ---------------------------------------------------

    def expand(self, node_id: str, op: OpDef, succs: list[str]) -> list[str]:
        """Expand node: costs 1 step fuel, marks Expanding, records visited,
        adds external effects/budget if external, adds successors to frontier."""
        if self.status != Status.SEARCHING or self.step_count >= self.max_steps:
            return []
        self.step_count += 1
        self.nodes[node_id] = "Expanding"
        self.visited.append(Visit(node_id))
        if op.kind == "external":
            self.budget_spent += op.charge()
            self.effects.append(f"external({op.op_id})")
        for s in succs:
            if s not in self.nodes:
                self.nodes[s] = "Frontier"
                self.frontier.append(s)
        return succs

    def check_satisfaction(self, node_id: str,
                           satisfier_map: dict[str, tuple[str, bool, Any]],
                           on_satisfier_error: str = "abort") -> bool:
        """Satisfier attempt. Returns True if search should terminate (Satisfied or Failed)."""
        if self.status != Status.SEARCHING:
            return False
        kind, ok, value = satisfier_map.get(node_id, ("ok", False, None))
        self.satisfaction_attempts += 1
        if kind == "err":
            if on_satisfier_error == "abort":
                self.status = Status.FAILED
                self.outcome = SemanticOutcome(Status.FAILED, error=value)
                return True
            return False
        if ok:
            self.status = Status.SATISFIED
            self.outcome = SemanticOutcome(Status.SATISFIED, value=value)
            return True
        return False

    def cancel(self) -> None:
        """Owner cancellation (R2)."""
        if self.status == Status.SEARCHING:
            self.status = Status.CANCELLED
            self.outcome = SemanticOutcome(Status.CANCELLED)

    def exhaust(self) -> None:
        """Natural exhaustion."""
        if self.status == Status.SEARCHING:
            self.status = Status.EXHAUSTED
            self.outcome = SemanticOutcome(Status.EXHAUSTED)

    # ---- autonomous runner ----------------------------------------------

    def run_program(self, prog: ScenarioProgram) -> SemanticOutcome:
        """Execute a ScenarioProgram purely via semantic search semantics."""
        self.max_steps = prog.max_steps
        self.budget_limit = prog.budget_limit

        for n in prog.initial_frontier:
            self.frontier.append(n)
            self.nodes[n] = "Frontier"

        while self.status == Status.SEARCHING:
            if self.step_count >= self.max_steps or not self.frontier:
                break

            node = self.frontier.pop(0)
            op = prog.node_ops.get(node, OpDef(op_id=f"op:{node}"))
            op_cost = op.charge() if op.kind == "external" else 0

            # R15: CanAfford check against budget_limit in search policy
            if self.budget_spent + op_cost > self.budget_limit:
                # Unaffordable operation: cannot expand within budget
                continue

            succs = list(prog.successors.get(node, []))
            self.expand(node, op, succs)

            # Check for environmental cancellation
            if prog.fault_spec.cancel_in_flight:
                self.cancel()
                return self.outcome

            # Candidates to check: the expanded node itself, then its successors
            candidates = [node] + succs
            for cand in candidates:
                if self.check_satisfaction(cand, prog.satisfier_map, prog.on_satisfier_error):
                    return self.outcome

        # Post-fuel / partial check (D03)
        if self.status == Status.SEARCHING and prog.check_partial_after_fuel:
            self.check_satisfaction(prog.check_partial_after_fuel, prog.satisfier_map, prog.on_satisfier_error)

        if self.status == Status.SEARCHING:
            self.exhaust()

        return self.outcome

    # ---- observables ----------------------------------------------------

    def observe(self) -> dict:
        return {
            "status": self.status,
            "value": self.outcome.value if self.outcome else None,
            "error": self.outcome.error if self.outcome else None,
            "step_count": self.step_count,
            "satisfaction_attempts": self.satisfaction_attempts,
            "visited": [v.node_id for v in self.visited],
            "frontier": list(self.frontier),
            "budget_spent": self.budget_spent,
            "outstanding_scope_commitment": 0,
            "unsettled_request_count": 0,
            "attributable_owner_reserved": 0,
            "intent_available_consumed": self.budget_spent,
            "effects": sorted(self.effects),
        }
