"""Mutation kill-rate gate. Queries mutmut result-ids and exits 1 if below threshold.

Usage: python scripts/check_mutation_gate.py
"""
import subprocess
import sys

GATE = 85
WARN = 90


def _count(status: str) -> int:
    """Return the number of mutants with the given status by querying mutmut result-ids."""
    try:
        out = subprocess.check_output(
            ["mutmut", "result-ids", status], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return 0
    if not out:
        return 0
    return len(out.split())


def main(count_fn=_count) -> int:
    killed   = count_fn("killed")
    survived = count_fn("survived")
    timeout  = count_fn("timeout")
    total    = killed + survived + timeout

    if total == 0:
        print("ERROR: No mutants generated — check paths_to_mutate config", file=sys.stderr)
        return 1

    denominator = killed + survived
    if denominator == 0:
        print("ERROR: All mutants timed out — runner timeout too short", file=sys.stderr)
        return 1

    kill_rate = (killed / denominator) * 100
    print(f"Mutants: {total} total | {killed} killed | {survived} survived | {timeout} timeout")
    print(f"Kill rate: {kill_rate:.1f}%")

    if kill_rate < WARN:
        print(f"WARNING: kill rate {kill_rate:.1f}% below warn threshold ({WARN}%)")
    if kill_rate < GATE:
        print(f"FAILED: kill rate {kill_rate:.1f}% below gate ({GATE}%)", file=sys.stderr)
        return 1

    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
