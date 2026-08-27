use std::collections::BTreeMap;

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
    lowering::LoweringContext,
    verifier::HighLevelVerifier,
    vm::{
        adapters::RuntimeAdapters,
        interpreter::VmStatus,
        VmInterpreter,
    },
    vm_verifier::VmVerifier,
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

    let adapters = RuntimeAdapters::default();
    let interp = VmInterpreter::new(&vm_module.functions[0], &adapters);
    let state = interp.execute(BTreeMap::new(), 100);

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
            args: vec![FactArg::Symbol("$value".to_string()), FactArg::Literal("docs".to_string())],
        }],
        on_err: Vec::new(),
    };

    // R1: High-level structured MatchResult with Region
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

    // R1: Lowering flattens structured regions into CFG blocks and SwitchResult
    let mut lowering = LoweringContext::new();
    let vm_module = lowering.lower_module(&module);
    assert!(VmVerifier::verify_module(&vm_module).is_ok());

    // R2: Assert static effect-row preservation in VM function
    let vm_func = &vm_module.functions[0];
    assert!(vm_func.declared_effects.contains(&Effect::Read("docs".to_string())));

    let adapters = RuntimeAdapters::default();
    let interp = VmInterpreter::new(vm_func, &adapters);
    let state = interp.execute(BTreeMap::new(), 100);

    assert_eq!(state.status, VmStatus::Terminated);
    assert_eq!(state.return_value, Some(Value::String("data_of(docs)".to_string())));
    assert_eq!(state.observable_effects, vec!["read[docs]"]);

    let expected_fact = Fact::new("ObservedAt", vec![FactArg::Symbol("v2".to_string()), FactArg::Literal("docs".to_string())]);
    assert!(state.active_facts.contains(&expected_fact));
}

#[test]
fn test_c05_c06_diamond_must_fact_merge() {
    let mut func = Function::new("main", BlockId(0), Type::String);
    func.declared_effects = EffectRow::empty().with(Effect::Read("doc".to_string()));

    let latent = LatentPostconditions {
        on_ok: vec![
            FactTemplate { predicate: "ExclusiveOk".to_string(), args: vec![FactArg::Symbol("$value".to_string())] },
            FactTemplate { predicate: "CommonFact".to_string(), args: vec![FactArg::Literal("doc".to_string())] },
        ],
        on_err: vec![
            FactTemplate { predicate: "CommonFact".to_string(), args: vec![FactArg::Literal("doc".to_string())] },
        ],
    };

    let mut entry = Block::new(
        BlockId(0),
        Terminator::MatchResult {
            result_val: ValueId(1),
            ok_arg: ValueId(2),
            ok_body: Region::new(RegionTerminator::Br { target: BlockId(3), args: vec![ValueId(2)] }),
            err_arg: ValueId(3),
            err_body: Region::new(RegionTerminator::Br { target: BlockId(3), args: vec![ValueId(3)] }),
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
    let merge_facts = analysis.block_in_facts.get(&bando::vm_ir::VmBlockId(3)).unwrap();

    let common_fact = Fact::new("CommonFact", vec![FactArg::Literal("doc".to_string())]);
    assert!(merge_facts.contains(&common_fact));
    assert!(!merge_facts.iter().any(|f| f.predicate == "ExclusiveOk"));
}

#[test]
fn test_r3_ssa_dominance_and_scope_visibility() {
    // Dominating entry value used in downstream block => ACCEPTED
    let mut func_ok = Function::new("ok", BlockId(0), Type::I64);
    let mut b0 = Block::new(BlockId(0), Terminator::Br { target: BlockId(1), args: vec![] });
    b0.instructions.push(Instruction::Pure { dest: ValueId(1), val: Value::I64(10), ty: Type::I64 });
    func_ok.blocks.insert(BlockId(0), b0);

    let b1 = Block::new(BlockId(1), Terminator::Return(Some(ValueId(1)))); // Value 1 from dominating b0
    func_ok.blocks.insert(BlockId(1), b1);

    let mut mod_ok = Module::new("m_ok");
    mod_ok.functions.push(func_ok);
    assert!(HighLevelVerifier::verify_module(&mod_ok).is_ok());

    // Sibling block value used without block argument => REJECTED
    let mut func_bad = Function::new("bad", BlockId(0), Type::I64);
    let b_entry = Block::new(BlockId(0), Terminator::CondBr { cond: ValueId(1), true_target: BlockId(1), true_args: vec![], false_target: BlockId(2), false_args: vec![] });
    func_bad.params.push((ValueId(1), Type::Bool));
    func_bad.blocks.insert(BlockId(0), b_entry);

    let mut b_left = Block::new(BlockId(1), Terminator::Return(Some(ValueId(2))));
    b_left.instructions.push(Instruction::Pure { dest: ValueId(2), val: Value::I64(100), ty: Type::I64 });
    func_bad.blocks.insert(BlockId(1), b_left);

    let b_right = Block::new(BlockId(2), Terminator::Return(Some(ValueId(2)))); // Value 2 defined in sibling block 1!
    func_bad.blocks.insert(BlockId(2), b_right);

    let mut mod_bad = Module::new("m_bad");
    mod_bad.functions.push(func_bad);
    let diags = HighLevelVerifier::verify_module(&mod_bad).unwrap_err();
    assert!(diags.iter().any(|d| d.code == DiagnosticCode::SsaUseBeforeDef));
}

#[test]
fn test_s1_region_local_definition_isolation_and_dominance() {
    // 1. Dominating parent value used inside both ok_body and err_body => ACCEPTED
    let mut func_dom = Function::new("main", BlockId(0), Type::I64);
    let mut entry = Block::new(
        BlockId(0),
        Terminator::MatchResult {
            result_val: ValueId(1),
            ok_arg: ValueId(3),
            ok_body: Region::new(RegionTerminator::Return(Some(ValueId(2)))), // Value 2 from parent!
            err_arg: ValueId(4),
            err_body: Region::new(RegionTerminator::Return(Some(ValueId(2)))), // Value 2 from parent!
        },
    );
    entry.instructions.push(Instruction::Pure { dest: ValueId(1), val: Value::I64(10), ty: Type::result(Type::I64, Type::I64) });
    entry.instructions.push(Instruction::Pure { dest: ValueId(2), val: Value::I64(100), ty: Type::I64 });
    func_dom.blocks.insert(BlockId(0), entry);

    let mut mod_dom = Module::new("m_dom");
    mod_dom.functions.push(func_dom);
    assert!(HighLevelVerifier::verify_module(&mod_dom).is_ok());

    // 2. Region-local Ok definition used outside MatchResult without block arg => REJECTED
    let mut func_leak = Function::new("main", BlockId(0), Type::I64);
    let mut entry_leak = Block::new(
        BlockId(0),
        Terminator::MatchResult {
            result_val: ValueId(1),
            ok_arg: ValueId(2),
            ok_body: Region {
                instructions: vec![Instruction::Pure { dest: ValueId(4), val: Value::I64(42), ty: Type::I64 }],
                terminator: RegionTerminator::Br { target: BlockId(1), args: vec![] }, // Did not transport 4!
            },
            err_arg: ValueId(3),
            err_body: Region::new(RegionTerminator::Br { target: BlockId(1), args: vec![] }),
        },
    );
    entry_leak.instructions.push(Instruction::Pure { dest: ValueId(1), val: Value::I64(10), ty: Type::result(Type::I64, Type::I64) });
    func_leak.blocks.insert(BlockId(0), entry_leak);

    let b_merge = Block::new(BlockId(1), Terminator::Return(Some(ValueId(4)))); // ILLEGAL USE OF REGION-LOCAL VALUE 4!
    func_leak.blocks.insert(BlockId(1), b_merge);

    let mut mod_leak = Module::new("m_leak");
    mod_leak.functions.push(func_leak);
    let diags = HighLevelVerifier::verify_module(&mod_leak).unwrap_err();
    assert!(diags.iter().any(|d| d.code == DiagnosticCode::SsaUseBeforeDef));

    // 3. Region-local Err definition used from Ok region => REJECTED
    let mut func_cross = Function::new("main", BlockId(0), Type::I64);
    let mut entry_cross = Block::new(
        BlockId(0),
        Terminator::MatchResult {
            result_val: ValueId(1),
            ok_arg: ValueId(2),
            ok_body: Region::new(RegionTerminator::Return(Some(ValueId(4)))), // Uses Value 4 defined in err_body!
            err_arg: ValueId(3),
            err_body: Region {
                instructions: vec![Instruction::Pure { dest: ValueId(4), val: Value::I64(99), ty: Type::I64 }],
                terminator: RegionTerminator::Return(Some(ValueId(4))),
            },
        },
    );
    entry_cross.instructions.push(Instruction::Pure { dest: ValueId(1), val: Value::I64(10), ty: Type::result(Type::I64, Type::I64) });
    func_cross.blocks.insert(BlockId(0), entry_cross);

    let mut mod_cross = Module::new("m_cross");
    mod_cross.functions.push(func_cross);
    let diags_cross = HighLevelVerifier::verify_module(&mod_cross).unwrap_err();
    assert!(diags_cross.iter().any(|d| d.code == DiagnosticCode::SsaUseBeforeDef));
}

#[test]
fn test_negative_verifier_undeclared_effect() {
    let mut func = Function::new("main", BlockId(0), Type::String);
    let mut entry = Block::new(BlockId(0), Terminator::Return(None));
    entry.instructions.push(Instruction::Read {
        dest: ValueId(1),
        domain: "secret".to_string(),
        ok_type: Type::String,
        err_type: Type::String,
        latent: LatentPostconditions::default(),
    });
    func.blocks.insert(BlockId(0), entry);

    let mut module = Module::new("test_neg");
    module.functions.push(func);

    let diags = HighLevelVerifier::verify_module(&module).unwrap_err();
    assert!(diags.iter().any(|d| d.code == DiagnosticCode::EffectUndeclared));
}
