"""harness.py — transition executor with fault injection and recovery.

The executor checks invariants after every transition. Instrumentation here
observes; it never decides machine behavior (campaign principle).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from invariants import InvariantViolation, assert_clean
from model import ConvergeTransactionDomain, HarnessBookkeeping


@dataclass
class CrashInjected(Exception):
    crash_point: str


@dataclass
class RunResult:
    steps: list[str] = field(default_factory=list)
    invariant_checks: int = 0
    crashes_injected: list[str] = field(default_factory=list)


class Harness:
    def __init__(self, domain: ConvergeTransactionDomain,
                 bookkeeping: HarnessBookkeeping | None = None):
        self.d = domain
        self.bk = bookkeeping or HarnessBookkeeping()
        self.result = RunResult()

    # ---- core loop -------------------------------------------------

    def step(self, name: str, fn, *args, **kwargs):
        """Run one transition, then verify all invariants."""
        out = fn(self.d, *args, **kwargs)

        # R12/R17: Transactional Harness-only bookkeeping for I3 attribution:
        # Commit attribution ONLY AFTER transition succeeds:
        if getattr(fn, "__name__", "") == "stage_local" and len(args) >= 5:
            req_id = args[2]  # (node_id, op_id, request_id, resource, amount)
            amt = args[4]
            if amt > 0:
                self.bk.reservations_created_by_cf[req_id] = amt
        elif getattr(fn, "__name__", "") == "settle" and len(args) >= 1:
            handle_id = args[0]
            st = self.d.handles.get(handle_id)
            if st:
                self.bk.reservations_created_by_cf.pop(st.request_id, None)
        elif getattr(fn, "__name__", "") == "cancel":
            for hid, st in self.d.handles.items():
                if st.state == "Aborted":
                    self.bk.reservations_created_by_cf.pop(st.request_id, None)
        elif getattr(fn, "__name__", "") == "confirmed_not_delivered" and len(args) >= 1:
            handle_id = args[0]
            st = self.d.handles.get(handle_id)
            if st:
                self.bk.reservations_created_by_cf.pop(st.request_id, None)

        self.result.steps.append(name)
        self.result.invariant_checks += 1
        assert_clean(self.d, self.bk)
        return out

    def snapshot(self) -> ConvergeTransactionDomain:
        return self.d.copy()

    def inject_crash(self, crash_point: str) -> None:
        """Simulate a process crash at a named point: local RAM state is lost;
        durable state = last snapshot."""
        self.result.crashes_injected.append(crash_point)
        raise CrashInjected(crash_point)

    def report(self) -> str:
        r = self.result
        return (f"steps={len(r.steps)} invariant_checks={r.invariant_checks} "
                f"crashes={len(r.crashes_injected)}")
