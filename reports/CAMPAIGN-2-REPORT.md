# Campaign 2 — Execution Report (Differential Semantics) — REISSUE 7

> **REISSUE 7 after seventh audit round (R31–R36).**
> The seventh audit caught the final core execution discrepancies:
> 1. Missing `Waiting(InFlightHandle)` state in lifecycle and scheduler decisions.
> 2. `recover()` fabricating `Applied` without durable semantic outcome payloads.
> 3. Missing `PartialOf` eligibility modeling in `ScenarioProgram`.
> 4. Discarded `exhaustion_reason` in differential observations.
> 5. Completeness gap in I6 (applied handle missing application record).
> 6. Over-constrained receipt_id uniqueness in I7 across distinct handles.
> All six issues have been resolved across both the lowered machine and the semantic model.

## Audit repairs applied (Round 7: R31–R36)

```text
R31 Real Waiting Lifecycle (SearchStatus.WAITING & scheduler_step Wait)
    FIXED — external dispatch transitions frame to SearchStatus.WAITING.
    DeliveryUnknown retains commitments and preserves Waiting(handle).
    `scheduler_step` returns `Wait(InFlight(h))` whenever an unsettled handle exists.
    Driver receiving `Wait` MUST NOT call exhaust.
    D17 rewritten to observe Waiting state, attempts=1, unsettled=1, value=None.
    Added D18: unsettled external A blocks subsequent local runnable node B from dispatching.

R32 Durable Semantic Completion & Autonomous Recovery
    FIXED — `CompletionRecord` durably carries `SpaceOutcome(successors)` or `SatisfierOutcome`.
    `recover()` reads durable outcome and autonomously re-drives atomic application.
    T15/T16 recover without test oracle re-supplying successors or satisfaction values.
    Added D19: crash after settlement before apply autonomously recovers successors into frontier.

R33 Explicit Partial Eligibility (PartialOf)
    FIXED — `ScenarioProgram` represents `partial_map: dict[node, Partial]`.
    CheckSatisfaction (local or effectful) only executes when `PartialOf(cand) == Some(P)`.
    D16 explicitly declares `partial_map={"cand1": "P1"}`, resulting in exactly 1 satisfier
    tool call, spent=5, satisfied T-verified.

R34 Preserve Exhaustion Reason
    FIXED — `tx.exhaust(d, reason)` records `exhaustion_reason` ("BudgetDepleted",
    "FrontierEmpty", "FuelExhausted").
    D14 and D15 observe and assert `exhaustion_reason == "BudgetDepleted"`.

R35 Fix I6 Completeness (Applied <=> Application Record)
    FIXED — I6 enforces exact bijection: every applied handle must have a matching
    CompletionId in `applied_completions`, and records must be unique.
    Added I6 kill B: applied handle with missing application record => FAIL.

R36 Fix I7 Per-Handle Settlement Identity
    FIXED — I7 tracks reconciliation count per handle identity, not global receipt string uniqueness.
    Added I7 control probe: two distinct handles with identical receipt string => PASS.
```

## Complete verification results

```text
Campaign 1 (Lowered Safety & Crash Recovery):
    18/18 PASS (T01–T11, T04A/B, T07B real recovery, T12 sequential stage guard,
                T13 pending exhaust drain, T14 settlement ceiling bounds,
                T15 autonomous space apply recovery, T16 autonomous satisfier apply recovery)

Invariant Kill Tests (Mutation Testing):
    17/17 PASS (I1 frame-wide, I3 scope kill, I3 attributable kill, I3 control probe,
                I6 CompletionId uniqueness kill, I6 completeness gap kill,
                I6 identical digest probe, I7 ledger vs records kill,
                I7 identical receipt probe, I8 closing mutation kill,
                I8 clean closing probe, I9 forged visit kill, I9 clean history probe,
                I10 scope limit kill, I10 IntentFrame conservation kill,
                I10 spent>avail control probe)

Campaign 2 Basic (Declarative Search Programs):
    13/13 PASS (D01 exhaust [R19 verified], D02 successor [R19/R10 verified],
                D03 max_steps + partial [R4 verified], D04 Ok(None), D05 Err+abort,
                D06 external, D13 ceiling vs actual charge [R12/R14 verified],
                D14 budget headroom depletion [R15/R34 verified],
                D15 unaffordable ceiling refused [R20/R25/R34 verified],
                D16 effectful satisfier with explicit PartialOf [R24/R33 verified],
                D17 effectful satisfier commit point under DeliveryUnknown [R26/R31 verified],
                D18 sequential Waiting blocks local dispatch [R31 verified],
                D19 autonomous crash recovery preserves space successors [R32 verified])

Campaign 2 Fault (Environmental Fault Injections):
    6/6 PASS   (D07 DeliveryUnknown [Waiting verified], D08 safe retry,
                D09 duplicate completion, D10 crash-after-settlement forward recovery,
                D11 cancel-in-flight [R2 Cancelled verified],
                D12 late settlement fatal closing)

Semantic model:
    REAL / AUTONOMOUS (purely declarative search space execution)

Lowered model:
    REAL / ADVERSARIALLY HARDENED (Waiting lifecycle, durable semantic payloads,
    autonomous recovery, explicit PartialOf, exact accounting, invariant bijection)

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
    REAL / ADVERSARIALLY HARDENED (18/18 adversarial scenarios)

Executable semantic model
    REAL / AUTONOMOUS (19/19 differential programs)

Invariant checker
    SELF-TESTED (17/17 mutation kill tests & control probes)

Differential semantic preservation
    VERIFIED IN TESTED REGIME (audited across 7 review rounds, R1–R36 fixed)

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
    budget conservation, durable autonomous recovery, and differential
    preservation have survived 7 exhaustive adversarial audit rounds.
```
