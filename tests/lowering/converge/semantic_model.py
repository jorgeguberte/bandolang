"""semantic_model.py — minimal semantic model of ConvergeFrame v0.

Models the WHAT (ConvergeFrame v0 semantics), not the soma.vm.* HOW.
Deliberately more direct than the lowered model in model.py/transitions.py:
no outbox, no CompletionRecord, no StageLocal, no settlement records.

R9/R67: SemanticFrame executes ScenarioProgram autonomously using unified
scheduling over RunnableAction (EligibleChecks & EligibleExpansions).
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

    nodes: dict[str, str] = field(default_factory=dict)   # node_id -> status ("Frontier"|"Expanding"|"Pruned"|"Queued")
    node_satisfaction_states: dict[str, str] = field(default_factory=dict) # R61: node_id -> SatisfactionState
    node_satisfaction_retries: dict[str, int] = field(default_factory=dict)
    node_space_attempts: dict[str, int] = field(default_factory=dict) # A2-S: per-node expansion attempt counter
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
                    self.node_satisfaction_states.setdefault(s, "Untested")
                    self.node_satisfaction_retries.setdefault(s, 0)
                    self.frontier.append(s)
        return succs if not delivery_unknown else []

    def check_satisfaction(self, node_id: str,
                           satisfier_map: dict[str, Any],
                           on_error: str = "abort") -> bool:
        """Check satisfaction on a candidate node (R61/R67)."""
        if self.status not in (Status.SEARCHING, Status.EXHAUSTED):
            return False
        self.satisfaction_attempts += 1
        map_entry = satisfier_map.get(node_id, ("ok", False, None))
        retries = self.node_satisfaction_retries.get(node_id, 0)
        if isinstance(map_entry, list):
            idx = min(retries, len(map_entry) - 1)
            kind, ok, val = map_entry[idx]
        else:
            kind, ok, val = map_entry

        if kind == "err":
            self.node_satisfaction_states[node_id] = "RetryableFailure"
            self.node_satisfaction_retries[node_id] = retries + 1
            if on_error == "abort":
                self.status = Status.FAILED
                self.outcome = SemanticOutcome(Status.FAILED, error=val)
                return True
            return False
        elif ok:
            self.node_satisfaction_states[node_id] = "Satisfied"
            self.status = Status.SATISFIED
            self.outcome = SemanticOutcome(Status.SATISFIED, val)
            return True
        else:
            self.node_satisfaction_states[node_id] = "CheckedNotSatisfied"
            return False

    def cancel(self) -> None:
        """Owner cancellation (R2)."""
        if self.status == Status.SEARCHING:
            self.status = Status.CANCELLED
            self.outcome = SemanticOutcome(Status.CANCELLED)

    def exhaust(self, reason: str = "FrontierEmpty") -> None:
        """Exhaustion: search complete without satisfying predicate."""
        if self.status == Status.SEARCHING:
            self.status = Status.EXHAUSTED
            self.exhaustion_reason = reason
            self.outcome = SemanticOutcome(Status.EXHAUSTED)

    # ---- autonomous program execution (R9/R67) -------------------------

    def run_program(self, prog: ScenarioProgram) -> SemanticOutcome:
        """Execute a ScenarioProgram purely via unified RunnableAction semantics (R67)."""
        self.max_steps = prog.max_steps
        self.budget_limit = prog.budget_limit
        self.exhaustion_reason = None

        for n in prog.initial_frontier:
            self.frontier.append(n)
            self.nodes[n] = "Frontier"
            self.node_satisfaction_states[n] = "Untested"
            self.node_satisfaction_retries[n] = 0

        while self.status == Status.SEARCHING:
            # 1. Compute and execute eligible satisfaction checks (R67/R68)
            action_taken = False
            if self.satisfaction_attempts < prog.max_satisfaction_attempts:
                for cand, sat_state in list(self.node_satisfaction_states.items()):
                    if cand in prog.partial_map and sat_state in ("Untested", "RetryableFailure"):
                        if prog.effectful_satisfier:
                            es = prog.effectful_satisfier
                            if self.budget_spent + es.cost > self.budget_limit:
                                continue
                            self.satisfaction_attempts += 1
                            retries = self.node_satisfaction_retries.get(cand, 0)
                            self.effects.append(f"external({es.op_id})")

                            es_is_delivery_unknown = prog.fault_spec.delivery_unknown or (es.op_id in prog.fault_spec.delivery_unknown_ops)
                            if es_is_delivery_unknown:
                                if prog.fault_spec.safe_retry and (es.dedup_capable or es.idempotent):
                                    if prog.fault_spec.double_delivery_unknown:
                                        self.status = "Waiting"
                                        self.outcome = SemanticOutcome("Waiting")
                                        self.outstanding_scope_commitment = es.cost
                                        self.unsettled_request_count = 1
                                        self.attributable_owner_reserved = es.cost
                                        self.intent_available_consumed = self.budget_spent + es.cost
                                        return self.outcome
                                    else:
                                        self.budget_spent += es.charge()
                                else:
                                    self.status = "Waiting"
                                    self.outcome = SemanticOutcome("Waiting")
                                    self.outstanding_scope_commitment = es.cost
                                    self.unsettled_request_count = 1
                                    self.attributable_owner_reserved = es.cost
                                    self.intent_available_consumed = self.budget_spent + es.cost
                                    return self.outcome
                            else:
                                self.budget_spent += es.charge()

                            if prog.fault_spec.cancel_in_flight:
                                self.cancel()
                                return self.outcome

                            map_entry = prog.satisfier_map.get(cand, ("ok", False, None))
                            if isinstance(map_entry, list):
                                idx = min(retries, len(map_entry) - 1)
                                kind, ok, val = map_entry[idx]
                            else:
                                kind, ok, val = map_entry

                            if kind == "err":
                                self.node_satisfaction_states[cand] = "RetryableFailure"
                                self.node_satisfaction_retries[cand] = retries + 1
                                self.satisfier_error = val
                                if prog.on_satisfier_error == "abort":
                                    self.status = Status.FAILED
                                    self.outcome = SemanticOutcome(Status.FAILED, error=val)
                                    return self.outcome
                                action_taken = True
                                break
                            elif ok:
                                self.node_satisfaction_states[cand] = "Satisfied"
                                self.status = Status.SATISFIED
                                self.outcome = SemanticOutcome(Status.SATISFIED, val)
                                return self.outcome
                            else:
                                self.node_satisfaction_states[cand] = "CheckedNotSatisfied"
                                action_taken = True
                                break
                        else:
                            # Local satisfier
                            if self.check_satisfaction(cand, prog.satisfier_map, prog.on_satisfier_error):
                                return self.outcome
                            action_taken = True
                            break

            if action_taken:
                continue

            # 2. Compute and execute eligible expansions (R67)
            if self.step_count < self.max_steps and self.frontier:
                runnable_idx = None
                for i, n in enumerate(self.frontier):
                    op = prog.node_ops.get(n, OpDef(op_id=f"op:{n}"))
                    op_ceiling = op.cost if op.kind == "external" else 0
                    if self.budget_spent + op_ceiling <= self.budget_limit:
                        runnable_idx = i
                        break

                if runnable_idx is not None:
                    node = self.frontier.pop(runnable_idx)
                    op = prog.node_ops.get(node, OpDef(op_id=f"op:{node}"))
                    succs = list(prog.successors.get(node, []))

                    # R64/R69/A2-S: declarative space fault handling resolved by semantic attempt
                    self.node_space_attempts[node] = self.node_space_attempts.get(node, 0) + 1
                    attempt_no = self.node_space_attempts[node]
                    fault_spec_val = prog.space_faults.get(op.op_id)
                    if isinstance(fault_spec_val, list):
                        fault_idx = min(attempt_no - 1, len(fault_spec_val) - 1)
                        fault_msg = fault_spec_val[fault_idx]
                    else:
                        fault_msg = fault_spec_val

                    if fault_msg is not None:
                        self.step_count += 1
                        self.budget_spent += op.charge()
                        self.visited.append(Visit(node))
                        self.effects.append(f"external({op.op_id})")
                        if prog.on_step_failure == "abort":
                            self.status = Status.FAILED
                            self.outcome = SemanticOutcome(Status.FAILED, error=fault_msg)
                            return self.outcome
                        elif prog.on_step_failure == "prune":
                            self.nodes[node] = "Pruned"
                            continue
                        elif prog.on_step_failure == "requeue":
                            self.nodes[node] = "Queued"
                            if node not in self.frontier:
                                self.frontier.append(node)
                            continue

                    op_is_delivery_unknown = prog.fault_spec.delivery_unknown or (op.op_id in prog.fault_spec.delivery_unknown_ops)
                    self.expand(node, op, succs, delivery_unknown=op_is_delivery_unknown)

                    if op_is_delivery_unknown and op.kind == "external":
                        if prog.fault_spec.safe_retry and (op.dedup_capable or op.idempotent):
                            if prog.fault_spec.double_delivery_unknown:
                                self.status = "Waiting"
                                self.outcome = SemanticOutcome("Waiting")
                                self.outstanding_scope_commitment = op.cost
                                self.unsettled_request_count = 1
                                self.attributable_owner_reserved = op.cost
                                self.intent_available_consumed = self.budget_spent + op.cost
                                return self.outcome
                            else:
                                self.budget_spent += op.charge()
                                for s in succs:
                                    if s not in self.nodes:
                                        self.nodes[s] = "Frontier"
                                        self.node_satisfaction_states[s] = "Untested"
                                        self.node_satisfaction_retries[s] = 0
                                        self.frontier.append(s)
                        else:
                            self.status = "Waiting"
                            self.outcome = SemanticOutcome("Waiting")
                            self.outstanding_scope_commitment = op.cost
                            self.unsettled_request_count = 1
                            self.attributable_owner_reserved = op.cost
                            self.intent_available_consumed = self.budget_spent + op.cost
                            return self.outcome

                    if prog.fault_spec.cancel_in_flight:
                        self.cancel()
                        return self.outcome

                    continue

            # 3. Stop reasons when no eligible actions exist
            if self.step_count >= self.max_steps:
                reason = "FuelExhausted"
            elif not self.frontier:
                reason = "FrontierEmpty"
            else:
                reason = "BudgetDepleted"
            self.exhaust(reason)
            break

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
