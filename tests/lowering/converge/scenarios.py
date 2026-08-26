"""scenarios.py — declarative search space specifications for Campaign 2.

Frozen principle: tests describe the SEARCH SPACE and ENVIRONMENTAL FAULTS as inputs,
NOT the expected trajectory or outcome.

R8 (audit): ScenarioProgram replaces the old scripted Scenario/Step lists.
R14 (audit): fault specs are inputs to the harness, not outcome oracles.
R33/R48 (audit): explicit partial_map (only nodes with PartialOf(node)==Some(P) are checkable).
R42/R49 (audit): max_satisfaction_attempts limit.
R46 (audit): deterministic completion payload binding.
R47 (audit): DeliveryUnknown does not incorporate successors before completion.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class OpDef:
    op_id: str
    kind: str = "local"              # "local" | "external"
    cost: int = 0                    # budget ceiling reserved at stage_local
    actual_cost: Optional[int] = None # actual charge at settlement (defaults to cost)
    request_id: Optional[str] = None # defaults to f"req:{op_id}"
    dedup_capable: bool = True
    idempotent: bool = True

    def charge(self) -> int:
        return self.actual_cost if self.actual_cost is not None else self.cost


@dataclass(frozen=True)
class FaultSpec:
    """Environmental/transport fault injection flags (inputs, not outcome oracles)."""
    delivery_unknown: bool = False
    delivery_unknown_ops: tuple[str, ...] = ()  # R41: targeted op_ids that suffer DeliveryUnknown
    safe_retry: bool = False
    duplicate_completion: bool = False
    crash_after_settlement: bool = False
    cancel_in_flight: bool = False


@dataclass(frozen=True)
class ScenarioProgram:
    name: str
    initial_frontier: list[str]
    successors: dict[str, list[str]] = field(default_factory=dict)
    node_ops: dict[str, OpDef] = field(default_factory=dict)
    # satisfier_map: node_id -> ("ok", True/False, val) | ("err", False, error_msg)
    satisfier_map: dict[str, tuple[str, bool, Any]] = field(default_factory=dict)
    on_satisfier_error: str = "abort"      # "abort" | "retry"
    max_steps: int = 6
    budget_limit: int = 100
    fault_spec: FaultSpec = field(default_factory=FaultSpec)
    # For D03: check a specific partial candidate after expansion fuel is exhausted
    check_partial_after_fuel: Optional[str] = None
    # R24: effectful satisfier definition (own budget/cost, effects trace)
    effectful_satisfier: Optional[OpDef] = None
    # R33/R48: explicit PartialOf mapping: node_id -> Partial (only partial nodes are checkable)
    partial_map: dict[str, Any] = field(default_factory=dict)
    # R42/R49: maximum satisfaction attempts before satisfier eligibility is exhausted
    max_satisfaction_attempts: int = 10


# =====================================================================
# Basic battery D01–D06 programs (R48: explicit partial_map)
# =====================================================================

D01 = ScenarioProgram(
    name="D01_local_expand_exhausted",
    initial_frontier=["root"],
    successors={"root": []},
    node_ops={"root": OpDef("op1", kind="local")},
    partial_map={"root": "P_root"},
    satisfier_map={"root": ("ok", False, None)},
    max_steps=6,
)

# R10 restored: Expand A produces successor B. CheckSatisfaction(B) satisfies
# with T-value-B. B is NEVER expanded, never in visited, never consumes step fuel.
D02 = ScenarioProgram(
    name="D02_expand_successor_satisfied",
    initial_frontier=["A"],
    successors={"A": ["B"], "B": []},
    node_ops={"A": OpDef("opA", kind="local"), "B": OpDef("opB", kind="local")},
    partial_map={"A": "P_A", "B": "P_B"},
    satisfier_map={"A": ("ok", False, None), "B": ("ok", True, "T-value-B")},
    max_steps=6,
)

# R4: max_steps reached, partial checked after fuel ends
D03 = ScenarioProgram(
    name="D03_max_steps_partial_still_checked",
    initial_frontier=["P"],
    successors={"P": ["Q"], "Q": []},
    node_ops={
        "P": OpDef("opP", kind="external", cost=10),
        "Q": OpDef("opQ", kind="external", cost=10),
    },
    partial_map={"P": "P_P", "Q": "P_Q", "partial_candidate": "P_cand"},
    satisfier_map={
        "P": ("ok", False, None),
        "Q": ("ok", False, None),
        "partial_candidate": ("ok", True, "T-partial"),
    },
    max_steps=2,
    check_partial_after_fuel="partial_candidate",
)

D04 = ScenarioProgram(
    name="D04_satisfier_none_exhausts",
    initial_frontier=["root"],
    successors={"root": []},
    node_ops={"root": OpDef("op4", kind="external", cost=8)},
    partial_map={"root": "P_root"},
    satisfier_map={"root": ("ok", False, None)},
    max_steps=6,
)

D05 = ScenarioProgram(
    name="D05_satisfier_error_abort",
    initial_frontier=["root"],
    successors={"root": []},
    node_ops={"root": OpDef("op5", kind="external", cost=9)},
    partial_map={"root": "P_root"},
    satisfier_map={"root": ("err", False, "satisfier exploded")},
    on_satisfier_error="abort",
    max_steps=6,
)

D06 = ScenarioProgram(
    name="D06_external_satisfied",
    initial_frontier=["root"],
    successors={"root": []},
    node_ops={"root": OpDef("opExt", kind="external", cost=12)},
    partial_map={"root": "P_root"},
    satisfier_map={"root": ("ok", True, "T-ext")},
    max_steps=6,
)


# =====================================================================
# Fault/recovery battery D07–D12 programs
# =====================================================================

D07 = ScenarioProgram(
    name="D07_delivery_unknown",
    initial_frontier=["root"],
    successors={"root": []},
    node_ops={"root": OpDef("op7", kind="external", cost=10)},
    partial_map={"root": "P_root"},
    satisfier_map={"root": ("ok", False, None)},
    max_steps=6,
    fault_spec=FaultSpec(delivery_unknown=True),
)

D08 = ScenarioProgram(
    name="D08_safe_transport_retry",
    initial_frontier=["root"],
    successors={"root": []},
    node_ops={"root": OpDef("op8", kind="external", cost=15, dedup_capable=True)},
    partial_map={"root": "P_root"},
    satisfier_map={"root": ("ok", True, "T-retry")},
    max_steps=6,
    fault_spec=FaultSpec(delivery_unknown=True, safe_retry=True),
)

D09 = ScenarioProgram(
    name="D09_duplicate_completion",
    initial_frontier=["root"],
    successors={"root": []},
    node_ops={"root": OpDef("op9", kind="external", cost=20)},
    partial_map={"root": "P_root"},
    satisfier_map={"root": ("ok", False, None)},
    max_steps=6,
    fault_spec=FaultSpec(duplicate_completion=True),
)

D10 = ScenarioProgram(
    name="D10_crash_after_settlement",
    initial_frontier=["root"],
    successors={"root": []},
    node_ops={"root": OpDef("op10", kind="external", cost=25)},
    partial_map={"root": "P_root"},
    satisfier_map={"root": ("ok", True, "T-crash")},
    max_steps=6,
    fault_spec=FaultSpec(crash_after_settlement=True),
)

D11 = ScenarioProgram(
    name="D11_cancel_while_in_flight",
    initial_frontier=["root"],
    successors={"root": []},
    node_ops={"root": OpDef("op11", kind="external", cost=40)},
    partial_map={"root": "P_root"},
    satisfier_map={"root": ("ok", False, None)},
    max_steps=6,
    fault_spec=FaultSpec(cancel_in_flight=True),
)

D12 = ScenarioProgram(
    name="D12_late_settlement_fatal_closing",
    initial_frontier=["root"],
    successors={"root": []},
    node_ops={"root": OpDef("op12", kind="external", cost=50)},
    partial_map={"root": "P_root"},
    satisfier_map={"root": ("err", False, "fatal protocol breach")},
    on_satisfier_error="abort",
    max_steps=6,
)

# R12/R14: budget ceiling vs actual charge (reserve 10, charge 6)
D13 = ScenarioProgram(
    name="D13_budget_ceiling_vs_actual_charge",
    initial_frontier=["root"],
    successors={"root": []},
    node_ops={"root": OpDef("op13", kind="external", cost=10, actual_cost=6)},
    partial_map={"root": "P_root"},
    satisfier_map={"root": ("ok", True, "T-reconciled")},
    max_steps=6,
)

# R15: budget headroom exhaustion / depletion (limit=100, A costs 60, B costs 60)
D14 = ScenarioProgram(
    name="D14_budget_depleted_exhausts",
    initial_frontier=["A"],
    successors={"A": ["B"], "B": []},
    node_ops={
        "A": OpDef("opA", kind="external", cost=60),
        "B": OpDef("opB", kind="external", cost=60),
    },
    partial_map={"A": "PA", "B": "PB"},
    satisfier_map={
        "A": ("ok", False, None),
        "B": ("ok", False, None),
    },
    max_steps=6,
    budget_limit=100,
)

# R20: unaffordable cost ceiling (remaining headroom 40 < ceiling 60), actual charge would be 10 -> MUST NOT DISPATCH
D15 = ScenarioProgram(
    name="D15_unaffordable_ceiling_refused",
    initial_frontier=["A"],
    successors={"A": ["B"], "B": ["C"], "C": []},
    node_ops={
        "A": OpDef("opA", kind="external", cost=60),
        "B": OpDef("opB", kind="external", cost=60, actual_cost=10), # ceiling 60 > remaining 40!
        "C": OpDef("opC", kind="local"),
    },
    partial_map={"A": "PA", "B": "PB", "C": "PC"},
    satisfier_map={
        "A": ("ok", False, None),
        "B": ("ok", False, None),
        "C": ("ok", True, "T-unreached-goal"),
    },
    max_steps=6,
    budget_limit=100,
)

# R24/R33/R48: effectful satisfier coverage (own budget, effect trace, settlement, explicit PartialOf)
D16 = ScenarioProgram(
    name="D16_effectful_satisfier",
    initial_frontier=["root"],
    successors={"root": ["cand1"]},
    node_ops={
        "root": OpDef("opRoot", kind="local"),
        "cand1": OpDef("opCand1", kind="local"),
    },
    partial_map={
        "cand1": "PartialCandidate1",  # root has PartialOf=None; only cand1 is partial
    },
    satisfier_map={
        "cand1": ("ok", True, "T-verified"),
    },
    max_steps=6,
    budget_limit=100,
    effectful_satisfier=OpDef("opVerify", kind="external", cost=5),
)

# R26/R31: effectful satisfier commit point under DeliveryUnknown -> Waiting state with attempts=1
D17 = ScenarioProgram(
    name="D17_effectful_satisfier_delivery_unknown",
    initial_frontier=["root"],
    successors={"root": []},
    node_ops={
        "root": OpDef("opRoot", kind="local"),
    },
    partial_map={
        "root": "PartialRoot",
    },
    satisfier_map={
        "root": ("ok", True, "T-unreached"),
    },
    max_steps=6,
    budget_limit=100,
    effectful_satisfier=OpDef("opVerify", kind="external", cost=5),
    fault_spec=FaultSpec(delivery_unknown=True),
)

# R31: sequential Waiting blocks subsequent local runnable nodes
D18_WAITING = ScenarioProgram(
    name="D18_sequential_waiting_blocks_local",
    initial_frontier=["A", "B"],
    successors={"A": [], "B": []},
    node_ops={
        "A": OpDef("opA", kind="external", cost=10),
        "B": OpDef("opB", kind="local"),
    },
    partial_map={},
    fault_spec=FaultSpec(delivery_unknown=True),
    max_steps=6,
    budget_limit=100,
)

# R32: autonomous crash recovery preserves and applies space successors
D19_CRASH_RECOVERY = ScenarioProgram(
    name="D19_external_space_crash_recovery_preserves_successors",
    initial_frontier=["root"],
    successors={"root": ["childB"]},
    node_ops={
        "root": OpDef("opRoot", kind="external", cost=10),
        "childB": OpDef("opB", kind="local"),
    },
    partial_map={"childB": "P_childB"},
    satisfier_map={
        "childB": ("ok", True, "T-recovered"),
    },
    fault_spec=FaultSpec(crash_after_settlement=True),
    max_steps=6,
    budget_limit=100,
)

# R41: targeted DeliveryUnknown on second external op preserves prior settled budget spend
D20_TARGETED_DELIVERY_UNKNOWN = ScenarioProgram(
    name="D20_waiting_preserves_prior_spend",
    initial_frontier=["A"],
    successors={"A": ["B"], "B": []},
    node_ops={
        "A": OpDef("opA", kind="external", cost=20),
        "B": OpDef("opB", kind="external", cost=10),
    },
    partial_map={},
    fault_spec=FaultSpec(delivery_unknown_ops=("opB",)),
    max_steps=6,
    budget_limit=100,
)

# R42/R49: max_satisfaction_attempts limit exhaustion across multiple partial candidates
D21_SATISFACTION_LIMIT = ScenarioProgram(
    name="D21_satisfaction_attempt_limit_exhausts",
    initial_frontier=["root"],
    successors={"root": ["P1", "P2"]},
    node_ops={
        "root": OpDef("opRoot", kind="local"),
        "P1": OpDef("opP1", kind="local"),
        "P2": OpDef("opP2", kind="local"),
    },
    partial_map={
        "P1": "Part1",
        "P2": "Part2",
    },
    satisfier_map={
        "P1": ("ok", False, None),
        "P2": ("ok", True, "T-unreached-attempt-blocked"),
    },
    max_steps=6,
    budget_limit=100,
    max_satisfaction_attempts=1,
)

# R47: DeliveryUnknown on external expansion does not incorporate successors
D22_DELIVERY_UNKNOWN_NO_SUCCESSORS = ScenarioProgram(
    name="D22_delivery_unknown_does_not_incorporate_successors",
    initial_frontier=["A"],
    successors={"A": ["B"], "B": []},
    node_ops={
        "A": OpDef("opA", kind="external", cost=10),
        "B": OpDef("opB", kind="local"),
    },
    partial_map={},
    fault_spec=FaultSpec(delivery_unknown=True),
    max_steps=6,
    budget_limit=100,
)
