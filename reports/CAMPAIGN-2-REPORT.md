# Campaign 2 — Execution Report (Differential Semantics) — REISSUE 10

> **REISSUE 10 after tenth adversarial audit round (R50–R55).**
> The tenth audit completed the deep binding, fault targeting, error handling, and recovery isolation guarantees:
> 1. R50: Exact canonical digest binding (order-preserving on successors, full field inclusion including `op_id`).
> 2. R51: Real differential safe retry (D08 verified with transport retry on identical `request_id` reaching `Satisfied(T-retry)`).
> 3. R52: Effectful satisfier `Err(e)` error semantics (`OnSatisfierError` as durable machine frame state; D23 abort and D24 retry verified).
> 4. R53: Snapshot-authoritative recovery (T19 verified: volatile live RAM mutations cannot corrupt durable snapshot redrive).
> 5. R54: I7 ghost-spend detector (checks union of resources; scope_spent without settlement records fails).
> 6. R55: Unified targeted faults (`delivery_unknown_ops` applies uniformly to both space and satisfier operations; D25 verified).
> All 67 test cases pass across all 4 test suites without divergence or false positives.

## Audit repairs applied (Round 10: R50–R55)

```text
R50 Exact Canonical Digest Binding
    FIXED — `canonical_digest` preserves exact successor order in SpaceOutcome and includes
    all fields (including `op_id`) in SatisfierOutcome. Verified with negative order and op_id mutation kills.

R51 Real Differential Safe Retry (D08)
    FIXED — D08 executes transport retry upon initial DeliveryUnknown on dedup-capable external operations.
    The second attempt succeeds on the exact same request_id -> reaches Satisfied(T-retry).

R52 Effectful Satisfier Err(e) & Durable Error Policy (D23, D24)
    FIXED — `on_satisfier_error` policy is durable machine/frame state (`d.on_satisfier_error`),
    not caller arguments. Handled `Err(e)` in both semantic and lowered models.
    Added D23 (abort -> Failed(e)) and D24 (retry -> next candidate Satisfied).

R53 Snapshot-Authoritative Crash Recovery (T19)
    FIXED — `recover()` redrives exclusively on the durable snapshot state before authoritatively
    updating volatile RAM. Added T19 regression scenario proving that post-crash live RAM corruption
    is discarded during recovery.

R54 I7 Ghost-Spend Detection
    FIXED — I7 compares `scope_spent` against settlement totals over the full union of resources.
    Added I7 kill D (scope_spent with zero settlements => FAIL).

R55 Unified Targeted Faults (D25)
    FIXED — `delivery_unknown_ops` applies uniformly to all external operations (expansion and satisfier).
    Added D25 verifying targeted DeliveryUnknown on effectful satisfier `opVerify`.
```

## Complete verification results

```text
Campaign 1 (Lowered Safety & Crash Recovery):
    21/21 PASS (T01–T11, T04A/B, T07B real recovery, T12 sequential stage guard,
                T13 pending exhaust drain, T14 settlement ceiling bounds,
                T15 autonomous space apply recovery, T16 autonomous satisfier apply recovery,
                T17 request_id reuse rejection, T18 generic apply bypass refused,
                T19 snapshot-authoritative recovery)

Invariant Kill Tests (Mutation Testing & Bijection):
    21/21 PASS (I1 frame-wide, I3 scope kill, I3 attributable kill, I3 control probe,
                I6 CompletionId uniqueness kill, I6 ghost record kill, I6 completeness gap kill,
                I6 identical digest probe, I7 ledger vs records kill, I7 duplicate reconciliation kill,
                I7 ghost reconciliation kill, I7 ghost scope_spent kill, I7 identical receipt probe,
                R50 exact canonical digest binding tests, I8 closing mutation kill,
                I8 clean closing probe, I9 forged visit kill, I9 clean history probe,
                I10 scope limit kill, I10 IntentFrame conservation kill,
                I10 spent>avail control probe)

Campaign 2 Basic (Declarative Search Programs):
    19/19 PASS (D01 exhaust [R19 verified], D02 successor [R19/R10 verified],
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
                D24 effectful satisfier Err(e) with retry policy [R52 verified],
                D25 targeted effectful satisfier DeliveryUnknown [R55 verified])

Campaign 2 Fault (Environmental Fault Injections):
    6/6 PASS   (D07 DeliveryUnknown [Waiting verified], D08 safe retry [R51 verified],
                D09 duplicate completion with same receipt_id, D10 crash-after-settlement forward recovery,
                D11 cancel-in-flight [R2 Cancelled verified],
                D12 late settlement fatal closing)

Semantic model:
    REAL / AUTONOMOUS (purely declarative search space execution)

Lowered model:
    REAL / ADVERSARIALLY HARDENED (exact canonical bound completion digests, two-way bijection invariants,
    independent reconciliation tracking, ghost-spend checks, snapshot-authoritative recovery,
    request_id reuse protection)

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
    REAL / ADVERSARIALLY HARDENED (21/21 adversarial scenarios)

Executable semantic model
    REAL / AUTONOMOUS (25/25 differential programs)

Invariant checker
    SELF-TESTED (21/21 mutation kill tests & control probes)

Differential semantic preservation
    VERIFIED IN TESTED REGIME (audited across 10 adversarial review rounds, R1–R55 fixed)

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
    budget conservation, snapshot-authoritative recovery, invariant two-way bijection,
    effectful satisfier error semantics, and differential preservation have survived
    10 adversarial audit rounds.
```
