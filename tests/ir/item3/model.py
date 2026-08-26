"""model.py — SOMA-IR Item 3 (CFG / Result / Error Model) data structures.

Formal representation of:
- Types (Primitive, Result, ChildHandle, ActOutcome, PartialReport)
- Facts and LatentPostconditions (on_ok, on_err templates)
- Values and Runtime Outcomes (Result, ActOutcome, PartialEffectReport, ChildHandle)
- Flat CFG with Typed SSA and Block Arguments (no phi nodes)
- Control Flow Terminators (Br, CondBr, SwitchResult, SwitchActOutcome, Return)
- Path Facts (Ψ) with Exact Intersection Merge and SSA Variable Renaming
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Union


# ---------------------------------------------------------------------
# 1. Type Algebra
# ---------------------------------------------------------------------

class Type:
    """Base SOMA-IR Type."""
    def matches(self, other: Type) -> bool:
        return self == other


@dataclass(frozen=True)
class PrimitiveType(Type):
    name: str

    def __str__(self) -> str:
        return self.name


@dataclass(frozen=True)
class ResultType(Type):
    ok_type: Type
    err_type: Type

    def __str__(self) -> str:
        return f"Result<{self.ok_type}, {self.err_type}>"


@dataclass(frozen=True)
class ChildHandleType(Type):
    ok_type: Type
    err_type: Type
    may_effects: frozenset[str] = field(default_factory=frozenset)

    def __str__(self) -> str:
        eff_str = "{" + ", ".join(sorted(self.may_effects)) + "}"
        return f"ChildHandle<{self.ok_type}, {self.err_type}, {eff_str}>"

    def is_compatible_for_join(self, other: ChildHandleType) -> bool:
        """Handle join compatibility (R15): same success type T and error type E."""
        return self.ok_type == other.ok_type and self.err_type == other.err_type

    def join(self, other: ChildHandleType) -> ChildHandleType:
        """May-effect union join (R13/R14): Σ_join = Σ_a ∪ Σ_b."""
        if not self.is_compatible_for_join(other):
            raise TypeError(f"Incompatible handle types for join: {self} vs {other}")
        return ChildHandleType(
            ok_type=self.ok_type,
            err_type=self.err_type,
            may_effects=self.may_effects | other.may_effects,
        )


@dataclass(frozen=True)
class PartialReportType(Type):
    def __str__(self) -> str:
        return "PartialEffectReport"


@dataclass(frozen=True)
class ActOutcomeType(Type):
    ok_type: Type
    err_type: Type
    partial_type: Type = field(default_factory=PartialReportType)

    def __str__(self) -> str:
        return f"ActOutcome<{self.ok_type}, {self.err_type}, {self.partial_type}>"


# Standard primitive singletons
I64 = PrimitiveType("i64")
BOOL = PrimitiveType("bool")
STRING = PrimitiveType("string")
UNIT = PrimitiveType("unit")


# ---------------------------------------------------------------------
# 2. Facts and Latent Postconditions (Track A)
# ---------------------------------------------------------------------

@dataclass(frozen=True)
class Fact:
    """An instantiated path fact in Ψ."""
    name: str
    args: tuple[str, ...]

    def __str__(self) -> str:
        return f"{self.name}({', '.join(self.args)})"

    def rename(self, mapping: dict[str, str]) -> Fact:
        """Rename SSA symbols in fact arguments across block argument transfer."""
        new_args = tuple(mapping.get(a, a) for a in self.args)
        return Fact(self.name, new_args)


@dataclass(frozen=True)
class FactTemplate:
    """A latent postcondition template attached to an SSA definition."""
    name: str
    params: tuple[str, ...]  # Formal parameters, e.g. ("$value", "target_A")

    def instantiate(self, bindings: dict[str, str]) -> Fact:
        args = tuple(bindings.get(p, p) for p in self.params)
        return Fact(self.name, args)


@dataclass(frozen=True)
class LatentPostconditions:
    """Postconditions latent on a Result or ActOutcome (Track A)."""
    on_ok: tuple[FactTemplate, ...] = ()
    on_err: tuple[FactTemplate, ...] = ()
    on_partial: tuple[FactTemplate, ...] = ()

    def instantiate_ok(self, value_sym: str) -> frozenset[Fact]:
        return frozenset(t.instantiate({"$value": value_sym, "$payload": value_sym}) for t in self.on_ok)

    def instantiate_err(self, error_sym: str) -> frozenset[Fact]:
        return frozenset(t.instantiate({"$error": error_sym}) for t in self.on_err)

    def instantiate_partial(self, report_sym: str) -> frozenset[Fact]:
        return frozenset(t.instantiate({"$report": report_sym}) for t in self.on_partial)


# ---------------------------------------------------------------------
# 3. Values and Runtime Outcomes (Tracks A, B, C, D)
# ---------------------------------------------------------------------

@dataclass(frozen=True)
class Variable:
    """Typed SSA Variable symbol."""
    name: str
    val_type: Type

    def __str__(self) -> str:
        return f"%{self.name}: {self.val_type}"


@dataclass(frozen=True)
class Constant:
    val: Any
    val_type: Type


# Partial Effect Report (Track C)
@dataclass(frozen=True)
class PartialEffectReport:
    """Explicit report of confirmed footprint when an action partially completes."""
    op_id: str
    confirmed_applied: tuple[str, ...]
    confirmed_not_applied: tuple[str, ...]
    receipt_id: str
    error: Optional[str] = None


# Concrete runtime Result values
@dataclass(frozen=True)
class OkVal:
    value: Any
    val_type: Type
    latent: LatentPostconditions = field(default_factory=LatentPostconditions)


@dataclass(frozen=True)
class ErrVal:
    error: Any
    err_type: Type
    latent: LatentPostconditions = field(default_factory=LatentPostconditions)


# Concrete runtime ActOutcome values (Track B & Track C)
@dataclass(frozen=True)
class ActSuccessVal:
    value: Any
    val_type: Type
    latent: LatentPostconditions = field(default_factory=LatentPostconditions)


@dataclass(frozen=True)
class ActFailureVal:
    error: Any
    err_type: Type
    latent: LatentPostconditions = field(default_factory=LatentPostconditions)


@dataclass(frozen=True)
class ActPartialVal:
    report: PartialEffectReport
    latent: LatentPostconditions = field(default_factory=LatentPostconditions)


@dataclass(frozen=True)
class DeliveryUnknownVal:
    request_id: str
    op_id: str


@dataclass(frozen=True)
class SettlementUnknownVal:
    request_id: str
    op_id: str


# Child Handle (Track D)
@dataclass(frozen=True)
class ChildHandleVal:
    handle_id: str
    ok_type: Type
    err_type: Type
    may_effects: frozenset[str]
    actual_provenance: tuple[str, ...]   # Real child execution dependency trace (Track D provenance)
    settlement_state: str = "Settled"    # "Settled" | "SettlementUnknown"
    result_val: Optional[OkVal | ErrVal] = None


# ---------------------------------------------------------------------
# 4. SSA Instructions & CFG Nodes
# ---------------------------------------------------------------------

class Instruction:
    pass


@dataclass(frozen=True)
class InstAssign(Instruction):
    dest: Variable
    source: Variable | Constant


@dataclass(frozen=True)
class InstRead(Instruction):
    dest: Variable
    target: str
    latent: LatentPostconditions = field(default_factory=LatentPostconditions)


@dataclass(frozen=True)
class InstInfer(Instruction):
    dest: Variable
    query: str
    latent: LatentPostconditions = field(default_factory=LatentPostconditions)


@dataclass(frozen=True)
class InstVerify(Instruction):
    dest: Variable
    target: str
    latent: LatentPostconditions = field(default_factory=LatentPostconditions)


@dataclass(frozen=True)
class InstAct(Instruction):
    dest: Variable
    op_id: str
    is_atomic: bool = True               # Track C: adapter atomicity contract
    latent: LatentPostconditions = field(default_factory=LatentPostconditions)


@dataclass(frozen=True)
class InstSpawnChild(Instruction):
    dest: Variable
    child_id: str
    may_effects: frozenset[str]
    ok_type: Type
    err_type: Type
    latent: LatentPostconditions = field(default_factory=LatentPostconditions)


@dataclass(frozen=True)
class InstAwaitHandle(Instruction):
    dest: Variable
    handle: Variable


# ---------------------------------------------------------------------
# 5. Terminators
# ---------------------------------------------------------------------

class Terminator:
    pass


@dataclass(frozen=True)
class TermBr(Terminator):
    target: str
    args: tuple[Variable | Constant, ...] = ()


@dataclass(frozen=True)
class TermCondBr(Terminator):
    cond: Variable
    true_target: str
    true_args: tuple[Variable | Constant, ...]
    false_target: str
    false_args: tuple[Variable | Constant, ...]


@dataclass(frozen=True)
class TermSwitchResult(Terminator):
    """Refinement terminator for Result<T,E> (Track A)."""
    result_var: Variable
    ok_target: str
    ok_arg: Variable        # Block arg in target receiving unwrapped T
    err_target: str
    err_arg: Variable       # Block arg in target receiving unwrapped E


@dataclass(frozen=True)
class TermSwitchActOutcome(Terminator):
    """Refinement terminator for ActOutcome (Tracks B & C)."""
    outcome_var: Variable
    success_target: str
    success_arg: Variable
    failure_target: str
    failure_arg: Variable
    partial_target: Optional[str] = None
    partial_arg: Optional[Variable] = None
    unknown_target: Optional[str] = None
    unknown_arg: Optional[Variable] = None


@dataclass(frozen=True)
class TermReturn(Terminator):
    value: Optional[Variable | Constant] = None


@dataclass(frozen=True)
class TermUnreachable(Terminator):
    pass


# ---------------------------------------------------------------------
# 6. Basic Block & CFG
# ---------------------------------------------------------------------

@dataclass
class BasicBlock:
    name: str
    params: list[Variable] = field(default_factory=list)
    instructions: list[Instruction] = field(default_factory=list)
    terminator: Terminator = field(default_factory=TermUnreachable)


@dataclass
class CFGProgram:
    name: str
    entry: str
    blocks: dict[str, BasicBlock] = field(default_factory=dict)
    # Metadata on declared operations
    op_contracts: dict[str, dict[str, Any]] = field(default_factory=dict)
