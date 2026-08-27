use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

use crate::{
    ir::{
        effects::Effect,
        ops::{Instruction, RegionTerminator, Terminator},
        types::Type,
        Function, Module,
    },
    registry::RegistrySnapshot,
    vm_ir::{VmBlock, VmBlockId, VmFunction, VmInstruction, VmModule, VmTerminator, VmValueId},
};

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct CompilerMutations {
    // Slice 1 mutations
    #[serde(default)]
    pub m01_drop_err_edge: bool,
    #[serde(default)]
    pub m02_swap_ok_err_targets: bool,
    #[serde(default)]
    pub m03_corrupt_block_arg_type: bool,
    #[serde(default)]
    pub m04_drop_latent_metadata: bool,
    #[serde(default)]
    pub m05_eager_on_ok_materialization: bool,
    #[serde(default)]
    pub m06_merge_union_facts: bool,
    #[serde(default)]
    pub m07_drop_read_effect: bool,
    #[serde(default)]
    pub m08_drop_infer_effect: bool,
    #[serde(default)]
    pub m09_stale_source_value_id: bool,
    #[serde(default)]
    pub m10_single_pass_loop_analysis: bool,

    // Slice 2 mutations (S2M01–S2M16)
    #[serde(default)]
    pub s2m01_verifier_out_of_envelope: bool,
    #[serde(default)]
    pub s2m02_drop_verifier_effect: bool,
    #[serde(default)]
    pub s2m03_trust_arbitrary_issuer: bool,
    #[serde(default)]
    pub s2m04_deferred_treated_as_proved: bool,
    #[serde(default)]
    pub s2m05_gate_rejection_still_invokes_target: bool,
    #[serde(default)]
    pub s2m06_gate_effect_omitted_from_act: bool,
    #[serde(default)]
    pub s2m07_trusted_gate_requires_caller_authority: bool,
    #[serde(default)]
    pub s2m08_toctou_revalidation_omitted: bool,
    #[serde(default)]
    pub s2m09_footprint_enforcement_disabled: bool,
    #[serde(default)]
    pub s2m10_partial_collapsed_to_failure: bool,
    #[serde(default)]
    pub s2m11_unknown_collapsed_to_failure: bool,
    #[serde(default)]
    pub s2m12_success_fact_on_partial: bool,
    #[serde(default)]
    pub s2m13_atomic_adapter_partial_accepted: bool,
    #[serde(default)]
    pub s2m14_current_facts_not_invalidated: bool,
    #[serde(default)]
    pub s2m15_historical_facts_invalidated: bool,
    #[serde(default)]
    pub s2m16_untrusted_attestation_accepted: bool,

    // Slice 3 mutations (S3M01–S3M24)
    #[serde(default)]
    pub s3m01_drop_delegate_child_effect: bool,
    #[serde(default)]
    pub s3m02_allow_requested_below_child: bool,
    #[serde(default)]
    pub s3m03_allow_requested_above_exported: bool,
    #[serde(default)]
    pub s3m04_native_authority_unattenuated: bool,
    #[serde(default)]
    pub s3m05_granted_authority_unattenuated: bool,
    #[serde(default)]
    pub s3m06_child_runtime_allows_out_of_ceiling: bool,
    #[serde(default)]
    pub s3m07_delegation_shadow_reservation: bool,
    #[serde(default)]
    pub s3m08_spawn_failure_budget_debited: bool,
    #[serde(default)]
    pub s3m09_duplicate_settlement_refunds_twice: bool,
    #[serde(default)]
    pub s3m10_settlement_with_commitments_allowed: bool,
    #[serde(default)]
    pub s3m11_child_spent_copied_to_parent: bool,
    #[serde(default)]
    pub s3m12_nested_delegation_breaks_conservation: bool,
    #[serde(default)]
    pub s3m13_await_reattributes_child_effects: bool,
    #[serde(default)]
    pub s3m14_await_returns_result_on_settlement_unknown: bool,
    #[serde(default)]
    pub s3m15_parent_generation_validation_omitted: bool,
    #[serde(default)]
    pub s3m16_handle_join_drops_effect: bool,
    #[serde(default)]
    pub s3m17_handle_join_invents_provenance: bool,
    #[serde(default)]
    pub s3m18_duplicate_await_duplicate_settlement: bool,
    #[serde(default)]
    pub s3m19_internalize_uses_runtime_authority: bool,
    #[serde(default)]
    pub s3m20_failed_validation_constructs_belief: bool,
    #[serde(default)]
    pub s3m21_failed_internalize_materializes_fact: bool,
    #[serde(default)]
    pub s3m22_received_belief_reowned: bool,
    #[serde(default)]
    pub s3m23_delegated_provenance_removed_on_internalize: bool,
    #[serde(default)]
    pub s3m24_effect_summary_used_as_clean_provenance: bool,

    // Slice 4 mutations (S4M01–S4M20)
    #[serde(default)]
    pub s4m01_scheduler_pops_unaffordable_node: bool,
    #[serde(default)]
    pub s4m02_policy_hidden_effect_allowed: bool,
    #[serde(default)]
    pub s4m03_ranking_promotes_satisfied: bool,
    #[serde(default)]
    pub s4m04_stage_rejected_leaves_reservation: bool,
    #[serde(default)]
    pub s4m05_first_emit_fails_step: bool,
    #[serde(default)]
    pub s4m06_transport_retry_increments_step: bool,
    #[serde(default)]
    pub s4m07_transport_retry_changes_request_id: bool,
    #[serde(default)]
    pub s4m08_second_unsettled_request_allowed: bool,
    #[serde(default)]
    pub s4m09_delivery_unknown_releases_commitment: bool,
    #[serde(default)]
    pub s4m10_duplicate_completion_applies_twice: bool,
    #[serde(default)]
    pub s4m11_duplicate_settlement_reconciles_twice: bool,
    #[serde(default)]
    pub s4m12_settlement_marks_applied_automatically: bool,
    #[serde(default)]
    pub s4m13_crash_after_settlement_loses_semantic_result: bool,
    #[serde(default)]
    pub s4m14_closing_accepts_late_payload: bool,
    #[serde(default)]
    pub s4m15_closing_mutates_frontier: bool,
    #[serde(default)]
    pub s4m16_terminalizes_with_commitment: bool,
    #[serde(default)]
    pub s4m17_budget_scope_mints_ownership: bool,
    #[serde(default)]
    pub s4m18_requeue_reuses_request_id: bool,
    #[serde(default)]
    pub s4m19_failed_requeue_incorporates_successors: bool,
    #[serde(default)]
    pub s4m20_satisfaction_retry_bypasses_attempt_ceiling: bool,
}

pub struct LoweringContext {
    pub mutations: CompilerMutations,
    pub registry: Option<RegistrySnapshot>,
    pub value_map: BTreeMap<crate::ir::ValueId, VmValueId>,
    pub block_map: BTreeMap<crate::ir::BlockId, VmBlockId>,
    pub next_block_id: u32,
    pub next_value_id: u32,
    pub value_types: BTreeMap<crate::ir::ValueId, Type>,
}

impl LoweringContext {
    pub fn new() -> Self {
        Self {
            mutations: CompilerMutations::default(),
            registry: None,
            value_map: BTreeMap::new(),
            block_map: BTreeMap::new(),
            next_block_id: 100,
            next_value_id: 5000,
            value_types: BTreeMap::new(),
        }
    }

    pub fn with_mutations(mutations: CompilerMutations) -> Self {
        Self {
            mutations,
            registry: None,
            value_map: BTreeMap::new(),
            block_map: BTreeMap::new(),
            next_block_id: 100,
            next_value_id: 5000,
            value_types: BTreeMap::new(),
        }
    }

    pub fn with_registry(registry: RegistrySnapshot, mutations: CompilerMutations) -> Self {
        Self {
            mutations,
            registry: Some(registry),
            value_map: BTreeMap::new(),
            block_map: BTreeMap::new(),
            next_block_id: 100,
            next_value_id: 5000,
            value_types: BTreeMap::new(),
        }
    }

    pub fn map_value(&mut self, val: crate::ir::ValueId) -> VmValueId {
        *self
            .value_map
            .entry(val)
            .or_insert_with(|| VmValueId(val.0))
    }

    pub fn alloc_value(&mut self) -> VmValueId {
        let id = VmValueId(self.next_value_id);
        self.next_value_id += 1;
        id
    }

    pub fn map_block(&mut self, block: crate::ir::BlockId) -> VmBlockId {
        *self
            .block_map
            .entry(block)
            .or_insert_with(|| VmBlockId(block.0))
    }

    pub fn alloc_block(&mut self) -> VmBlockId {
        let id = VmBlockId(self.next_block_id);
        self.next_block_id += 1;
        id
    }

    pub fn lower_module(&mut self, module: &Module) -> VmModule {
        let mut vm_module = VmModule::new(module.name.clone());
        for func in &module.functions {
            vm_module.functions.push(self.lower_function(func));
        }
        vm_module
    }

    pub fn lower_function(&mut self, func: &Function) -> VmFunction {
        // Collect value types
        for (p_id, p_ty) in &func.params {
            self.value_types.insert(*p_id, p_ty.clone());
        }
        for block in func.blocks.values() {
            for (p_id, p_ty) in &block.params {
                self.value_types.insert(*p_id, p_ty.clone());
            }
            for inst in &block.instructions {
                match inst {
                    Instruction::Pure { dest, ty, .. } => {
                        self.value_types.insert(*dest, ty.clone());
                    }
                    Instruction::Read {
                        dest,
                        ok_type,
                        err_type,
                        ..
                    } => {
                        self.value_types
                            .insert(*dest, Type::result(ok_type.clone(), err_type.clone()));
                    }
                    Instruction::Infer {
                        dest,
                        ok_type,
                        err_type,
                        ..
                    } => {
                        self.value_types
                            .insert(*dest, Type::result(ok_type.clone(), err_type.clone()));
                    }
                    Instruction::Assign { dest, ty, .. } => {
                        self.value_types.insert(*dest, ty.clone());
                    }
                    Instruction::Verify {
                        dest,
                        verifier_id,
                        output_predicate,
                        subject_type,
                        ..
                    } => {
                        let (out_p, subj_t) = if let Some(reg) = &self.registry {
                            if let Some(desc) = reg.verifiers.get(verifier_id) {
                                (desc.output_predicate.clone(), desc.subject_type.clone())
                            } else {
                                (output_predicate.clone(), subject_type.clone())
                            }
                        } else {
                            (output_predicate.clone(), subject_type.clone())
                        };
                        let att_ty = Type::attestation(out_p, subj_t);
                        self.value_types
                            .insert(*dest, Type::result(att_ty, Type::String));
                    }
                    Instruction::Act {
                        dest,
                        success_type,
                        failure_type,
                        ..
                    } => {
                        self.value_types.insert(
                            *dest,
                            Type::act_outcome(success_type.clone(), failure_type.clone()),
                        );
                    }
                    Instruction::Delegate {
                        dest, intent_id, ..
                    } => {
                        let reg = self
                            .registry
                            .as_ref()
                            .expect("Lowering Delegate requires RegistrySnapshot");
                        let desc = reg.intents.get(intent_id).expect("Unknown intent");
                        self.value_types.insert(
                            *dest,
                            Type::child_handle(
                                desc.output_type.clone(),
                                desc.error_type.clone(),
                                desc.child_effects.clone(),
                            ),
                        );
                    }
                    Instruction::Await { dest, handle } => {
                        let handle_ty = self.value_types.get(handle).cloned();
                        if let Some(Type::ChildHandle { ok, err, .. }) = handle_ty {
                            self.value_types.insert(*dest, Type::result(*ok, *err));
                        } else {
                            self.value_types
                                .insert(*dest, Type::result(Type::String, Type::String));
                        }
                    }
                    Instruction::Internalize { dest, claim, .. } => {
                        let claim_ty = self.value_types.get(claim).cloned();
                        if let Some(Type::Claim(payload)) = claim_ty {
                            self.value_types
                                .insert(*dest, Type::result(Type::belief(*payload), Type::String));
                        } else {
                            self.value_types.insert(
                                *dest,
                                Type::result(Type::belief(Type::String), Type::String),
                            );
                        }
                    }
                    Instruction::Converge {
                        dest,
                        satisfied_type,
                        partial_type,
                        ..
                    } => {
                        let outcome_ty = Type::convergence_outcome(
                            satisfied_type.clone(),
                            Type::exhaustion_report(partial_type.clone()),
                        );
                        self.value_types
                            .insert(*dest, Type::result(outcome_ty, Type::String));
                    }
                }
            }
        }

        let entry_id = self.map_block(func.entry);
        let mut vm_func = VmFunction::new(func.name.clone(), entry_id, func.return_type.clone());

        // R2: Preserve effect row in VM IR (unless mutated)
        let mut effects = func.declared_effects.clone();
        if self.mutations.m07_drop_read_effect {
            effects.effects.retain(|e| !matches!(e, Effect::Read(_)));
        }
        if self.mutations.m08_drop_infer_effect {
            effects.effects.retain(|e| !matches!(e, Effect::Infer));
        }
        vm_func.declared_effects = effects;

        for (param_id, param_ty) in &func.params {
            let vm_param_id = self.map_value(*param_id);
            vm_func.params.push((vm_param_id, param_ty.clone()));
        }

        // Lower blocks and structured regions
        let mut generated_blocks = BTreeMap::new();

        for (block_id, block) in &func.blocks {
            let vm_block_id = self.map_block(*block_id);
            let mut vm_block = VmBlock::new(vm_block_id, VmTerminator::Unreachable);
            vm_block.name = block.name.clone();

            if block_id != &func.entry {
                for (param_id, param_ty) in &block.params {
                    let vm_param_id = self.map_value(*param_id);
                    vm_block.params.push((vm_param_id, param_ty.clone()));
                }
            }

            if let Some(pos) = block
                .instructions
                .iter()
                .position(|i| matches!(i, Instruction::Converge { .. }))
            {
                // Lower instructions before Converge into current block
                self.lower_instruction_sequence(
                    &block.instructions[..pos],
                    &mut vm_block.instructions,
                );

                if let Instruction::Converge {
                    dest,
                    root_node,
                    initial_frontier,
                    successors,
                    node_ops,
                    satisfier,
                    partial_map,
                    space_faults,
                    fault_spec,
                    search_policy,
                    budget_scope,
                    max_steps,
                    max_satisfaction_attempts,
                    space_effects,
                    satisfier_effects,
                    partial_type,
                    satisfied_type,
                    ..
                } = &block.instructions[pos]
                {
                    let vm_dest = self.map_value(*dest);
                    let frame_var = self.alloc_value();
                    let step_status_var = self.alloc_value();
                    let handle_var = self.alloc_value();
                    let loop_header_id = self.alloc_block();
                    let tx_body_id = self.alloc_block();
                    let exit_block_id = self.alloc_block();

                    vm_block.instructions.push(VmInstruction::VmConvergeInit {
                        frame_var,
                        root_node: root_node.clone(),
                        initial_frontier: if initial_frontier.is_empty() {
                            vec![root_node.clone()]
                        } else {
                            initial_frontier.clone()
                        },
                        budget_resource: budget_scope.resource.clone(),
                        budget_limit: budget_scope.limit,
                        max_steps: *max_steps,
                        max_satisfaction_attempts: *max_satisfaction_attempts,
                        on_step_failure: search_policy.on_step_failure.clone(),
                        on_satisfier_error: search_policy.on_satisfier_error.clone(),
                    });
                    vm_block.terminator = VmTerminator::Br {
                        target: loop_header_id,
                        args: Vec::new(),
                    };
                    generated_blocks.insert(vm_block_id, vm_block);

                    // 1. Loop Header Block (Scheduler Decision only)
                    let mut loop_block = VmBlock::new(loop_header_id, VmTerminator::Unreachable);
                    loop_block.name = Some("converge_step_loop".to_string());
                    loop_block.instructions.push(VmInstruction::VmConvergeStep {
                        dest: step_status_var,
                        frame_var,
                        successors: successors.clone(),
                        node_ops: node_ops.clone(),
                        satisfier: satisfier.clone(),
                        partial_map: partial_map
                            .iter()
                            .map(|(k, v)| (k.clone(), v.clone()))
                            .collect(),
                        space_faults: space_faults.clone(),
                        fault_spec: fault_spec.clone(),
                        space_effects: space_effects.effects.iter().cloned().collect(),
                        satisfier_effects: satisfier_effects.effects.iter().cloned().collect(),
                    });
                    loop_block.terminator = VmTerminator::CondBr {
                        cond: step_status_var,
                        true_target: tx_body_id,
                        true_args: Vec::new(),
                        false_target: exit_block_id,
                        false_args: Vec::new(),
                    };
                    generated_blocks.insert(loop_header_id, loop_block);

                    // 2. Action Execution Block (Discrete Local Execution & Transactional External Lifecycle)
                    let mut tx_block = VmBlock::new(tx_body_id, VmTerminator::Unreachable);
                    tx_block.name = Some("converge_action_body".to_string());
                    tx_block
                        .instructions
                        .push(VmInstruction::VmConvergeDispatchLocal {
                            frame_var,
                            successors: successors.clone(),
                        });
                    tx_block
                        .instructions
                        .push(VmInstruction::VmConvergeCheckSatisfactionLocal {
                            frame_var,
                            satisfier: satisfier.clone(),
                        });
                    tx_block.instructions.push(VmInstruction::VmConvergeStage {
                        handle_dest: handle_var,
                        frame_var,
                        node_ops: node_ops.clone(),
                        satisfier: satisfier.clone(),
                        fault_spec: fault_spec.clone(),
                    });
                    tx_block.instructions.push(VmInstruction::VmConvergeEmit {
                        frame_var,
                        handle_var,
                        node_ops: node_ops.clone(),
                        satisfier: satisfier.clone(),
                        fault_spec: fault_spec.clone(),
                        space_effects: space_effects.effects.iter().cloned().collect(),
                        satisfier_effects: satisfier_effects.effects.iter().cloned().collect(),
                    });
                    tx_block
                        .instructions
                        .push(VmInstruction::VmConvergeAdmitCompletion {
                            frame_var,
                            handle_var,
                            successors: successors.clone(),
                            node_ops: node_ops.clone(),
                            satisfier: satisfier.clone(),
                            space_faults: space_faults.clone(),
                            fault_spec: fault_spec.clone(),
                        });
                    tx_block.instructions.push(VmInstruction::VmConvergeSettle {
                        frame_var,
                        handle_var,
                        node_ops: node_ops.clone(),
                        satisfier: satisfier.clone(),
                        fault_spec: fault_spec.clone(),
                    });
                    tx_block.instructions.push(VmInstruction::VmConvergeApply {
                        frame_var,
                        handle_var,
                        fault_spec: fault_spec.clone(),
                    });
                    tx_block.terminator = VmTerminator::Br {
                        target: loop_header_id,
                        args: Vec::new(),
                    };
                    generated_blocks.insert(tx_body_id, tx_block);

                    // 3. Exit Block
                    let mut exit_block = VmBlock::new(exit_block_id, VmTerminator::Unreachable);
                    exit_block.name = Some("converge_exit".to_string());
                    exit_block.instructions.push(VmInstruction::VmConvergeFinish {
                        dest: vm_dest,
                        frame_var,
                        partial_type: partial_type.clone(),
                        satisfied_type: satisfied_type.clone(),
                    });
                    self.lower_instruction_sequence(
                        &block.instructions[pos + 1..],
                        &mut exit_block.instructions,
                    );
                    exit_block.terminator = self.lower_terminator(&block.terminator);
                    generated_blocks.insert(exit_block_id, exit_block);
                    continue;
                }
            }

            self.lower_instruction_sequence(&block.instructions, &mut vm_block.instructions);

            match &block.terminator {
                Terminator::MatchResult {
                    result_val,
                    ok_arg,
                    ok_body,
                    err_arg,
                    err_body,
                } => {
                    let ok_block_id = self.alloc_block();
                    let err_block_id = self.alloc_block();

                    let (ok_ty, err_ty) = match self.value_types.get(result_val) {
                        Some(Type::Result { ok, err }) => (*ok.clone(), *err.clone()),
                        _ => (Type::String, Type::String),
                    };

                    let vm_ok_arg = self.map_value(*ok_arg);
                    let vm_err_arg = self.map_value(*err_arg);

                    let mut ok_vm_block = VmBlock::new(ok_block_id, VmTerminator::Unreachable);
                    ok_vm_block.name = Some("ok_branch".to_string());
                    ok_vm_block.params.push((vm_ok_arg, ok_ty));
                    self.lower_instruction_sequence(&ok_body.instructions, &mut ok_vm_block.instructions);
                    ok_vm_block.terminator = self.lower_region_terminator(&ok_body.terminator);
                    generated_blocks.insert(ok_block_id, ok_vm_block);

                    let mut err_vm_block = VmBlock::new(err_block_id, VmTerminator::Unreachable);
                    err_vm_block.name = Some("err_branch".to_string());

                    let err_block_param_ty = if self.mutations.m03_corrupt_block_arg_type {
                        Type::I64
                    } else {
                        err_ty
                    };

                    err_vm_block.params.push((vm_err_arg, err_block_param_ty));
                    self.lower_instruction_sequence(&err_body.instructions, &mut err_vm_block.instructions);
                    err_vm_block.terminator = self.lower_region_terminator(&err_body.terminator);
                    generated_blocks.insert(err_block_id, err_vm_block);

                    let ok_target_id = if self.mutations.m02_swap_ok_err_targets {
                        err_block_id
                    } else {
                        ok_block_id
                    };
                    let err_target_id = if self.mutations.m01_drop_err_edge {
                        VmBlockId(9999)
                    } else if self.mutations.m02_swap_ok_err_targets {
                        ok_block_id
                    } else {
                        err_block_id
                    };

                    vm_block.terminator = VmTerminator::SwitchResult {
                        result_val: self.map_value(*result_val),
                        ok_target: ok_target_id,
                        ok_arg: vm_ok_arg,
                        err_target: err_target_id,
                        err_arg: vm_err_arg,
                    };
                }
                Terminator::MatchActOutcome {
                    outcome_val,
                    success_arg,
                    success_body,
                    failure_arg,
                    failure_body,
                    partial_arg,
                    partial_body,
                    unknown_arg,
                    unknown_body,
                } => {
                    let succ_block_id = self.alloc_block();
                    let fail_block_id = self.alloc_block();
                    let part_block_id = self.alloc_block();
                    let unk_block_id = self.alloc_block();

                    let (succ_ty, fail_ty) = match self.value_types.get(outcome_val) {
                        Some(Type::ActOutcome { success, failure }) => {
                            (*success.clone(), *failure.clone())
                        }
                        _ => (Type::String, Type::String),
                    };

                    let vm_succ_arg = self.map_value(*success_arg);
                    let vm_fail_arg = self.map_value(*failure_arg);
                    let vm_part_arg = self.map_value(*partial_arg);
                    let vm_unk_arg = self.map_value(*unknown_arg);

                    // 1. Success region
                    let mut succ_block = VmBlock::new(succ_block_id, VmTerminator::Unreachable);
                    succ_block.name = Some("success_branch".to_string());
                    succ_block.params.push((vm_succ_arg, succ_ty));
                    self.lower_instruction_sequence(&success_body.instructions, &mut succ_block.instructions);
                    succ_block.terminator = self.lower_region_terminator(&success_body.terminator);
                    generated_blocks.insert(succ_block_id, succ_block);

                    // 2. Failure region
                    let mut fail_block = VmBlock::new(fail_block_id, VmTerminator::Unreachable);
                    fail_block.name = Some("failure_branch".to_string());
                    fail_block.params.push((vm_fail_arg, fail_ty));
                    self.lower_instruction_sequence(&failure_body.instructions, &mut fail_block.instructions);
                    fail_block.terminator = self.lower_region_terminator(&failure_body.terminator);
                    generated_blocks.insert(fail_block_id, fail_block);

                    // 3. Partial region
                    let mut part_block = VmBlock::new(part_block_id, VmTerminator::Unreachable);
                    part_block.name = Some("partial_branch".to_string());
                    part_block.params.push((vm_part_arg, Type::PartialReport));
                    self.lower_instruction_sequence(&partial_body.instructions, &mut part_block.instructions);
                    part_block.terminator = self.lower_region_terminator(&partial_body.terminator);
                    generated_blocks.insert(part_block_id, part_block);

                    // 4. Unknown region
                    let mut unk_block = VmBlock::new(unk_block_id, VmTerminator::Unreachable);
                    unk_block.name = Some("unknown_branch".to_string());
                    unk_block.params.push((vm_unk_arg, Type::String));
                    self.lower_instruction_sequence(&unknown_body.instructions, &mut unk_block.instructions);
                    unk_block.terminator = self.lower_region_terminator(&unknown_body.terminator);
                    generated_blocks.insert(unk_block_id, unk_block);

                    vm_block.terminator = VmTerminator::SwitchActOutcome {
                        outcome_val: self.map_value(*outcome_val),
                        success_target: succ_block_id,
                        success_arg: vm_succ_arg,
                        failure_target: fail_block_id,
                        failure_arg: vm_fail_arg,
                        partial_target: part_block_id,
                        partial_arg: vm_part_arg,
                        unknown_target: unk_block_id,
                        unknown_arg: vm_unk_arg,
                    };
                }
                other => {
                    vm_block.terminator = self.lower_terminator(other);
                }
            }

            generated_blocks.insert(vm_block_id, vm_block);
        }

        vm_func.blocks = generated_blocks;
        vm_func
    }

    fn lower_instruction_sequence(
        &mut self,
        instructions: &[Instruction],
        target_vec: &mut Vec<VmInstruction>,
    ) {
        for inst in instructions {
            if !matches!(inst, Instruction::Converge { .. }) {
                target_vec.push(self.lower_instruction(inst));
            }
        }
    }

    fn lower_instruction(&mut self, inst: &Instruction) -> VmInstruction {
        match inst {
            Instruction::Pure { dest, val, ty } => VmInstruction::VmPure {
                dest: self.map_value(*dest),
                val: val.clone(),
                ty: ty.clone(),
            },
            Instruction::Read {
                dest,
                domain,
                ok_type,
                err_type,
                latent,
            } => {
                let lat = if self.mutations.m04_drop_latent_metadata {
                    crate::ir::facts::LatentPostconditions::empty()
                } else {
                    latent.clone()
                };
                VmInstruction::VmRead {
                    dest: self.map_value(*dest),
                    domain: domain.clone(),
                    ok_type: ok_type.clone(),
                    err_type: err_type.clone(),
                    latent: lat,
                }
            }
            Instruction::Infer {
                dest,
                prompt,
                ok_type,
                err_type,
                latent,
            } => VmInstruction::VmInfer {
                dest: self.map_value(*dest),
                prompt: prompt.clone(),
                ok_type: ok_type.clone(),
                err_type: err_type.clone(),
                latent: latent.clone(),
            },
            Instruction::Assign { dest, source, ty } => {
                let src = if self.mutations.m09_stale_source_value_id {
                    VmValueId(9999)
                } else {
                    self.map_value(*source)
                };
                VmInstruction::VmAssign {
                    dest: self.map_value(*dest),
                    source: src,
                    ty: ty.clone(),
                }
            }
            Instruction::Verify {
                dest,
                verifier_id,
                subject,
                ..
            } => {
                // Q1: Authoritative descriptor lookup in registry (fail-closed, no legacy fallback)
                let (out_p, subj_t, mut effs) = {
                    let reg = self.registry.as_ref().expect(
                        "Lowering Instruction::Verify requires an authenticated RegistrySnapshot",
                    );
                    let desc = reg.verifiers.get(verifier_id).unwrap_or_else(|| {
                        panic!(
                            "Lowering failed: VerifierId {:?} not found in trusted registry",
                            verifier_id
                        )
                    });
                    (
                        desc.output_predicate.clone(),
                        desc.subject_type.clone(),
                        desc.effect_envelope
                            .effects
                            .iter()
                            .cloned()
                            .collect::<Vec<_>>(),
                    )
                };

                if self.mutations.s2m02_drop_verifier_effect && !effs.is_empty() {
                    effs.pop();
                }

                let vm_dest = self.map_value(*dest);
                let vm_subject = self.map_value(*subject);

                VmInstruction::VmVerify {
                    dest: vm_dest,
                    verifier_id: verifier_id.clone(),
                    subject: vm_subject,
                    output_predicate: out_p,
                    subject_type: subj_t,
                    verifier_effects: effs,
                }
            }
            Instruction::Act {
                dest,
                op_id,
                success_type,
                failure_type,
                args,
                evidence,
                latent,
                ..
            } => {
                // Q1: Authoritative descriptor lookup in registry (fail-closed, no legacy fallback)
                let (target_d, effs) = {
                    let reg = self.registry.as_ref().expect(
                        "Lowering Instruction::Act requires an authenticated RegistrySnapshot",
                    );
                    let op_desc = reg.operations.get(op_id).unwrap_or_else(|| {
                        panic!(
                            "Lowering failed: OperationId {:?} not found in trusted registry",
                            op_id
                        )
                    });
                    let g_effs = op_desc
                        .requirements
                        .iter()
                        .flat_map(|r| r.required_gate_effects())
                        .collect::<Vec<_>>();
                    (op_desc.target_domain.clone(), g_effs)
                };

                let gate_effs = if self.mutations.s2m06_gate_effect_omitted_from_act {
                    Vec::new()
                } else {
                    effs
                };

                let vm_dest = self.map_value(*dest);
                let vm_args = args.iter().map(|a| self.map_value(*a)).collect();
                let vm_evidence = evidence.iter().map(|e| self.map_value(*e)).collect();

                VmInstruction::VmAct {
                    dest: vm_dest,
                    op_id: op_id.clone(),
                    target_domain: target_d,
                    success_type: success_type.clone(),
                    failure_type: failure_type.clone(),
                    args: vm_args,
                    evidence: vm_evidence,
                    gate_effects: gate_effs,
                    latent: latent.clone(),
                }
            }
            // Slice 3: Delegate
            Instruction::Delegate {
                dest,
                intent_id,
                args,
                requested_effects,
                authority_grant,
                budget_grant,
                ..
            } => {
                let (ok_ty, err_ty, mut c_effs) = {
                    let reg = self.registry.as_ref().expect(
                        "Lowering Instruction::Delegate requires an authenticated RegistrySnapshot",
                    );
                    let desc = reg.intents.get(intent_id).unwrap_or_else(|| {
                        panic!(
                            "Lowering failed: IntentId {:?} not found in trusted registry",
                            intent_id
                        )
                    });
                    (
                        desc.output_type.clone(),
                        desc.error_type.clone(),
                        desc.child_effects
                            .effects
                            .iter()
                            .cloned()
                            .collect::<Vec<_>>(),
                    )
                };

                // Mutation S3M01: delegate drops child effect from semantic requirement
                if self.mutations.s3m01_drop_delegate_child_effect && !c_effs.is_empty() {
                    c_effs.pop();
                }

                let vm_dest = self.map_value(*dest);
                let vm_args = args.iter().map(|a| self.map_value(*a)).collect();

                VmInstruction::VmSpawnChild {
                    dest: vm_dest,
                    intent_id: intent_id.clone(),
                    args: vm_args,
                    requested_effects: requested_effects.clone(),
                    authority_grant: authority_grant.clone(),
                    budget_grant: *budget_grant,
                    child_effects: c_effs,
                    ok_type: ok_ty,
                    err_type: err_ty,
                }
            }
            // Slice 3: Await
            Instruction::Await { dest, handle } => {
                let (ok_ty, err_ty) = match self.value_types.get(handle) {
                    Some(Type::ChildHandle { ok, err, .. }) => ((**ok).clone(), (**err).clone()),
                    _ => (Type::String, Type::String),
                };

                let vm_dest = self.map_value(*dest);
                let vm_handle = self.map_value(*handle);

                VmInstruction::VmAwaitChild {
                    dest: vm_dest,
                    handle: vm_handle,
                    ok_type: ok_ty,
                    err_type: err_ty,
                }
            }
            // Slice 3: Internalize
            Instruction::Internalize {
                dest,
                policy_id,
                claim,
                ..
            } => {
                let val_effs = {
                    let reg = self.registry.as_ref().expect(
                        "Lowering Instruction::Internalize requires an authenticated RegistrySnapshot",
                    );
                    let policy_desc =
                        reg.internalization_policies
                            .get(policy_id)
                            .unwrap_or_else(|| {
                                panic!(
                                    "Lowering failed: PolicyId {:?} not found in trusted registry",
                                    policy_id
                                )
                            });
                    policy_desc
                        .validation_effect_envelope
                        .effects
                        .iter()
                        .cloned()
                        .collect::<Vec<_>>()
                };

                let payload_ty = match self.value_types.get(claim) {
                    Some(Type::Claim(payload)) => (**payload).clone(),
                    _ => Type::String,
                };

                let vm_dest = self.map_value(*dest);
                let vm_claim = self.map_value(*claim);

                let latent = if self.mutations.m04_drop_latent_metadata {
                    crate::ir::facts::LatentPostconditions::empty()
                } else {
                    crate::ir::facts::LatentPostconditions {
                        on_ok: vec![crate::ir::facts::FactTemplate {
                            predicate: "Internalized".to_string(),
                            args: vec![
                                crate::ir::facts::FactArg::Symbol("$value".to_string()),
                                crate::ir::facts::FactArg::Symbol(format!("v{}", claim.0)),
                                crate::ir::facts::FactArg::Literal(policy_id.0.clone()),
                            ],
                        }],
                        on_err: Vec::new(),
                    }
                };

                VmInstruction::VmInternalize {
                    dest: vm_dest,
                    policy_id: policy_id.clone(),
                    claim: vm_claim,
                    validation_effects: val_effs,
                    payload_type: payload_ty,
                    latent,
                }
            }
            Instruction::Converge {
                dest,
                root_node,
                initial_frontier,
                budget_scope,
                max_steps,
                max_satisfaction_attempts,
                search_policy,
                ..
            } => {
                let vm_dest = self.map_value(*dest);
                VmInstruction::VmConvergeInit {
                    frame_var: vm_dest,
                    root_node: root_node.clone(),
                    initial_frontier: if initial_frontier.is_empty() {
                        vec![root_node.clone()]
                    } else {
                        initial_frontier.clone()
                    },
                    budget_resource: budget_scope.resource.clone(),
                    budget_limit: budget_scope.limit,
                    max_steps: *max_steps,
                    max_satisfaction_attempts: *max_satisfaction_attempts,
                    on_step_failure: search_policy.on_step_failure.clone(),
                    on_satisfier_error: search_policy.on_satisfier_error.clone(),
                }
            }
        }
    }

    fn lower_terminator(&mut self, term: &Terminator) -> VmTerminator {
        match term {
            Terminator::Return(val_opt) => VmTerminator::Return(val_opt.map(|v| self.map_value(v))),
            Terminator::Br { target, args } => VmTerminator::Br {
                target: self.map_block(*target),
                args: args.iter().map(|a| self.map_value(*a)).collect(),
            },
            Terminator::CondBr {
                cond,
                true_target,
                true_args,
                false_target,
                false_args,
            } => VmTerminator::CondBr {
                cond: self.map_value(*cond),
                true_target: self.map_block(*true_target),
                true_args: true_args.iter().map(|a| self.map_value(*a)).collect(),
                false_target: self.map_block(*false_target),
                false_args: false_args.iter().map(|a| self.map_value(*a)).collect(),
            },
            Terminator::MatchResult { .. } => {
                unreachable!("MatchResult handled in block lowering")
            }
            Terminator::MatchActOutcome { .. } => {
                unreachable!("MatchActOutcome handled in block lowering")
            }
            Terminator::Unreachable => VmTerminator::Unreachable,
        }
    }

    fn lower_region_terminator(&mut self, term: &RegionTerminator) -> VmTerminator {
        match term {
            RegionTerminator::Return(val_opt) => {
                VmTerminator::Return(val_opt.map(|v| self.map_value(v)))
            }
            RegionTerminator::Br { target, args } => VmTerminator::Br {
                target: self.map_block(*target),
                args: args.iter().map(|a| self.map_value(*a)).collect(),
            },
            RegionTerminator::Unreachable => VmTerminator::Unreachable,
        }
    }
}
