# SOMA — Compiler Conformance v0 (Slice 1: Result / CFG / Pure-Read-Infer) Execution Report

> **Compiler Conformance v0 — Slice 1 execution report.**
> Independent implementation of the real SOMA toolchain in Rust (`crates/bando`) verified against independent Python semantic reference models and differential oracles.
> 
> Status:
> - Compiler Conformance v0 Slice 1: **VERIFIED IN TESTED REGIME**
> - Actual compiler/lowering implementation: **PARTIALLY VERIFIED IN TESTED REGIME**
> - Implementation language: **Rust**
> - Independent executable oracle: **Python**
> - Formal soundness: **NOT PROVED**

---

## 1. Technological Division & Independence

```text
Rust Toolchain (Production Implementation):
    crates/bando/src/
      ├── ir/              (Types, ValueId, BlockId, OpId, LatentPostconditions, Fact, EffectRow, ops)
      ├── verifier/        (Single SSA def, use-before-def, types, effects, MatchResult verification)
      ├── lowering/        (Lowering from structured soma.* to flat soma.vm.* CFG)
      ├── vm_ir/           (SOMA-VM IR, typed block arguments, VmRead, VmInfer, SwitchResult, no phi nodes)
      ├── vm_verifier/     (VM-level SSA, block argument arity/type matching, CFG target validation)
      ├── analysis/        (PathFactAnalyzer worklist fixed-point analyzer over CFG edges)
      ├── vm/              (Deterministic VM interpreter with ReadAdapter and InferAdapter traits)
      ├── diagnostics/     (Structured DiagnosticCode enumeration)
      ├── printer/         (Pretty printer for debugging)
      └── conformance/     (JSON protocol runner `bando-conformance`)

Python Conformance Harness (Independent Oracle):
    tests/compiler_conformance/
      ├── protocol.py          (Interchange bridge to Rust CLI `bando-conformance`)
      ├── test_golden.py       (Golden programs C01–C12)
      ├── test_negative.py     (Negative verifier tests V01–V12)
      ├── test_mutations.py    (Mutation kills M01–M10)
      └── test_differential.py (Exact observable differential comparator)
```

---

## 2. Test Execution Matrix

```text
Rust Native Unit/Integration Tests:
    4/4 PASS
    - test_c01_pure_value [PASS]
    - test_c02_read_ok_and_latent_facts [PASS]
    - test_c05_c06_diamond_must_fact_merge [PASS]
    - test_negative_verifier_undeclared_effect [PASS]

Golden Conformance Programs (C01–C12):
    11/11 PASS
    - C01_pure_value: constant emission and termination [PASS]
    - C02_read_ok: read execution, Ok refinement, on_ok ObservedAt fact instantiation [PASS]
    - C03_read_err: read error handling, Err refinement, ErrorOccurred fact instantiation [PASS]
    - C04_result_payload_ssa_rename: block argument transfer and SSA renaming [PASS]
    - C05_C06_diamond_facts: must-fact intersection merge (branch-only fact lost, common fact preserved) [PASS]
    - C07_forwarded_result_remains_latent: unrefined forwarded Result keeps postconditions latent [PASS]
    - C08_loop_fixed_point: static dataflow fixed-point convergence over back-edges [PASS]
    - C09_infer_ok: infer execution, Ok refinement, InferredFact instantiation [PASS]
    - C10_infer_err: infer error handling, Err refinement [PASS]
    - C11_read_effect_preservation: observable effect trace records read[domain] [PASS]
    - C12_infer_effect_preservation: observable effect trace records infer [PASS]

Negative Verifier Cases (V01–V12):
    12/12 PASS
    - V01_duplicate_ssa: rejected with SsaDuplicateDef [PASS]
    - V02_use_before_definition: rejected with SsaUseBeforeDef [PASS]
    - V03_wrong_ok_payload_type: rejected with ResultPayloadType [PASS]
    - V04_wrong_err_payload_type: rejected with ResultPayloadType [PASS]
    - V05_block_arg_arity: rejected with BlockArgArity [PASS]
    - V06_block_arg_type: rejected with BlockArgType [PASS]
    - V07_invalid_target_block: rejected with CfgBadTarget [PASS]
    - V08_missing_read_effect: rejected with EffectUndeclared [PASS]
    - V09_missing_infer_effect: rejected with EffectUndeclared [PASS]
    - V10_type_mismatch_assign: rejected with TypeMismatch [PASS]
    - V11_return_type_mismatch: rejected with TypeMismatch [PASS]
    - V12_cond_br_non_bool: rejected with TypeMismatch [PASS]

Mutation Kills (M01–M10):
    10/10 PASS
    - M01_drop_err_edge: caught by CfgBadTarget [PASS]
    - M02_swap_ok_err_payloads: caught by ResultPayloadType [PASS]
    - M03_wrong_block_arg_type: caught by BlockArgType [PASS]
    - M04_lose_latent_postcondition: caught by missing ObservedAt fact [PASS]
    - M05_eager_on_ok: caught by absence of premature fact in unrefined block [PASS]
    - M06_merge_union_instead_of_intersection: caught by absence of exclusive branch fact at merge [PASS]
    - M07_omit_read_effect: caught by EffectUndeclared [PASS]
    - M08_omit_infer_effect: caught by EffectUndeclared [PASS]
    - M09_stale_ssa_reference: caught by SsaUseBeforeDef [PASS]
    - M10_single_pass_loop_leakage: caught by absence of unproven loop body fact on exit path [PASS]

Python Oracle ↔ Rust Toolchain Differential Testing:
    4/4 PASS (exact agreement across return value, effects, path facts Ψ, and status)

Phase D Lowering Regression Battery:
    81/81 PASS (zero regressions)

Item 3 Regression Battery:
    53/53 PASS (zero regressions)
```

---

## 3. Scope Covered vs Not Covered

```text
Covered in Slice 1:
    - Pure constant values
    - soma.read & soma.infer
    - Result<T,E> and LatentPostconditions
    - Result refinement (MatchResult / SwitchResult)
    - Typed SSA values (ValueId)
    - Basic blocks and typed block arguments
    - Flat CFG lowering (no phi nodes)
    - Worklist / fixed-point path fact dataflow analysis
    - Effect rows and effect checking
    - SOMA-VM interpreter with deterministic test adapters

Not Yet Covered (Reserved for Subsequent Slices):
    - Slice 2: verify / act / gates / ActOutcome / PartialCompletion
    - Slice 3: delegate / await / internalize / ChildHandle / effect unions
    - Slice 4: converge lowering & full Phase D runtime pressure
```

---

## 4. Final Status

```text
Compiler Conformance v0 — Slice 1
    VERIFIED IN TESTED REGIME

Actual compiler/lowering implementation
    PARTIALLY VERIFIED IN TESTED REGIME (Slice 1: Result/CFG/Pure-Read-Infer)

Implementation language
    Rust

Independent executable oracle
    Python

Formal soundness
    NOT PROVED
```
