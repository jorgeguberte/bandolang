# Campaign 2 — Execution Report (Differential Semantics) — REISSUE 12

> **REISSUE 12 after twelfth adversarial audit round (R61–R65).**
> The twelfth audit finalized the machine-owned operational states, receipt identity binding, post-fuel unification, space step failures, and confirmed-not-delivered transitions:
> 1. R61: Machine-owned `SatisfactionState` (`Untested`, `CheckedNotSatisfied`, `RetryableFailure`, `Satisfied`) stored directly on `SearchNode` and updated by transitions. `CheckedNotSatisfied` nodes are never re-checked upon subsequent expansion (D29 verified; T23 verified crash survival).
> 2. R62: Mandatory `ExecutionReceipt` bound to `request_id` and `receipt_id`. `settle()` derives charges authoritatively with zero caller accounting parameters across all 26 Campaign 1 scenarios.
> 3. R63: Unified post-fuel `CheckSatisfaction` path without caller-side filtering (D31 Ok(None) verified).
> 4. R58/Semantic Disposition: Explicit `semantic_disposition` ("Applied" vs "DiscardedDueToClosing" vs "StepFailure") on `InFlightLifecycleState`.
> 5. R64: Typed Space `StepFailure` outcome handling `DynamicGateRejection` with `on_step_failure` policy (D32 verified).
> 6. R65: `ConfirmedNotDelivered` transition releasing reservations and commitments with 0 spend and returning to `Searching` (T24 verified).
> All 78 test cases pass across all 4 test suites without divergence or false positives.

## Audit repairs applied (Round 12: R61–R65)

```text
R61 Machine-Owned SatisfactionState (D29, T23)
    FIXED — `SearchNode` stores `satisfaction_state` and `satisfaction_retries`.
    `apply_satisfier_completion` and `check_satisfaction` update node satisfaction states machine-side.
    Nodes in `CheckedNotSatisfied` or `Satisfied` are ineligible for subsequent re-checking.
    Added D29 (CheckedNotSatisfied node not re-checked on subsequent expansion) and
    T23 (RetryableFailure state survives crash and redrives second attempt).

R62 Mandatory ExecutionReceipt Bound to Request ID
    FIXED — `ExecutionReceipt` carrying (request_id, receipt_id, resource, amount) is mandatory
    on all external completions. `admit_completion()` verifies receipt identity matching.
    `settle(handle)` derives resource and amount authoritatively without caller parameters across all scenarios.

R63 Unified Post-Fuel CheckSatisfaction (D31)
    FIXED — Removed duplicate driver post-fuel block. Driver invokes machine `check_satisfaction`
    uniformly regardless of outcome. Added D31 testing post-fuel Ok(None) candidate exhaustion.

R64 Typed Space StepFailure & DynamicGateRejection (D32)
    FIXED — `SpaceOutcome` supports `is_failure=True` with error payload.
    `apply_space_completion()` handles StepFailure under `on_step_failure` policy.
    Added D32 verifying DynamicGateRejection StepFailure terminating as Failed.

R65 ConfirmedNotDelivered Transition (T24)
    FIXED — `confirmed_not_delivered(d, handle)` releases reservations and committed scope
    with 0 spend and restores frame to Searching/Closing. Added T24 regression scenario.
```

## Complete verification results

```text
Campaign 1 (Lowered Safety & Crash Recovery):
    26/26 PASS (T01–T11, T04A/B, T07B real recovery, T12 sequential stage guard,
                T13 pending exhaust drain, T14 settlement ceiling bounds,
                T15 autonomous space apply recovery, T16 autonomous satisfier apply recovery,
                T17 request_id reuse rejection, T18 generic apply bypass refused,
                T19 snapshot-authoritative recovery, T20 late satisfaction discarded during Closing,
                T21 late space discarded during Closing, T22 recovery while Closing discards payload,
                T23 satisfaction retry survives crash, T24 confirmed not delivered)

Invariant Kill Tests (Mutation Testing & Bijection):
    21/21 PASS (I1 frame-wide, I3 scope kill, I3 attributable kill, I3 control probe,
                I6 CompletionId uniqueness kill, I6 ghost record kill, I6 completeness gap kill,
                I6 identical digest probe, I7 ledger vs records kill, I7 duplicate reconciliation kill,
                I7 ghost reconciliation kill, I7 ghost scope_spent kill, I7 identical receipt probe,
                R50/R56 canonical digest order/op_id/type collision tests,
                R57/R62 durable ExecutionReceipt authority test,
                I8 closing mutation kill, I8 clean closing probe, I9 forged visit kill,
                I9 clean history probe, I10 scope limit kill, I10 IntentFrame conservation kill,
                I10 spent>avail control probe)

Campaign 2 Basic (Declarative Search Programs):
    25/25 PASS (D01 exhaust [R19 verified], D02 successor [R19/R10 verified],
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
                D24 effectful satisfier transient retry on same candidate [R52/R59/R61 verified],
                D25 targeted effectful satisfier DeliveryUnknown [R55 verified],
                D26 satisfier retry attempt limit blocks second attempt [R59/R61 verified],
                D27 safe retry on idempotent-only operation [R60 verified],
                D28 double DeliveryUnknown on retry leaves frame in Waiting [R60 verified],
                D29 CheckedNotSatisfied node is not re-checked on subsequent expansion [R61 verified],
                D31 post-fuel Ok(None) candidate exhausts naturally [R63 verified],
                D32 space StepFailure DynamicGateRejection terminates as Failed [R64 verified])

Campaign 2 Fault (Environmental Fault Injections):
    6/6 PASS   (D07 DeliveryUnknown [Waiting verified],
                D08 safe transport retry real [Satisfied(T-retry) verified],
                D09 duplicate completion with same receipt_id,
                D10 crash-after-settlement forward recovery,
                D11 cancel-in-flight [R2 Cancelled verified],
                D12 late settlement fatal closing)

Semantic model:
    REAL / AUTONOMOUS (purely declarative search space execution)

Lowered model:
    REAL / ADVERSARIALLY HARDENED (machine-owned SatisfactionState, mandatory ExecutionReceipt authority,
    Closing semantic barrier, space StepFailure handling, ConfirmedNotDelivered transitions,
    exact canonical JSON digests, true two-way bijection invariants, snapshot-authoritative recovery)

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
    REAL / ADVERSARIALLY HARDENED (26/26 adversarial scenarios)

Executable semantic model
    REAL / AUTONOMOUS (31/31 differential programs)

Invariant checker
    SELF-TESTED (21/21 mutation kill tests & control probes)

Differential semantic preservation
    VERIFIED IN TESTED REGIME (audited across 12 adversarial review rounds, R1–R65 fixed)

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
    Closing semantic barrier, budget conservation, mandatory ExecutionReceipt authority,
    machine-owned SatisfactionState, space StepFailure recovery, ConfirmedNotDelivered,
    and differential preservation have survived 12 adversarial audit rounds.
```
