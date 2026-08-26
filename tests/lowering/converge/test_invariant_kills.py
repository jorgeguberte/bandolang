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
    d.intent_available["usd"] = 100
    return d


# ---------------------------------------------------------------------
print("=" * 70)
print("INVARIANT KILL TESTS — detector must flag every fabricated violation")

# I1 kill: two unsettled handles for the current in-flight request
d = base_domain()
h1 = InFlightLifecycleState(handle_id="h1", request_id="r1")
h2 = InFlightLifecycleState(handle_id="h2", request_id="r1")
d.handles = {"h1": h1, "h2": h2}
d.current_in_flight = h1
kill("I1 kill (two unsettled current handles)", lambda x: __import__("invariants").i1_unique_unsettled(x), d)

d2 = base_domain()
h1b = InFlightLifecycleState(handle_id="h1", request_id="r1")
d2.handles = {"h1": h1b}
d2.current_in_flight = h1b
survives("I1 clean state accepted", lambda x: __import__("invariants").i1_unique_unsettled(x), d2)

# I3 kill: terminal frame with outstanding scope commitments
d3 = base_domain()
d3.frame_status = SearchStatus.SATISFIED
d3.scope_committed["usd"] = 5
kill("I3 kill (terminal with committed scope)", lambda x: __import__("invariants").i3_terminal_zero_obligations(x), d3)

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

# I9 kill: visited record for an op that never crossed emission
d6 = base_domain()
d6.visited.append(VisitedRecord(visit_key="k", node_id="n1", op_id="ghost-op", visit_no=1))
kill("I9 kill (visited without dispatch)", lambda x: __import__("invariants").i9_visited_requires_dispatch(x), d6)
survives("I9 clean history accepted", lambda x: __import__("invariants").i9_visited_requires_dispatch(x), base_domain())

# I10 kill: scope committed beyond its limit (minted ownership)
d7 = base_domain()
d7.scope_committed["usd"] = 500   # limit was 100
kill("I10 kill (scope minted beyond limit)", lambda x: __import__("invariants").i10_scope_cannot_mint(x), d7)

print("=" * 70)
print(f"RESULT: {PASS} passed, {FAIL} failed")
if FAIL:
    print("THE DETECTOR IS BROKEN. Fix invariants.py before trusting any green run.")
    sys.exit(1)
print("Detector validated: every fabricated violation flagged, no false positives.")
