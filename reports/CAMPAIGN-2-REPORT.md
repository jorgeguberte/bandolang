# Campaign 2 — Execution Report (Differential Semantics) — REISSUE 8

> **REISSUE 8 after eighth audit round (R37–R43).**
> The eighth audit verified deep integrity and binding properties:
> 1. Completion / Payload binding (digest and outcome strictly bind semantic payloads; failure cannot carry success payload).
> 2. Generic `apply_semantic` bypass removed for typed outcomes.
> 3. I6 true bijection (Applied handles <=> unique application records).
> 4. I7 real independent reconciliation count per handle (`settlement_reconciliations`).
> 5. Targeted fault injection (`delivery_unknown_ops`) and preservation of prior settled spend during Waiting.
> 6. Unambiguous `PartialOf` eligibility and `max_satisfaction_attempts` limit.
> 7. `request_id` identity reuse rejection before any mutation or reservation.
> All seven issues have been resolved across both the lowered machine and the semantic model.

## Audit repairs applied (Round 8: R37–R43)

```text
R37 Completion / Payload Binding
    FIXED — `admit_completion()` strictly validates that `digest`, `outcome`, and `semantic_payload`
    form a coherent bound outcome. Rejects Failure outcome carrying success payload.
    Equivocation detection checks full payload divergence on the same handle.

R38 Remove Generic Apply Bypass
    FIXED — `apply_semantic()` refuses to apply handles carrying typed SpaceOutcome
    or SatisfierOutcome, preventing bypass of successor discovery or satisfaction incorporation.
    Added T18 regression scenario.

R39 I6 True Bijection
    FIXED — I6 enforces exact two-way bijection:
        (a) unique application records
        (b) every Applied handle has matching application record
        (c) every application record corresponds to an actual Applied handle
    Added I6 kill B (ghost application record with no Applied handle => FAIL).

R40 I7 Real Reconciliation Count
    FIXED — domain tracks independent `settlement_reconciliations[handle_id]` count.
    I7 verifies `reconciliation_count[h] == 1` per handle and exact scope spent match.

R41 Targeted Faults & DeliveryUnknown History Preservation (D20)
    FIXED — FaultSpec supports targeted `delivery_unknown_ops`.
    SemanticFrame preserves prior settled `budget_spent` when an in-flight operation
    suffers DeliveryUnknown.
    Added D20 (A settles 20, B suffers DeliveryUnknown ceiling 10 => spent=20, committed=10).

R42 PartialOf & Satisfaction Attempt Limit (D21)
    FIXED — explicit `partial_map` mapping and `max_satisfaction_attempts` limit.
    Added D21 testing exhaustion when satisfaction attempts reach the configured limit.

R43 Request ID Identity & Reuse Protection (T17)
    FIXED — `StageLocal` rejects historical `request_id` reuse for new requests before
    any mutation of available, reserved, or committed funds.
    Added T17 regression scenario.
```

## Complete verification results

```text
Campaign 1 (Lowered Safety & Crash Recovery):
    20/20 PASS (T01–T11, T04A/B, T07B real recovery, T12 sequential stage guard,
                T13 pending exhaust drain, T14 settlement ceiling bounds,
                T15 autonomous space apply recovery, T16 autonomous satisfier apply recovery,
                T17 request_id reuse rejection, T18 generic apply bypass refused)

Invariant Kill Tests (Mutation Testing):
    17/17 PASS (I1 frame-wide, I3 scope kill, I3 attributable kill, I3 control probe,
                I6 CompletionId uniqueness kill, I6 completeness gap kill,
                I6 identical digest probe, I7 ledger vs records kill,
                I7 identical receipt probe, I8 closing mutation kill,
                I8 clean closing probe, I9 forged visit kill, I9 clean history probe,
                I10 scope limit kill, I10 IntentFrame conservation kill,
                I10 spent>avail control probe)

Campaign 2 Basic (Declarative Search Programs):
    15/15 PASS (D01 exhaust [R19 verified], D02 successor [R19/R10 verified],
                D03 max_steps + partial [R4 verified], D04 Ok(None), D05 Err+abort,
                D06 external, D13 ceiling vs actual charge [R12/R14 verified],
                D14 budget headroom depletion [R15/R34 verified],
                D15 unaffordable ceiling refused [R20/R25/R34 verified],
                D16 effectful satisfier with explicit PartialOf [R24/R33 verified],
                D17 effectful satisfier commit point under DeliveryUnknown [R26/R31 verified],
                D18 sequential Waiting blocks local dispatch [R31 verified],
                D19 autonomous crash recovery preserves space successors [R32/R37 verified],
                D20 targeted DeliveryUnknown preserves prior spend [R41 verified],
                D21 satisfaction attempt limit exhaustion [R42 verified])

Campaign 2 Fault (Environmental Fault Injections):
    6/6 PASS   (D07 DeliveryUnknown [Waiting verified], D08 safe retry,
                D09 duplicate completion, D10 crash-after-settlement forward recovery,
                D11 cancel-in-flight [R2 Cancelled verified],
                D12 late settlement fatal closing)

Semantic model:
    REAL / AUTONOMOUS (purely declarative search space execution)

Lowered model:
    REAL / ADVERSARIALLY HARDENED (bound completion payloads, bijection invariants,
    independent reconciliation tracking, request_id reuse protection, autonomous recovery)

Differential counterexamples:
    NONE IN TESTED REGIME

LLM calls / network / randomness:
    0 / 0 / 0
```

## Evidence level statement

```text
Phase D
    RESOLVED FOR CURRENT PHASE

Design
    DESIGN-LEVEL
    ADVERSARIALLY REVIEWED

Executable lowered state-machine model
    REAL / ADVERSARIALLY HARDENED (20/20 adversarial scenarios)

Executable semantic model
    REAL / AUTONOMOUS (21/21 differential programs)

Invariant checker
    SELF-TESTED (17/17 mutation kill tests & control probes)

Differential semantic preservation
    VERIFIED IN TESTED REGIME (audited across 8 adversarial review rounds, R1–R43 fixed)

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
    UNBLOCKED per campaign plan — Phase D lowering safety, Waiting lifecycle,
    budget conservation, durable autonomous recovery, invariant bijection,
    and differential preservation have survived 8 adversarial audit rounds.
```
