"""test_invariant_kills.py — mutation checks: the detector must detect.

For each kill, we fabricate a deliberately invalid state and require the
invariant checker to flag it. A green suite with a broken checker proves
nothing (see soma_mini episode, 2026-08-26).

Run: python -m pytest tests/lowering/converge/test_invariant_kills.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from model import (ConvergeTransactionDomain, DispatchRecord, InFlightLifecycleState,
                   SearchStatus, VisitedRecord)

PASS, FAIL = 0, 0


def kill(name: str, checker, domain: ConvergeTransactionDomain) -> None:
    """checker semantics: True == state is VALID. A kill state must yield False."""
    global PASS, FAIL
    valid = checker(domain)
    if not valid:
        print(f"  \u2713 {name}: checker flagged invalid state")
        PASS += 1
    else:
        print(f"  \u2717 {name}: checker ACCEPTED an invalid state -- detector is broken!")
        FAIL += 1


def survives(name: str, checker, domain: ConvergeTransactionDomain) -> None:
    """The checker must also accept valid states — no false positives."""
    global PASS, FAIL
    if not checker(domain):
        print(f"  \u2717 {name}: checker flagged a VALID state (false positive)")
        FAIL += 1
    else:
        print(f"  \u2713 {name}: valid state accepted")
        PASS += 1


def base_domain() -> ConvergeTransactionDomain:
    d = ConvergeTransactionDomain()
    d.scope_limit["usd"] = 100
    d.intent_initial_total["usd"] = 100
    d.intent_available["usd"] = 100
    return d


# ---------------------------------------------------------------------
print("=" * 70)
print("INVARIANT KILL TESTS — detector must flag every fabricated violation")

# I1 kill: TWO unsettled handles on DIFFERENT requests (R7 strengthened kill)
d = base_domain()
h1 = InFlightLifecycleState(handle_id="h1", request_id="r1")
h2 = InFlightLifecycleState(handle_id="h2", request_id="r2")   # different request!
d.handles = {"h1": h1, "h2": h2}
d.current_in_flight = h1
kill("I1 kill (two unsettled requests r1+r2)", lambda x: __import__("invariants").i1_unique_unsettled(x), d)

d2 = base_domain()
h1b = InFlightLifecycleState(handle_id="h1", request_id="r1")
d2.handles = {"h1": h1b}
d2.current_in_flight = h1b
survives("I1 clean state accepted", lambda x: __import__("invariants").i1_unique_unsettled(x), d2)

# I3 kill A: terminal frame with outstanding scope commitments
d3a = base_domain()
d3a.frame_status = SearchStatus.SATISFIED
d3a.scope_committed["usd"] = 5
kill("I3 kill A (terminal with committed scope)", lambda x: __import__("invariants").i3_terminal_zero_obligations(x), d3a)

# I3 kill B (R12): terminal frame with scope=0 but attributable owner reservation still active
from model import HarnessBookkeeping
d3b = base_domain()
d3b.frame_status = SearchStatus.SATISFIED
d3b.scope_committed["usd"] = 0
bk_with_cf_res = HarnessBookkeeping(reservations_created_by_cf={"req-1": 5})
kill("I3 kill B (terminal with active attributable reservation)",
     lambda x: __import__("invariants").i3_terminal_zero_obligations(x, bk_with_cf_res), d3b)

# I3 control probe (R12): terminal frame with reservation belonging to ANOTHER CF/operation
d3c = base_domain()
d3c.frame_status = SearchStatus.SATISFIED
d3c.scope_committed["usd"] = 0
d3c.intent_reserved["usd"] = 50   # belongs to another operation in the IntentFrame!
bk_empty = HarnessBookkeeping(reservations_created_by_cf={})
survives("I3 control probe (reservation of OTHER operation accepted)",
         lambda x: __import__("invariants").i3_terminal_zero_obligations(x, bk_empty), d3c)

# I6 kill A (R28): same CompletionId applied twice
d4 = base_domain()
d4.applied_completions = ["ha:rcpt-1", "ha:rcpt-1"]
kill("I6 kill A (same CompletionId applied twice)", lambda x: __import__("invariants").i6_apply_at_most_once(x), d4)

# I6 kill B (R39/R44): ghost application record with no Applied handle
d4c = base_domain()
d4c.applied_completions = ["ha:rcpt-ghost"]
d4c.handles = {}
kill("I6 kill B (ghost application record with no Applied handle)", lambda x: __import__("invariants").i6_apply_at_most_once(x), d4c)

# I6 kill C (R35): applied handle missing application record (forward completeness gap)
d4d = base_domain()
st_app = InFlightLifecycleState("ha", "ra", applied=True, state="Applied")
d4d.handles["ha"] = st_app
d4d.applied_completions = []
kill("I6 kill C (applied handle missing application record)", lambda x: __import__("invariants").i6_apply_at_most_once(x), d4d)

# I6 control probe (R28/R39): two different completions with identical digests
d4b = base_domain()
st_a = InFlightLifecycleState("ha", "ra", applied=True, state="Applied")
st_b = InFlightLifecycleState("hb", "rb", applied=True, state="Applied")
st_a.completion = __import__("model").CompletionRecord("ha", "rcpt-1", "same-digest", "Success")
st_b.completion = __import__("model").CompletionRecord("hb", "rcpt-2", "same-digest", "Success")
d4b.handles = {"ha": st_a, "hb": st_b}
d4b.applied_completions = ["ha:rcpt-1", "hb:rcpt-2"]
survives("I6 control probe (distinct completions with identical digest accepted)",
         lambda x: __import__("invariants").i6_apply_at_most_once(x), d4b)

# I7 kill A: scope_spent disagrees with sum of settlement records
d5 = base_domain()
hs = InFlightLifecycleState(handle_id="hs", request_id="rs")
hs.settlement = __import__("model").SettlementRecord("hs", "rcpt", "usd", 10)
d5.handles = {"hs": hs}
d5.settlement_reconciliations = {"hs": 1}
d5.scope_spent["usd"] = 99   # ledger says 99, records say 10
kill("I7 kill A (ledger != settled amounts)", lambda x: __import__("invariants").i7_settlement_exactly_once(x), d5)

# I7 kill B (R40/R44): reconciliation count > 1 on same handle
d5a = base_domain()
hs_a = InFlightLifecycleState(handle_id="hs_a", request_id="rs_a")
hs_a.settlement = __import__("model").SettlementRecord("hs_a", "rcpt", "usd", 10)
d5a.handles = {"hs_a": hs_a}
d5a.scope_spent["usd"] = 10
d5a.settlement_reconciliations = {"hs_a": 2}
kill("I7 kill B (duplicate reconciliation count on same handle)", lambda x: __import__("invariants").i7_settlement_exactly_once(x), d5a)

# I7 kill C (R40/R44): ghost reconciliation record without matching settled handle
d5c = base_domain()
d5c.settlement_reconciliations = {"ghost_h": 1}
d5c.handles = {}
kill("I7 kill C (ghost reconciliation record without settled handle)", lambda x: __import__("invariants").i7_settlement_exactly_once(x), d5c)

# I7 kill D (R54): ghost scope_spent with zero settlements
d5d = base_domain()
d5d.scope_spent["usd"] = 10
d5d.handles = {}
d5d.settlement_reconciliations = {}
kill("I7 kill D (ghost scope_spent with zero settlements)", lambda x: __import__("invariants").i7_settlement_exactly_once(x), d5d)

# I7 control probe (R36/R40): two distinct handles with the same receipt_id
d5b = base_domain()
hs1 = InFlightLifecycleState(handle_id="hs1", request_id="rs1")
hs2 = InFlightLifecycleState(handle_id="hs2", request_id="rs2")
hs1.settlement = __import__("model").SettlementRecord("hs1", "same-rcpt", "usd", 10)
hs2.settlement = __import__("model").SettlementRecord("hs2", "same-rcpt", "usd", 10)
d5b.handles = {"hs1": hs1, "hs2": hs2}
d5b.settlement_reconciliations = {"hs1": 1, "hs2": 1}
d5b.scope_spent["usd"] = 20
survives("I7 control probe (different handles with same receipt_id accepted)",
         lambda x: __import__("invariants").i7_settlement_exactly_once(x), d5b)

# R50/R56: Exact canonical digest property tests (order, op_id, and collision freedom)
from transitions import canonical_digest
from model import SpaceOutcome, SatisfierOutcome, ExecutionReceipt
digest_order1 = canonical_digest("rcpt", "Success", SpaceOutcome(successors=["B", "C"]))
digest_order2 = canonical_digest("rcpt", "Success", SpaceOutcome(successors=["C", "B"]))
assert digest_order1 != digest_order2, "R50: successor order must change canonical digest"

digest_op1 = canonical_digest("rcpt", "Success", SatisfierOutcome(node_id="n", op_id="opVerifyA", satisfied=True, value="val"))
digest_op2 = canonical_digest("rcpt", "Success", SatisfierOutcome(node_id="n", op_id="opVerifyB", satisfied=True, value="val"))
assert digest_op1 != digest_op2, "R50: op_id must change canonical digest"

digest_colon1 = canonical_digest("rcpt", "Success", SatisfierOutcome(node_id="a:b", op_id="c", satisfied=True, value="val"))
digest_colon2 = canonical_digest("rcpt", "Success", SatisfierOutcome(node_id="a", op_id="b:c", satisfied=True, value="val"))
assert digest_colon1 != digest_colon2, "R56: colon structure must not collide in canonical digest"

digest_none1 = canonical_digest("rcpt", "Success", SatisfierOutcome(node_id="a", op_id="b", satisfied=True, value=None))
digest_none2 = canonical_digest("rcpt", "Success", SatisfierOutcome(node_id="a", op_id="b", satisfied=True, value="None"))
assert digest_none1 != digest_none2, "R56: None vs 'None' string must not collide in canonical digest"
print("  ✓ R50/R56 exact canonical digest verified: order, op_id, and typed structure are strictly bound")

# R57/R62: Durable ExecutionReceipt authority and mandatory validation tests
d_settle = base_domain()
h_st = InFlightLifecycleState(handle_id="h_settle", request_id="r_settle", state="Delivered", reserved_amount=10)
h_st.completion = __import__("model").CompletionRecord(
    handle_id="h_settle", receipt_id="rcpt", digest="d", outcome="Success",
    receipt=ExecutionReceipt("r_settle", "rcpt", "usd", 7),
)
d_settle.handles["h_settle"] = h_st
try:
    __import__("transitions").settle(d_settle, "h_settle")
except Exception as e:
    raise AssertionError(f"valid settlement failed: {e}")
assert d_settle.scope_spent["usd"] == 7, "durable receipt amount was not settled"

# Negative R62: missing receipt MUST FAIL
d_no_rcpt = base_domain()
h_inflight = InFlightLifecycleState(handle_id="h_inf", request_id="r_inf", state="InFlight", reserved_amount=10)
d_no_rcpt.handles["h_inf"] = h_inflight
try:
    __import__("transitions").admit_completion(d_no_rcpt, "h_inf", "rcpt-1", receipt=None)
    raise AssertionError("missing receipt was accepted on admit_completion")
except __import__("transitions").TransitionError as e:
    assert "MissingExecutionReceipt" in str(e), f"wrong refusal: {e}"

# Negative R62: wrong request_id MUST FAIL
try:
    bad_rcpt = ExecutionReceipt("r_wrong", "rcpt-1", "usd", 10)
    __import__("transitions").admit_completion(d_no_rcpt, "h_inf", "rcpt-1", receipt=bad_rcpt)
    raise AssertionError("receipt with mismatched request_id was accepted")
except __import__("transitions").TransitionError as e:
    assert "ReceiptRequestIdMismatch" in str(e), f"wrong refusal: {e}"

# Negative R62: wrong receipt_id MUST FAIL
try:
    bad_rcpt_id = ExecutionReceipt("r_inf", "rcpt_mismatch", "usd", 10)
    __import__("transitions").admit_completion(d_no_rcpt, "h_inf", "rcpt-1", receipt=bad_rcpt_id)
    raise AssertionError("receipt with mismatched receipt_id was accepted")
except __import__("transitions").TransitionError as e:
    assert "ReceiptIdMismatch" in str(e), f"wrong refusal: {e}"

print("  ✓ R57/R62 settlement & receipt authority verified: receipt is mandatory and strictly bound to request_id/receipt_id")

# I8 kill (R30): attempt actual machine frontier mutation while Closing
d8 = base_domain()
d8.frame_status = SearchStatus.CLOSING
try:
    __import__("transitions").discover_successors(d8, ["ghost_node"])
except __import__("transitions").TransitionError:
    pass
kill("I8 kill (frontier mutation attempted during closing)", lambda x: __import__("invariants").i8_closing_frontier_frozen(x), d8)
survives("I8 clean closing state accepted", lambda x: __import__("invariants").i8_closing_frontier_frozen(x), base_domain())

# I9 kill (R29): forged visit record without corresponding dispatch record
d6 = base_domain()
d6.dispatches = [DispatchRecord("n1", "op-real", 1, "Local")]
d6.visited.append(VisitedRecord(visit_key="op-ghost:n1", node_id="n1", op_id="op-ghost", visit_no=1))
kill("I9 kill (forged visit without matching dispatch)", lambda x: __import__("invariants").i9_visited_requires_dispatch(x), d6)

d6_probe = base_domain()
d6_probe.dispatches = [DispatchRecord("n1", "op-real", 1, "Local")]
d6_probe.visited.append(VisitedRecord(visit_key="op-real:n1", node_id="n1", op_id="op-real", visit_no=1))
survives("I9 clean history accepted", lambda x: __import__("invariants").i9_visited_requires_dispatch(x), d6_probe)

# I10 kill A: scope committed beyond its limit (minted ownership)
d7a = base_domain()
d7a.scope_committed["usd"] = 500   # limit was 100
kill("I10 kill A (scope minted beyond limit)", lambda x: __import__("invariants").i10_scope_cannot_mint(x), d7a)

# I10 kill B (R18): IntentFrame broken conservation (total > initial)
d7b = base_domain()
d7b.intent_available["usd"] = 50
d7b.intent_spent["usd"] = 60       # 50 + 60 = 110 != 100!
kill("I10 kill B (IntentFrame conservation broken)", lambda x: __import__("invariants").i10_scope_cannot_mint(x), d7b)

# I10 control probe (R18): valid state where spent > current available (60 > 40)
d7c = base_domain()
d7c.intent_available["usd"] = 40
d7c.intent_spent["usd"] = 60
d7c.scope_spent["usd"] = 60
survives("I10 control probe (spent > available accepted when conserved)",
         lambda x: __import__("invariants").i10_scope_cannot_mint(x), d7c)

print("=" * 70)
print(f"RESULT: {PASS} passed, {FAIL} failed")
if FAIL:
    print("THE DETECTOR IS BROKEN. Fix invariants.py before trusting any green run.")
    sys.exit(1)
print("Detector validated: every fabricated violation flagged, no false positives.")
