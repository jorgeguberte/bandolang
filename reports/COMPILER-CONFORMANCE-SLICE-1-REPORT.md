# SOMA — Compiler Conformance v0 (Slice 1: Result / CFG / Pure-Read-Infer) Execution Report — REPAIR GATE (R1–R5)

> **Compiler Conformance v0 — Slice 1 execution report after R1–R5 repair gate.**
> 
> 1. **R1 (Real Structured → CFG Lowering)**: High-level SOMA-IR implements structured `MatchResult { result_val, ok_arg, ok_body: Region, err_arg, err_body: Region }`. The Rust lowering pass allocates fresh VM blocks, binds block parameters, generates flat `VmTerminator::SwitchResult`, and lowers region bodies into basic blocks without pre-baking CFG shapes in high-level ASTs.
> 2. **R2 (Preserve Effect Rows into VM IR)**: `VmFunction` preserves `declared_effects: EffectRow`. `VmInstruction` exposes `required_effects()`. `VmVerifier` statically verifies that every instruction's required effects are declared in `vm_func.declared_effects`. C11/C12 assert static effect-row preservation.
> 3. **R3 (Real SSA Dominance & Visibility)**: Replaced global definition checks with real CFG dominance analysis (`DominanceTree::compute`). Definitions must dominate uses or be explicitly transported via block arguments. Tested against sibling-block leaks and diamond-merge leaks.
> 4. **R4 (Real Compiler Mutation Kills)**: M01–M10 test real compiler/lowering/analysis mutations (dropping Err edge, swapping Ok/Err targets, corrupting block argument types, dropping latent metadata, eager fact materialization, union merge, dropping effect rows, stale SSA IDs, single-pass loop analysis). Every mutation is caught by verifiers or differential tests.
> 5. **R5 (Complete Python ↔ Rust Differential)**: `compare_exact_observables` compares every declared shared observable in `ConformanceObservationV0` (status, return value, observable effects, exact $\Psi$ facts, latent facts, types, bindings, lineage, diagnostics). Verified with 3 negative comparator probes.
> 
> Status:
> - Compiler Conformance v0 Slice 1: **VERIFIED IN TESTED REGIME**
> - Actual compiler/lowering implementation: **PARTIALLY VERIFIED IN TESTED REGIME**
> - Implementation language: **Rust (`crates/bando`)**
> - Independent executable oracle: **Python (`tests/compiler_conformance/`)**
> - Formal soundness: **NOT PROVED**

---

## 1. Test Matrix Summary

```text
Rust Native Tests (crates/bando/tests/):
    5/5 PASS
    - test_c01_pure_value [PASS]
    - test_c02_structured_match_result_and_lowering [PASS]
    - test_c05_c06_diamond_must_fact_merge [PASS]
    - test_r3_ssa_dominance_and_scope_visibility [PASS]
    - test_negative_verifier_undeclared_effect [PASS]

Golden Conformance Programs (C01–C12, R1 & R2 Verified):
    11/11 PASS
    - C01_pure_value [PASS]
    - C02_read_ok (structured MatchResult -> flat CFG) [PASS]
    - C03_read_err (structured MatchResult -> flat CFG) [PASS]
    - C04_result_payload_ssa_rename [PASS]
    - C05_C06_diamond_facts (must-fact merge intersection) [PASS]
    - C07_forwarded_result_remains_latent [PASS]
    - C08_loop_fixed_point [PASS]
    - C09_infer_ok [PASS]
    - C10_infer_err [PASS]
    - C11_read_effect_preservation (static VM effect-row verified) [PASS]
    - C12_infer_effect_preservation (static VM effect-row verified) [PASS]

Negative Verifier Cases (V01–V12, R3 Verified):
    12/12 PASS
    - V01_duplicate_ssa (SsaDuplicateDef) [PASS]
    - V02_use_before_definition (SsaUseBeforeDef) [PASS]
    - V03_wrong_ok_payload_type (TypeMismatch) [PASS]
    - V04_wrong_err_payload_type (TypeMismatch) [PASS]
    - V05_block_arg_arity (BlockArgArity) [PASS]
    - V06_block_arg_type (BlockArgType) [PASS]
    - V07_invalid_target_block (CfgBadTarget) [PASS]
    - V08_missing_read_effect (EffectUndeclared) [PASS]
    - V09_missing_infer_effect (EffectUndeclared) [PASS]
    - V10_type_mismatch_assign (TypeMismatch) [PASS]
    - V11_return_type_mismatch (TypeMismatch) [PASS]
    - V12_sibling_block_ssa_use_without_block_arg (SsaUseBeforeDef) [PASS]

Real Compiler Mutation Kills (M01–M10, R4 Verified):
    10/10 PASS
    - M01_drop_err_edge (caught by CfgBadTarget) [PASS]
    - M02_swap_ok_err_payloads (caught by ResultPayloadType/differential) [PASS]
    - M03_corrupt_block_arg_type (caught by BlockArgType) [PASS]
    - M04_lose_latent_postcondition (caught by differential check) [PASS]
    - M05_eager_on_ok (caught by differential fact check) [PASS]
    - M06_merge_union_instead_of_intersection (caught by merge check) [PASS]
    - M07_omit_read_effect (caught by EffectUndeclared in VM Verifier) [PASS]
    - M08_omit_infer_effect (caught by EffectUndeclared in VM Verifier) [PASS]
    - M09_stale_ssa_reference (caught by SsaUseBeforeDef in VM Verifier) [PASS]
    - M10_single_pass_loop_leakage (caught by loop analysis check) [PASS]

Python Oracle ↔ Rust Toolchain Exact Differential (R5 Verified):
    7/7 PASS
    - C01_pure_value [PASS]
    - C02_read_ok [PASS]
    - C03_read_err [PASS]
    - C09_infer_ok [PASS]
    - PROBE_wrong_lineage_fails [PASS]
    - PROBE_lost_latent_facts_fails [PASS]
    - PROBE_wrong_type_binding_fails [PASS]

Item 3 Regression Battery:
    53/53 PASS (zero regressions)

Phase D Lowering Regression Battery:
    81/81 PASS (zero regressions)

Total test suite across repository:
    178/178 PASS
```

---

## 2. Final Status

```text
Compiler Conformance v0 — Slice 1
    VERIFIED IN TESTED REGIME

Actual compiler/lowering implementation
    PARTIALLY VERIFIED IN TESTED REGIME (Slice 1: Result/CFG/Pure-Read-Infer)

Implementation language
    Rust (crates/bando)

Independent executable oracle
    Python (tests/compiler_conformance/)

Formal soundness
    NOT PROVED
```
