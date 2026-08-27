use std::collections::{BTreeMap, BTreeSet};

use bando::{
    analysis::PathFactAnalyzer,
    diagnostics::DiagnosticCode,
    ir::{
        block::Block,
        effects::{Effect, EffectRow},
        facts::{Fact, FactArg, FactTemplate, LatentPostconditions},
        function::Function,
        module::Module,
        ops::{Instruction, Region, RegionTerminator, Terminator},
        types::Type,
        values::{BlockId, Value, ValueId},
    },
    lowering::{CompilerMutations, LoweringContext},
    registry::{
        AtomicityGuarantee, CallerAuthority, MutationFootprint, OperationDescriptor, OperationId,
        PolicyRequirement, RegistrySnapshot, TrustedRuntimeAuthority, VerifierDescriptor,
        VerifierId,
    },
    verifier::HighLevelVerifier,
    vm::{adapters::RuntimeAdapters, interpreter::VmStatus, VmInterpreter},
    vm_verifier::VmVerifier,
    world::WorldState,
};

#[test]
fn test_c01_pure_value() {
    let mut func = Function::new("main", BlockId(0), Type::I64);
    let mut entry = Block::new(BlockId(0), Terminator::Return(Some(ValueId(1))));
    entry.instructions.push(Instruction::Pure {
        dest: ValueId(1),
        val: Value::I64(42),
        ty: Type::I64,
    });
    func.blocks.insert(BlockId(0), entry);

    let mut module = Module::new("test_c01");
    module.functions.push(func);

    assert!(HighLevelVerifier::verify_module(&module).is_ok());

    let mut lowering = LoweringContext::new();
    let vm_module = lowering.lower_module(&module);
    assert!(VmVerifier::verify_module(&vm_module).is_ok());

    let mut adapters = RuntimeAdapters::default();
    let registry = RegistrySnapshot::default();
    let mut interp = VmInterpreter::new(&vm_module.functions[0], &mut adapters, &registry);
    let state = interp.execute(
        BTreeMap::new(),
        WorldState::new(),
        BTreeSet::new(),
        None,
        None,
        100,
    );

    assert_eq!(state.status, VmStatus::Terminated);
    assert_eq!(state.return_value, Some(Value::I64(42)));
}

#[test]
fn test_c02_structured_match_result_and_lowering() {
    let mut func = Function::new("main", BlockId(0), Type::String);
    func.declared_effects = EffectRow::empty().with(Effect::Read("docs".to_string()));

    let latent = LatentPostconditions {
        on_ok: vec![FactTemplate {
            predicate: "ObservedAt".to_string(),
            args: vec![
                FactArg::Symbol("$value".to_string()),
                FactArg::Literal("docs".to_string()),
            ],
        }],
        on_err: Vec::new(),
    };

    let mut entry = Block::new(
        BlockId(0),
        Terminator::MatchResult {
            result_val: ValueId(1),
            ok_arg: ValueId(2),
            ok_body: Region::new(RegionTerminator::Return(Some(ValueId(2)))),
            err_arg: ValueId(3),
            err_body: Region::new(RegionTerminator::Return(Some(ValueId(3)))),
        },
    );

    entry.instructions.push(Instruction::Read {
        dest: ValueId(1),
        domain: "docs".to_string(),
        ok_type: Type::String,
        err_type: Type::String,
        latent,
    });
    func.blocks.insert(BlockId(0), entry);

    let mut module = Module::new("test_c02");
    module.functions.push(func);

    assert!(HighLevelVerifier::verify_module(&module).is_ok());

    let mut lowering = LoweringContext::new();
    let vm_module = lowering.lower_module(&module);
    assert!(VmVerifier::verify_module(&vm_module).is_ok());

    let vm_func = &vm_module.functions[0];
    assert!(vm_func
        .declared_effects
        .contains(&Effect::Read("docs".to_string())));

    let mut adapters = RuntimeAdapters::default();
    let registry = RegistrySnapshot::default();
    let mut interp = VmInterpreter::new(vm_func, &mut adapters, &registry);
    let state = interp.execute(
        BTreeMap::new(),
        WorldState::new(),
        BTreeSet::new(),
        None,
        None,
        100,
    );

    assert_eq!(state.status, VmStatus::Terminated);
    assert_eq!(
        state.return_value,
        Some(Value::String("data_of(docs)".to_string()))
    );
    assert_eq!(state.observable_effects, vec!["read[docs]"]);

    let expected_fact = Fact::new(
        "ObservedAt",
        vec![
            FactArg::Symbol("v2".to_string()),
            FactArg::Literal("docs".to_string()),
        ],
    );
    assert!(state.active_facts.contains(&expected_fact));
}

#[test]
fn test_c05_c06_diamond_must_fact_merge() {
    let mut func = Function::new("main", BlockId(0), Type::String);
    func.declared_effects = EffectRow::empty().with(Effect::Read("doc".to_string()));

    let latent = LatentPostconditions {
        on_ok: vec![
            FactTemplate {
                predicate: "ExclusiveOk".to_string(),
                args: vec![FactArg::Symbol("$value".to_string())],
            },
            FactTemplate {
                predicate: "CommonFact".to_string(),
                args: vec![FactArg::Literal("doc".to_string())],
            },
        ],
        on_err: vec![FactTemplate {
            predicate: "CommonFact".to_string(),
            args: vec![FactArg::Literal("doc".to_string())],
        }],
    };

    let mut entry = Block::new(
        BlockId(0),
        Terminator::MatchResult {
            result_val: ValueId(1),
            ok_arg: ValueId(2),
            ok_body: Region::new(RegionTerminator::Br {
                target: BlockId(3),
                args: vec![ValueId(2)],
            }),
            err_arg: ValueId(3),
            err_body: Region::new(RegionTerminator::Br {
                target: BlockId(3),
                args: vec![ValueId(3)],
            }),
        },
    );
    entry.instructions.push(Instruction::Read {
        dest: ValueId(1),
        domain: "doc".to_string(),
        ok_type: Type::String,
        err_type: Type::String,
        latent,
    });
    func.blocks.insert(BlockId(0), entry);

    let mut b_merge = Block::new(BlockId(3), Terminator::Return(Some(ValueId(4))));
    b_merge.params.push((ValueId(4), Type::String));
    func.blocks.insert(BlockId(3), b_merge);

    let mut module = Module::new("test_diamond");
    module.functions.push(func);

    assert!(HighLevelVerifier::verify_module(&module).is_ok());

    let mut lowering = LoweringContext::new();
    let vm_module = lowering.lower_module(&module);
    assert!(VmVerifier::verify_module(&vm_module).is_ok());

    let analysis = PathFactAnalyzer::new(&vm_module.functions[0]).analyze();
    let merge_facts = analysis
        .block_in_facts
        .get(&bando::vm_ir::VmBlockId(3))
        .unwrap();

    let common_fact = Fact::new("CommonFact", vec![FactArg::Literal("doc".to_string())]);
    assert!(merge_facts.contains(&common_fact));
    assert!(!merge_facts.iter().any(|f| f.predicate == "ExclusiveOk"));
}

#[test]
fn test_r3_ssa_dominance_and_scope_visibility() {
    let mut func_ok = Function::new("ok", BlockId(0), Type::I64);
    let mut b0 = Block::new(
        BlockId(0),
        Terminator::Br {
            target: BlockId(1),
            args: vec![],
        },
    );
    b0.instructions.push(Instruction::Pure {
        dest: ValueId(1),
        val: Value::I64(10),
        ty: Type::I64,
    });
    func_ok.blocks.insert(BlockId(0), b0);

    let b1 = Block::new(BlockId(1), Terminator::Return(Some(ValueId(1))));
    func_ok.blocks.insert(BlockId(1), b1);

    let mut mod_ok = Module::new("m_ok");
    mod_ok.functions.push(func_ok);
    assert!(HighLevelVerifier::verify_module(&mod_ok).is_ok());

    let mut func_bad = Function::new("bad", BlockId(0), Type::I64);
    let b_entry = Block::new(
        BlockId(0),
        Terminator::CondBr {
            cond: ValueId(1),
            true_target: BlockId(1),
            true_args: vec![],
            false_target: BlockId(2),
            false_args: vec![],
        },
    );
    func_bad.params.push((ValueId(1), Type::Bool));
    func_bad.blocks.insert(BlockId(0), b_entry);

    let mut b_left = Block::new(BlockId(1), Terminator::Return(Some(ValueId(2))));
    b_left.instructions.push(Instruction::Pure {
        dest: ValueId(2),
        val: Value::I64(100),
        ty: Type::I64,
    });
    func_bad.blocks.insert(BlockId(1), b_left);

    let b_right = Block::new(BlockId(2), Terminator::Return(Some(ValueId(2))));
    func_bad.blocks.insert(BlockId(2), b_right);

    let mut mod_bad = Module::new("m_bad");
    mod_bad.functions.push(func_bad);
    let diags = HighLevelVerifier::verify_module(&mod_bad).unwrap_err();
    assert!(diags
        .iter()
        .any(|d| d.code == DiagnosticCode::SsaUseBeforeDef));
}

#[test]
fn test_s1_region_local_definition_isolation_and_dominance() {
    let mut func_dom = Function::new("main", BlockId(0), Type::I64);
    let mut entry = Block::new(
        BlockId(0),
        Terminator::MatchResult {
            result_val: ValueId(1),
            ok_arg: ValueId(3),
            ok_body: Region::new(RegionTerminator::Return(Some(ValueId(2)))),
            err_arg: ValueId(4),
            err_body: Region::new(RegionTerminator::Return(Some(ValueId(2)))),
        },
    );
    entry.instructions.push(Instruction::Pure {
        dest: ValueId(1),
        val: Value::I64(10),
        ty: Type::result(Type::I64, Type::I64),
    });
    entry.instructions.push(Instruction::Pure {
        dest: ValueId(2),
        val: Value::I64(100),
        ty: Type::I64,
    });
    func_dom.blocks.insert(BlockId(0), entry);

    let mut mod_dom = Module::new("m_dom");
    mod_dom.functions.push(func_dom);
    assert!(HighLevelVerifier::verify_module(&mod_dom).is_ok());

    let mut func_leak = Function::new("main", BlockId(0), Type::I64);
    let mut entry_leak = Block::new(
        BlockId(0),
        Terminator::MatchResult {
            result_val: ValueId(1),
            ok_arg: ValueId(2),
            ok_body: Region {
                instructions: vec![Instruction::Pure {
                    dest: ValueId(4),
                    val: Value::I64(42),
                    ty: Type::I64,
                }],
                terminator: RegionTerminator::Br {
                    target: BlockId(1),
                    args: vec![],
                },
            },
            err_arg: ValueId(3),
            err_body: Region::new(RegionTerminator::Br {
                target: BlockId(1),
                args: vec![],
            }),
        },
    );
    entry_leak.instructions.push(Instruction::Pure {
        dest: ValueId(1),
        val: Value::I64(10),
        ty: Type::result(Type::I64, Type::I64),
    });
    func_leak.blocks.insert(BlockId(0), entry_leak);

    let b_merge = Block::new(BlockId(1), Terminator::Return(Some(ValueId(4))));
    func_leak.blocks.insert(BlockId(1), b_merge);

    let mut mod_leak = Module::new("m_leak");
    mod_leak.functions.push(func_leak);
    let diags = HighLevelVerifier::verify_module(&mod_leak).unwrap_err();
    assert!(diags
        .iter()
        .any(|d| d.code == DiagnosticCode::SsaUseBeforeDef));
}

#[test]
fn test_slice2_verify_and_gated_act() {
    let mut registry = RegistrySnapshot::new();
    let v_desc = VerifierDescriptor::new(
        VerifierId::new("auditor_v1"),
        "1.0.0",
        EffectRow::empty().with(Effect::Read("workspace".to_string())),
        "PassesAudit",
        Type::String,
    );
    registry.register_verifier(v_desc);

    let op_desc = OperationDescriptor::new(
        OperationId::new("deploy_patch"),
        "workspace",
        EffectRow::empty()
            .with(Effect::Act("workspace".to_string()))
            .with(Effect::Read("trust_store".to_string())),
        MutationFootprint::Exact(BTreeSet::from(["workspace/doc1".to_string()])),
        AtomicityGuarantee::Atomic,
        vec![PolicyRequirement::RequiresAttestation {
            predicate: "PassesAudit".to_string(),
            subject_arg_idx: 0,
        }],
    );
    registry.register_operation(op_desc);
    registry
        .trust_policy
        .trust_verifier("PassesAudit", VerifierId::new("auditor_v1"));

    registry.caller_authority = Some(CallerAuthority {
        effects: BTreeSet::from([
            Effect::Read("workspace".to_string()),
            Effect::Act("workspace".to_string()),
        ]),
    });
    registry.runtime_authority = Some(TrustedRuntimeAuthority {
        effects: BTreeSet::from([Effect::Read("trust_store".to_string())]),
    });

    let mut func = Function::new("main", BlockId(0), Type::String);
    func.declared_effects = EffectRow::empty()
        .with(Effect::Read("workspace".to_string()))
        .with(Effect::Read("trust_store".to_string()))
        .with(Effect::Act("workspace".to_string()));

    let mut entry = Block::new(BlockId(0), Terminator::Return(Some(ValueId(4))));
    entry.instructions.push(Instruction::Pure {
        dest: ValueId(1),
        val: Value::String("patch_subject".to_string()),
        ty: Type::String,
    });
    entry.instructions.push(Instruction::Verify {
        dest: ValueId(2),
        verifier_id: VerifierId::new("auditor_v1"),
        subject: ValueId(1),
        output_predicate: "PassesAudit".to_string(),
        subject_type: Type::String,
        verifier_effects: vec![Effect::Read("workspace".to_string())],
    });
    entry.instructions.push(Instruction::Act {
        dest: ValueId(3),
        op_id: OperationId::new("deploy_patch"),
        target_domain: "workspace".to_string(),
        success_type: Type::String,
        failure_type: Type::String,
        args: vec![ValueId(1)],
        evidence: vec![ValueId(2)],
        gate_effects: vec![Effect::Read("trust_store".to_string())],
        latent: Default::default(),
    });
    entry.instructions.push(Instruction::Pure {
        dest: ValueId(4),
        val: Value::String("done".to_string()),
        ty: Type::String,
    });
    func.blocks.insert(BlockId(0), entry);

    let mut module = Module::new("test_s2");
    module.functions.push(func);

    assert!(HighLevelVerifier::verify_module_with_registry(&module, &registry).is_ok());

    let mut lowering =
        LoweringContext::with_registry(registry.clone(), CompilerMutations::default());
    let vm_module = lowering.lower_module(&module);
    assert!(VmVerifier::verify_module(&vm_module).is_ok());

    let mut adapters = RuntimeAdapters::default();
    let mut interp = VmInterpreter::new(&vm_module.functions[0], &mut adapters, &registry);
    let state = interp.execute(
        BTreeMap::new(),
        WorldState::new(),
        BTreeSet::new(),
        None,
        None,
        100,
    );

    assert_eq!(state.status, VmStatus::Terminated);
    assert!(state
        .observable_effects
        .contains(&"read[workspace]".to_string()));
    assert!(state
        .observable_effects
        .contains(&"read[trust_store]".to_string()));
    assert!(state
        .observable_effects
        .contains(&"act[workspace]".to_string()));
    assert_eq!(state.world.mutation_trace.len(), 1);
}

#[test]
fn test_slice3_delegate_await_internalize() {
    let mut registry = RegistrySnapshot::default();
    let agent_desc = bando::registry::agent::AgentDescriptor {
        agent_id: bando::registry::agent::AgentId("worker_agent".to_string()),
        native_authority: BTreeSet::from([Effect::Read("docs".to_string()), Effect::Infer]),
    };
    registry
        .agents
        .insert(agent_desc.agent_id.clone(), agent_desc);

    let intent_desc = bando::registry::intent::IntentInvocationDescriptor {
        intent_id: bando::registry::intent::IntentId("summarize_docs".to_string()),
        target_agent_id: bando::registry::agent::AgentId("worker_agent".to_string()),
        input_types: vec![Type::String],
        output_type: Type::claim(Type::String),
        error_type: Type::String,
        child_effects: EffectRow::empty()
            .with(Effect::Read("docs".to_string()))
            .with(Effect::Infer),
        exported_envelope: EffectRow::empty()
            .with(Effect::Read("docs".to_string()))
            .with(Effect::Infer),
        declared_envelope: EffectRow::empty()
            .with(Effect::Read("docs".to_string()))
            .with(Effect::Infer),
        authority_policy: "AllowNative".to_string(),
    };
    registry
        .intents
        .insert(intent_desc.intent_id.clone(), intent_desc);

    let policy_desc = bando::registry::internalization::InternalizationPolicyDescriptor {
        policy_id: bando::registry::internalization::PolicyId("default_policy".to_string()),
        accepted_claim_contract: bando::registry::internalization::ClaimContract::AcceptAll,
        validation_requirements: Vec::new(),
        validation_effect_envelope: EffectRow::empty()
            .with(Effect::Read("policy_store".to_string())),
    };
    registry
        .internalization_policies
        .insert(policy_desc.policy_id.clone(), policy_desc);

    registry.caller_authority = Some(CallerAuthority {
        effects: BTreeSet::from([Effect::Read("policy_store".to_string())]),
    });

    let mut func = Function::new("main", BlockId(0), Type::String);
    func.declared_effects = EffectRow::empty()
        .with(Effect::Read("docs".to_string()))
        .with(Effect::Infer)
        .with(Effect::Read("policy_store".to_string()));

    let mut entry = Block::new(
        BlockId(0),
        Terminator::MatchResult {
            result_val: ValueId(3),
            ok_arg: ValueId(4),
            ok_body: Region {
                instructions: vec![Instruction::Internalize {
                    dest: ValueId(5),
                    policy_id: bando::registry::internalization::PolicyId(
                        "default_policy".to_string(),
                    ),
                    claim: ValueId(4),
                }],
                terminator: RegionTerminator::Return(Some(ValueId(1))),
            },
            err_arg: ValueId(6),
            err_body: Region::new(RegionTerminator::Return(Some(ValueId(1)))),
        },
    );

    entry.instructions.push(Instruction::Pure {
        dest: ValueId(1),
        val: Value::String("doc_query".to_string()),
        ty: Type::String,
    });
    entry.instructions.push(Instruction::Delegate {
        dest: ValueId(2),
        intent_id: bando::registry::intent::IntentId("summarize_docs".to_string()),
        args: vec![ValueId(1)],
        requested_effects: vec![Effect::Read("docs".to_string()), Effect::Infer],
        authority_grant: Vec::new(),
        budget_grant: 50,
    });
    entry.instructions.push(Instruction::Await {
        dest: ValueId(3),
        handle: ValueId(2),
    });

    func.blocks.insert(BlockId(0), entry);

    let mut module = Module::new("test_s3");
    module.functions.push(func);

    assert!(HighLevelVerifier::verify_module_with_registry(&module, &registry).is_ok());

    let mut lowering =
        LoweringContext::with_registry(registry.clone(), CompilerMutations::default());
    let vm_module = lowering.lower_module(&module);
    assert!(VmVerifier::verify_module(&vm_module).is_ok());

    let mut adapters = RuntimeAdapters::default();
    let mut interp = VmInterpreter::new(&vm_module.functions[0], &mut adapters, &registry);
    let state = interp.execute(
        BTreeMap::new(),
        WorldState::new(),
        BTreeSet::new(),
        None,
        None,
        100,
    );

    assert_eq!(state.status, VmStatus::Terminated);
    assert!(state.observable_effects.contains(&"read[docs]".to_string()));
    assert!(state.observable_effects.contains(&"infer".to_string()));
    assert!(state
        .observable_effects
        .contains(&"read[policy_store]".to_string()));
    assert_eq!(state.child_handles.len(), 1);
    assert_eq!(state.beliefs.len(), 1);
}

#[test]
fn test_slice4_converge_pipeline() {
    let registry = RegistrySnapshot::default();

    let expected_return_ty = Type::result(
        Type::convergence_outcome(Type::String, Type::exhaustion_report(Type::String)),
        Type::String,
    );

    let mut func = Function::new("main", BlockId(0), expected_return_ty);
    func.declared_effects = EffectRow::empty().with(Effect::Read("data".to_string()));

    let mut entry = Block::new(
        BlockId(0),
        Terminator::Return(Some(ValueId(1))),
    );

    entry.instructions.push(Instruction::Converge {
        dest: ValueId(1),
        root_node: "root".to_string(),
        initial_frontier: vec!["root".to_string()],
        successors: std::collections::BTreeMap::new(),
        node_ops: std::collections::BTreeMap::new(),
        satisfier: bando::ir::ops::SatisfierDef::default(),
        partial_map: std::collections::BTreeMap::new(),
        space_faults: std::collections::BTreeMap::new(),
        fault_spec: bando::ir::ops::ConvergeFaultSpec::default(),
        space_ops: vec![bando::registry::OperationId("local_op".to_string())],
        satisfier_op: bando::registry::OperationId("local_satisfier".to_string()),
        search_policy: bando::ir::ops::SearchPolicyDescriptor {
            policy_id: "pure_policy".to_string(),
            on_step_failure: "abort".to_string(),
            on_satisfier_error: "abort".to_string(),
            policy_effects: EffectRow::empty(),
        },
        budget_scope: bando::ir::ops::BudgetScopeConfig {
            resource: "usd".to_string(),
            limit: 100,
        },
        max_steps: 10,
        max_satisfaction_attempts: 5,
        space_effects: EffectRow::empty().with(Effect::Read("data".to_string())),
        satisfier_effects: EffectRow::empty(),
        partial_type: Type::String,
        satisfied_type: Type::String,
    });

    func.blocks.insert(BlockId(0), entry);

    let mut module = Module::new("test_s4");
    module.functions.push(func);

    // 1. High level verifier
    assert!(HighLevelVerifier::verify_module_with_registry(&module, &registry).is_ok());

    // 2. Lowering
    let mut lowering =
        LoweringContext::with_registry(registry.clone(), CompilerMutations::default());
    let vm_module = lowering.lower_module(&module);

    // 3. VM Verifier
    assert!(VmVerifier::verify_module(&vm_module).is_ok());

    // 4. Interpreter execution
    let mut adapters = RuntimeAdapters::default();
    let mut interp = VmInterpreter::new(&vm_module.functions[0], &mut adapters, &registry);
    let state = interp.execute(
        BTreeMap::new(),
        WorldState::new(),
        BTreeSet::new(),
        None,
        None,
        100,
    );

    assert_eq!(state.status, VmStatus::Terminated);
    // R4: May-effects are not copied to observable_effects; only executed operations appear
    assert_eq!(state.observable_effects.len(), 0);
    assert_eq!(state.converge_domains.len(), 1);
}

#[test]
fn test_slice4_vm_verifier_rejects_dropped_converge_effect() {
    let registry = RegistrySnapshot::default();

    let expected_return_ty = Type::result(
        Type::convergence_outcome(Type::String, Type::exhaustion_report(Type::String)),
        Type::String,
    );

    let mut func = Function::new("main", BlockId(0), expected_return_ty);
    func.declared_effects = EffectRow::empty().with(Effect::Act("space_target".to_string()));

    let mut entry = Block::new(BlockId(0), Terminator::Return(Some(ValueId(1))));

    let mut node_ops = std::collections::BTreeMap::new();
    node_ops.insert(
        "root".to_string(),
        bando::ir::ops::SpaceOpDef {
            op_id: "opExt".to_string(),
            kind: "external".to_string(),
            cost: 10,
            actual_cost: None,
            request_id: None,
            dedup_capable: true,
            idempotent: true,
            required_effects: vec![Effect::Act("space_target".to_string())],
        },
    );

    entry.instructions.push(Instruction::Converge {
        dest: ValueId(1),
        root_node: "root".to_string(),
        initial_frontier: vec!["root".to_string()],
        successors: std::collections::BTreeMap::new(),
        node_ops,
        satisfier: bando::ir::ops::SatisfierDef::default(),
        partial_map: std::collections::BTreeMap::new(),
        space_faults: std::collections::BTreeMap::new(),
        fault_spec: bando::ir::ops::ConvergeFaultSpec::default(),
        space_ops: vec![],
        satisfier_op: bando::registry::OperationId("local_satisfier".to_string()),
        search_policy: bando::ir::ops::SearchPolicyDescriptor {
            policy_id: "pure_policy".to_string(),
            on_step_failure: "abort".to_string(),
            on_satisfier_error: "abort".to_string(),
            policy_effects: EffectRow::empty(),
        },
        budget_scope: bando::ir::ops::BudgetScopeConfig {
            resource: "usd".to_string(),
            limit: 100,
        },
        max_steps: 10,
        max_satisfaction_attempts: 5,
        space_effects: EffectRow::empty().with(Effect::Act("space_target".to_string())),
        satisfier_effects: EffectRow::empty(),
        partial_type: Type::String,
        satisfied_type: Type::String,
    });

    func.blocks.insert(BlockId(0), entry);

    let mut module = Module::new("test_s4_eff");
    module.functions.push(func);

    // 1. High level verifier passes
    assert!(HighLevelVerifier::verify_module_with_registry(&module, &registry).is_ok());

    // 2. Lowering creates valid VM module
    let mut lowering =
        LoweringContext::with_registry(registry.clone(), CompilerMutations::default());
    let mut vm_module = lowering.lower_module(&module);
    assert!(VmVerifier::verify_module(&vm_module).is_ok());

    // 3. Corrupt/drop the declared effect from the VM function
    vm_module.functions[0].declared_effects = EffectRow::empty();

    // 4. VmVerifier MUST reject the VM function with EffectUndeclared
    let vm_res = VmVerifier::verify_module(&vm_module);
    assert!(vm_res.is_err(), "R4: VmVerifier must reject VM function when converge effect is undeclared");
}

#[test]
fn test_slice4_lowering_emits_discrete_transactional_opcodes() {
    let registry = RegistrySnapshot::default();

    let expected_return_ty = Type::result(
        Type::convergence_outcome(Type::String, Type::exhaustion_report(Type::String)),
        Type::String,
    );

    let mut func = Function::new("main", BlockId(0), expected_return_ty);
    func.declared_effects = EffectRow::empty().with(Effect::Act("opRoot".to_string()));

    let mut entry = Block::new(BlockId(0), Terminator::Return(Some(ValueId(1))));

    let mut node_ops = std::collections::BTreeMap::new();
    node_ops.insert(
        "root".to_string(),
        bando::ir::ops::SpaceOpDef {
            op_id: "opRoot".to_string(),
            kind: "external".to_string(),
            cost: 10,
            actual_cost: None,
            request_id: None,
            dedup_capable: true,
            idempotent: true,
            required_effects: vec![Effect::Act("opRoot".to_string())],
        },
    );

    entry.instructions.push(Instruction::Converge {
        dest: ValueId(1),
        root_node: "root".to_string(),
        initial_frontier: vec!["root".to_string()],
        successors: std::collections::BTreeMap::new(),
        node_ops,
        satisfier: bando::ir::ops::SatisfierDef::default(),
        partial_map: std::collections::BTreeMap::new(),
        space_faults: std::collections::BTreeMap::new(),
        fault_spec: bando::ir::ops::ConvergeFaultSpec::default(),
        space_ops: vec![],
        satisfier_op: bando::registry::OperationId("local_satisfier".to_string()),
        search_policy: bando::ir::ops::SearchPolicyDescriptor {
            policy_id: "pure_policy".to_string(),
            on_step_failure: "abort".to_string(),
            on_satisfier_error: "abort".to_string(),
            policy_effects: EffectRow::empty(),
        },
        budget_scope: bando::ir::ops::BudgetScopeConfig {
            resource: "usd".to_string(),
            limit: 100,
        },
        max_steps: 10,
        max_satisfaction_attempts: 5,
        space_effects: EffectRow::empty().with(Effect::Act("opRoot".to_string())),
        satisfier_effects: EffectRow::empty(),
        partial_type: Type::String,
        satisfied_type: Type::String,
    });

    func.blocks.insert(BlockId(0), entry);

    let mut module = Module::new("test_s4_lowering");
    module.functions.push(func);

    let mut lowering =
        LoweringContext::with_registry(registry.clone(), CompilerMutations::default());
    let vm_module = lowering.lower_module(&module);
    let vm_func = &vm_module.functions[0];

    // Assert that the local and external transactional opcodes are explicitly present in the VM CFG:
    // DispatchLocal < CheckSatisfactionLocal < Stage < Emit < Admit < Settle < Apply
    let mut has_init = false;
    let mut has_step = false;
    let mut dispatch_local_idx = None;
    let mut check_sat_local_idx = None;
    let mut stage_idx = None;
    let mut emit_idx = None;
    let mut admit_idx = None;
    let mut settle_idx = None;
    let mut apply_idx = None;

    for (_block_id, block) in &vm_func.blocks {
        for (idx, inst) in block.instructions.iter().enumerate() {
            match inst {
                bando::vm_ir::VmInstruction::VmConvergeInit { .. } => has_init = true,
                bando::vm_ir::VmInstruction::VmConvergeStep { .. } => has_step = true,
                bando::vm_ir::VmInstruction::VmConvergeDispatchLocal { .. } => dispatch_local_idx = Some(idx),
                bando::vm_ir::VmInstruction::VmConvergeCheckSatisfactionLocal { .. } => check_sat_local_idx = Some(idx),
                bando::vm_ir::VmInstruction::VmConvergeStage { .. } => stage_idx = Some(idx),
                bando::vm_ir::VmInstruction::VmConvergeEmit { .. } => emit_idx = Some(idx),
                bando::vm_ir::VmInstruction::VmConvergeAdmitCompletion { .. } => admit_idx = Some(idx),
                bando::vm_ir::VmInstruction::VmConvergeSettle { .. } => settle_idx = Some(idx),
                bando::vm_ir::VmInstruction::VmConvergeApply { .. } => apply_idx = Some(idx),
                _ => {}
            }
        }
    }

    assert!(has_init, "R2: VM CFG must contain VmConvergeInit");
    assert!(has_step, "R2: VM CFG must contain VmConvergeStep");
    assert!(dispatch_local_idx.is_some(), "R2: VM CFG must contain VmConvergeDispatchLocal");
    assert!(check_sat_local_idx.is_some(), "R2: VM CFG must contain VmConvergeCheckSatisfactionLocal");
    assert!(stage_idx.is_some(), "R2: VM CFG must contain VmConvergeStage");
    assert!(emit_idx.is_some(), "R2: VM CFG must contain VmConvergeEmit");
    assert!(admit_idx.is_some(), "R2: VM CFG must contain VmConvergeAdmitCompletion");
    assert!(settle_idx.is_some(), "R2: VM CFG must contain VmConvergeSettle");
    assert!(apply_idx.is_some(), "R2: VM CFG must contain VmConvergeApply");

    // Order assertion: DispatchLocal < CheckSatisfactionLocal < Stage < Emit < Admit < Settle < Apply
    assert!(dispatch_local_idx.unwrap() < check_sat_local_idx.unwrap());
    assert!(check_sat_local_idx.unwrap() < stage_idx.unwrap());
    assert!(stage_idx.unwrap() < emit_idx.unwrap());
    assert!(emit_idx.unwrap() < admit_idx.unwrap());
    assert!(admit_idx.unwrap() < settle_idx.unwrap());
    assert!(settle_idx.unwrap() < apply_idx.unwrap());
}

#[test]
fn test_slice4_local_boundary_stopping_between_selection_and_execution() {
    let registry = RegistrySnapshot::default();

    let expected_return_ty = Type::result(
        Type::convergence_outcome(Type::String, Type::exhaustion_report(Type::String)),
        Type::String,
    );

    let mut func = Function::new("main", BlockId(0), expected_return_ty);
    let mut entry = Block::new(BlockId(0), Terminator::Return(Some(ValueId(1))));

    let mut succs = std::collections::BTreeMap::new();
    succs.insert("root".to_string(), vec!["leaf".to_string()]);

    entry.instructions.push(Instruction::Converge {
        dest: ValueId(1),
        root_node: "root".to_string(),
        initial_frontier: vec!["root".to_string()],
        successors: succs,
        node_ops: std::collections::BTreeMap::new(),
        satisfier: bando::ir::ops::SatisfierDef::default(),
        partial_map: std::collections::BTreeMap::new(),
        space_faults: std::collections::BTreeMap::new(),
        fault_spec: bando::ir::ops::ConvergeFaultSpec::default(),
        space_ops: vec![],
        satisfier_op: bando::registry::OperationId("local_satisfier".to_string()),
        search_policy: bando::ir::ops::SearchPolicyDescriptor {
            policy_id: "pure_policy".to_string(),
            on_step_failure: "abort".to_string(),
            on_satisfier_error: "abort".to_string(),
            policy_effects: EffectRow::empty(),
        },
        budget_scope: bando::ir::ops::BudgetScopeConfig {
            resource: "usd".to_string(),
            limit: 100,
        },
        max_steps: 10,
        max_satisfaction_attempts: 5,
        space_effects: EffectRow::empty(),
        satisfier_effects: EffectRow::empty(),
        partial_type: Type::String,
        satisfied_type: Type::String,
    });

    func.blocks.insert(BlockId(0), entry);

    let mut module = Module::new("test_s4_local_boundary");
    module.functions.push(func);

    let mut lowering =
        LoweringContext::with_registry(registry.clone(), CompilerMutations::default());
    let vm_module = lowering.lower_module(&module);

    let mut adapters = RuntimeAdapters::default();
    let mut interp = VmInterpreter::new(&vm_module.functions[0], &mut adapters, &registry);

    // 1. Execute up to step 2 (Init -> Br -> Step -> CondBr).
    // Stops at action body block BEFORE VmConvergeDispatchLocal executes!
    let mut state = interp.execute(
        BTreeMap::new(),
        WorldState::new(),
        BTreeSet::new(),
        None,
        None,
        2,
    );

    // 2. Assert that scheduler selection has occurred, but local semantic execution has NOT
    assert_ne!(state.status, VmStatus::Terminated);
    let domain = state.converge_domains.values().last().unwrap();
    assert!(domain.pending_action.is_some(), "R2: PendingAction must be selected by VmConvergeStep");
    let act = domain.pending_action.as_ref().unwrap();
    assert_eq!(act.kind, "local", "R2: Selected action must be local");
    assert_eq!(act.node_id, "root");
    // Node is not yet expanded in the domain
    assert!(domain.visited.is_empty(), "R2: VmConvergeStep must not have executed dispatch_local yet");

    // 3. Resume execution to execute VmConvergeDispatchLocal
    state.status = VmStatus::Running;
    interp.resume(&mut state, 100);

    // 4. Assert that semantic execution has now occurred
    assert_eq!(state.status, VmStatus::Terminated);
    let final_domain = state.converge_domains.values().last().unwrap();
    assert!(!final_domain.visited.is_empty(), "R2: dispatch_local executed on resume");
    assert_eq!(final_domain.visited[0].node_id, "root");
}

#[test]
fn test_slice4_stop_boundary_stopping_between_selection_and_exhaustion() {
    let registry = RegistrySnapshot::default();

    let expected_return_ty = Type::result(
        Type::convergence_outcome(Type::String, Type::exhaustion_report(Type::String)),
        Type::String,
    );

    let mut func = Function::new("main", BlockId(0), expected_return_ty);
    let mut entry = Block::new(BlockId(0), Terminator::Return(Some(ValueId(1))));

    // Converge with max_steps: 0 -> scheduler immediately selects Stop("FuelExhausted")
    entry.instructions.push(Instruction::Converge {
        dest: ValueId(1),
        root_node: "root".to_string(),
        initial_frontier: vec!["root".to_string()],
        successors: std::collections::BTreeMap::new(),
        node_ops: std::collections::BTreeMap::new(),
        satisfier: bando::ir::ops::SatisfierDef::default(),
        partial_map: std::collections::BTreeMap::new(),
        space_faults: std::collections::BTreeMap::new(),
        fault_spec: bando::ir::ops::ConvergeFaultSpec::default(),
        space_ops: vec![],
        satisfier_op: bando::registry::OperationId("local_satisfier".to_string()),
        search_policy: bando::ir::ops::SearchPolicyDescriptor {
            policy_id: "pure_policy".to_string(),
            on_step_failure: "abort".to_string(),
            on_satisfier_error: "abort".to_string(),
            policy_effects: EffectRow::empty(),
        },
        budget_scope: bando::ir::ops::BudgetScopeConfig {
            resource: "usd".to_string(),
            limit: 100,
        },
        max_steps: 0,
        max_satisfaction_attempts: 5,
        space_effects: EffectRow::empty(),
        satisfier_effects: EffectRow::empty(),
        partial_type: Type::String,
        satisfied_type: Type::String,
    });

    func.blocks.insert(BlockId(0), entry);

    let mut module = Module::new("test_s4_stop_boundary");
    module.functions.push(func);

    let mut lowering =
        LoweringContext::with_registry(registry.clone(), CompilerMutations::default());
    let vm_module = lowering.lower_module(&module);

    let mut adapters = RuntimeAdapters::default();
    let mut interp = VmInterpreter::new(&vm_module.functions[0], &mut adapters, &registry);

    // 1. Execute up to step 2 (Init -> Br -> Step -> CondBr(false)).
    // Stops at exit block BEFORE VmConvergeExhaust executes!
    let mut state = interp.execute(
        BTreeMap::new(),
        WorldState::new(),
        BTreeSet::new(),
        None,
        None,
        2,
    );

    // 2. Assert that scheduler Stop decision occurred, but frame is NOT yet terminalized
    assert_ne!(state.status, VmStatus::Terminated);
    let domain = state.converge_domains.values().last().unwrap();
    assert_eq!(
        domain.pending_stop,
        Some("FuelExhausted".to_string()),
        "R2: pending_stop must be recorded by VmConvergeStep"
    );
    assert_eq!(
        domain.frame_status,
        bando::converge::domain::SearchStatus::Searching,
        "R2: frame must NOT be terminal yet"
    );
    assert_eq!(
        domain.exhaustion_reason, None,
        "R2: exhaust() must not have executed yet"
    );

    // 3. Resume execution to execute VmConvergeExhaust -> VmConvergeFinish
    state.status = VmStatus::Running;
    interp.resume(&mut state, 100);

    // 4. Assert that frame is now properly exhausted and terminalized
    assert_eq!(state.status, VmStatus::Terminated);
    let final_domain = state.converge_domains.values().last().unwrap();
    assert_eq!(
        final_domain.frame_status,
        bando::converge::domain::SearchStatus::Exhausted
    );
    assert_eq!(
        final_domain.exhaustion_reason,
        Some("FuelExhausted".to_string())
    );
}
#[test]
fn test_slice4_crash_recovery_instance_reconstruction() {
    let registry = RegistrySnapshot::default();

    let expected_return_ty = Type::result(
        Type::convergence_outcome(Type::String, Type::exhaustion_report(Type::String)),
        Type::String,
    );

    let mut func = Function::new("main", BlockId(0), expected_return_ty);
    func.declared_effects = EffectRow::empty().with(Effect::Act("opRoot".to_string()));

    let mut entry = Block::new(BlockId(0), Terminator::Return(Some(ValueId(1))));

    let mut node_ops = std::collections::BTreeMap::new();
    node_ops.insert(
        "root".to_string(),
        bando::ir::ops::SpaceOpDef {
            op_id: "opRoot".to_string(),
            kind: "external".to_string(),
            cost: 10,
            actual_cost: None,
            request_id: None,
            dedup_capable: true,
            idempotent: true,
            required_effects: vec![Effect::Act("opRoot".to_string())],
        },
    );
    node_ops.insert(
        "succ".to_string(),
        bando::ir::ops::SpaceOpDef {
            op_id: "opSucc".to_string(),
            kind: "local".to_string(),
            cost: 0,
            actual_cost: None,
            request_id: None,
            dedup_capable: true,
            idempotent: true,
            required_effects: vec![],
        },
    );

    let mut succs = std::collections::BTreeMap::new();
    succs.insert("root".to_string(), vec!["succ".to_string()]);

    let mut satisfier_map = std::collections::BTreeMap::new();
    satisfier_map.insert("root".to_string(), serde_json::json!(["ok", false, null]));
    satisfier_map.insert(
        "succ".to_string(),
        serde_json::json!(["ok", true, {"kind": "String", "payload": "T-recovered"}]),
    );

    let mut partial_map = std::collections::BTreeMap::new();
    partial_map.insert(
        "succ".to_string(),
        bando::ir::values::Value::String("P_succ".to_string()),
    );

    let mut fault_spec = bando::ir::ops::ConvergeFaultSpec::default();
    fault_spec.crash_after_settlement = true;

    entry.instructions.push(Instruction::Converge {
        dest: ValueId(1),
        root_node: "root".to_string(),
        initial_frontier: vec!["root".to_string()],
        successors: succs,
        node_ops,
        satisfier: bando::ir::ops::SatisfierDef {
            kind: "local".to_string(),
            effectful_op: None,
            satisfier_map,
        },
        partial_map,
        space_faults: std::collections::BTreeMap::new(),
        fault_spec,
        space_ops: vec![],
        satisfier_op: bando::registry::OperationId("local_satisfier".to_string()),
        search_policy: bando::ir::ops::SearchPolicyDescriptor {
            policy_id: "pure_policy".to_string(),
            on_step_failure: "abort".to_string(),
            on_satisfier_error: "abort".to_string(),
            policy_effects: EffectRow::empty(),
        },
        budget_scope: bando::ir::ops::BudgetScopeConfig {
            resource: "usd".to_string(),
            limit: 100,
        },
        max_steps: 10,
        max_satisfaction_attempts: 5,
        space_effects: EffectRow::empty().with(Effect::Act("opRoot".to_string())),
        satisfier_effects: EffectRow::empty(),
        partial_type: Type::String,
        satisfied_type: Type::String,
    });

    func.blocks.insert(BlockId(0), entry);

    let mut module = Module::new("test_s4_crash");
    module.functions.push(func);

    let mut lowering =
        LoweringContext::with_registry(registry.clone(), CompilerMutations::default());
    let vm_module = lowering.lower_module(&module);

    // 1. Instantiate First Interpreter (runs through Stage -> Emit -> Admit -> Settle and stops before Apply)
    let mut adapters1 = RuntimeAdapters::default();
    let mut interp1 = VmInterpreter::new(&vm_module.functions[0], &mut adapters1, &registry);
    let state1 = interp1.execute(
        BTreeMap::new(),
        WorldState::new(),
        BTreeSet::new(),
        None,
        None,
        100,
    );




    // 2. Assert that state1 is stopped BEFORE Apply (R6)
    assert_ne!(state1.status, VmStatus::Terminated, "R6: state1 must not be terminated before Apply");
    let domain1 = state1.converge_domains.values().last().unwrap();
    let handle_rec = domain1.handles.values().last().unwrap();
    assert!(handle_rec.settlement.is_some(), "R6: settlement must exist before crash");
    assert!(!handle_rec.applied, "R6: applied must be false before Apply");
    assert!(handle_rec.completion.is_some(), "R6: pending completion must exist before Apply");

    // 3. Snapshot the state and completely discard the first interpreter instance (R6)
    let snapshot_json = serde_json::to_string(&state1).expect("Failed to serialize snapshot");
    drop(interp1);
    drop(state1);

    // 4. Deserialize into a new state
    let mut state2: bando::vm::interpreter::VmExecutionState =
        serde_json::from_str(&snapshot_json).expect("Failed to deserialize snapshot");

    // 5. Instantiate a brand NEW interpreter instance
    let mut adapters2 = RuntimeAdapters::default();
    let mut interp2 = VmInterpreter::new(&vm_module.functions[0], &mut adapters2, &registry);

    // 6. Resume execution on the reconstructed state from the saved continuation
    interp2.resume(&mut state2, 100);

    // 7. Verify completion applied exactly once and execution terminated in Satisfied
    assert_eq!(state2.status, VmStatus::Terminated);
    assert_eq!(
        state2.observable_effects,
        vec!["external(opRoot)".to_string()]
    );
    let domain2 = state2.converge_domains.values().last().unwrap();
    assert_eq!(
        domain2.frame_status,
        bando::converge::domain::SearchStatus::Satisfied
    );
}
