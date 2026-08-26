# Campaign 2 — Execution Report (Differential Semantics) — REISSUE 3

> **REISSUE 3 after third audit round (R12–R14).**
> Previous audits resolved apparatus oracles and driver bypasses (R1–R11).
> The third audit caught a real resource-conservation defect in the lowered model's
> ledger reconciliation, an unexercised branch in invariant I3, a drain-to-Satisfied bug
> in PendingExhausted, and missing obligation observables in differential comparison.
> All issues have been formally resolved in the implementation and verified.

## Audit repairs applied (Round 3: R12–R14)

```text
R12 IntentFrame Budget Ledger & I3 Attribution
    FIXED — StageLocal reserves ceiling R:
        intent_available -= R
        intent_reserved  += R
        scope_committed  += R
    Settlement reconciles actual charge C <= R:
        intent_reserved  -= R
        intent_spent     += C
        intent_available += (R - C)    # unspent ceiling refunded
        scope_committed  -= R
        scope_spent      += C
    I3 Attribution:
        Removed dead `_all_released() = True`.
        HarnessBookkeeping explicitly tracks active reservations attributable to THIS CF.
        Added I3 kill B (scope==0 but attributable owner reservation active => MUST FAIL).
        Added I3 control probe (reservation belonging to another CF => MUST PASS).

R13 PendingExhausted Non-Satisfaction Drain
    FIXED — exhaust() with pending obligations sets Closing(PendingExhausted).
    finish_if_drained() maps PendingExhausted -> Exhausted (NEVER Satisfied).
    Added T13_EXHAUST_WHILE_COMMITMENT_PENDING to Campaign 1 regression suite.

R14 Differential Obligation & Ledger Observables
    FIXED — differential observation now compares:
        outstanding_scope_commitment
        unsettled_request_count
        attributable_owner_reserved
        intent_available_delta
    Added D13_budget_ceiling_vs_actual_charge (reserve 10, charge 6 => available delta -6,
    spent 6, reserved 0, obligations 0).
    Eliminated premature Closing -> terminal status mapping in lowered observation.
```

## Complete verification results

```text
Campaign 1 (Lowered Safety & Crash Recovery):
    15/15 PASS (T01–T11, T04A/B, T07B, T12 sequential regression, T13 pending exhaust)

Invariant Kill Tests (Mutation Testing):
    10/10 PASS (I1 frame-wide, I3 scope kill, I3 attributable reservation kill,
                I3 control probe, I6 double apply, I7 ledger vs records,
                I9 dispatch history, I10 minted ownership)

Campaign 2 Basic (Declarative Search Programs):
    7/7 PASS   (D01 exhaust, D02 successor satisfied [R10 verified],
                D03 max_steps + partial [R4 verified],
                D04 Ok(None), D05 Err+abort, D06 external,
                D13 budget ceiling vs actual charge [R12/R14 verified])

Campaign 2 Fault (Environmental Fault Injections):
    6/6 PASS   (D07 DeliveryUnknown, D08 safe retry, D09 duplicate completion,
                D10 crash-after-settlement forward recovery,
                D11 cancel-in-flight [R2 Cancelled verified],
                D12 late settlement fatal closing)

Semantic model:
    REAL / AUTONOMOUS (executes ScenarioProgram independently)

Lowered model:
    REAL / AUTONOMOUS (executes ScenarioProgram independently)

Differential counterexamples:
    NONE IN TESTED REGIME (now covering lifecycle, fuel, visited, frontier,
    effects, exact values, commitments, and budget conservation)

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
    REAL / EXERCISED (15/15 adversarial scenarios)

Executable semantic model
    REAL / AUTONOMOUS (13/13 differential programs)

Invariant checker
    SELF-TESTED (10/10 mutation kill tests)

Differential semantic preservation
    VERIFIED IN TESTED REGIME (audited across 3 review rounds, R1–R14 fixed)

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
    UNBLOCKED per campaign plan — Phase D lowering safety and semantic
    differential preservation have survived 3 rigorous adversarial audit cycles.
```
