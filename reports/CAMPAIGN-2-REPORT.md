# Campaign 2 — Execution Report (Differential Semantics) — REISSUE 11

> **REISSUE 11 after eleventh adversarial audit round (R56–R60).**
> The eleventh audit resolved structural authority, typed canonical encoding, Closing barrier, and retry semantics:
> 1. R56: Injective recursive canonical JSON encoding for completion digests (eliminates textual separator/None collisions).
> 2. R57: Durable `ExecutionReceipt` carrying authoritative usage/accounting facts; `settle()` derives charges authoritatively, preventing caller override.
> 3. R58: Closing semantic barrier enforced: late typed completions during `Closing` safely discard semantic payloads without mutating frontiers or overriding `PendingCancelled`/`PendingFailure` (T20, T21, T22 verified).
> 4. R59: Real `SatisfactionState` retry of the same candidate across transient `Err(e)` failures (D24 retry and D26 limit-blocked verified).
> 5. R60: Decoupled retry capability (`dedup_capable or idempotent`) from environment transport outcomes (D27 idempotent retry and D28 double DeliveryUnknown verified).
> All 73 test cases pass across all 4 test suites without divergence or false positives.

## Audit repairs applied (Round 11: R56–R60)

```text
R56 Injective Canonical JSON Completion Digest
    FIXED — `canonical_digest` uses typed canonical JSON structure with version tags.
    Eliminated colon-delimiter collisions and `None` vs `"None"` string collisions.
    Verified with negative collision mutation tests.

R57 Settlement & Receipt Authority Binding
    FIXED — `ExecutionReceipt` is durable state on `CompletionRecord`.
    `settle(handle)` derives resource and amount authoritatively from the receipt,
    rejecting arbitrary caller overrides with `SettlementAmountMismatch`.

R58 Closing Semantic Barrier (T20, T21, T22)
    FIXED — `apply_space_completion` and `apply_satisfier_completion` safely discard
    semantic payloads during `Closing` (no frontier mutation, no override of PendingCancelled/PendingFailure).
    Added T20 (PendingCancelled + late satisfaction => Cancelled),
    T21 (PendingFailure + late space => Failed), and
    T22 (recovery of settled typed completion while Closing => preserves Closing reason).

R59 Real SatisfactionState & Candidate Retry (D24, D26)
    FIXED — `SatisfactionState` modeled with transient error retries on the same candidate.
    D24 tests transient failure on attempt 1 retrying and satisfying on attempt 2.
    D26 tests max_satisfaction_attempts=1 blocking the second attempt -> Exhausted.

R60 Decoupled Retry Capability & Environmental Fault Sequences (D27, D28)
    FIXED — Retry allowed if `dedup_capable or idempotent`.
    Added D27 (idempotent-only safe retry => Satisfied) and
    D28 (double DeliveryUnknown on retry leaves frame in Waiting with transport_attempts==2).
```

## Complete verification results

```text
Campaign 1 (Lowered Safety & Crash Recovery):
    24/24 PASS (T01–T11, T04A/B, T07B real recovery, T12 sequential stage guard,
                T13 pending exhaust drain, T14 settlement ceiling bounds,
                T15 autonomous space apply recovery, T16 autonomous satisfier apply recovery,
                T17 request_id reuse rejection, T18 generic apply bypass refused,
                T19 snapshot-authoritative recovery, T20 late satisfaction discarded during Closing,
                T21 late space discarded during Closing, T22 recovery while Closing discards payload)

Invariant Kill Tests (Mutation Testing & Bijection):
    21/21 PASS (I1 frame-wide, I3 scope kill, I3 attributable kill, I3 control probe,
                I6 CompletionId uniqueness kill, I6 ghost record kill, I6 completeness gap kill,
                I6 identical digest probe, I7 ledger vs records kill, I7 duplicate reconciliation kill,
                I7 ghost reconciliation kill, I7 ghost scope_spent kill, I7 identical receipt probe,
                R50/R56 canonical digest order/op_id/collision tests, R57 settlement authority test,
                I8 closing mutation kill, I8 clean closing probe, I9 forged visit kill,
                I9 clean history probe, I10 scope limit kill, I10 IntentFrame conservation kill,
                I10 spent>avail control probe)

Campaign 2 Basic (Declarative Search Programs):
    22/22 PASS (D01 exhaust [R19 verified], D02 successor [R19/R10 verified],
                D03 max_steps + partial [R4 verified], D04 Ok(None), D05 Err+abort,
                D06 external, D13 ceiling vs actual charge [R12/R14 verified],
                D14 budget headroom depletion [R15/R34 verified],
                D15 unaffordable ceiling refused [R20/R25/R34 verified],
                D16 effectful satisfier with explicit PartialOf [R24/R33/R48 verified],
                D17 effectful satisfier commit point under DeliveryUnknown [R26/R31 verified],
                D18 sequential Waiting blocks local dispatch [R31 verified],
                D19 autonomous crash recovery preserves space successors [R32/R45/R53 verified],
                D20 targeted DeliveryUnknown preserves prior spend [R41 verified],
                D21 multi-candidate satisfaction attempt limit exhaustion [R42/R49 verified],
                D22 DeliveryUnknown prevents premature successor discovery [R47 verified],
                D23 effectful satisfier Err(e) with abort policy [R52 verified],
                D24 effectful satisfier transient retry on same candidate [R52/R59 verified],
                D25 targeted effectful satisfier DeliveryUnknown [R55 verified],
                D26 satisfier retry attempt limit blocks second attempt [R59 verified],
                D27 safe retry on idempotent-only operation [R60 verified],
                D28 double DeliveryUnknown on retry leaves frame in Waiting [R60 verified])

Campaign 2 Fault (Environmental Fault Injections):
    6/6 PASS   (D07 DeliveryUnknown [Waiting verified],
                D08 safe transport retry real [Satisfied(T-retry) verificado],
                D09 duplicate completion com mesmo receipt_id,
                D10 crash-after-settlement forward recovery,
                D11 cancel-in-flight [R2 Cancelled verificado],
                D12 late settlement fatal closing)

Semantic model:
    REAL / AUTONOMOUS (purely declarative search space execution)

Lowered model:
    REAL / ADVERSARIALLY HARDENED (exact canonical JSON digests, durable ExecutionReceipt authority,
    Closing semantic barrier, true two-way bijection invariants, independent reconciliation tracking,
    ghost-spend checks, snapshot-authoritative recovery, request_id reuse protection)

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
    REAL / ADVERSARIALLY HARDENED (24/24 adversarial scenarios)

Executable semantic model
    REAL / AUTONOMOUS (28/28 differential programs)

Invariant checker
    SELF-TESTED (21/21 mutation kill tests & control probes)

Differential semantic preservation
    VERIFIED IN TESTED REGIME (audited across 11 adversarial review rounds, R1–R60 fixed)

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
    Closing semantic barrier, budget conservation, durable receipt authority,
    snapshot-authoritative recovery, invariant two-way bijection,
    effectful satisfier retry semantics, and differential preservation have survived
    11 adversarial audit rounds.
```
