# bando-lang

Validation and falsification harnesses for the Bando Lang (dev codename: SOMA) specification.

This repository intentionally contains **only validation code**. Normative
specification lives in the docs site (`jorgeguberte/bando`) and in the research
wiki. Per the Phase D falsification campaign plan, nothing here may decide the
behavior of the modeled machine: harness instrumentation exists to observe, never to govern.

## Layout

```text
tests/lowering/converge/   Campaign 1 — soma.converge lowering state-machine harness
```

## Method contract

- Spec SHA is immutable during a campaign.
- Any failure is classified first: `HARNESS_BUG`, `LOWERING_COUNTEREXAMPLE`,
  or `CONVERGEFRAME_COUNTEREXAMPLE`. Only then may spec change.
- Every invariant carries kill tests: the checker must prove it detects.
