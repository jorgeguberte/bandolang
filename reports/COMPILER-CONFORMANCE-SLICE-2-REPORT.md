# SOMA — Compiler Conformance v0 (Slice 2: `verify` / `act` / Gates / `ActOutcome` / `PartialCompletion`) Execution Report

> **Compiler Conformance v0 — Slice 2 final execution report.**
> Independent verification of the real production compiler and VM in Rust (`crates/bando`) against independent Python reference test oracles (`tests/compiler_conformance_slice2/`).

---

## 1. Executive Summary

| Dimension | Specification | Actual Result | Status |
| :--- | :--- | :--- | :--- |
| **Mandate** | Compiler Conformance v0 — Slice 2 (Final Bounded Repair Q1–Q4) | Implemented in Rust `crates/bando` | **VERIFIED IN TESTED REGIME** |
| **Q1: Registry-bound Lowering & VM** | Descriptors as sole authority for Lowering & VM verification; program-supplied metadata has 0 authority | Enforced in `crates/bando/src/lowering/` and `crates/bando/src/vm_verifier/` | **PASS** |
| **Q2: Fail-Closed Authority Separation** | `CallerAuthority` and `TrustedRuntimeAuthority` decoupled from complete semantic may-effect rows | Enforced in `HighLevelVerifier`, `VmVerifier`, and `VmInterpreter` | **PASS** |
| **Q3: Real Static Subject/Policy Resolution** | Strict SSA identity / artifact resolution (not mere type matching); diagnostic-specific assertions | Enforced in `HighLevelVerifier` and `GateEngine` | **PASS** |
| **Q4: Complete P5 Observable Trace** | Observation and differential comparator covering `gate_resolutions` and `gate_trace` + negative probes | Verified in `test_differential_s2.py` | **PASS** |
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

1. **Q1 — Registry-Bound Lowering and VM Verification**:
   - High-level IR instructions `Instruction::Verify` and `Instruction::Act` reference exclusively `VerifierId` and `OperationId`.
   - `LoweringContext` takes `RegistrySnapshot`: lowering generates `VmInstruction::VmVerify` and `VmInstruction::VmAct` deriving effective $\Sigma_V$, predicate, subject type, target domain, and gate effects directly from authenticated descriptors. Program-supplied metadata in high-level IR has zero authority over lowered VM IR.
2. **Q2 — Fail-Closed Authority Model Fully Separated from Effect Rows**:
   - `func.declared_effects` specifies the complete semantic may-effect row (including gate check effects, e.g. `read[workspace]`, `read[trust_store]`, `act[workspace]`).
   - `CallerAuthority` specifies what the caller owns (e.g. `read[workspace]`, `act[workspace]`).
   - `TrustedRuntimeAuthority` specifies what the runtime gate engine owns (e.g. `read[trust_store]`).
   - S2C04, S2C11, and S2C12 verify that authority insufficiency is caught fail-closed at compile time with `DiagnosticCode::AuthorityInsufficient`, while permitted trusted gate checks succeed without requiring caller authority.
3. **Q3 — Real Static Policy/Subject Resolution & Specific Diagnostics**:
   - `RequiresStaticProof`: resolution inspects exact SSA ValueId identity and constant artifact binding rather than coarse type matching. Conflicting subjects are statically refuted (`DiagnosticCode::RefutedRequirement`, S2C09).
   - Missing required evidence yields `DiagnosticCode::UncoveredRequirement` (S2C10).
   - Envelope omissions yield `DiagnosticCode::EnvelopeExceeded` (S2C13).
4. **Q4 — Complete Gate Resolution & Gate Trace Observables**:
   - `ConformanceObservationV0` and the exact differential comparator track `gate_resolutions` (`Proved`, `Deferred`, `Refuted`, `Uncovered`) and `gate_trace` (`CheckTrustPolicy`, `CheckSubjectBinding`, `CheckStateBaseVersion` with `authority_source`, `effects`, and `result`).
   - Negative probes verify detection of forged resolutions, forged authority sources, extra mutations, corrupted worlds, and stale current facts.

---

## 3. Test Suite Summary (236/236 PASS)

```text
Rust Native Tests (crates/bando/tests/):
    6/6 PASS (includes verify, act, and gate lowering tests)

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
