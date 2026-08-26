# Campaign 2 — Execution Report (Differential Semantics) — REISSUE 9

> **REISSUE 9 after ninth adversarial audit round (R44–R49).**
> The ninth audit verified exact alignment between declared detector semantics and actual test harness implementations:
> 1. R44: Real I6 two-way bijection and I7 independent `settlement_reconciliations` tracking fully implemented and verified with mutation kills.
> 2. R45: Typed apply operations (`apply_space_completion`, `apply_satisfier_completion`) autonomously consume durable payloads without caller-supplied authority.
> 3. R46: Deterministic canonical digest binding (`canonical_digest`) validating outcome and semantic payload.
> 4. R47: `DeliveryUnknown` prevents premature successor incorporation (D22 verified).
> 5. R48: Strict `PartialOf` eligibility across all declarative scenarios without implicit fallback.
> 6. R49: Real satisfaction attempt limit test (D21 verified with multi-candidate blocking).
> All 62 test cases pass across all 4 test suites without divergence or false positives.

## Audit repairs applied (Round 9: R44–R49)

```text
R44 Real I6 Bijection & I7 Reconciliation Count Implementation
    FIXED — `invariants.py` checks both directions of I6:
        (1) uniqueness of application records
        (2) every Applied handle has a corresponding record
        (3) every application record corresponds to an actual Applied handle
    Added I6 kill B (ghost application record with no Applied handle => FAIL).
    I7 consumes `d.settlement_reconciliations[handle_id]` directly and enforces count == 1 per handle.
    Added I7 kill B (duplicate reconciliation count => FAIL) and kill C (ghost reconciliation record => FAIL).

R45 Typed Apply Consumes Durable Payload
    FIXED — `apply_space_completion(d, handle_id)` and `apply_satisfier_completion(d, handle_id)`
    read directly from `st.completion.semantic_payload`. Removed caller-supplied successor/satisfaction parameters.

R46 Canonical Completion Digest Binding
    FIXED — `canonical_digest(receipt_id, outcome, semantic_payload)` cryptographically/deterministically
    binds the receipt, outcome, and payload. `admit_completion()` validates that supplied digest matches.

R47 DeliveryUnknown Successor Discovery Guard (D22)
    FIXED — `SemanticFrame.expand()` avoids discovering/adding successors to the frontier when `delivery_unknown`
    is True. Added D22 verifying that successor B is absent from frontier/nodes during Waiting.

R48 Strict PartialOf Eligibility
    FIXED — Removed truthiness fallback (`if cand not in prog.partial_map: continue`).
    Annotated all declarative scenarios D01–D22 with explicit `partial_map`.

R49 Multi-Candidate Satisfaction Attempt Limit Verification (D21)
    FIXED — D21 pressure-tests `max_satisfaction_attempts=1` across two partial candidates (P1 and P2).
    Verified that P1 attempt is counted and P2 check is blocked -> natural Exhaustion.
    Enforced `max_satisfaction_attempts` on post-fuel partial checks as well.
```

## Complete verification results

```text
Campaign 1 (Lowered Safety & Crash Recovery):
    20/20 PASS (T01–T11, T04A/B, T07B real recovery, T12 sequential stage guard,
                T13 pending exhaust drain, T14 settlement ceiling bounds,
                T15 autonomous space apply recovery, T16 autonomous satisfier apply recovery,
                T17 request_id reuse rejection, T18 generic apply bypass refused)

Invariant Kill Tests (Mutation Testing & Bijection):
    20/20 PASS (I1 frame-wide, I3 scope kill, I3 attributable kill, I3 control probe,
                I6 CompletionId uniqueness kill, I6 ghost record kill, I6 completeness gap kill,
                I6 identical digest probe, I7 ledger vs records kill, I7 duplicate reconciliation kill,
                I7 ghost reconciliation kill, I7 identical receipt probe, I8 closing mutation kill,
                I8 clean closing probe, I9 forged visit kill, I9 clean history probe,
                I10 scope limit kill, I10 IntentFrame conservation kill,
                I10 spent>avail control probe)

Campaign 2 Basic (Declarative Search Programs):
    16/16 PASS (D01 exhaust [R19 verified], D02 successor [R19/R10 verified],
                D03 max_steps + partial [R4 verified], D04 Ok(None), D05 Err+abort,
                D06 external, D13 ceiling vs actual charge [R12/R14 verified],
                D14 budget headroom depletion [R15/R34 verified],
                D15 unaffordable ceiling refused [R20/R25/R34 verified],
                D16 effectful satisfier with explicit PartialOf [R24/R33/R48 verified],
                D17 effectful satisfier commit point under DeliveryUnknown [R26/R31 verified],
                D18 sequential Waiting blocks local dispatch [R31 verified],
                D19 autonomous crash recovery preserves space successors [R32/R45 verified],
                D20 targeted DeliveryUnknown preserves prior spend [R41 verified],
                D21 multi-candidate satisfaction attempt limit exhaustion [R42/R49 verified],
                D22 DeliveryUnknown prevents premature successor discovery [R47 verified])

Campaign 2 Fault (Environmental Fault Injections):
    6/6 PASS   (D07 DeliveryUnknown [Waiting verified], D08 safe retry,
                D09 duplicate completion, D10 crash-after-settlement forward recovery,
                D11 cancel-in-flight [R2 Cancelled verified],
                D12 late settlement fatal closing)

Semantic model:
    REAL / AUTONOMOUS (purely declarative search space execution)

Lowered model:
    REAL / ADVERSARIALLY HARDENED (canonical bound completion digests, two-way bijection invariants,
    independent reconciliation tracking, request_id reuse protection, autonomous recovery)

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
    REAL / ADVERSARIALLY HARDENED (20/20 adversarial scenarios)

Executable semantic model
    REAL / AUTONOMOUS (22/22 differential programs)

Invariant checker
    SELF-TESTED (20/20 mutation kill tests & control probes)

Differential semantic preservation
    VERIFIED IN TESTED REGIME (audited across 9 adversarial review rounds, R1–R49 fixed)

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
    budget conservation, durable autonomous recovery, invariant two-way bijection,
    and differential preservation have survived 9 adversarial audit rounds.
```
