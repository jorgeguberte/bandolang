"""semantic_model.py — minimal semantic model of ConvergeFrame v0.

Models the WHAT (ConvergeFrame v0 semantics), not the soma.vm.* HOW.
Deliberately more direct than the lowered model in model.py/transitions.py:
no outbox, no CompletionRecord, no StageLocal, no settlement records.

Deterministic stubs only: 0 LLM calls, 0 network, 0 randomness.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


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
    status: str                 # Satisfied / Exhausted / Failed / Searching
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

    # ---- deterministic stubs (injected by each scenario) ----------------

    # successors(node_id) -> list of successor ids (pure)
    successors: Callable[[str], list[str]] = lambda n: []

    # external_expand(node_id) -> performs one external action; returns cost
    #   and appends to effects. This is the semantic 'act/read' directly.
    external_expand_cost: int = 0

    # satisfier(node_id) -> ("ok", True, value) | ("ok", False, None) | ("err", msg)
    satisfier: Callable[[str], tuple] = staticmethod(lambda n: ("ok", False, None))

    on_satisfier_error: str = "retry_once"     # "retry_once" | "abort"

    max_steps_partial_check: bool = True       # D03 normative rule: partial still checked

    # ---- core loop ------------------------------------------------------

    def expand_local(self, node_id: str) -> list[str]:
        """Local expansion: pure computation, no external effect. Costs 1 step."""
        if self.status != Status.SEARCHING or self.step_count >= self.max_steps:
            return []
        self.step_count += 1
        self.nodes[node_id] = "Expanding"
        self.visited.append(Visit(node_id))
        succs = list(self.successors(node_id))
        for s in succs:
            if s not in self.nodes:
                self.nodes[s] = "Frontier"
                self.frontier.append(s)
        return succs

    def check_satisfaction(self, node_id: str) -> bool:
        """Satisfier attempt. Counts regardless of result (semantic attempt)."""
        if self.status != Status.SEARCHING:
            return False
        kind, ok, value = self.satisfier(node_id)
        if kind == "err":
            self.satisfaction_attempts += 1
            if self.on_satisfier_error == "abort":
                self.status = Status.FAILED
                self.outcome = SemanticOutcome(Status.FAILED, error=value)
                return True     # terminal
            return False        # retryable: continue searching
        self.satisfaction_attempts += 1
        if ok:
            self.status = Status.SATISFIED
            self.outcome = SemanticOutcome(Status.SATISFIED, value=value)
            return True
        return False

    def run(self) -> SemanticOutcome:
        """Deterministic DFS-style drive of the space until outcome."""
        seed = self.frontier[0] if self.frontier else "root"
        if seed not in self.nodes:
            self.nodes[seed] = "Frontier"
            self.frontier.insert(0, seed)

        while self.status == Status.SEARCHING:
            if self.step_count >= self.max_steps:
                break
            if not self.frontier:
                break
            node = self.frontier.pop(0)
            succs = self.expand_local(node)
            # satisfaction check on the expanded node itself, then successors
            candidates = [node] + succs
            for c in candidates:
                if self.check_satisfaction(c):
                    break

        if self.status == Status.SEARCHING:
            # exhausted fuel or frontier without satisfaction
            if self.max_steps_partial_check and self.outcome is None:
                pass    # partial produced may still be checked by scenario harness
            self.status = Status.EXHAUSTED
            self.outcome = SemanticOutcome(Status.EXHAUSTED)
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
            "effects": sorted(self.effects),
        }
