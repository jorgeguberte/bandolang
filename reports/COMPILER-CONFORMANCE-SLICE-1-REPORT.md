# SOMA — Compiler Conformance v0 (Slice 1: Result / CFG / Pure-Read-Infer) Execution Report — FINAL ACCEPTANCE (S2 REPAIR COMPLETE)

> **Compiler Conformance v0 — Slice 1 final execution report.**
> 
> 1. **S1 (Region-Local SSA Scoping & Type Registration)**: High-level verifier enforces strict lexical region isolation. Definitions inside `ok_body` and `err_body` are not attributed to the parent block's definition set, preventing leakage past `MatchResult` without explicit transport via block arguments. Region parameters and instructions are registered with their exact types. Tested against region definition leakage and cross-region contamination.
> 2. **S2 (Genuine Killed M10 Mutation on Loop Fixed-Point)**: M10 verifies loop fixed-point analysis on a loop where `loop_header` has exactly one initial incoming edge carrying `LoopFact(%initial)` and the backedge transports fresh SSA `%fresh -> %h` with a divergent fact set. At baseline fixed point, backedge intersection eliminates `LoopFact` (`baseline_facts == EXPECTED_FIXED_POINT`). The single-pass mutant (`m10_single_pass_loop_analysis`) skips backedge re-evaluation, retaining stale facts (`mutant_facts != EXPECTED_FIXED_POINT`), demonstrably killing the mutation.
> 3. **S3 (True Exact Equality Across All 9 Shared Observables)**: `compare_exact_observables` executes full structural equality on all 9 observables: `status`, `return_val`, `effects`, `active_facts`, `latent_facts`, `types`, `bindings`, `lineage`, `diagnostics`. Rejects phantom extra entries and unexpected diagnostics via 4 adversarial negative probes.
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
    6/6 PASS
    - test_c01_pure_value [PASS]
    - test_c02_structured_match_result_and_lowering [PASS]
    - test_c05_c06_diamond_must_fact_merge [PASS]
    - test_r3_ssa_dominance_and_scope_visibility [PASS]
    - test_s1_region_local_definition_isolation_and_dominance [PASS]
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

Negative Verifier Cases (V01–V14, R3 & S1 Verified):
    14/14 PASS
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
    - V13_region_local_def_leak (SsaUseBeforeDef) [PASS]
    - V14_region_cross_use (SsaUseBeforeDef) [PASS]

Real Compiler Mutation Kills (M01–M10, R4 & S2 Verified):
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
    - M10_single_pass_loop_leakage (demonstrably killed via independent fixed-point property) [PASS]

Python Oracle ↔ Rust Toolchain Exact Differential (R5 & S3 Verified):
    8/8 PASS
    - C01_pure_value [PASS]
    - C02_read_ok [PASS]
    - C03_read_err [PASS]
    - C09_infer_ok [PASS]
    - PROBE_extra_lineage_fails [PASS]
    - PROBE_extra_latent_fact_fails [PASS]
    - PROBE_extra_binding_entry_fails [PASS]
    - PROBE_unexpected_diagnostic_fails [PASS]

Item 3 Regression Battery:
    53/53 PASS (zero regressions)

Phase D Lowering Regression Battery:
    81/81 PASS (zero regressions)

Total test suite across repository:
    183/183 PASS
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
