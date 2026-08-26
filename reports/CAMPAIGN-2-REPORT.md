# Campaign 2 — Execution Report (Differential Semantics) — REISSUE 5

> **REISSUE 5 after fifth audit round (R19–R24).**
> The fifth audit caught:
> 1. Local/pure operations routed through StageLocal/outbox rather than DISPATCH_LOCAL.
> 2. Test driver mutating `d.frontier` directly rather than through machine transitions.
> 3. Loose handle lifecycle allowing out-of-order transitions.
> 4. Incomplete crash recovery tests (T07B tautology, T09 missing recovery branch).
> 5. Untested effectful satisfier coverage.
> All five issues have been formally resolved in both the lowered machine and the semantic model.

## Audit repairs applied (Round 5: R19–R24)

```text
R19 Real Local Dispatch (dispatch_local)
    FIXED — local/pure expansions execute strictly via `dispatch_local()`:
        consumes step fuel
        records visited
        discovers successors
        creates ZERO handles, ZERO outbox records, ZERO completions, ZERO settlements
    D01 and D02 explicitly verify `handles == 0`, `outbox == 0`, `completions == 0`.

R20 Machine-Owned Frontier & Budget Ineligibility
    FIXED — deleted `d.frontier.clear()` from test driver entirely.
    Machine-level helpers (`discover_successors`, `dispatch_local`, `classify_runnable`)
    own all frontier mutations.
    SemanticFrame and lowered driver both enforce CanAfford using cost ceiling `op.cost`.
    Added D15_unaffordable_ceiling_refused (remaining headroom 40 < ceiling 60,
    eventual charge 10 => operation MUST NOT dispatch, exhausts with 1 step).

R21 Strict Handle Lifecycle Enforcement
    FIXED — strictly ordered state ladder:
        Staged -> EmitExternal -> InFlight/DeliveryUnknown
        InFlight -> CompletionRecorded -> Delivered
        Delivered -> Settle -> Settled
        Settled -> ApplySemantic -> Applied
    Refuses: completion-before-emit, settlement-before-completion, apply-before-settle.
    Fatal invariant violations automatically and immediately enter Closing(PendingFailure).

R22 Real Crash Recovery Tests (T07B & T09)
    FIXED — T07B deletes tautology and reconstructs a fresh domain from durable post-conflict state;
    proves conflict evidence, handle, and unsettled reservation survive RAM crash.
    FIXED — T09 implements `recover(..., "mid_apply_loop")` transactional atomicity:
    resets partial uncommitted RAM state back to durable pre-state before clean re-apply.

R23 End-to-End I8 Checker (Frontier Frozen During Closing)
    FIXED — all frontier additions guarded by `discover_successors()` / `apply_semantic()`;
    attempted frontier mutation while Closing raises TransitionError.
    I8 kill verified with mutation testing.

R24 Effectful Satisfier Coverage (D16)
    ADDED — D16_effectful_satisfier: space expansion + external satisfier tool call
    with its own budget, effect trace, and settlement. Both models execute and match.
```

## Complete verification results

```text
Campaign 1 (Lowered Safety & Crash Recovery):
    16/16 PASS (T01–T11, T04A/B, T07B real recovery, T12 sequential stage guard,
                T13 pending exhaust drain, T14 settlement ceiling bounds)

Invariant Kill Tests (Mutation Testing):
    14/14 PASS (I1 frame-wide, I3 scope kill, I3 attributable kill, I3 control probe,
                I6 double apply, I7 ledger vs records, I8 closing mutation kill,
                I8 clean closing probe, I9 dispatch history, I10 scope limit kill,
                I10 IntentFrame conservation kill, I10 spent>avail control probe)

Campaign 2 Basic (Declarative Search Programs):
    10/10 PASS (D01 exhaust [R19 verified], D02 successor satisfied [R19/R10 verified],
                D03 max_steps + partial [R4 verified], D04 Ok(None), D05 Err+abort,
                D06 external, D13 ceiling vs actual charge [R12/R14 verified],
                D14 budget headroom depletion [R15 verified],
                D15 unaffordable ceiling refused [R20 verified],
                D16 effectful satisfier [R24 verified])

Campaign 2 Fault (Environmental Fault Injections):
    6/6 PASS   (D07 DeliveryUnknown, D08 safe retry, D09 duplicate completion,
                D10 crash-after-settlement forward recovery,
                D11 cancel-in-flight [R2 Cancelled verified],
                D12 late settlement fatal closing)

Semantic model:
    REAL / AUTONOMOUS (purely declarative search space execution)

Lowered model:
    REAL / ADVERSARIALLY HARDENED (strict lifecycle, real local dispatch,
    machine-owned frontier, transactional recovery)

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
    REAL / ADVERSARIALLY HARDENED (16/16 adversarial scenarios)

Executable semantic model
    REAL / AUTONOMOUS (16/16 differential programs)

Invariant checker
    SELF-TESTED (14/14 mutation kill tests & control probes)

Differential semantic preservation
    VERIFIED IN TESTED REGIME (audited across 5 review rounds, R1–R24 fixed)

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
    budget conservation, and semantic differential preservation have survived
    5 rigorous adversarial audit rounds.
```
