# Campaign 1 — Execution Report (lowered machine safety)

> Evidência histórica. Este report NÃO modifica a semântica nem o freeze da Phase D.
> Spec normativa permanece em `my-wiki@4a66862` / `bando@943754b`.

## Registration

```text
spec freeze:
    my-wiki@4a66862          (architecture/soma-ir-v0.md, Candidate v2.3, 2026-08-26)

published freeze:
    bando@943754b            (content/docs/ir/semantic-ops-phase-d.mdx)

campaign implementation:
    bandolang@8eff3e5        (tests/lowering/converge/)
```

## Result

```text
scenarios:
    13/13 PASS   (T01–T11; T04 split A/B; T07B equivocation-crash;
                  T11 late-settlement-after-fatal-closing)

invariant kill tests:
    8/8 PASS     (I1, I3, I6, I7, I9, I10 kills + false-positive probes)

lowering counterexamples:
    NONE IN TESTED REGIME

ConvergeFrame counterexamples:
    NONE IN TESTED REGIME
```

## Harness/test defects found during construction

```text
YES — evidence FOR the methodology, not noise to hide:

1. inverted checker expectation in kill() itself
   (checker returns True=valid; test initially read it as "violation found")

2. incorrect durable snapshot point in T08
   (snapshot taken BEFORE settlement made forward-recovery vacuous)

3. checker defects caught by kill tests:
   - I1 used ==1 where settled handles legitimately leave 0 unsettled
   - I9 had a vacuous disjunct (`visit_no >= 1`) that let ghost visits pass

The mutation checks flagged every one of these before any green run was trusted.
A green suite with a broken detector proves nothing (cf. soma_mini episode).
```

## Modeling decisions (NON-NORMATIVE, harness-local)

```text
transport retry re-uses the in-flight handle (no second handle minted)
terminal frames clear current_in_flight (I2 enforcement point)
best_partial: opaque, unexercised
reservation attribution: harness bookkeeping only, never consulted by transitions
```

## Evidence level statement

```text
Phase D
    RESOLVED FOR CURRENT PHASE

Design
    DESIGN-LEVEL
    ADVERSARIALLY REVIEWED

Executable lowered state-machine model
    REAL
    EXERCISED
    13/13 ADVERSARIAL SCENARIOS PASS

Invariant checker
    SELF-TESTED
    8/8 KILL TESTS PASS

Differential semantic preservation
    NOT YET TESTED

Actual compiler/lowering implementation
    NOT YET VERIFIED

Formal soundness
    NOT PROVED
```
