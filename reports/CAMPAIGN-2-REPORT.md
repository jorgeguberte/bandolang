# Campaign 2 — Execution Report (Differential Semantics) — REISSUE

> **REISSUE after audit NO-GO on `03d27d4`.** The original report claimed
> "VERIFIED IN TESTED REGIME" and "Item 3 UNBLOCKED". The audit correctly
> identified that the apparatus normalized away real semantic distinctions
> (R1–R7). This reissue reflects the repaired state. Prior claims are
> WITHDRAWN and superseded by this document.

## Audit repairs applied

```text
R1  satisfaction_attempts
    FIXED — EmitExternal no longer increments attempts; only
    CheckSatisfaction does. All scenario-side -=1 normalizations removed.

R2  cancellation
    FIXED — new terminal status Cancelled; PendingCancelled drains to
    Cancelled, never Exhausted. Semantic model mirrors it. Differential
    observation now distinguishes cancellation from exhaustion (D11 asserts
    Cancelled explicitly).

R3  satisfaction transition
    FIXED — check_satisfaction Ok(Some(T)) performs the normative Satisfied
    transition itself. No scenario sets frame_status="Satisfied" manually.

R4  D03 genuinely differential
    FIXED — D03 descriptor: two external expansions reaching max_steps,
    partial produced, CheckSatisfaction(partial) succeeds AFTER expansion
    fuel ends → Satisfied(T-partial). Both models execute the same
    descriptor independently; result matches.

R5  external semantic execution
    FIXED — scenarios.py defines shared Scenario/Step descriptors;
    drive_semantic and drive_lowered derive effects/budget/attempts from the
    descriptor alone. No scenario pre-fills observations.

R6  value preservation
    FIXED — compare() does exact T-value equality on all fields including
    value. None/non-None normalization deleted.

R7  sequential in-flight invariant
    FIXED — I1 strengthened: at most one unsettled handle for ANY request in
    the frame. New kill test (h1@r1 + h2@r2 unsettled ⇒ I1 must fail).
    New transition guard: first emission of r2 while r1 unsettled is REFUSED;
    regression verified. Retry of same request remains exempt.
```

## Result (post-repair)

```text
Campaign 2 — Differential Semantics

Basic scenarios:
    6/6 PASS   (D01 exhaust, D02 successor satisfied, D03 max_steps +
                partial checked, D04 Ok(None), D05 Err+abort, D06 external)

Fault/recovery scenarios:
    6/6 PASS   (D07 DeliveryUnknown, D08 safe retry, D09 duplicate completion,
                D10 crash-after-settlement forward recovery,
                D11 cancel-in-flight [Cancelled ≠ Exhausted],
                D12 late settlement after fatal closing)

Campaign 1 regressions:
    13/13 PASS (T02/T10 assertions updated from Exhausted to Cancelled —
                they had baked in the R2 defect as expected behavior)

Invariant kill tests:
    8/8 PASS   (including R7-strengthened I1 kill on distinct requests)
    Transition regression: second request while first unsettled REFUSED

Semantic model:
    REAL / EXERCISED (descriptor-driven, independent derivation)

Lowered model:
    REAL / EXERCISED (same descriptors, independent derivation)

Differential counterexamples:
    NONE IN TESTED REGIME (post-repair regime is strictly stronger:
    exact values, attempt accounting by CheckSatisfaction only,
    cancellation distinguished, I1 frame-wide)

LLM calls / network / randomness:
    0 / 0 / 0
```

## Evidence level statement (reissued)

```text
Phase D
    RESOLVED FOR CURRENT PHASE

Design
    DESIGN-LEVEL
    ADVERSARIALLY REVIEWED

Executable lowered state-machine model
    REAL / EXERCISED (13/13 adversarial)

Executable semantic model
    REAL / EXERCISED (12/12 differential, exact-value comparison)

Differential semantic preservation
    VERIFIED IN TESTED REGIME (post-audit repairs R1–R7 incorporated)

Actual compiler/lowering implementation
    NOT YET VERIFIED

Formal soundness
    NOT PROVED

best_partial / lineage / Ψ
    OUT OF SCOPE (Open Question #8 OPEN; Campaign 2B pending)
```

## Item 3 gate

Reconsidered per audit instructions: with R1–R7 incorporated and all batteries
green under the strengthened regime, **Item 3 unblocked** is reasserted —
with the explicit caveat that this claim has now survived one adversarial
audit cycle, and any further NO-GO supersedes it again.
