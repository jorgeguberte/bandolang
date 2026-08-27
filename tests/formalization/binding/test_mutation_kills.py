"""test_mutation_kills.py — SOMA Binding Contract v0 Mutation Kill Suite.

Exercises mutants M1–M10 against the formal invariant suite and verifies that
every unsound semantic shortcut is caught and killed.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Add package directory to path
sys.path.insert(0, str(Path(__file__).parent))

from mutations import get_all_mutants


def main():
    print("=" * 70)
    print("SOMA BINDING CONTRACT v0 — Mutation Kill Verification Suite (M1–M10)")
    print("=" * 70)

    mutants = get_all_mutants()
    killed = 0
    total = len(mutants)

    for m in mutants:
        try:
            m.run_killer()
            # If no assertion failed, mutant escaped!
            raise RuntimeError(f"MUTANT ESCAPED: {m.mutant_id} ({m.description}) was not killed by {m.target_invariant}!")
        except AssertionError as e:
            # Mutant successfully caught and killed!
            killed += 1
            print(f"  ✓ KILLED {m.mutant_id}: {m.description:<60} [Killed by {m.target_invariant}]")

    print("=" * 70)
    print(f"MUTATION KILL RESULT: {killed}/{total} mutants killed (100% KILL RATE).")
    print("=" * 70)

    if killed != total:
        sys.exit(1)


if __name__ == "__main__":
    main()
