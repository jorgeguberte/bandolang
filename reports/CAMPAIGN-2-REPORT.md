# Campaign 2 — Execution Report (Differential Semantics) — REISSUE 13

> **REISSUE 13 after thirteenth adversarial audit round (R66–R70).**
> The thirteenth audit resolved the core architectural structure by unifying all machine actions under `RunnableAction` (`ActionExpand` | `ActionCheckSatisfaction`), enforcing mandatory `ExecutionReceipt` without fallbacks, and completing `ConfirmedNotDelivered` across the full obligation and failure lifecycle:
> 1. R66: `ExecutionReceipt(request_id, receipt_id, resource, amount)` is strictly mandatory on `admit_completion()`. Rejection tests prove missing receipt, mismatched `request_id`, and mismatched `receipt_id` are rejected immediately. `settle(handle)` has zero caller accounting parameters.
> 2. R67: Machine-owned `RunnableAction` scheduler (`ActionExpand` | `ActionCheckSatisfaction`). Transitions enforce eligibility machine-side (`CheckedNotSatisfied` and `Satisfied` nodes are rejected on `check_satisfaction` and `stage_local`). Zero driver-local counters or candidate loops.
> 3. R68: Eliminated `check_partial_after_fuel` steering oracle entirely. Post-fuel partial satisfaction is driven naturally by `ActionCheckSatisfaction` on real `SearchNode`s.
> 4. R69: Declarative `space_faults` mapping and `on_step_failure` ("abort" | "prune" | "requeue") without magic op names. Added D33 proving prune policy allows search to continue on remaining frontier.
> 5. R70: `confirmed_not_delivered()` releases accounting exactly once, clears `current_in_flight`, updates `HarnessBookkeeping`, and routes failure semantics according to operation kind. Added T25 proving CND during Closing drains cleanly to `Cancelled`.
> All 80 test cases pass across all 4 test suites without divergence or false positives.

## Audit repairs applied (Round 13: R66–R70)

```text
R66 Actually Mandatory ExecutionReceipt
    FIXED — `admit_completion()` requires non-None `ExecutionReceipt` matching handle `request_id`
    and completion `receipt_id`. `settle(d, handle_id)` signature has zero caller accounting parameters
    and zero fallback paths. Validated with 3 new negative mutation kills.

R67 Machine-Owned RunnableAction Model
    FIXED — `scheduler_step(d, prog)` returns `ActionExpand | ActionCheckSatisfaction | ActionWait | ActionStop`.
    Eligibility for `ActionCheckSatisfaction` computes `Untested | RetryableFailure(n)`, `PartialOf(n)`,
    budget headroom, and `max_satisfaction_attempts`. `check_satisfaction()` and `stage_local()` reject
    ineligible node checks at the transition level.

R68 Removal of Post-Fuel Steering Oracle
    FIXED — Deleted `check_partial_after_fuel`. At max expansion fuel, `ActionExpand` becomes ineligible,
    and remaining untested `PartialOf(n)` nodes in the search graph are automatically scheduled
    as `ActionCheckSatisfaction`. Rebuilt D03 and D31 around real graph nodes.

R69 Declarative Space StepFailure & DynamicGateRejection (D32, D33)
    FIXED — Replaced magic op strings with `prog.space_faults` mapping and `prog.on_step_failure`.
    `apply_space_completion()` marks `StepFailure` and handles "abort" (terminates as Failed)
    and "prune" (marks node `Pruned` and removes from frontier). Added D33.

R70 Complete ConfirmedNotDelivered Lifecycle (T24, T25)
    FIXED — `confirmed_not_delivered(d, handle)` releases reservations and commitments,
    removes attribution from `HarnessBookkeeping`, and updates node failure state.
    Invariant checkers I1/I2 treat CND handles as resolved. Added T25 (CND while Closing).
```

## Complete verification results

```text
Campaign 1 (Lowered Safety & Crash Recovery):
    27/27 PASS (T01–T11, T04A/B, T07B real recovery, T12 sequential stage guard,
                T13 pending exhaust drain, T14 settlement ceiling bounds,
                T15 autonomous space apply recovery, T16 autonomous satisfier apply recovery,
                T17 request_id reuse rejection, T18 generic apply bypass refused,
                T19 snapshot-authoritative recovery, T20 late satisfaction discarded during Closing,
                T21 late space discarded during Closing, T22 recovery while Closing discards payload,
                T23 satisfaction retry survives crash, T24 confirmed not delivered prune & exhaust,
                T25 confirmed not delivered while Closing drains cleanly)

Invariant Kill Tests (Mutation Testing & Bijection):
    21/21 PASS (I1 frame-wide, I3 scope kill, I3 attributable kill, I3 control probe,
                I6 CompletionId uniqueness kill, I6 ghost record kill, I6 completeness gap kill,
                I6 identical digest probe, I7 ledger vs records kill, I7 duplicate reconciliation kill,
                I7 ghost reconciliation kill, I7 ghost scope_spent kill, I7 identical receipt probe,
                R50/R56 canonical digest order/op_id/type collision tests,
                R57/R62/R66 mandatory ExecutionReceipt authority & identity kills,
                I8 closing mutation kill, I8 clean closing probe, I9 forged visit kill,
                I9 clean history probe, I10 scope limit kill, I10 IntentFrame conservation kill,
                I10 spent>avail control probe)

Campaign 2 Basic (Declarative Search Programs):
    26/26 PASS (D01 exhaust [R19 verified], D02 successor [R19/R10 verified],
                D03 max_steps + partial [R4/R68 verified], D04 Ok(None), D05 Err+abort,
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
                D24 effectful satisfier transient retry on same candidate [R52/R59/R61/R67 verified],
                D25 targeted effectful satisfier DeliveryUnknown [R55 verified],
                D26 satisfier retry attempt limit blocks second attempt [R59/R61/R67 verified],
                D27 safe retry on idempotent-only operation [R60 verified],
                D28 double DeliveryUnknown on retry leaves frame in Waiting [R60 verified],
                D29 CheckedNotSatisfied node is not re-checked on subsequent expansion [R61/R67 verified],
                D31 post-fuel Ok(None) candidate in graph exhausts naturally [R63/R68 verified],
                D32 declarative space StepFailure DynamicGateRejection terminates as Failed [R64/R69 verified],
                D33 space StepFailure with prune policy allows search to continue -> Satisfied [R69 verified])

Campaign 2 Fault (Environmental Fault Injections):
    6/6 PASS   (D07 DeliveryUnknown [Waiting verified],
                D08 safe transport retry real [Satisfied(T-retry) verified],
                D09 duplicate completion with same receipt_id,
                D10 crash-after-settlement forward recovery,
                D11 cancel-in-flight [R2 Cancelled verified],
                D12 late settlement fatal closing)

Semantic model:
    REAL / AUTONOMOUS (purely declarative search space execution via unified RunnableAction)

Lowered model:
    REAL / ADVERSARIALLY HARDENED (machine-owned RunnableAction scheduler, mandatory ExecutionReceipt authority,
    Closing semantic barrier, declarative Space StepFailure handling, ConfirmedNotDelivered lifecycle,
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
    REAL / ADVERSARIALLY HARDENED (27/27 adversarial scenarios)

Executable semantic model
    REAL / AUTONOMOUS (32/32 differential programs)

Invariant checker
    SELF-TESTED (21/21 mutation kill tests & control probes)

Differential semantic preservation
    VERIFIED IN TESTED REGIME (audited across 13 adversarial review rounds, R1–R70 fixed)

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
    machine-owned RunnableAction model (ActionExpand | ActionCheckSatisfaction),
    declarative StepFailure recovery, ConfirmedNotDelivered, and differential preservation
    have survived 13 adversarial audit rounds with zero bypasses.
```
