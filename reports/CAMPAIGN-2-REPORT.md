# Campaign 2 — Execution Report (Differential Semantics) — REISSUE 2

> **REISSUE 2 after second audit round.** The second audit correctly identified
> that scenario descriptors were functioning as trace/outcome oracles (R8),
> `drive_semantic` was bypassing `SemanticFrame` methods (R9), D02 had
> regressed into expanding B (R10), and the sequential in-flight emission
> regression needed persistent test coverage (R11).
> All four issues have been resolved.

## Audit repairs applied (Round 2: R8–R11)

```text
R8  declarative ScenarioProgram (no trace oracle)
    FIXED — scenarios.py defines ScenarioProgram with initial_frontier,
    graph successors, OpDef dictionary, satisfier mapping, on_satisfier_error
    policy, and FaultSpec. It contains ZERO ordered step traces and ZERO
    end_state oracles. Both models derive their own execution path from the
    space definition alone.

R9  SemanticFrame executes autonomously via internal methods only
    FIXED — SemanticFrame.run_program(prog) executes search purely through its
    own expand(), check_satisfaction(), cancel(), and exhaust() logic. Drivers
    never mutate internal status, outcome, or satisfaction_attempts.

R10 D02 restored: successor satisfaction without expansion
    FIXED — D02: Expand(A) -> successor B -> CheckSatisfaction(B) -> Satisfied.
    Explicit assertion verifies: B is NEVER expanded, step_count==1,
    visited==['A'], value=='T-value-B'.

R4  D03 explicit step_count check
    VERIFIED — explicit assertion verifies step_count==max_steps (2) BEFORE
    partial check -> Satisfied(T-partial).

R11 sequential in-flight regression test persisted
    FIXED — T12 added to test_scenarios.py: emitting r2 while r1 is unsettled
    is proven refused; after r1 settles, r2 is admitted.
```

## Result (post-Round 2 repair)

```text
Campaign 2 — Differential Semantics

Basic scenarios (declarative programs):
    6/6 PASS   (D01 exhaust, D02 successor satisfied [R10 verified],
                D03 max_steps + partial checked [R4 verified],
                D04 Ok(None), D05 Err+abort, D06 external)

Fault/recovery scenarios (declarative programs):
    6/6 PASS   (D07 DeliveryUnknown, D08 safe retry, D09 duplicate completion,
                D10 crash-after-settlement forward recovery,
                D11 cancel-in-flight [R2 Cancelled verified],
                D12 late settlement after fatal closing)

Campaign 1 regressions:
    14/14 PASS (T01–T11 + T12 sequential in-flight emission regression)

Invariant kill tests:
    8/8 PASS   (including R7-strengthened I1 kill on distinct requests)

Semantic model:
    REAL / AUTONOMOUS (executes ScenarioProgram independently)

Lowered model:
    REAL / AUTONOMOUS (executes ScenarioProgram independently)

Differential counterexamples:
    NONE IN TESTED REGIME (strictly independent: no oracle descriptors,
    no driver state injections, exact T-values)

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
    REAL / EXERCISED (14/14 adversarial)

Executable semantic model
    REAL / AUTONOMOUS (12/12 differential, declarative programs)

Differential semantic preservation
    VERIFIED IN TESTED REGIME (audited across 2 review rounds, R1–R11 fixed)

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
    UNBLOCKED per campaign plan — Campaign 2 differential preservation
    verified under independent, non-oracle execution.
```
