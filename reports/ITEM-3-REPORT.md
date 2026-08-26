# SOMA-IR Item 3 — Execution Report (CFG / Result / Error Model)

> **Item 3 integrated execution report.**
> SOMA-IR Item 3 defines how success, failure, ambiguity, partial completion, and conditional refinements appear as SSA values and control flow in the CFG across four core tracks:
> 1. `RESULT-LATENT-POSTCOND`: Result<T,E> latent postconditions, refinement, block argument symbol renaming, and must-fact intersection merge.
> 2. `ACT-SETTLEMENT-OUTCOME`: Physical effect ambiguity (`DeliveryUnknown`, `SettlementUnknown`) never collapses into clean `Result::Err`.
> 3. `ACT-PARTIAL-COMPLETION`: Partial completion footprint explicitly distinguished from clean failure; transactional contracts reject partial completion.
> 4. `HANDLE-EFFECT-JOIN`: May-effect union on handle join, await effect neutrality ($\Sigma_{await} = \emptyset$), and concrete result lineage separation.

---

## 1. Baseline

```text
my-wiki
    canonical normative source
    baseline: 4a6686287719b3ce9cf81d5a791a0b1bf48a6162

bandolang
    executable harness / language experiments
    Phase-D accepted baseline: 5351b0395db111100463852053f8983647bab094

bando (soma-docs)
    published Fumadocs docs
    baseline: 943754b24f5e1e7d8f4a3071db769847fa97abe4
```

---

## 2. Normative Obligations & Architecture

```text
Track A — RESULT-LATENT-POSTCOND
    Result<T,E> binds LatentPostconditions(on_ok, on_err).
    Postconditions remain LATENT on SSA definitions and NEVER enter Ψ before refinement.
    `SwitchResult` branches instantiate postconditions bound to the block argument SSA symbol.
    CFG join points compute strict must-fact intersection: Ψ_merge = ⋂ rename(Ψ_pred_i).
    Branch-specific facts are discarded on merge; common facts are preserved.

Track B — ACT-SETTLEMENT-OUTCOME
    Physical ambiguity (DeliveryUnknown, SettlementUnknown) is strictly disjoint from Definite Failure.
    `ActOutcome` / `EffectOutcome` distinguishes Completed(Result<T,E>) vs Pending(Unknown).
    `await` on ChildHandle suspends while settlement is unknown; does not fabricate Err.
    Confirmed failure (ConfirmedNotDelivered) becomes clean Err only upon definite certainty.

Track C — ACT-PARTIAL-COMPLETION
    Partial completion (A+B applied, C+D failed) carries PartialEffectReport.
    Partial is distinct from Success, clean Failure, and Unknown.
    Adapters declaring transactional/atomic contracts reject Partial with FatalProtocolViolation.
    Success-only facts do NOT materialize in Partial branch.

Track D — HANDLE-EFFECT-JOIN
    Compatible ChildHandle<T, E, Σa> and ChildHandle<T, E, Σb> join into ChildHandle<T, E, Σa ∪ Σb>.
    May-effects summary Σ_join = Σa ∪ Σb does not invent concrete execution provenance.
    `await` adds zero observable effects to parent trace (Σ_await = ∅).
    Child result latent postconditions refine only upon SwitchResult on await result.
```

---

## 3. Executable Validation Results

```text
Golden Scenarios Battery (R01–R18, X1–X4):
    21/21 PASS
    - R01_OK_POSTCONDITION: on_ok facts materialize on Ok branch [PASS]
    - R02_ERR_ISOLATION: on_ok facts strictly isolated from Err branch [PASS]
    - R03_BLOCK_ARGUMENT_RENAME: facts correctly bound to block argument SSA symbols [PASS]
    - R04_MERGE_LOSES_BRANCH_ONLY_FACT: branch-only fact lost on merge intersection [PASS]
    - R05_MERGE_PRESERVES_COMMON_FACT: common must-fact preserved across predecessors [PASS]
    - R06_FORWARDED_RESULT_REMAINS_LATENT: unrefined forwarded Result keeps postconditions latent [PASS]
    - R07_LOOP_LEAKAGE_KILL: loop iteration facts do not leak without proof [PASS]
    - R08_UNKNOWN_IS_NOT_ERR: DeliveryUnknown and SettlementUnknown do not collapse to Err [PASS]
    - R09_CONFIRMED_FAILURE_BECOMES_ERROR: definite failure routes to clean Failure branch [PASS]
    - R10_PARTIAL_COMPLETION_DISTINCT: PartialCompletion routes to distinct partial block [PASS]
    - R11_TRANSACTIONAL_ADAPTER_EXCLUDES_PARTIAL: atomic op rejects partial with ProtocolViolation [PASS]
    - R12_PARTIAL_BRANCH_FACTS: partial footprint facts materialize, success facts absent [PASS]
    - R13_HANDLE_SAME_EFFECTS_JOIN: identical effects join preserves Σ [PASS]
    - R14_HANDLE_HETEROGENEOUS_EFFECTS_JOIN: may-effects union Σa ∪ Σb strictly preserved [PASS]
    - R15_HANDLE_TYPE_MISMATCH_REJECT: incompatible handle types reject join [PASS]
    - R16_AWAIT_EFFECT_PRESERVATION: await adds zero observable effects (Σ_await = ∅) [PASS]
    - R17_HANDLE_UNION_DOES_NOT_BECOME_RESULT_PROVENANCE: concrete lineage reflects actual child execution [PASS]
    - R18_RESULT_AFTER_JOINED_HANDLE: await result refines normally [PASS]
    - X1_RESULT_ACT_INTEGRATION: 4-way ActOutcome refinement verified [PASS]
    - X2_PARTIAL_MERGE_INTEGRATION: CompleteSuccess + PartialCompletion merge verified [PASS]
    - X3_X4_HANDLE_AWAIT_REFINEMENT_INTEGRATION: handle join + await neutrality + result refinement [PASS]

Adversarial Mutation Kills (K1–K12 & Probes):
    15/15 PASS
    - K1 Eager postcondition leak: detector flagged unrefined fact in Ψ [PASS]
    - K2 Err receives Ok fact: detector flagged contradiction [PASS]
    - K3 Union instead of intersection merge: detector flagged non-intersection fact [PASS]
    - K4 Missing SSA renaming: detector flagged unbound predecessor symbol [PASS]
    - K5 Unknown coerced to Err: detector flagged outcome overlap [PASS]
    - K6 Partial coerced to Err: detector flagged false clean failure [PASS]
    - K7 Partial coerced to Success: detector flagged false success [PASS]
    - K8 Transactional emits Partial: interpreter flagged ProtocolViolation [PASS]
    - K9 Handle join drops effects: detector flagged non-monotonic union [PASS]
    - K10 Handle join invents lineage: detector flagged fabricated dependency [PASS]
    - K11 Await reattributes child effects: detector flagged polluted effect trace [PASS]
    - K12 Branch fact survives merge: detector flagged missing intersection [PASS]
    - Control Probes: 3/3 clean valid states accepted [PASS]

Differential Semantics Battery (Semantic Model vs Lowered CFG):
    8/8 PASS
    - D_R01_ok_postcondition [PASS]
    - D_R02_err_isolation [PASS]
    - D_R08_unknown_not_err [PASS]
    - D_R10_partial_completion [PASS]
    - D_R11_transactional_rejection [PASS]
    - D_R14_handle_join_await_neutrality [PASS]
    - D_X1_result_act_integration [PASS]
    - D_X3_X4_handle_await_refinement [PASS]

Phase D Lowering Regression Suite:
    81/81 PASS (zero regressions across all 4 Phase D suites)
```

---

## 4. Formal Invariants Verification (I3.1–I3.8)

```text
I3.1 Result Fact Soundness
    VERIFIED — every postcondition in Ψ has a dominating proof of IsOk/IsErr/IsSuccess/IsFailure.

I3.2 No Eager Latent Discharge
    VERIFIED — unrefined Result definitions never leak latent postconditions into Ψ.

I3.3 CFG Must-Fact Merge
    VERIFIED — join points compute exact intersection: Ψ_merge = ⋂ rename(Ψ_pred_i).

I3.4 Outcome Disjointness
    VERIFIED — Success, Failure, Partial, and Unknown are strictly mutually exclusive.

I3.5 No False Clean Failure
    VERIFIED — operations with confirmed or ambiguous mutations cannot be labeled as clean failures.

I3.6 Handle Effect Monotonicity
    VERIFIED — Σ_left ⊆ Σ_join and Σ_right ⊆ Σ_join; Σ_join == Σ_left ∪ Σ_right.

I3.7 Await Effect Neutrality
    VERIFIED — ObsEffects(await) == ∅; awaiting does not pollute observable effect trace.

I3.8 Provenance / Effect Separation
    VERIFIED — concrete result lineage reflects actual execution dependency, not may-effects union.
```

---

## 5. Status & Resolution

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
