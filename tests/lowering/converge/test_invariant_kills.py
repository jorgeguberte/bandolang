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

from model import (ConvergeTransactionDomain, InFlightLifecycleState,
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

# I6 kill: same completion digest applied twice via two handles
d4 = base_domain()
ha = InFlightLifecycleState(handle_id="ha", request_id="ra", applied=True, state="Applied")
hb = InFlightLifecycleState(handle_id="hb", request_id="rb", applied=True, state="Applied")
comp_a = __import__("model").CompletionRecord("ha", "receipt-1", "same-digest", "Success")
comp_b = __import__("model").CompletionRecord("hb", "receipt-2", "same-digest", "Success")
ha.completion, hb.completion = comp_a, comp_b
d4.handles = {"ha": ha, "hb": hb}
kill("I6 kill (same completion applied twice)", lambda x: __import__("invariants").i6_apply_at_most_once(x), d4)

# I7 kill: scope_spent disagrees with sum of settlement records
d5 = base_domain()
hs = InFlightLifecycleState(handle_id="hs", request_id="rs")
hs.settlement = __import__("model").SettlementRecord("hs", "rcpt", "usd", 10)
d5.handles = {"hs": hs}
d5.scope_spent["usd"] = 99   # ledger says 99, records say 10
kill("I7 kill (ledger != settled amounts)", lambda x: __import__("invariants").i7_settlement_exactly_once(x), d5)

# I8 kill (R18): frontier mutation during closing state
d8 = base_domain()
d8.frame_status = SearchStatus.CLOSING
d8.frontier_mutations_during_closing = 1
kill("I8 kill (frontier mutation during closing)", lambda x: __import__("invariants").i8_closing_frontier_frozen(x), d8)
survives("I8 clean closing state accepted", lambda x: __import__("invariants").i8_closing_frontier_frozen(x), base_domain())

# I9 kill: visited record for an op that never crossed emission
d6 = base_domain()
d6.visited.append(VisitedRecord(visit_key="k", node_id="n1", op_id="ghost-op", visit_no=1))
kill("I9 kill (visited without dispatch)", lambda x: __import__("invariants").i9_visited_requires_dispatch(x), d6)
survives("I9 clean history accepted", lambda x: __import__("invariants").i9_visited_requires_dispatch(x), base_domain())

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
