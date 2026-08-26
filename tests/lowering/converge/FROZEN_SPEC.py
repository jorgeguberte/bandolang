# FROZEN SPEC REFERENCE
#
# This harness models the SOMA-IR Item 2 Phase D lowering (soma.converge),
# frozen as Candidate v2.3 on 2026-08-26.
#
# Normative sources (immutable during campaign):
#   - wiki: architecture/soma-ir-v0.md            (commit 4a66862, 2026-08-26)
#   - wiki: architecture/soma-phase-d-falsification-campaign.md
#   - docs site: jorgeguberte/bando commit 943754b
#
# CAMPAIGN CONTRACT:
#   - Spec SHA is immutable during the campaign.
#   - Any harness failure must be classified first:
#       HARNESS_BUG | LOWERING_COUNTEREXAMPLE | CONVERGEFRAME_COUNTEREXAMPLE
#     Only after classification may the spec change.
#   - Harness instrumentation observes; it never decides machine behavior.
#   - NON-NORMATIVE in this model: best_partial (opaque, unexercised);
#     reservation attribution (harness-only bookkeeping).

SPEC_FREEZE = {
    "name": "SOMA-IR Phase D — soma.converge lowering",
    "candidate": "v2.3",
    "frozen_at": "2026-08-26",
    "evidence_level": ["DESIGN-LEVEL", "ADVERSARIALLY REVIEWED",
                       "NOT EXECUTABLE-VERIFIED", "NOT SOUNDNESS-PROVED"],
    "campaign": 1,
    "scenarios_expected": 13,
    "invariants_expected": "I1-I10 (+ kill tests)",
}
