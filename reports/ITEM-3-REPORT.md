# SOMA-IR Item 3 — Execution Report (CFG / Result / Error Model) — FINAL ACCEPTANCE (F1–F3)

> **Item 3 integrated execution report after final acceptance gate.**
> 1. F1: Exact observable differential comparator comparing strict `Fact` object equality ($\text{sem.ctx.psi} == \text{cfg\_state.psi}$) without name+arity shortcuts, exact latent postcondition sets, block-argument bindings, derived handle $\Sigma$, concrete value lineage, outcome variant, observable effects ($\Sigma$), and status. Verified with 2 negative mutations proving fact argument mismatches and extra conditional facts fail differential checks.
> 2. F2: Completed `check_all_invariants` contract returning explicit `PASS`, `VIOLATION`, or `NOT_APPLICABLE(reason)` across all invariants I3.1–I3.8.
> 3. F3: R15 exercises real CFG dataflow verification over mismatched predecessor handles via `CFGDataflowAnalyzer(prog).analyze()`, strictly asserting `TypeError`.
> All 49 Item 3 test cases (21 golden, 15 kills, 13 exact differential) and all 81 Phase D regression tests pass across the repository.

---

## 1. Baseline

```text
my-wiki
    canonical normative source
    baseline: 9f0abb6957813a37213cb5593c66f563dbe927e1

bandolang
    executable harness / language experiments
    baseline: 765e48aa25f8263595f9c42a20e36365b210ce84

bando (soma-docs)
    published Fumadocs docs
    baseline: 62a756a1b24982da9408696d594b46c0780280eb
```

---

## 2. Normative Obligations & Architecture

```text
Track A — RESULT-LATENT-POSTCOND (J1, F1)
    Result<T,E> binds LatentPostconditions(on_ok, on_err).
    Postconditions remain LATENT on SSA definitions and NEVER enter Ψ before refinement.
    `SwitchResult` branches instantiate postconditions bound to the block argument SSA symbol.
    Static dataflow analyzer computes fixed-point must-fact intersection: Ψ_in(block) = ⋂_{pred} rename_edge(Ψ_out).
    Branch-specific facts are discarded on merge; common facts are preserved.
    Loop fixed-point analysis proves iteration facts do not leak to headers or exit paths without proof.

Track B — ACT-SETTLEMENT-OUTCOME (J3, F1)
    Physical ambiguity (DeliveryUnknown, SettlementUnknown) is strictly disjoint from Definite Failure.
    `ActOutcome` / `EffectOutcome` distinguishes Completed(Result<T,E>) vs Pending(Unknown).
    `await` on ChildHandle suspends while settlement is unknown; does not fabricate Err.
    Confirmed failure (ConfirmedNotDelivered) becomes clean Err only upon definite certainty.

Track C — ACT-PARTIAL-COMPLETION (J3, F1)
    Partial completion (A+B applied, C+D failed) carries PartialEffectReport.
    Partial is distinct from Success, clean Failure, and Unknown.
    Adapters declaring transactional/atomic contracts reject Partial with FatalProtocolViolation.
    Success-only facts do NOT materialize in Partial branch.

Track D — HANDLE-EFFECT-JOIN (J2, J3, F1, F3)
    Derived ChildHandle block argument types compute may-effect union Σ_join = ⋃_P Σ_P from all predecessor edges.
    Type mismatch between predecessor handles is strictly rejected at CFG dataflow verification (F3).
    May-effects summary Σ_join does not invent concrete execution provenance.
    `await` adds zero observable effects to parent trace (Σ_await = ∅).
    Concrete result lineage reflects actual child execution, not may-effects union.
```

---

## 3. Executable Validation Results

```text
Golden Scenarios Battery (R01–R18, X1–X4) — F3 Verified:
    21/21 PASS
    - R01_OK_POSTCONDITION: on_ok facts materialize on Ok branch [PASS]
    - R02_ERR_ISOLATION: on_ok facts strictly isolated from Err branch [PASS]
    - R03_BLOCK_ARGUMENT_RENAME: facts correctly bound to block argument SSA symbols [PASS]
    - R04_MERGE_LOSES_BRANCH_ONLY_FACT: static CFG fixed-point analyzer verifies branch-only fact loss [PASS]
    - R05_MERGE_PRESERVES_COMMON_FACT: static CFG fixed-point analyzer verifies common fact preservation [PASS]
    - R06_FORWARDED_RESULT_REMAINS_LATENT: unrefined forwarded Result keeps postconditions latent [PASS]
    - R07_LOOP_LEAKAGE_KILL: static fixed-point analyzer proves loop iteration fact does not leak [PASS]
    - R08_UNKNOWN_IS_NOT_ERR: DeliveryUnknown and SettlementUnknown do not collapse to Err [PASS]
    - R09_CONFIRMED_FAILURE_BECOMES_ERROR: definite failure routes to clean Failure branch [PASS]
    - R10_PARTIAL_COMPLETION_DISTINCT: PartialCompletion routes to distinct partial block [PASS]
    - R11_TRANSACTIONAL_ADAPTER_EXCLUDES_PARTIAL: atomic op rejects partial with ProtocolViolation [PASS]
    - R12_PARTIAL_BRANCH_FACTS: partial footprint facts materialize, success facts absent [PASS]
    - R13_HANDLE_SAME_EFFECTS_JOIN: derived parameter type computes identical effects [PASS]
    - R14_HANDLE_HETEROGENEOUS_EFFECTS_JOIN: derived parameter type computes may-effects union Σa ∪ Σb [PASS]
    - R15_HANDLE_TYPE_MISMATCH_REJECT: CFGDataflowAnalyzer.analyze() rejects join with TypeError [F3 PASS]
    - R16_AWAIT_EFFECT_PRESERVATION: await adds zero observable effects (Σ_await = ∅) [PASS]
    - R17_HANDLE_UNION_DOES_NOT_BECOME_RESULT_PROVENANCE: concrete lineage reflects actual child execution [PASS]
    - R18_RESULT_AFTER_JOINED_HANDLE: await result refines normally [PASS]
    - X1_RESULT_ACT_INTEGRATION: 4-way ActOutcome refinement verified [PASS]
    - X2_PARTIAL_MERGE_INTEGRATION: static dataflow analyzer verifies CompleteSuccess + PartialCompletion merge [PASS]
    - X3_X4_HANDLE_AWAIT_REFINEMENT_INTEGRATION: handle join + await neutrality + result refinement [PASS]

Adversarial Mutation Kills (K1–K12 & Probes) — F2 Verified:
    15/15 PASS
    - K1 Eager postcondition leak: detector flagged unrefined fact in Ψ [PASS]
    - K2 Err receives Ok fact: detector flagged contradiction [PASS]
    - K3 Union instead of intersection merge: detector flagged non-intersection fact [PASS]
    - K4 Missing SSA renaming: detector flagged unbound predecessor symbol [PASS]
    - K5 Unknown coerced to Err: detector flagged outcome overlap [PASS]
    - K6 Partial coerced to Err: I3.4 and I3.5 flagged false clean failure [PASS]
    - K7 Partial coerced to Success: detector flagged false success [PASS]
    - K8 Transactional emits Partial: interpreter flagged ProtocolViolation [PASS]
    - K9 Handle join drops effects: detector flagged non-monotonic union [PASS]
    - K10 Handle join invents lineage: I3.8 flagged fabricated dependency [PASS]
    - K11 Await reattributes child effects: detector flagged polluted effect trace [PASS]
    - K12 Branch fact survives merge: detector flagged missing intersection [PASS]
    - Control Probes: 3/3 clean valid states accepted [PASS]

Exact Observable Differential Semantics Battery (F1):
    13/13 PASS
    - D_R01_ok_postcondition [PASS]
    - D_R02_err_isolation [PASS]
    - D_R08_unknown_not_err [PASS]
    - D_R10_partial_completion [PASS]
    - D_R11_transactional_rejection [PASS]
    - D_R14_handle_join_await_neutrality [PASS]
    - D_diamond_must_fact_merge [PASS]
    - D_loop_fixed_point_convergence [PASS]
    - D_handle_join_provenance_separation [PASS]
    - D_X1_result_act_integration [PASS]
    - D_X3_X4_handle_await_refinement [PASS]
    - MUTATION_same_fact_name_wrong_args: exact comparator caught mismatched fact args [F1 PASS]
    - MUTATION_extra_conditional_cfg_fact: exact comparator caught extra spurious CFG fact [F1 PASS]

Phase D Lowering Regression Battery:
    81/81 PASS (zero regressions across all 4 Phase D suites)
```

---

## 4. Status & Resolution

```text
SOMA-IR Item 3 (CFG / Result / Error Model)
    RESOLVED FOR CURRENT PHASE

RESULT-LATENT-POSTCOND
    RESOLVED FOR CURRENT PHASE

ACT-SETTLEMENT-OUTCOME
    RESOLVED FOR CURRENT PHASE

ACT-PARTIAL-COMPLETION
    RESOLVED FOR CURRENT PHASE

HANDLE-EFFECT-JOIN
    RESOLVED FOR CURRENT PHASE

Actual compiler/lowering implementation
    NOT YET VERIFIED

Formal soundness
    NOT PROVED

LLM calls / network / randomness
    0 / 0 / 0
```
