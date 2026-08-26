"""cfg_model.py — Executable Lowered CFG Interpreter & Path Fact Analyzer for SOMA-IR Item 3.

Implements:
1. SSA Environment & Block Argument Passing (no phi nodes)
2. Latent Postcondition Refinement on SwitchResult & SwitchActOutcome (Track A)
3. Must-Fact Intersection Merge at CFG Join Points (with SSA symbol renaming)
4. Settlement & Physical Ambiguity Handling (Track B)
5. Partial Completion Distinguishability & Transactional Rejection (Track C)
6. ChildHandle May-Effect Join, Await Effect Neutrality, and Concrete Lineage (Track D)
"""
from __future__ import annotations

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

        # Map entry parameters
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
            # Runtime handle carrying concrete execution provenance
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
                # Materialize on_ok postconditions bound to unwrapped SSA symbol
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
                    # Track B: Unknown cannot collapse to clean Err; frame suspends
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

        # 1. Bind block arguments and build SSA symbol renaming map
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
                    # Type transfer / join (Track D)
                    src_type = state.var_types.get(arg.name, param.val_type)
                    if isinstance(src_type, ChildHandleType) and isinstance(param.val_type, ChildHandleType):
                        # Join may-effects
                        state.var_types[param.name] = param.val_type.join(src_type)
                    else:
                        state.var_types[param.name] = param.val_type
                    # Lineage transfer
                    if arg.name in state.value_lineage:
                        state.value_lineage[param.name] = state.value_lineage[arg.name]
                    # Latent postcondition transfer (R06)
                    if arg.name in state.var_latent:
                        state.var_latent[param.name] = state.var_latent[arg.name]
                elif isinstance(arg, Constant):
                    new_env[param.name] = arg.val
                    state.var_types[param.name] = arg.val_type

        # 2. Path Facts (Ψ) propagation & renaming (Track A)
        # Rename outgoing predecessor facts to match new block argument symbols
        renamed_pred_facts = frozenset(f.rename(renaming_map) for f in state.psi)
        outgoing_facts = renamed_pred_facts | refinement_facts

        # Must-Fact Merge (R04/R05):
        # If target block was already visited from another predecessor, compute intersection!
        if target_block in state.block_entry_psi:
            prior_psi = state.block_entry_psi[target_block]
            merged_psi = prior_psi & outgoing_facts  # Strict intersection merge
        else:
            merged_psi = outgoing_facts

        state.block_entry_psi[target_block] = merged_psi
        state.psi = merged_psi
        state.env = new_env
        state.current_block = target_block
