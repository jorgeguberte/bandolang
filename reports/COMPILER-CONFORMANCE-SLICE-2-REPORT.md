# SOMA — Compiler Conformance v0 (Slice 2: `verify` / `act` / Gates / `ActOutcome` / `PartialCompletion`) Execution Report

> **Compiler Conformance v0 — Slice 2 final execution report.**
> Independent verification of the real production compiler and VM in Rust (`crates/bando`) against independent Python reference test oracles (`tests/compiler_conformance_slice2/`).

---

## 1. Executive Summary

| Dimension | Specification | Actual Result | Status |
| :--- | :--- | :--- | :--- |
| **Mandate** | Compiler Conformance v0 — Slice 2 (Bounded Repair Gate) | Implemented in Rust `crates/bando` | **VERIFIED IN TESTED REGIME** |
| **P1: Trusted Descriptors** | `VerifierDescriptor`, `OperationDescriptor` as sole source of truth (fail-closed, no synthetic fallbacks) | Enforced in `crates/bando/src/verifier/` and `crates/bando/src/vm/` | **PASS** |
| **P2: Real Authority Model** | `CallerAuthority`, `TrustedRuntimeAuthority`, `AuthoritySource` with strict separation from effect rows | Implemented in `crates/bando/src/registry/` and `crates/bando/src/gate/` | **PASS** |
| **P3: Requirement Resolution** | 4 distinct reachable states (`Proved`, `Deferred`, `Refuted`, `Uncovered`) + declared envelope checks | Enforced in `HighLevelVerifier` and `GateEngine` | **PASS** |
| **P4: Complete Outcome / World / TOCTOU** | Deterministic TOCTOU inter-check-and-commit race falsification; complete golden matrix | Verified in `test_golden_s2.py` and `test_mutations_s2.py` | **PASS** |
| **P5: Slice 2 Differential** | Exact comparator covering 11 observables including `mutation_trace` and `final_world` + 5 negative probes | Verified in `test_differential_s2.py` | **PASS** |
| **Golden Conformance** | S2C01–S2C21 (Complete 21-case matrix) | 21/21 PASS | **PASS** |
| **Negative Verifier** | S2V01–S2V07 (Structured DiagnosticCodes) | 7/7 PASS | **PASS** |
| **Mutation Kills** | S2M01–S2M16 (Complete 16 real compiler mutation kills) | 16/16 PASS | **PASS** |
| **Exact Differential** | 11 shared observables + 5 negative probes | 7/7 PASS | **PASS** |
| **Slice 1 Regressions** | Slice 1 Rust + Python tests | 49/49 PASS | **PASS** |
| **Item 3 Regressions** | Item 3 Golden, Kills, Differential | 53/53 PASS | **PASS** |
| **Phase D Regressions** | Phase D Campaigns 1 & 2 | 81/81 PASS | **PASS** |
| **Total Test Suite** | All suites combined | **234/234 PASS** | **100% GREEN** |

---

## 2. Core Architectural & Semantic Guarantees (P1–P5)

1. **P1 — Trusted Descriptors as Source of Truth**:
   - `Instruction::Verify` references `VerifierId`; its effective $\Sigma_V$, output predicate, subject type, and version binding come strictly from the authenticated `VerifierDescriptor`. Unknown verifiers fail closed (`DiagnosticCode::UnknownVerifier`).
   - `Instruction::Act` references `OperationId`; its effective target domain, requirements, declared envelope, footprint, and atomicity come strictly from `OperationDescriptor`. Unknown operations fail closed (`DiagnosticCode::UnknownOperation`).
2. **P2 — Explicit Authority Model**:
   - `CallerAuthority` and `TrustedRuntimeAuthority` decouple authority attribution from semantic effect rows.
   - `Verify`: caller authority must cover $\Sigma_V$ (S2C04).
   - `Act`: caller authority must cover target `act[D]` (S2C11).
   - Trusted gate check: executed with `TrustedRuntimeAuthority` without requiring caller authority (S2C12, S2M07 killed).
   - Semantic $\Sigma_{act} = \{\text{act}[D]\} \cup \Sigma_{gate}$ includes all observable effects.
3. **P3 — Decidable Requirement Resolution & Envelope**:
   - Four distinct reachable states: `Proved` (statically discharged with matching static evidence, S2C06), `Deferred` (dynamic state/trust checks needed, S2C07/S2C08), `Refuted` (statically refuted, S2C09), `Uncovered` (missing evidence, S2C10).
   - Envelope enforcement: $\Sigma_{act} \subseteq \text{OperationDescriptor.declared\_envelope}$ (S2C13).
4. **P4 — Complete Outcome / World / TOCTOU Falsification**:
   - Deterministic hook mutates state version between gate check and commit: baseline atomic revalidation rejects commit with 0 writes, while mutant `s2m08_toctou_revalidation_omitted` incorrectly commits.
   - Disjoint algebra of outcomes: `Success`, `CleanFailure`, `PartialCompletion`, `DeliveryUnknown`, `SettlementUnknown`. Atomic operations returning partial yield `ProtocolViolation` (S2C16, S2M13 killed).
   - Invalidation of `CurrentState` facts upon writes with preservation of `Historical` provenance facts (S2C20, S2C21, S2M14/S2M15 killed).
5. **P5 — Exact Shared Observable Comparator**:
   - Exact differential verification over all 11 shared observables (status, return_val, effects, active_facts, latent_facts, types, bindings, lineage, diagnostics, mutation_trace, final_world) + 5 negative probes.

---

## 3. Test Suite Summary (234/234 PASS)

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
    7/7 PASS (exact agreement across all 11 shared observables + 5 negative probes)

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
    234/234 PASS (100% GREEN)
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
