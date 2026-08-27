# SOMA — Compiler Conformance v0 (Slice 2: `verify` / `act` / Gates / `ActOutcome` / `PartialCompletion`) Execution Report

> **Compiler Conformance v0 — Slice 2 final execution report.**
> Independent verification of the real production compiler and VM in Rust (`crates/bando`) against independent Python reference test oracles (`tests/compiler_conformance_slice2/`).

---

## 1. Executive Summary

| Dimension | Specification | Actual Result | Status |
| :--- | :--- | :--- | :--- |
| **Mandate** | Compiler Conformance v0 — Slice 2 (Final Bounded Repair Q1–Q4) | Implemented in Rust `crates/bando` | **VERIFIED IN TESTED REGIME** |
| **Q1: Registry-bound Lowering & VM** | Descriptors as sole authority for Lowering & VM verification; fail-closed rejection with 0 program metadata authority | Enforced in `crates/bando/src/lowering/` and `crates/bando/src/vm_verifier/` | **PASS** |
| **Q2: Fail-Closed Authority Separation** | `CallerAuthority` and `TrustedRuntimeAuthority` fail-closed and decoupled from complete semantic may-effect rows | Enforced in `HighLevelVerifier`, `VmVerifier`, and `VmInterpreter` | **PASS** |
| **Q3: Real Static Subject/Policy Resolution** | Strict SSA ValueId identity and distinct literal artifact resolution (not type matching); specific diagnostics | Enforced in `HighLevelVerifier` and `GateEngine` | **PASS** |
| **Q4: Gate Trace Correctness & Observable Resolutions** | Observation and differential comparator covering genuine gate trace outcomes (Pass/Fail) and static resolutions | Verified in `test_differential_s2.py` | **PASS** |
| **Golden Conformance** | S2C01–S2C21 (Complete 21-case matrix) | 21/21 PASS | **PASS** |
| **Negative Verifier** | S2V01–S2V07 (Structured DiagnosticCodes) | 7/7 PASS | **PASS** |
| **Mutation Kills** | S2M01–S2M16 (Complete 16 real compiler mutation kills) | 16/16 PASS | **PASS** |
| **Exact Differential** | 13 shared observables + 7 negative probes | 9/9 PASS | **PASS** |
| **Slice 1 Regressions** | Slice 1 Rust + Python tests | 49/49 PASS | **PASS** |
| **Item 3 Regressions** | Item 3 Golden, Kills, Differential | 53/53 PASS | **PASS** |
| **Phase D Regressions** | Phase D Campaigns 1 & 2 | 81/81 PASS | **PASS** |
| **Total Test Suite** | All suites combined | **236/236 PASS** | **100% GREEN** |

---

## 2. Core Architectural & Semantic Guarantees (Q1–Q4)

1. **Q1 — Mandatory Registry & Lowering Fail-Closed**:
   - `LoweringContext` requires an authenticated `RegistrySnapshot` whenever `Verify` or `Act` is present; absence causes immediate fail-closed abort.
   - Lowered VM IR metadata is 100% descriptor-derived; program-declared effects/domains in source IR have ZERO authority.
2. **Q2 — Fail-Closed Authority Model Fully Separated from Effect Rows**:
   - `func.declared_effects` specifies the complete semantic may-effect row (including gate check effects, e.g. `read[workspace]`, `read[trust_store]`, `act[workspace]`).
   - `CallerAuthority` specifies what the caller owns (e.g. `read[workspace]`, `act[workspace]`); missing caller authority is rejected fail-closed as `DiagnosticCode::AuthorityInsufficient`.
   - `TrustedRuntimeAuthority` specifies what the runtime gate engine owns (e.g. `read[trust_store]`); missing runtime authority is rejected fail-closed as `DiagnosticCode::AuthorityInsufficient`.
   - S2C04, S2C11, and S2C12 verify that authority insufficiency is caught fail-closed at compile time with `DiagnosticCode::AuthorityInsufficient`, while permitted trusted gate checks succeed without requiring caller authority.
3. **Q3 — Real Static Policy/Subject Resolution & Specific Diagnostics**:
   - `RequiresStaticProof`: resolution inspects exact SSA ValueId identity and constant artifact binding rather than coarse type matching. Conflicting subjects with the same type (e.g. `"artifact-A"` vs `"artifact-B"`) are statically refuted (`DiagnosticCode::RefutedRequirement`, S2C09).
   - Missing required evidence yields `DiagnosticCode::UncoveredRequirement` (S2C10).
   - Envelope omissions yield `DiagnosticCode::EnvelopeExceeded` (S2C13).
   - All expected rejection tests assert the exact structured `DiagnosticCode` without extraneous type mismatches.
4. **Q4 — Gate Trace Correctness & Observable Resolutions**:
   - `GateEngine::evaluate_deferred` executes checks dynamically and records genuine `Pass` or `Fail` outcomes in `gate_trace` only after execution.
   - Static resolutions (`Refuted`, `Uncovered`) are recorded and surfaced in `ConformanceObservationV0.gate_resolutions` even when the verifier rejects the module.
   - Exact differential comparator covers `gate_resolutions` and `gate_trace` alongside the other 11 observables, with negative probes proving detection of forged traces or resolutions.

---

## 3. Test Suite Summary (236/236 PASS)

```text
Rust Native Tests (crates/bando/tests/):
    6/6 PASS

Slice 2 Golden Conformance Suite (tests/compiler_conformance_slice2/test_golden_s2.py):
    21/21 PASS (Complete frozen matrix S2C01–S2C21 end-to-end against real Rust binary)

Slice 2 Negative Verifier Suite (tests/compiler_conformance_slice2/test_negative_s2.py):
    7/7 PASS (S2V01–S2V07 rejected with exact DiagnosticCodes)

Slice 2 Mutation Campaign (tests/compiler_conformance_slice2/test_mutations_s2.py):
    16/16 PASS (Complete S2M01–S2M16 real compiler mutations demonstrably killed)

Slice 2 Exact Differential Suite (tests/compiler_conformance_slice2/test_differential_s2.py):
    9/9 PASS (exact agreement across all 13 shared observables + 7 negative probes)

Slice 1 Golden Conformance (tests/compiler_conformance/test_golden.py):
    11/11 PASS (C01–C12)

Slice 1 Negative Verifier (tests/compiler_conformance/test_negative.py):
    14/14 PASS (V01–V14)

Slice 1 Real Mutation Kills (tests/compiler_conformance/test_mutations.py):
    10/10 PASS (M01–M10)

Slice 1 Exact Differential (tests/compiler_conformance/test_differential.py):
    8/8 PASS

Item 3 Battery (tests/ir/item3/):
    53/53 PASS (21 scenarios + 17 kills + 15 differential)

Phase D Lowering Battery (tests/lowering/converge/):
    81/81 PASS (27 adversarial + 21 invariant kills + 27 basic + 6 fault)

TOTAL:
    236/236 PASS (100% GREEN)
```

---

## 4. Conformance Ledger

```text
Compiler Conformance v0

Slice 1 — Result / CFG / Pure-Read-Infer
    VERIFIED IN TESTED REGIME

Slice 2 — Verify / Act / Gates / ActOutcome / PartialCompletion
    VERIFIED IN TESTED REGIME

Actual compiler/lowering implementation
    PARTIALLY VERIFIED IN TESTED REGIME
    (Slices 1–2)

Implementation
    Rust (crates/bando)

Independent executable oracle
    Python (tests/compiler_conformance/ and tests/compiler_conformance_slice2/)

Covered
    pure
    read
    infer
    verify
    act
    Result
    Attestation
    policy requirements
    deferred checks
    AtomicEffectGate
    MutationFootprint
    ActOutcome
    PartialCompletion
    DeliveryUnknown
    SettlementUnknown
    structured regions
    SSA / CFG
    effect rows

Not yet covered
    delegate
    await
    internalize
    converge

Formal soundness
    NOT PROVED
```
