"""scenarios.py — shared scenario descriptors for Campaign 2.

R5 (audit): ONE descriptor per scenario, consumed INDEPENDENTLY by the
semantic model and the lowered model. Neither model sees the other's output;
both derive effects/budget/attempts from this descriptor alone.

R6 (audit): descriptors carry exact T values; comparison is exact.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Step:
    """One expansion step in the scenario's intended execution."""
    node: str
    op: str
    request: str
    kind: str                  # "local" | "external"
    cost: int = 0              # budget consumed by an external action
    check_after: bool = False  # CheckSatisfaction(node) after expansion?
    check_result: str = "none" # "none" | "fail" | f"satisfied:{T}" | f"error:{msg}"
    abort_on_error: bool = False


@dataclass
class Scenario:
    name: str
    max_steps: int
    steps: list[Step] = field(default_factory=list)
    end_state: str = "Searching"   # Searching / Satisfied / Exhausted / Failed / Cancelled
    cancel_at_end: bool = False


# =====================================================================
# Basic battery D01–D06
# =====================================================================

D01 = Scenario(
    name="D01_local_expand_exhausted",
    max_steps=6,
    steps=[Step("root", "op1", "r1", "local", check_after=True, check_result="fail")],
    end_state="Exhausted",
)

D02 = Scenario(
    name="D02_expand_successor_satisfied",
    max_steps=6,
    steps=[
        Step("A", "opA", "rA", "local"),
        Step("B", "opB", "rB", "local", check_after=True, check_result="satisfied:T-value-B"),
    ],
    end_state="Satisfied",
)

D03 = Scenario(
    name="D03_max_steps_partial_still_checked",
    max_steps=2,
    steps=[
        Step("P", "opP", "rP", "external", cost=10),
        Step("Q", "opQ", "rQ", "external", cost=10,
             check_after=True, check_result="satisfied:T-partial"),
    ],
    end_state="Satisfied",
)

D04 = Scenario(
    name="D04_satisfier_none_exhausts",
    max_steps=6,
    steps=[
        Step("root", "op4", "r4", "external", cost=8,
             check_after=True, check_result="fail"),
    ],
    end_state="Exhausted",
)

D05 = Scenario(
    name="D05_satisfier_error_abort",
    max_steps=6,
    steps=[
        Step("root", "op5", "r5", "external", cost=9,
             check_after=True, check_result="error:satisfier exploded",
             abort_on_error=True),
    ],
    end_state="Failed",
)

D06 = Scenario(
    name="D06_external_satisfied",
    max_steps=6,
    steps=[
        Step("root", "opExt", "rext", "external", cost=12,
             check_after=True, check_result="satisfied:T-ext"),
    ],
    end_state="Satisfied",
)
