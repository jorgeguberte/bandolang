# Campaign 2 — Execution Report (Differential Semantics) — REISSUE 15 (FINAL PHASE-D ACCEPTANCE)

> **REISSUE 15 after Final Phase-D Acceptance with A2-S aligned reference model.**
> 1. A1: Transition-level satisfaction attempt limit enforcement persisted in domain configuration (`d.max_satisfaction_attempts`). Both `check_satisfaction` and `stage_local(is_expansion=False)` reject attempts exceeding the ceiling with strict zero delta (negative mutation tests verified).
> 2. A2 / A2-S: `SemanticFrame` and `Lowered` models align exactly on space `StepFailure` with `on_step_failure="requeue"`. Step failures consume exactly 1 semantic step, debit cost/effect once, mark node `Queued`, restore node to `frontier` without calling `expand()` or incorporating successors prematurely. Next scheduler selection executes a genuinely new semantic attempt with a fresh `request_id` (`req:opRoot:root:2`) and succeeds.
> D34 verifies exact trajectory parity: step_count=2, visited=['root', 'root'], effects=['external(opRoot)', 'external(opRoot)'], budget_spent=20, and final `Satisfied("T-requeue-success")`.
> All 81 test cases pass across all 4 test suites without divergence or false positives.

## Audit repairs applied (Final Acceptance: A1 + A2 / A2-S)

```text
A1 Transition-Level Satisfaction Attempt Ceiling
    FIXED — `ConvergeTransactionDomain.max_satisfaction_attempts` is a persistent machine configuration.
    `check_satisfaction()` and `stage_local(is_expansion=False)` check `satisfaction_attempts >= max_satisfaction_attempts`
    before any state or accounting mutation and raise `TransitionError("SatisfactionLimitReached")`.
    Direct negative mutation tests prove strict rejection with zero delta on counters and reservations.

A2 / A2-S Space StepFailure Requeue Policy Parity (D34)
    FIXED — `SemanticFrame` owns per-node expansion attempt counters and resolves sequence-valued
    `space_faults` per attempt. On `StepFailure` with `requeue`: consumes 1 step, marks node `Queued`,
    restores to `frontier`, and continues without premature successor discovery. Lowered machine stages
    fresh `request_id` on attempt 2 and discovers successors only upon success.
    D34 trajectory assertions prove strict parity on step_count (2), visited, effects, and spent budget.
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
                A1 transition-level satisfaction attempt ceiling & zero-delta kill,
                I8 closing mutation kill, I8 clean closing probe, I9 forged visit kill,
                I9 clean history probe, I10 scope limit kill, I10 IntentFrame conservation kill,
                I10 spent>avail control probe)

Campaign 2 Basic (Declarative Search Programs):
    27/27 PASS (D01 exhaust [R19 verified], D02 successor [R19/R10 verified],
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
                D33 space StepFailure with prune policy allows search to continue -> Satisfied [R69 verified],
                D34 space StepFailure with requeue policy retries with fresh request_id -> Satisfied [A2/A2-S verified])

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
    REAL / ADVERSARIALLY HARDENED (machine-owned RunnableAction scheduler, transition-level attempt limits,
    mandatory ExecutionReceipt authority, Closing semantic barrier, declarative Space StepFailure requeue/prune handling,
    ConfirmedNotDelivered lifecycle, exact canonical JSON digests, true two-way bijection invariants, snapshot-authoritative recovery)

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
    REAL / AUTONOMOUS (33/33 differential programs)

Invariant checker
    SELF-TESTED (21/21 mutation kill tests & control probes)

Differential semantic preservation
    VERIFIED IN TESTED REGIME (audited across 14 adversarial review rounds, R1–R70 + A1–A2/A2-S fixed)

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
    transition-level attempt limits (A1), declarative StepFailure requeue with fresh request identity (A2/A2-S),
    ConfirmedNotDelivered, and differential preservation have survived 14 adversarial audit rounds with zero bypasses.
```
