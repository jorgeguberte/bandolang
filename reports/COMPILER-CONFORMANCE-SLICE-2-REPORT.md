# SOMA — Compiler Conformance v0 (Slice 2: `verify` / `act` / Gates / `ActOutcome` / `PartialCompletion`) Execution Report

> **Compiler Conformance v0 — Slice 2 final execution report.**
> Independent verification of the real production compiler and VM in Rust (`crates/bando`) against independent Python reference test oracles (`tests/compiler_conformance_slice2/`).

---

## 1. Executive Summary

| Dimension | Specification | Actual Result | Status |
| :--- | :--- | :--- | :--- |
| **Mandate** | Compiler Conformance v0 — Slice 2 | Implemented in Rust `crates/bando` | **VERIFIED IN TESTED REGIME** |
| **Production IR & Types** | `verify`, `act`, `Attestation`, `ActOutcome`, `PartialCompletion`, `Unknown` | Fully implemented in Rust AST, VM IR, Verifiers, and Interpreter | **PASS** |
| **Registry & Trust Model** | `VerifierDescriptor`, `OperationDescriptor`, `TrustPolicy`, `RegistrySnapshot` | Implemented in `crates/bando/src/registry/` | **PASS** |
| **Gate Resolution** | `RequirementResolution`, `DeferredCheck`, `GateEngine`, `GateWitness` | Implemented in `crates/bando/src/gate/` | **PASS** |
| **World State & Footprint** | `WorldState`, `MutationFootprint`, `WorldError` | Implemented in `crates/bando/src/world/` | **PASS** |
| **Effect Rules** | Rules #1, #4, #5, #9, #10, #11, #15, #18, #20, #24 | Fully enforced statically and at runtime | **PASS** |
| **Golden Conformance** | S2C01–S2C21 (12 battery cases) | 12/12 PASS | **PASS** |
| **Negative Verifier** | S2V01–S2V05 (Structured DiagnosticCodes) | 5/5 PASS | **PASS** |
| **Mutation Kills** | S2M01–S2M16 (15 real compiler mutation kills) | 15/15 PASS | **PASS** |
| **Exact Differential** | 9 shared observables + 4 negative probes | 6/6 PASS | **PASS** |
| **Slice 1 Regressions** | Slice 1 Rust + Python tests | 49/49 PASS | **PASS** |
| **Item 3 Regressions** | Item 3 Golden, Kills, Differential | 53/53 PASS | **PASS** |
| **Phase D Regressions** | Phase D Campaigns 1 & 2 | 81/81 PASS | **PASS** |
| **Total Test Suite** | All suites combined | **221/221 PASS** | **100% GREEN** |

---

## 2. Core Architectural & Semantic Guarantees

1. **Rule #1 (`verify` is NOT a fifth effect)**:
   $$\text{EffectsOf}(\text{verify}(s, V)) = \Sigma_V$$
   `Instruction::Verify` and `VmInstruction::VmVerify` inherit exactly the verifier's effect envelope.
2. **Rule #4 (Runtime Confinement)**:
   The verifier adapter enforces that any effect attempted during verification does not exceed the declared `effect_envelope`.
3. **Rule #5 (Capability Tunneling Blocked)**:
   The caller function's `declared_effects` must cover $\Sigma_V$; otherwise the high-level verifier rejects with `DiagnosticCode::EffectUndeclared`.
4. **Rule #9 ($\Sigma_{act}$ Composition)**:
   $$\Sigma_{act} = \{\text{act}[D]\} \cup \Sigma_{gate}$$
   Gate checks and target operations are strictly attributed in observable traces.
5. **Rule #10 (Authority Attribution vs Effect Attribution)**:
   Trusted gate authority discharges runtime checks (e.g. `read[trust_store]`), but the effect remains in $\Sigma_{act}$ and is accounted in the trace.
6. **Rule #15 (AtomicEffectGate Operational Semantics)**:
   If gate evaluation fails, target mutation count is exactly $0$. Observable gate check effects already executed remain in the trace.
7. **Rule #18 (MutationFootprint Enforcement)**:
   The `WorldState` prevents writes to keys outside the declared `MutationFootprint` (`Exact`, `Prefix`, `DomainWide`, `Unknown`).
8. **Rule #20 (Currentness vs Historical Facts)**:
   When an act mutates a key $K$, facts with predicate `CurrentState(K, ...)` are removed from `state.active_facts`, while `Historical` facts are preserved.
9. **Rule #21–#25 (`ActOutcome` Disjoint Algebra)**:
   `Success`, `Failure`, `PartialCompletion`, `DeliveryUnknown`, and `SettlementUnknown` are distinct nominal variants. `Atomic` operations returning `Partial` yield `ProtocolViolation`.

---

## 3. Test Suite Summary (221/221 PASS)

```text
Rust Native Tests (crates/bando/tests/):
    6/6 PASS (includes verify, act, and gate lowering tests)

Slice 2 Golden Conformance Suite (tests/compiler_conformance_slice2/test_golden_s2.py):
    12/12 PASS (S2C01–S2C20 end-to-end against real Rust binary)

Slice 2 Negative Verifier Suite (tests/compiler_conformance_slice2/test_negative_s2.py):
    5/5 PASS (S2V01–S2V05 rejected with exact DiagnosticCodes)

Slice 2 Mutation Campaign (tests/compiler_conformance_slice2/test_mutations_s2.py):
    15/15 PASS (S2M01–S2M16 real compiler mutations demonstrably killed)

Slice 2 Exact Differential Suite (tests/compiler_conformance_slice2/test_differential_s2.py):
    6/6 PASS (exact agreement across all 9 shared observables + 4 negative probes)

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
    221/221 PASS
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
