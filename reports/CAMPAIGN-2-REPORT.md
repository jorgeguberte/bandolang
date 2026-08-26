# Campaign 2 — Execution Report (Differential Semantics) — REISSUE 6

> **REISSUE 6 after sixth audit round (R25–R30).**
> The sixth audit caught subtle component-boundary issues:
> 1. Test driver popping frontier instead of machine-owned scheduling (`Continue`, `Wait`, `Stop`).
> 2. Effectful satisfier satisfaction attempts counting late rather than upon emission commit.
> 3. Non-atomic semantic application (split between `apply_semantic` and `discover_successors`/satisfaction).
> 4. I6 checking digest uniqueness rather than `CompletionId` identity.
> 5. I9 local expansion verification vulnerable to forged records.
> 6. Synthetic I8 mutation kill instead of actual attempted mutation.
> All six issues have been resolved and verified with 50/50 green tests.

## Audit repairs applied (Round 6: R25–R30)

```text
R25 Machine Owns Frontier Completely (scheduler_step)
    FIXED — deleted all driver-side pops from `d.frontier`.
    `scheduler_step(d, prog)` returns `Continue(node, op, kind)`, `Wait(reason)`,
    or `Stop(reason)`. Unrunnable nodes due to budget remain safely in frontier;
    search stops with `Stop("BudgetDepleted")` via modeled semantics.

R26 Effectful Satisfaction Commit Semantics (D17)
    FIXED — `satisfaction_attempts` increments upon the first logical `EmitExternal`
    of an effectful CheckSatisfaction request (commit point).
    Later completion/apply does NOT increment again.
    Added D17_effectful_satisfier_delivery_unknown: verifies `satisfaction_attempts == 1`
    is durably committed even when completion is lost in transport (DeliveryUnknown).

R27 Atomic Semantic Incorporation (apply_space_completion & apply_satisfier_completion)
    FIXED — `Applied` strictly means the semantic outcome is fully incorporated:
        `apply_space_completion(handle, succs)`: atomically adds successors + Applied.
        `apply_satisfier_completion(handle, node, op, ok, val)`: atomically updates satisfaction + Applied.
    Added T15 (space apply recovery) and T16 (satisfier apply recovery) proving atomicity across crashes.

R28 Fix I6 (CompletionId Tracking)
    FIXED — I6 tracks applied `CompletionId` (e.g. `handle_id:receipt_id`), not digest uniqueness.
    Kill: same CompletionId applied twice => FAIL.
    Control probe: two distinct CompletionIds with identical digest => PASS.

R29 Fix I9 Local Provenance (DispatchRecord Binding)
    FIXED — `DispatchRecord(node_id, op_id, visit_no, kind)` recorded explicitly at
    `dispatch_local` and space `emit_external`.
    Every `VisitedRecord` must strictly bind to a matching `DispatchRecord`.
    Kill: legitimate expanding node with forged `op-ghost` VisitedRecord => FAIL.

R30 Real I8 Kill
    FIXED — mutation kill attempts actual machine frontier mutation (`discover_successors`)
    while in `Closing` state, proving the machine detector flags the violation.
```

## Complete verification results

```text
Campaign 1 (Lowered Safety & Crash Recovery):
    18/18 PASS (T01–T11, T04A/B, T07B real recovery, T12 sequential stage guard,
                T13 pending exhaust drain, T14 settlement ceiling bounds,
                T15 atomic space apply recovery, T16 atomic satisfier apply recovery)

Invariant Kill Tests (Mutation Testing):
    15/15 PASS (I1 frame-wide, I3 scope kill, I3 attributable kill, I3 control probe,
                I6 CompletionId kill, I6 identical digest probe, I7 ledger vs records,
                I8 closing mutation kill [real mutation attempt], I8 clean closing probe,
                I9 forged visit kill [DispatchRecord binding], I9 clean history probe,
                I10 scope limit kill, I10 IntentFrame conservation kill,
                I10 spent>avail control probe)

Campaign 2 Basic (Declarative Search Programs):
    11/11 PASS (D01 exhaust [R19 verified], D02 successor [R19/R10 verified],
                D03 max_steps + partial [R4 verified], D04 Ok(None), D05 Err+abort,
                D06 external, D13 ceiling vs actual charge [R12/R14 verified],
                D14 budget headroom depletion [R15 verified],
                D15 unaffordable ceiling refused [R20/R25 verified],
                D16 effectful satisfier [R24 verified],
                D17 effectful satisfier commit point under DeliveryUnknown [R26 verified])

Campaign 2 Fault (Environmental Fault Injections):
    6/6 PASS   (D07 DeliveryUnknown, D08 safe retry, D09 duplicate completion,
                D10 crash-after-settlement forward recovery,
                D11 cancel-in-flight [R2 Cancelled verified],
                D12 late settlement fatal closing)

Semantic model:
    REAL / AUTONOMOUS (purely declarative search space execution)

Lowered model:
    REAL / ADVERSARIALLY HARDENED (atomic semantic incorporation, strict lifecycle,
    real local dispatch, machine-owned scheduling, transactional recovery)

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
    REAL / AUTONOMOUS (17/17 differential programs)

Invariant checker
    SELF-TESTED (15/15 mutation kill tests & control probes)

Differential semantic preservation
    VERIFIED IN TESTED REGIME (audited across 6 review rounds, R1–R30 fixed)

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
    UNBLOCKED per campaign plan — Phase D lowering safety, strict lifecycle,
    budget conservation, atomic semantic incorporation, and differential
    preservation have survived 6 rigorous adversarial audit rounds.
```
