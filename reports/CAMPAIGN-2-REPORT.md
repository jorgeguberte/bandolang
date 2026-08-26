# Campaign 2 — Execution Report (Differential Semantics)

> Evidência histórica. Não modifica a semântica nem o freeze da Phase D.
> Spec normativa permanece em `my-wiki@4a66862` / `bando@943754b`.
> Campaign 1 report: `reports/CAMPAIGN-1-REPORT.md`.

## Question

Campaign 1 asked: does the lowered machine keep its own invariants under
crash/retry/duplicate/cancel/settlement? (YES, 13/13)

**Campaign 2 asked: does the lowered machine preserve the MEANING of
ConvergeFrame v0?**

```text
Obs(SemanticExecution) == Obs(LoweredExecution)
```

## Result

```text
Campaign 2 — Differential Semantics

Basic scenarios:
    6/6 PASS   (D01 local-exhaust, D02 successor-satisfied,
                D03 fuel-cap parity, D04 Ok(None), D05 Err+abort,
                D06 external expand)

Fault/recovery scenarios:
    6/6 PASS   (D07 DeliveryUnknown, D08 safe retry, D09 duplicate completion,
                D10 crash-after-settlement forward recovery, D11 cancel-in-flight,
                D12 late settlement after fatal closing)

Semantic model:
    REAL / EXERCISED     (semantic_model.py: WHAT only — no outbox, no
                          CompletionRecord, no StageLocal, no vm mechanics)

Lowered model:
    REAL / EXERCISED     (reused from Campaign 1; not duplicated)

Differential counterexamples:
    NONE IN TESTED REGIME

LLM calls / network / randomness:
    0 / 0 / 0
```

## Harness/test defects found during construction

```text
YES — again evidence FOR the methodology:

4. natural-exhaustion transition missing entirely from the Campaign 1 harness.
      Campaign 1 tested cancel/fatal closing but never plain exhaustion
      (frontier drained without satisfaction). The semantic differential
      exposed the gap on the first run. Classified HARNESS_GAP; spec unchanged.

5. satisfaction of an UNEXPANDED successor had no lowered-model primitive.
      Frozen ConvergeFrame v0 semantics: CheckSatisfaction is part of the
      parent expansion's processing — the successor is consumed by the check
      without consuming fuel or entering visitation history. Added as
      check_satisfaction(); classified HARNESS_GAP.

6. attempt-accounting normalization: external emissions carry an implicit
   satisfier attempt; local dispatches do not. Encoded in emit_external and
   normalized in scenarios where the explicit check IS the emission's attempt.

7. scenario stub mismatches (D07–D12): semantic models initially declared
   zero-cost/no-effect runs while the lowered side performed real paid actions.
   Fixed the stubs to mirror observable reality — the semantic model must
   describe what actually happened observably, not an idealized version.
```

## Normalizations applied (administrative differences ≠ divergence)

```text
StageLocal/Outbox/CompletionRecord/SettlementRecord (lowered-only mechanics)
    → collapse to the single observable effect they realize

local dispatch (DISPATCH_LOCAL)
    → no observable Σ, no satisfier attempt

transport retry
    → invisible: same request_id, zero fuel delta, zero visitation delta

value identity
    → compared as None/non-None until the lineage campaign (2B) opens
```

## Evidence level statement

```text
Phase D
    RESOLVED FOR CURRENT PHASE

Design
    DESIGN-LEVEL
    ADVERSARIALLY REVIEWED

Executable lowered state-machine model
    REAL / EXERCISED (13/13 adversarial)

Executable semantic model
    REAL / EXERCISED (12/12 differential)

Differential semantic preservation
    VERIFIED IN TESTED REGIME (no counterexample found)

Actual compiler/lowering implementation
    NOT YET VERIFIED

Formal soundness
    NOT PROVED

best_partial / lineage / Ψ
    OUT OF SCOPE (Open Question #8 OPEN; Campaign 2B pending)
```

## Item 3 gate

```text
Item 3 (CFG / Result / Error Model)
    UNBLOCKED per campaign plan — Campaign 2 initial pass achieved with report.
```
