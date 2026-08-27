use std::collections::BTreeMap;
use serde::{Deserialize, Serialize};

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
}

pub struct LoweringContext {
    pub mutations: CompilerMutations,
    pub registry: Option<RegistrySnapshot>,
    pub value_map: BTreeMap<crate::ir::ValueId, VmValueId>,
    pub block_map: BTreeMap<crate::ir::BlockId, VmBlockId>,
    pub next_block_id: u32,
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
            value_types: BTreeMap::new(),
        }
    }

    pub fn map_value(&mut self, val: crate::ir::ValueId) -> VmValueId {
        *self
            .value_map
            .entry(val)
            .or_insert_with(|| VmValueId(val.0))
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

            for inst in &block.instructions {
                vm_block.instructions.push(self.lower_instruction(inst));
            }

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
                    for inst in &ok_body.instructions {
                        ok_vm_block.instructions.push(self.lower_instruction(inst));
                    }
                    ok_vm_block.terminator = self.lower_region_terminator(&ok_body.terminator);
                    generated_blocks.insert(ok_block_id, ok_vm_block);

                    let mut err_vm_block = VmBlock::new(err_block_id, VmTerminator::Unreachable);
                    err_vm_block.name = Some("err_branch".to_string());

                    let err_block_param_ty = if self.mutations.m03_corrupt_block_arg_type {
                        Type::I64
                    } else {
                        err_ty
                    };

                    err_vm_block
                        .params
                        .push((vm_err_arg, err_block_param_ty));
                    for inst in &err_body.instructions {
                        err_vm_block.instructions.push(self.lower_instruction(inst));
                    }
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
                    for inst in &success_body.instructions {
                        succ_block.instructions.push(self.lower_instruction(inst));
                    }
                    succ_block.terminator = self.lower_region_terminator(&success_body.terminator);
                    generated_blocks.insert(succ_block_id, succ_block);

                    // 2. Failure region
                    let mut fail_block = VmBlock::new(fail_block_id, VmTerminator::Unreachable);
                    fail_block.name = Some("failure_branch".to_string());
                    fail_block.params.push((vm_fail_arg, fail_ty));
                    for inst in &failure_body.instructions {
                        fail_block.instructions.push(self.lower_instruction(inst));
                    }
                    fail_block.terminator = self.lower_region_terminator(&failure_body.terminator);
                    generated_blocks.insert(fail_block_id, fail_block);

                    // 3. Partial region
                    let mut part_block = VmBlock::new(part_block_id, VmTerminator::Unreachable);
                    part_block.name = Some("partial_branch".to_string());
                    part_block
                        .params
                        .push((vm_part_arg, Type::PartialReport));
                    for inst in &partial_body.instructions {
                        part_block.instructions.push(self.lower_instruction(inst));
                    }
                    part_block.terminator = self.lower_region_terminator(&partial_body.terminator);
                    generated_blocks.insert(part_block_id, part_block);

                    // 4. Unknown region
                    let mut unk_block = VmBlock::new(unk_block_id, VmTerminator::Unreachable);
                    unk_block.name = Some("unknown_branch".to_string());
                    unk_block.params.push((vm_unk_arg, Type::String));
                    for inst in &unknown_body.instructions {
                        unk_block.instructions.push(self.lower_instruction(inst));
                    }
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
                output_predicate,
                subject_type,
                verifier_effects,
            } => {
                // Q1: Authoritative descriptor lookup in registry
                let (out_p, subj_t, mut effs) = if let Some(reg) = &self.registry {
                    if let Some(desc) = reg.verifiers.get(verifier_id) {
                        (
                            desc.output_predicate.clone(),
                            desc.subject_type.clone(),
                            desc.effect_envelope.effects.iter().cloned().collect(),
                        )
                    } else {
                        (
                            output_predicate.clone(),
                            subject_type.clone(),
                            verifier_effects.clone(),
                        )
                    }
                } else {
                    (
                        output_predicate.clone(),
                        subject_type.clone(),
                        verifier_effects.clone(),
                    )
                };

                if self.mutations.s2m02_drop_verifier_effect && !effs.is_empty() {
                    effs.pop();
                }

                VmInstruction::VmVerify {
                    dest: self.map_value(*dest),
                    verifier_id: verifier_id.clone(),
                    subject: self.map_value(*subject),
                    output_predicate: out_p,
                    subject_type: subj_t,
                    verifier_effects: effs,
                }
            }
            Instruction::Act {
                dest,
                op_id,
                target_domain,
                success_type,
                failure_type,
                args,
                evidence,
                gate_effects,
                latent,
            } => {
                // Q1: Authoritative descriptor lookup in registry
                let (target_d, effs) = if let Some(reg) = &self.registry {
                    if let Some(op_desc) = reg.operations.get(op_id) {
                        let g_effs = op_desc
                            .requirements
                            .iter()
                            .flat_map(|r| r.required_gate_effects())
                            .collect();
                        (op_desc.target_domain.clone(), g_effs)
                    } else {
                        (target_domain.clone(), gate_effects.clone())
                    }
                } else {
                    (target_domain.clone(), gate_effects.clone())
                };

                let gate_effs = if self.mutations.s2m06_gate_effect_omitted_from_act {
                    Vec::new()
                } else {
                    effs
                };

                VmInstruction::VmAct {
                    dest: self.map_value(*dest),
                    op_id: op_id.clone(),
                    target_domain: target_d,
                    success_type: success_type.clone(),
                    failure_type: failure_type.clone(),
                    args: args.iter().map(|a| self.map_value(*a)).collect(),
                    evidence: evidence.iter().map(|e| self.map_value(*e)).collect(),
                    gate_effects: gate_effs,
                    latent: latent.clone(),
                }
            }
        }
    }

    fn lower_terminator(&mut self, term: &Terminator) -> VmTerminator {
        match term {
            Terminator::Return(val_opt) => {
                VmTerminator::Return(val_opt.map(|v| self.map_value(v)))
            }
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
