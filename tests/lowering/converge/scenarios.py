"""scenarios.py — declarative search-space scenario programs for Campaign 2.

R8 (audit): ScenarioProgram is a DECLARATIVE specification of the search space,
operations, satisfier function, and environmental faults.
It NEVER contains:
- scripted step-by-step traces
- expected end_state oracles

Both the semantic model and the lowered model consume this program
independently and derive their own execution paths.
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
        return self.cost if self.actual_cost is None else self.actual_cost


@dataclass(frozen=True)
class FaultSpec:
    """Environmental/transport fault injection flags (inputs, not outcome oracles)."""
    delivery_unknown: bool = False
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


# =====================================================================
# Basic battery D01–D06 programs
# =====================================================================

D01 = ScenarioProgram(
    name="D01_local_expand_exhausted",
    initial_frontier=["root"],
    successors={"root": []},
    node_ops={"root": OpDef("op1", kind="local")},
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
    satisfier_map={"root": ("ok", False, None)},
    max_steps=6,
)

D05 = ScenarioProgram(
    name="D05_satisfier_error_abort",
    initial_frontier=["root"],
    successors={"root": []},
    node_ops={"root": OpDef("op5", kind="external", cost=9)},
    satisfier_map={"root": ("err", False, "satisfier exploded")},
    on_satisfier_error="abort",
    max_steps=6,
)

D06 = ScenarioProgram(
    name="D06_external_satisfied",
    initial_frontier=["root"],
    successors={"root": []},
    node_ops={"root": OpDef("opExt", kind="external", cost=12)},
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
    satisfier_map={"root": ("ok", False, None)},
    max_steps=6,
    fault_spec=FaultSpec(delivery_unknown=True),
)

D08 = ScenarioProgram(
    name="D08_safe_transport_retry",
    initial_frontier=["root"],
    successors={"root": []},
    node_ops={"root": OpDef("op8", kind="external", cost=15, dedup_capable=True)},
    satisfier_map={"root": ("ok", True, "T-retry")},
    max_steps=6,
    fault_spec=FaultSpec(delivery_unknown=True, safe_retry=True),
)

D09 = ScenarioProgram(
    name="D09_duplicate_completion",
    initial_frontier=["root"],
    successors={"root": []},
    node_ops={"root": OpDef("op9", kind="external", cost=20)},
    satisfier_map={"root": ("ok", False, None)},
    max_steps=6,
    fault_spec=FaultSpec(duplicate_completion=True),
)

D10 = ScenarioProgram(
    name="D10_crash_after_settlement",
    initial_frontier=["root"],
    successors={"root": []},
    node_ops={"root": OpDef("op10", kind="external", cost=25)},
    satisfier_map={"root": ("ok", True, "T-crash")},
    max_steps=6,
    fault_spec=FaultSpec(crash_after_settlement=True),
)

D11 = ScenarioProgram(
    name="D11_cancel_while_in_flight",
    initial_frontier=["root"],
    successors={"root": []},
    node_ops={"root": OpDef("op11", kind="external", cost=40)},
    max_steps=6,
    fault_spec=FaultSpec(cancel_in_flight=True),
)

D12 = ScenarioProgram(
    name="D12_late_settlement_fatal_closing",
    initial_frontier=["root"],
    successors={"root": []},
    node_ops={"root": OpDef("op12", kind="external", cost=50)},
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
    satisfier_map={"root": ("ok", True, "T-reconciled")},
    max_steps=6,
)
