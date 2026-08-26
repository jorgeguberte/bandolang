# Campaign 2 — Execution Report (Differential Semantics) — REISSUE 4

> **REISSUE 4 after fourth audit round (R15–R18).**
> The fourth audit caught critical budget headroom regeneration, unconstrained adversarial
> settlement bounds, non-transactional bookkeeping, non-atomic StageLocal handles,
> a dead I8 checker, and an incorrect I10 checker.
> All issues have been resolved across both the semantic model and the lowered machine.

## Audit repairs applied (Round 4: R15–R18)

```text
R15 BudgetScope Headroom & D14 Budget Depletion
    FIXED — scope headroom is strictly `limit - spent - committed`.
    SemanticFrame and lowered driver both enforce CanAfford against prog.budget_limit.
    Added D14_budget_depleted_exhausts (limit=100, A=60, B=60 => B not affordable,
    spent=60, zero second effect, Exhausted).

R16 Adversarial Settlement Receipt Bounds & T14
    FIXED — settle() enforces:
        0 <= amount <= reserved_ceiling
        resource == reserved_resource
        st.reserved_amount == 0 and amount > 0 => TransitionError
        amount > reserved_ceiling => FatalInvariantViolation (durable protocol violation)
    Added T14_SETTLEMENT_EXCEEDS_CEILING to Campaign 1 regression suite.

R17 Transactional Bookkeeping & Atomic StageLocal Handle
    FIXED — StageLocal creates stable InFlightHandle atomically with reservation
    and outbox, transitioning state to "Staged".
    HarnessBookkeeping updates attribution strictly AFTER transitions succeed.
    cancel() automatically aborts staged handles, refunds reservations, and clears attribution.
    T01 asserts no phantom reservations in bookkeeping on rejected stage.
    T02 verifies cancel-after-stage-before-emit autonomously without manual test mutation.
    T12 verifies sequential in-flight guard blocks second StageLocal while first is unsettled.
    attributable_owner_reserved observable reflects strictly this CF's active reservations.
    intent_available_consumed observable tracks exact net spent funds.

R18 Invariant Checkers & Self-Testing (I8 & I10)
    FIXED — I8 real check (frontier_mutations_during_closing == 0) + I8 kill test.
    FIXED — I10 verifies `committed >= 0`, `spent >= 0`, `committed + spent <= limit`,
    and IntentFrame conservation `initial_total == available + reserved + spent`.
    Added I10 conservation kill and I10 control probe (valid spent > available_current).
```

## Complete verification results

```text
Campaign 1 (Lowered Safety & Crash Recovery):
    16/16 PASS (T01–T11, T04A/B, T07B, T12 sequential regression,
                T13 pending exhaust, T14 settlement ceiling violation)

Invariant Kill Tests (Mutation Testing):
    14/14 PASS (I1 frame-wide, I3 scope kill, I3 attributable reservation kill,
                I3 control probe, I6 double apply, I7 ledger vs records,
                I8 closing frontier mutation kill, I8 clean closing probe,
                I9 dispatch history, I10 scope limit kill,
                I10 IntentFrame conservation kill, I10 spent>avail control probe)

Campaign 2 Basic (Declarative Search Programs):
    8/8 PASS   (D01 exhaust, D02 successor satisfied [R10 verified],
                D03 max_steps + partial [R4 verified],
                D04 Ok(None), D05 Err+abort, D06 external,
                D13 budget ceiling vs actual charge [R12/R14 verified],
                D14 budget headroom depletion [R15 verified])

Campaign 2 Fault (Environmental Fault Injections):
    6/6 PASS   (D07 DeliveryUnknown, D08 safe retry, D09 duplicate completion,
                D10 crash-after-settlement forward recovery,
                D11 cancel-in-flight [R2 Cancelled verified],
                D12 late settlement fatal closing)

Semantic model:
    REAL / AUTONOMOUS (enforces space, policy, affordability, and stubs)

Lowered model:
    REAL / AUTONOMOUS (enforces atomic staging, headroom, settlement bounds, and recovery)

Differential counterexamples:
    NONE IN TESTED REGIME (strictly independent: declarative programs,
    autonomous execution, full budget conservation, exact values,
    lifecycle distinctions, and obligation parity)

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
    REAL / EXERCISED (16/16 adversarial scenarios)

Executable semantic model
    REAL / AUTONOMOUS (14/14 differential programs)

Invariant checker
    SELF-TESTED (14/14 mutation kill tests & control probes)

Differential semantic preservation
    VERIFIED IN TESTED REGIME (audited across 4 review rounds, R1–R18 fixed)

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
    UNBLOCKED per campaign plan — Phase D lowering safety, budget conservation,
    and semantic differential preservation have survived 4 adversarial audit cycles.
```
