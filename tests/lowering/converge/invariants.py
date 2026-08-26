"""invariants.py — global invariants I1–I10 checked at every transition.

Each invariant has a `kill_*` counterpart used by test_invariant_kills.py:
a deliberately invalid state that the checker MUST flag.
"""
from __future__ import annotations

from model import NodeStatus, TERMINAL, ConvergeTransactionDomain, HarnessBookkeeping


class InvariantViolation(Exception):
    pass


def check_all(d: ConvergeTransactionDomain, bk: HarnessBookkeeping | None = None) -> list[str]:
    """Run every invariant; return list of violation names (empty == clean)."""
    bad = []
    if not i1_unique_unsettled(d):
        bad.append("I1")
    if not i2_terminal_no_inflight(d):
        bad.append("I2")
    if not i3_terminal_zero_obligations(d, bk):
        bad.append("I3")
    if not i6_apply_at_most_once(d):
        bad.append("I6")
    if not i7_settlement_exactly_once(d):
        bad.append("I7")
    if not i8_closing_frontier_frozen(d):
        bad.append("I8")
    if not i9_visited_requires_dispatch(d):
        bad.append("I9")
    if not i10_scope_cannot_mint(d):
        bad.append("I10")
    return bad


def assert_clean(d: ConvergeTransactionDomain, bk: HarnessBookkeeping | None = None) -> None:
    bad = check_all(d, bk)
    if bad:
        raise InvariantViolation(f"invariants violated: {', '.join(bad)}")


# I1. current_in_flight != None ==> at most one unsettled semantic request
#     for the ENTIRE ConvergeFrame (R7: any request, not just the current one)
def i1_unique_unsettled(d: ConvergeTransactionDomain) -> bool:
    unsettled = [s for s in d.handles.values() if s.settlement is None]
    return len(unsettled) <= 1


# I2. Terminal frame ==> no current in-flight handle
def i2_terminal_no_inflight(d: ConvergeTransactionDomain) -> bool:
    if d.frame_status not in TERMINAL:
        return True
    return d.current_in_flight is None and not any(
        s.settlement is None and s.state != "Aborted" for s in d.handles.values())


# I3. ConvergeFrame terminal ==> scope_committed == 0 AND no outstanding
#     IntentFrame reservation attributable to THIS ConvergeFrame (test metadata)
def i3_terminal_zero_obligations(d: ConvergeTransactionDomain,
                                 bk: HarnessBookkeeping | None = None) -> bool:
    if d.frame_status not in TERMINAL:
        return True
    if any(v > 0 for v in d.scope_committed.values()):
        return False
    if bk is not None:
        if any(amt > 0 for amt in bk.reservations_created_by_cf.values()):
            return False
    return True


# I4. StageLocal.Rejected ==> zero deltas. Enforced structurally in
#     transitions.stage_local (rejection raises before any mutation).
def i4_stage_reject_zero_delta(before: dict, after: dict) -> bool:
    for key in ("scope_committed", "intent_reserved"):
        b, a = before.get(key, {}), after.get(key, {})
        for r in set(b) | set(a):
            if b.get(r, 0) != a.get(r, 0):
                return False
    return True


# I5. Transport.Retry ==> same request_id. Structural: retries are keyed by
#     request_id; a different id is a new semantic attempt by construction.


# I6. Handle.Applied(c) ==> semantic_outcome applied <= 1 per CompletionId (R28)
def i6_apply_at_most_once(d: ConvergeTransactionDomain) -> bool:
    return len(d.applied_completions) == len(set(d.applied_completions))


# I7. SettlementRecord(h) ==> ledger reconciliation count == 1
def i7_settlement_exactly_once(d: ConvergeTransactionDomain) -> bool:
    seen_receipts = []
    for st in d.handles.values():
        if st.settlement is not None:
            seen_receipts.append(st.settlement.receipt_id)
            # scope_spent must equal sum of settled amounts
    total_by_resource: dict[str, int] = {}
    for st in d.handles.values():
        if st.settlement:
            r = st.settlement.resource
            total_by_resource[r] = total_by_resource.get(r, 0) + st.settlement.amount
    for r, total in total_by_resource.items():
        if d.scope_spent.get(r, 0) != total:
            return False
    return len(seen_receipts) == len(set(seen_receipts))


# I8. Closing ==> frontier mutations == 0 (frontier frozen during closing)
def i8_closing_frontier_frozen(d: ConvergeTransactionDomain) -> bool:
    return d.frontier_mutations_during_closing == 0


# I9. VisitedRecord(n, op, k) ==> that expansion crossed DISPATCH_LOCAL or
#     first logical EMIT_EXTERNAL, strictly bound to DispatchRecord(n, op, k) (R29)
def i9_visited_requires_dispatch(d: ConvergeTransactionDomain) -> bool:
    dispatched = {(dp.node_id, dp.op_id, dp.visit_no) for dp in d.dispatches}
    return all((v.node_id, v.op_id, v.visit_no) in dispatched for v in d.visited)


# I10. BudgetScope cannot grant or mint ownership; IntentFrame conserves resources
def i10_scope_cannot_mint(d: ConvergeTransactionDomain) -> bool:
    for r in set(d.scope_limit) | set(d.scope_committed) | set(d.scope_spent):
        committed = d.scope_committed.get(r, 0)
        spent = d.scope_spent.get(r, 0)
        limit = d.scope_limit.get(r, 0)
        if committed < 0 or spent < 0:
            return False
        if committed + spent > limit:
            return False
    # IntentFrame conservation check:
    for r in set(d.intent_initial_total) | set(d.intent_available) | set(d.intent_reserved) | set(d.intent_spent):
        avail = d.intent_available.get(r, 0)
        res = d.intent_reserved.get(r, 0)
        sp = d.intent_spent.get(r, 0)
        if avail < 0 or res < 0 or sp < 0:
            return False
        if r in d.intent_initial_total:
            if avail + res + sp != d.intent_initial_total[r]:
                return False
    return True
