"""cfg_model.py — Executable Lowered CFG Interpreter & Dataflow Fact Analyzer for SOMA-IR Item 3.

Implements:
1. SSA Environment & Block Argument Passing (no phi nodes)
2. Static CFG Worklist / Fixed-Point Fact Analyzer over CFG edges (J1):
   Ψ_in(block) = ⋂_{pred} rename_edge(Ψ_out(pred -> block))
3. Block-Argument Type Derivation & May-Effect Union Join (J2)
4. Latent Postcondition Refinement on SwitchResult & SwitchActOutcome (Track A)
5. Settlement & Physical Ambiguity Handling (Track B)
6. Partial Completion Distinguishability & Transactional Rejection (Track C)
7. ChildHandle May-Effect Join, Await Effect Neutrality, and Concrete Lineage (Track D)
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Optional

from model import (
    ActFailureVal, ActOutcomeType, ActPartialVal, ActSuccessVal,
    BasicBlock, CFGProgram, ChildHandleType, ChildHandleVal, Constant,
    DeliveryUnknownVal, ErrVal, Fact, InstAct, InstAssign, InstAwaitHandle,
    InstInfer, InstRead, InstSpawnChild, InstVerify, Instruction, LatentPostconditions,
    OkVal, PartialEffectReport, ResultType, SettlementUnknownVal,
    TermBr, TermCondBr, TermReturn, TermSwitchActOutcome, TermSwitchResult,
    TermUnreachable, Terminator, Type, Variable,
)


class CFGExecutionError(Exception):
    pass


class ProtocolViolationError(Exception):
    pass


@dataclass
class ExecutionState:
    """State of an executing CFG instance."""
    current_block: str
    env: dict[str, Any] = field(default_factory=dict)             # var_name -> runtime value
    var_types: dict[str, Type] = field(default_factory=dict)       # var_name -> Type
    var_latent: dict[str, LatentPostconditions] = field(default_factory=dict) # var_name -> latent postconditions
    psi: frozenset[Fact] = field(default_factory=frozenset)        # Active path facts Ψ
    block_entry_psi: dict[str, frozenset[Fact]] = field(default_factory=dict) # block_name -> Ψ upon entry
    observable_effects: list[str] = field(default_factory=list)   # Observable external action trace Σ
    value_lineage: dict[str, tuple[str, ...]] = field(default_factory=dict) # var_name -> concrete provenance
    protocol_violations: list[str] = field(default_factory=list)
    status: str = "Running"                                       # "Running" | "Terminated" | "SuspendedWaiting" | "ProtocolViolation"
    return_value: Any = None


# ---------------------------------------------------------------------
# Static CFG Dataflow & Type Join Analyzer (J1 & J2)
# ---------------------------------------------------------------------

@dataclass
class AnalysisResult:
    block_in_facts: dict[str, frozenset[Fact]]
    block_out_facts: dict[str, frozenset[Fact]]
    edge_facts: dict[tuple[str, str], frozenset[Fact]]
    derived_block_param_types: dict[str, list[Type]]


class CFGDataflowAnalyzer:
    """Computes static greatest fixed-point for must-facts Ψ across all CFG edges and derives block argument types."""
    def __init__(self, prog: CFGProgram):
        self.prog = prog

    def analyze(self) -> AnalysisResult:
        # 1. First pass: Collect instruction definitions, types, and latent metadata
        var_types: dict[str, Type] = {}
        var_latent: dict[str, LatentPostconditions] = {}

        for b in self.prog.blocks.values():
            for p in b.params:
                var_types[p.name] = p.val_type
            for inst in b.instructions:
                if isinstance(inst, (InstRead, InstInfer, InstVerify, InstAct)):
                    var_types[inst.dest.name] = inst.dest.val_type
                    var_latent[inst.dest.name] = inst.latent
                elif isinstance(inst, InstSpawnChild):
                    var_types[inst.dest.name] = ChildHandleType(inst.ok_type, inst.err_type, inst.may_effects)
                    var_latent[inst.dest.name] = inst.latent
                elif isinstance(inst, InstAssign):
                    var_types[inst.dest.name] = inst.dest.val_type
                    if isinstance(inst.source, Variable) and inst.source.name in var_latent:
                        var_latent[inst.dest.name] = var_latent[inst.source.name]
                elif isinstance(inst, InstAwaitHandle):
                    h_type = var_types.get(inst.handle.name)
                    if isinstance(h_type, ChildHandleType):
                        var_types[inst.dest.name] = ResultType(h_type.ok_type, h_type.err_type)

        # 2. Derive block argument types from ALL incoming predecessor edges (J2)
        derived_param_types: dict[str, list[Type]] = {}
        for b_name, b in self.prog.blocks.items():
            if b_name == self.prog.entry:
                derived_param_types[b_name] = [p.val_type for p in b.params]
                continue

            # Collect arguments from all predecessors
            preds = self._find_predecessors(b_name)
            if not preds:
                derived_param_types[b_name] = [p.val_type for p in b.params]
                continue

            derived_types: list[Type] = []
            for i, p in enumerate(b.params):
                incoming_arg_types = []
                for p_name, term in preds:
                    args = self._get_terminator_args_for_target(term, b_name)
                    if i < len(args):
                        arg = args[i]
                        if isinstance(arg, Variable):
                            arg_t = var_types.get(arg.name, p.val_type)
                        else:
                            arg_t = arg.val_type
                        incoming_arg_types.append(arg_t)

                if incoming_arg_types and all(isinstance(t, ChildHandleType) for t in incoming_arg_types):
                    # Check compatibility (R15)
                    first_h = incoming_arg_types[0]
                    for other_h in incoming_arg_types[1:]:
                        if not first_h.is_compatible_for_join(other_h):
                            raise TypeError(f"Incompatible handle types arriving at block '{b_name}' param '{p.name}': {first_h} vs {other_h}")
                    # J2: derive union of may-effects from all incoming predecessors
                    combined_effects = frozenset().union(*(t.may_effects for t in incoming_arg_types))
                    derived_h_type = ChildHandleType(first_h.ok_type, first_h.err_type, combined_effects)
                    derived_types.append(derived_h_type)
                    var_types[p.name] = derived_h_type
                elif incoming_arg_types:
                    # Validate all incoming types match
                    first_t = incoming_arg_types[0]
                    for other_t in incoming_arg_types[1:]:
                        if first_t != other_t:
                            raise TypeError(f"Type mismatch arriving at block '{b_name}' param '{p.name}': {first_t} vs {other_t}")
                    derived_types.append(first_t)
                    var_types[p.name] = first_t
                else:
                    derived_types.append(p.val_type)

            derived_param_types[b_name] = derived_types

        # 3. Worklist fixed-point analysis for path facts Ψ (J1)
        edge_facts: dict[tuple[str, str], frozenset[Fact]] = {}
        block_in_facts: dict[str, frozenset[Fact]] = {b_name: frozenset() for b_name in self.prog.blocks}
        block_out_facts: dict[str, frozenset[Fact]] = {b_name: frozenset() for b_name in self.prog.blocks}

        # Initialize reachable set and worklist
        worklist = deque([self.prog.entry])
        visited_blocks = set()

        while worklist:
            curr = worklist.popleft()
            block = self.prog.blocks[curr]
            in_facts = block_in_facts[curr]

            # Compute block out facts (instructions do not eagerly emit latent postconditions)
            out_facts = in_facts
            block_out_facts[curr] = out_facts

            # Transfer across terminator edges
            term = block.terminator
            succ_edges = self._compute_successor_edges(curr, term, out_facts, var_latent)

            for succ, facts_on_edge in succ_edges:
                edge_key = (curr, succ)
                edge_facts[edge_key] = facts_on_edge

                # Recompute Ψ_in(succ) as intersection of all active incoming edges (J1)
                incoming_to_succ = [edge_facts[(p_name, succ)]
                                    for p_name, _ in self._find_predecessors(succ)
                                    if (p_name, succ) in edge_facts]

                if incoming_to_succ:
                    new_succ_in = incoming_to_succ[0]
                    for inc in incoming_to_succ[1:]:
                        new_succ_in = new_succ_in & inc
                else:
                    new_succ_in = frozenset()

                # If fixed point changed or first visit, add to worklist
                if succ not in visited_blocks or new_succ_in != block_in_facts[succ]:
                    visited_blocks.add(succ)
                    block_in_facts[succ] = new_succ_in
                    if succ not in worklist:
                        worklist.append(succ)

        return AnalysisResult(
            block_in_facts=block_in_facts,
            block_out_facts=block_out_facts,
            edge_facts=edge_facts,
            derived_block_param_types=derived_param_types,
        )

    def _find_predecessors(self, target_name: str) -> list[tuple[str, Terminator]]:
        preds = []
        for b_name, b in self.prog.blocks.items():
            if target_name in self._get_terminator_targets(b.terminator):
                preds.append((b_name, b.terminator))
        return preds

    def _get_terminator_targets(self, term: Terminator) -> list[str]:
        if isinstance(term, TermBr):
            return [term.target]
        elif isinstance(term, TermCondBr):
            return [term.true_target, term.false_target]
        elif isinstance(term, TermSwitchResult):
            return [term.ok_target, term.err_target]
        elif isinstance(term, TermSwitchActOutcome):
            targets = [term.success_target, term.failure_target]
            if term.partial_target:
                targets.append(term.partial_target)
            if term.unknown_target:
                targets.append(term.unknown_target)
            return targets
        return []

    def _get_terminator_args_for_target(self, term: Terminator, target: str) -> tuple[Variable | Constant, ...]:
        if isinstance(term, TermBr) and term.target == target:
            return term.args
        elif isinstance(term, TermCondBr):
            if term.true_target == target:
                return term.true_args
            if term.false_target == target:
                return term.false_args
        elif isinstance(term, TermSwitchResult):
            if term.ok_target == target:
                return (term.ok_arg,)
            if term.err_target == target:
                return (term.err_arg,)
        elif isinstance(term, TermSwitchActOutcome):
            if term.success_target == target:
                return (term.success_arg,)
            if term.failure_target == target:
                return (term.failure_arg,)
            if term.partial_target == target and term.partial_arg:
                return (term.partial_arg,)
        return ()

    def _compute_successor_edges(self, src: str, term: Terminator,
                                 base_facts: frozenset[Fact],
                                 var_latent: dict[str, LatentPostconditions]) -> list[tuple[str, frozenset[Fact]]]:
        edges = []
        if isinstance(term, TermBr):
            target_block = self.prog.blocks[term.target]
            renaming = self._build_renaming(term.args, target_block.params)
            renamed = frozenset(f.rename(renaming) for f in base_facts)
            edges.append((term.target, renamed))

        elif isinstance(term, TermCondBr):
            t_block = self.prog.blocks[term.true_target]
            t_ren = self._build_renaming(term.true_args, t_block.params)
            t_facts = frozenset(f.rename(t_ren) for f in (base_facts | frozenset([Fact("IsTrue", (term.cond.name,))])))
            edges.append((term.true_target, t_facts))

            f_block = self.prog.blocks[term.false_target]
            f_ren = self._build_renaming(term.false_args, f_block.params)
            f_facts = frozenset(f.rename(f_ren) for f in (base_facts | frozenset([Fact("IsFalse", (term.cond.name,))])))
            edges.append((term.false_target, f_facts))

        elif isinstance(term, TermSwitchResult):
            latent = var_latent.get(term.result_var.name, LatentPostconditions())
            ok_block = self.prog.blocks[term.ok_target]
            ok_ren = self._build_renaming((term.ok_arg,), ok_block.params)
            ok_facts = frozenset(f.rename(ok_ren) for f in (
                base_facts | frozenset([Fact("IsOk", (term.result_var.name,))]) | latent.instantiate_ok(term.ok_arg.name)
            ))
            edges.append((term.ok_target, ok_facts))

            err_block = self.prog.blocks[term.err_target]
            err_ren = self._build_renaming((term.err_arg,), err_block.params)
            err_facts = frozenset(f.rename(err_ren) for f in (
                base_facts | frozenset([Fact("IsErr", (term.result_var.name,))]) | latent.instantiate_err(term.err_arg.name)
            ))
            edges.append((term.err_target, err_facts))

        elif isinstance(term, TermSwitchActOutcome):
            latent = var_latent.get(term.outcome_var.name, LatentPostconditions())
            s_block = self.prog.blocks[term.success_target]
            s_ren = self._build_renaming((term.success_arg,), s_block.params)
            s_facts = frozenset(f.rename(s_ren) for f in (
                base_facts | frozenset([Fact("IsSuccess", (term.outcome_var.name,))]) | latent.instantiate_ok(term.success_arg.name)
            ))
            edges.append((term.success_target, s_facts))

            fl_block = self.prog.blocks[term.failure_target]
            fl_ren = self._build_renaming((term.failure_arg,), fl_block.params)
            fl_facts = frozenset(f.rename(fl_ren) for f in (
                base_facts | frozenset([Fact("IsFailure", (term.outcome_var.name,))]) | latent.instantiate_err(term.failure_arg.name)
            ))
            edges.append((term.failure_target, fl_facts))

            if term.partial_target and term.partial_arg:
                p_block = self.prog.blocks[term.partial_target]
                p_ren = self._build_renaming((term.partial_arg,), p_block.params)
                p_facts = frozenset(f.rename(p_ren) for f in (
                    base_facts | frozenset([Fact("IsPartial", (term.outcome_var.name,))]) | latent.instantiate_partial(term.partial_arg.name)
                ))
                edges.append((term.partial_target, p_facts))

            if term.unknown_target:
                u_facts = base_facts | frozenset([Fact("IsUnknown", (term.outcome_var.name,))])
                edges.append((term.unknown_target, u_facts))

        return edges

    def _build_renaming(self, args: tuple[Variable | Constant, ...], params: list[Variable]) -> dict[str, str]:
        renaming = {}
        for i, p in enumerate(params):
            if i < len(args) and isinstance(args[i], Variable):
                renaming[args[i].name] = p.name
        return renaming


# ---------------------------------------------------------------------
# Dynamic CFG Execution Interpreter
# ---------------------------------------------------------------------

class CFGInterpreter:
    def __init__(self, prog: CFGProgram):
        self.prog = prog

    def execute(self, inputs: dict[str, Any], max_steps: int = 100) -> ExecutionState:
        """Run CFG program from entry block with input environment."""
        state = ExecutionState(current_block=self.prog.entry)
        for k, v in inputs.items():
            state.env[k] = v

        entry_block = self.prog.blocks.get(self.prog.entry)
        if not entry_block:
            raise CFGExecutionError(f"Entry block '{self.prog.entry}' not found")

        for param in entry_block.params:
            if param.name in inputs:
                state.var_types[param.name] = param.val_type

        step = 0
        while state.status == "Running" and step < max_steps:
            step += 1
            curr_block = self.prog.blocks.get(state.current_block)
            if not curr_block:
                raise CFGExecutionError(f"Block '{state.current_block}' not found")

            # Execute block instructions
            for inst in curr_block.instructions:
                self._exec_instruction(inst, state)
                if state.status != "Running":
                    break

            if state.status != "Running":
                break

            # Execute terminator
            self._exec_terminator(curr_block.terminator, state)

        return state

    def _exec_instruction(self, inst: Instruction, state: ExecutionState) -> None:
        if isinstance(inst, InstAssign):
            dest_name = inst.dest.name
            state.var_types[dest_name] = inst.dest.val_type
            if isinstance(inst.source, Variable):
                val = state.env.get(inst.source.name)
                state.env[dest_name] = val
                if inst.source.name in state.var_latent:
                    state.var_latent[dest_name] = state.var_latent[inst.source.name]
                if inst.source.name in state.value_lineage:
                    state.value_lineage[dest_name] = state.value_lineage[inst.source.name]
            elif isinstance(inst.source, Constant):
                state.env[dest_name] = inst.source.val
                if hasattr(inst.source.val, "latent"):
                    state.var_latent[dest_name] = inst.source.val.latent

        elif isinstance(inst, InstRead):
            dest_name = inst.dest.name
            state.var_types[dest_name] = inst.dest.val_type
            val = state.env.get(dest_name)
            if val is None:
                val = OkVal(f"data_of({inst.target})", inst.dest.val_type, inst.latent)
                state.env[dest_name] = val
                state.var_latent[dest_name] = inst.latent
            else:
                val_lat = getattr(val, "latent", None)
                state.var_latent[dest_name] = val_lat if (val_lat and (val_lat.on_ok or val_lat.on_err or val_lat.on_partial)) else inst.latent
            state.value_lineage[dest_name] = (f"read({inst.target})",)

        elif isinstance(inst, InstInfer):
            dest_name = inst.dest.name
            state.var_types[dest_name] = inst.dest.val_type
            val = state.env.get(dest_name)
            if val is None:
                val = OkVal(f"infer_of({inst.query})", inst.dest.val_type, inst.latent)
                state.env[dest_name] = val
                state.var_latent[dest_name] = inst.latent
            else:
                val_lat = getattr(val, "latent", None)
                state.var_latent[dest_name] = val_lat if (val_lat and (val_lat.on_ok or val_lat.on_err or val_lat.on_partial)) else inst.latent
            state.value_lineage[dest_name] = (f"infer({inst.query})",)

        elif isinstance(inst, InstVerify):
            dest_name = inst.dest.name
            state.var_types[dest_name] = inst.dest.val_type
            val = state.env.get(dest_name)
            if val is None:
                val = OkVal(True, inst.dest.val_type, inst.latent)
                state.env[dest_name] = val
                state.var_latent[dest_name] = inst.latent
            else:
                val_lat = getattr(val, "latent", None)
                state.var_latent[dest_name] = val_lat if (val_lat and (val_lat.on_ok or val_lat.on_err or val_lat.on_partial)) else inst.latent
            state.value_lineage[dest_name] = (f"verify({inst.target})",)

        elif isinstance(inst, InstAct):
            dest_name = inst.dest.name
            state.var_types[dest_name] = inst.dest.val_type
            state.observable_effects.append(f"act({inst.op_id})")

            val = state.env.get(dest_name)
            if val is None:
                val = ActSuccessVal("action_ok", inst.dest.val_type, inst.latent)
                state.env[dest_name] = val
                state.var_latent[dest_name] = inst.latent
            else:
                val_lat = getattr(val, "latent", None)
                state.var_latent[dest_name] = val_lat if (val_lat and (val_lat.on_ok or val_lat.on_err or val_lat.on_partial)) else inst.latent

            # Track C: Check transactional contract violation
            if inst.is_atomic and isinstance(val, ActPartialVal):
                state.protocol_violations.append(f"TransactionalAdapterYieldedPartial({inst.op_id})")
                state.status = "ProtocolViolation"
                return

            state.value_lineage[dest_name] = (f"act({inst.op_id})",)

        elif isinstance(inst, InstSpawnChild):
            dest_name = inst.dest.name
            handle_type = ChildHandleType(inst.ok_type, inst.err_type, inst.may_effects)
            state.var_types[dest_name] = handle_type
            val = state.env.get(dest_name)
            if val is None:
                val = ChildHandleVal(
                    handle_id=f"handle:{inst.child_id}",
                    ok_type=inst.ok_type,
                    err_type=inst.err_type,
                    may_effects=inst.may_effects,
                    actual_provenance=(f"exec({inst.child_id})",),
                    result_val=OkVal("child_success", inst.ok_type, inst.latent),
                )
                state.env[dest_name] = val
            state.value_lineage[dest_name] = val.actual_provenance

        elif isinstance(inst, InstAwaitHandle):
            dest_name = inst.dest.name
            handle_val = state.env.get(inst.handle.name)
            if not isinstance(handle_val, ChildHandleVal):
                raise CFGExecutionError(f"Await on non-handle variable '{inst.handle.name}': {handle_val}")

            # Track B: Await suspends if settlement is unknown
            if handle_val.settlement_state == "SettlementUnknown":
                state.status = "SuspendedWaiting"
                return

            # Track D (R16): Await has ZERO observable effect addition (Σ_await = ∅)
            # Track D (R17): Provenance reflects child's actual execution, NOT handle's may-effects union!
            state.value_lineage[dest_name] = handle_val.actual_provenance
            res = handle_val.result_val or OkVal("await_ok", handle_val.ok_type)
            state.env[dest_name] = res
            state.var_types[dest_name] = ResultType(handle_val.ok_type, handle_val.err_type)
            if hasattr(res, "latent"):
                state.var_latent[dest_name] = res.latent

    def _exec_terminator(self, term: Terminator, state: ExecutionState) -> None:
        if isinstance(term, TermReturn):
            state.status = "Terminated"
            if term.value:
                state.return_value = state.env.get(term.value.name) if isinstance(term.value, Variable) else term.value.val

        elif isinstance(term, TermUnreachable):
            state.status = "ProtocolViolation"
            state.protocol_violations.append("EnteredUnreachableBlock")

        elif isinstance(term, TermBr):
            self._transfer_control(
                src_block=state.current_block,
                target_block=term.target,
                args=term.args,
                refinement_facts=frozenset(),
                state=state,
            )

        elif isinstance(term, TermCondBr):
            cond_val = state.env.get(term.cond.name)
            if cond_val:
                self._transfer_control(
                    src_block=state.current_block,
                    target_block=term.true_target,
                    args=term.true_args,
                    refinement_facts=frozenset([Fact("IsTrue", (term.cond.name,))]),
                    state=state,
                )
            else:
                self._transfer_control(
                    src_block=state.current_block,
                    target_block=term.false_target,
                    args=term.false_args,
                    refinement_facts=frozenset([Fact("IsFalse", (term.cond.name,))]),
                    state=state,
                )

        elif isinstance(term, TermSwitchResult):
            # Track A: Refinement on Result<T,E>
            res_val = state.env.get(term.result_var.name)
            latent = state.var_latent.get(term.result_var.name, LatentPostconditions())

            if isinstance(res_val, OkVal):
                unwrapped_val = res_val.value
                val_sym = term.ok_arg.name
                ok_facts = frozenset([Fact("IsOk", (term.result_var.name,))]) | latent.instantiate_ok(val_sym)
                self._transfer_control(
                    src_block=state.current_block,
                    target_block=term.ok_target,
                    args=(Constant(unwrapped_val, term.ok_arg.val_type),),
                    refinement_facts=ok_facts,
                    state=state,
                    extra_env={val_sym: unwrapped_val},
                )
            elif isinstance(res_val, ErrVal):
                unwrapped_err = res_val.error
                err_sym = term.err_arg.name
                err_facts = frozenset([Fact("IsErr", (term.result_var.name,))]) | latent.instantiate_err(err_sym)
                self._transfer_control(
                    src_block=state.current_block,
                    target_block=term.err_target,
                    args=(Constant(unwrapped_err, term.err_arg.val_type),),
                    refinement_facts=err_facts,
                    state=state,
                    extra_env={err_sym: unwrapped_err},
                )
            else:
                raise CFGExecutionError(f"SwitchResult on non-Result value: {res_val}")

        elif isinstance(term, TermSwitchActOutcome):
            # Tracks B & C: Refinement on ActOutcome (Success, Failure, Partial, Unknown)
            outcome_val = state.env.get(term.outcome_var.name)
            latent = state.var_latent.get(term.outcome_var.name, LatentPostconditions())

            if isinstance(outcome_val, ActSuccessVal):
                val_sym = term.success_arg.name
                succ_facts = frozenset([Fact("IsSuccess", (term.outcome_var.name,))]) | latent.instantiate_ok(val_sym)
                self._transfer_control(
                    src_block=state.current_block,
                    target_block=term.success_target,
                    args=(Constant(outcome_val.value, term.success_arg.val_type),),
                    refinement_facts=succ_facts,
                    state=state,
                    extra_env={val_sym: outcome_val.value},
                )
            elif isinstance(outcome_val, ActFailureVal):
                err_sym = term.failure_arg.name
                fail_facts = frozenset([Fact("IsFailure", (term.outcome_var.name,))]) | latent.instantiate_err(err_sym)
                self._transfer_control(
                    src_block=state.current_block,
                    target_block=term.failure_target,
                    args=(Constant(outcome_val.error, term.failure_arg.val_type),),
                    refinement_facts=fail_facts,
                    state=state,
                    extra_env={err_sym: outcome_val.error},
                )
            elif isinstance(outcome_val, ActPartialVal):
                if term.partial_target is None or term.partial_arg is None:
                    raise CFGExecutionError("ActPartialVal received but no partial_target defined in SwitchActOutcome")
                part_sym = term.partial_arg.name
                part_facts = frozenset([Fact("IsPartial", (term.outcome_var.name,))]) | latent.instantiate_partial(part_sym)
                self._transfer_control(
                    src_block=state.current_block,
                    target_block=term.partial_target,
                    args=(Constant(outcome_val.report, term.partial_arg.val_type),),
                    refinement_facts=part_facts,
                    state=state,
                    extra_env={part_sym: outcome_val.report},
                )
            elif isinstance(outcome_val, (DeliveryUnknownVal, SettlementUnknownVal)):
                if term.unknown_target is not None:
                    self._transfer_control(
                        src_block=state.current_block,
                        target_block=term.unknown_target,
                        args=(),
                        refinement_facts=frozenset([Fact("IsUnknown", (term.outcome_var.name,))]),
                        state=state,
                    )
                else:
                    state.status = "SuspendedWaiting"

    def _transfer_control(self, src_block: str, target_block: str,
                          args: tuple[Variable | Constant, ...],
                          refinement_facts: frozenset[Fact],
                          state: ExecutionState,
                          extra_env: dict[str, Any] | None = None) -> None:
        """Transfer control across basic blocks with block argument binding and fact merging."""
        target = self.prog.blocks.get(target_block)
        if not target:
            raise CFGExecutionError(f"Target block '{target_block}' does not exist")

        renaming_map: dict[str, str] = {}
        new_env = dict(state.env)
        if extra_env:
            new_env.update(extra_env)

        for i, param in enumerate(target.params):
            if i < len(args):
                arg = args[i]
                if isinstance(arg, Variable):
                    val = state.env.get(arg.name)
                    new_env[param.name] = val
                    renaming_map[arg.name] = param.name
                    src_type = state.var_types.get(arg.name, param.val_type)
                    if isinstance(src_type, ChildHandleType) and isinstance(param.val_type, ChildHandleType):
                        state.var_types[param.name] = param.val_type.join(src_type)
                    else:
                        state.var_types[param.name] = param.val_type
                    if arg.name in state.value_lineage:
                        state.value_lineage[param.name] = state.value_lineage[arg.name]
                    if arg.name in state.var_latent:
                        state.var_latent[param.name] = state.var_latent[arg.name]
                elif isinstance(arg, Constant):
                    new_env[param.name] = arg.val
                    state.var_types[param.name] = arg.val_type

        renamed_pred_facts = frozenset(f.rename(renaming_map) for f in state.psi)
        outgoing_facts = renamed_pred_facts | refinement_facts

        if target_block in state.block_entry_psi:
            prior_psi = state.block_entry_psi[target_block]
            merged_psi = prior_psi & outgoing_facts
        else:
            merged_psi = outgoing_facts

        state.block_entry_psi[target_block] = merged_psi
        state.psi = merged_psi
        state.env = new_env
        state.current_block = target_block
