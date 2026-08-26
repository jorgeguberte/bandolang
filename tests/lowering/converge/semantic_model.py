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

    def expand(self, node_id: str, op: OpDef, succs: list[str],
               delivery_unknown: bool = False) -> list[str]:
        """Expand node: costs 1 step fuel, marks Expanding, records visited,
        adds external effects/budget if external, adds successors to frontier (R47)."""
        if self.status != Status.SEARCHING or self.step_count >= self.max_steps:
            return []
        self.step_count += 1
        self.nodes[node_id] = "Expanding"
        self.visited.append(Visit(node_id))
        if op.kind == "external":
            self.effects.append(f"external({op.op_id})")
            if not delivery_unknown:
                self.budget_spent += op.charge()
        if not delivery_unknown:
            for s in succs:
                if s not in self.nodes:
                    self.nodes[s] = "Frontier"
                    self.frontier.append(s)
        return succs if not delivery_unknown else []

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

    def exhaust(self, reason: str = "FrontierEmpty") -> None:
        """Natural exhaustion (R34)."""
        if self.status in (Status.SEARCHING, "Waiting"):
            self.exhaustion_reason = reason
            self.status = Status.EXHAUSTED
            self.outcome = SemanticOutcome(Status.EXHAUSTED)

    # ---- autonomous runner ----------------------------------------------

    def run_program(self, prog: ScenarioProgram) -> SemanticOutcome:
        """Execute a ScenarioProgram purely via semantic search semantics."""
        self.max_steps = prog.max_steps
        self.budget_limit = prog.budget_limit
        self.exhaustion_reason = None

        for n in prog.initial_frontier:
            self.frontier.append(n)
            self.nodes[n] = "Frontier"

        runnable_idx = 0
        while self.status == Status.SEARCHING:
            if self.step_count >= self.max_steps or not self.frontier:
                break

            # R25: Semantic search scheduler selects first runnable node
            runnable_idx = None
            for i, n in enumerate(self.frontier):
                op = prog.node_ops.get(n, OpDef(op_id=f"op:{n}"))
                op_ceiling = op.cost if op.kind == "external" else 0
                if self.budget_spent + op_ceiling <= self.budget_limit:
                    runnable_idx = i
                    break

            if runnable_idx is None:
                # No runnable node within budget -> Stop(BudgetDepleted)
                break

            node = self.frontier.pop(runnable_idx)
            op = prog.node_ops.get(node, OpDef(op_id=f"op:{node}"))
            succs = list(prog.successors.get(node, []))
            op_is_delivery_unknown = prog.fault_spec.delivery_unknown or (op.op_id in prog.fault_spec.delivery_unknown_ops)
            self.expand(node, op, succs, delivery_unknown=op_is_delivery_unknown)

            # R31/R41/R51/R60: External dispatch with DeliveryUnknown transitions to Waiting state unless safe_retry succeeds
            if op_is_delivery_unknown and op.kind == "external":
                if prog.fault_spec.safe_retry and (op.dedup_capable or op.idempotent):
                    if prog.fault_spec.double_delivery_unknown:
                        # R60: second retry attempt also suffers DeliveryUnknown -> remains Waiting
                        self.status = "Waiting"
                        self.outcome = SemanticOutcome("Waiting")
                        self.outstanding_scope_commitment = op.cost
                        self.unsettled_request_count = 1
                        self.attributable_owner_reserved = op.cost
                        self.intent_available_consumed = self.budget_spent + op.cost
                        return self.outcome
                    else:
                        # R51: Safe transport retry succeeds on second attempt
                        self.budget_spent += op.charge()
                        for s in succs:
                            if s not in self.nodes:
                                self.nodes[s] = "Frontier"
                                self.frontier.append(s)
                else:
                    self.status = "Waiting"
                    self.outcome = SemanticOutcome("Waiting")
                    self.outstanding_scope_commitment = op.cost
                    self.unsettled_request_count = 1
                    self.attributable_owner_reserved = op.cost
                    self.intent_available_consumed = self.budget_spent + op.cost
                    return self.outcome

            # Check for environmental cancellation
            if prog.fault_spec.cancel_in_flight:
                self.cancel()
                return self.outcome

            # Candidates to check: the expanded node itself, then its successors
            candidates = [node] + succs
            for cand in candidates:
                # R48: Strict PartialOf check — only nodes explicitly declared in partial_map are checkable
                if cand not in prog.partial_map:
                    continue

                cand_attempts = 0
                while True:
                    # R42/R49/R59: Check satisfaction attempt limit
                    if self.satisfaction_attempts >= prog.max_satisfaction_attempts:
                        break

                    # R24/R26/R52/R55/R59/R60: effectful satisfier
                    if prog.effectful_satisfier:
                        es = prog.effectful_satisfier
                        es_cost = es.cost
                        if self.budget_spent + es_cost > self.budget_limit:
                            break
                        # R26: satisfaction attempt committed upon emission
                        self.satisfaction_attempts += 1
                        cand_attempts += 1
                        self.effects.append(f"external({es.op_id})")

                        es_is_delivery_unknown = prog.fault_spec.delivery_unknown or (es.op_id in prog.fault_spec.delivery_unknown_ops)
                        if es_is_delivery_unknown:
                            if prog.fault_spec.safe_retry and (es.dedup_capable or es.idempotent):
                                if prog.fault_spec.double_delivery_unknown:
                                    self.status = "Waiting"
                                    self.outcome = SemanticOutcome("Waiting")
                                    self.outstanding_scope_commitment = es_cost
                                    self.unsettled_request_count = 1
                                    self.attributable_owner_reserved = es_cost
                                    self.intent_available_consumed = self.budget_spent + es_cost
                                    return self.outcome
                                else:
                                    self.budget_spent += es.charge()
                            else:
                                # R31: DeliveryUnknown leaves frame in Waiting state
                                self.status = "Waiting"
                                self.outcome = SemanticOutcome("Waiting")
                                self.outstanding_scope_commitment = es_cost
                                self.unsettled_request_count = 1
                                self.attributable_owner_reserved = es_cost
                                self.intent_available_consumed = self.budget_spent + es_cost
                                return self.outcome
                        else:
                            self.budget_spent += es.charge()

                        map_entry = prog.satisfier_map.get(cand, ("ok", False, None))
                        if isinstance(map_entry, list):
                            idx = min(cand_attempts - 1, len(map_entry) - 1)
                            kind, ok, val = map_entry[idx]
                        else:
                            kind, ok, val = map_entry

                        if kind == "err":
                            # R52/R59: effectful satisfier Err(e) honors on_satisfier_error policy
                            self.satisfier_error = val
                            if prog.on_satisfier_error == "abort":
                                self.status = "Failed"
                                self.outcome = SemanticOutcome("Failed", error=val)
                                return self.outcome
                            else:
                                # R59 retry policy: loop again to retry candidate if attempts < max
                                continue
                        elif ok:
                            self.status = Status.SATISFIED
                            self.outcome = SemanticOutcome(Status.SATISFIED, val)
                            return self.outcome
                        else:
                            # Not satisfied (Ok None)
                            break
                    else:
                        if self.check_satisfaction(cand, prog.satisfier_map, prog.on_satisfier_error):
                            return self.outcome
                        break

        # Post-fuel / partial check (D03 / R49)
        if self.status == Status.SEARCHING and prog.check_partial_after_fuel:
            if (self.satisfaction_attempts < prog.max_satisfaction_attempts and
                prog.check_partial_after_fuel in prog.partial_map):
                if self.check_satisfaction(prog.check_partial_after_fuel, prog.satisfier_map, prog.on_satisfier_error):
                    return self.outcome

        if self.status == Status.SEARCHING:
            if self.step_count >= self.max_steps:
                reason = "FuelExhausted"
            elif runnable_idx is None:
                reason = "BudgetDepleted"
            else:
                reason = "FrontierEmpty"
            self.exhaust(reason)

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
            "outstanding_scope_commitment": getattr(self, "outstanding_scope_commitment", 0),
            "unsettled_request_count": getattr(self, "unsettled_request_count", 0),
            "attributable_owner_reserved": getattr(self, "attributable_owner_reserved", 0),
            "intent_available_consumed": getattr(self, "intent_available_consumed", self.budget_spent),
            "effects": sorted(self.effects),
            "exhaustion_reason": getattr(self, "exhaustion_reason", None) if self.status == "Exhausted" else None,
        }
