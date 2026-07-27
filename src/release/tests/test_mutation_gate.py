"""Regression tests for release/check_mutation_gate.py.

The gate script uses mutmut result-ids to count killed/survived/timeout
mutants and exits 1 if the kill rate falls below GATE (90%).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from check_mutation_gate import main  # noqa: E402


def _make_count_fn(killed: int, survived: int, timeout: int, untested: int = 0,
                   suspicious: int = 0):
    counts = {"killed": killed, "survived": survived, "timeout": timeout,
              "untested": untested, "suspicious": suspicious}
    return counts.__getitem__


def test_a_high_enough_kill_rate_passes_the_gate_cleanly(capsys):
    """A kill rate comfortably above both the minimum bar (90%) and the warning line (95%)
    reports a clean OK and does not fail the build."""
    # 96 killed, 4 survived → 96.0% kill rate, above gate (90%) and warn (95%)
    exit_code = main(_make_count_fn(killed=96, survived=4, timeout=0))
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "OK" in out
    assert "WARNING" not in out


def test_a_kill_rate_just_above_minimum_still_passes_but_prints_a_warning(capsys):
    """A kill rate that clears the minimum bar (90%) but not the warning bar (95%) still passes,
    with a warning so thinning coverage is announced before it becomes a failure."""
    # 92 killed, 8 survived → 92.0% — above gate (90%), below warn (95%)
    exit_code = main(_make_count_fn(killed=92, survived=8, timeout=0))
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "WARNING" in out
    assert "OK" in out


def test_a_kill_rate_below_minimum_fails_the_build(capsys):
    """A kill rate below the 90% minimum bar fails the build, so weak test coverage never
    passes as if it were safe."""
    # 80 killed, 20 survived → 80.0% — below gate (90%)
    exit_code = main(_make_count_fn(killed=80, survived=20, timeout=0))
    assert exit_code == 1


def test_mutants_that_time_out_do_not_count_against_the_kill_rate(capsys):
    """Timed-out mutants are left out of the score entirely, so a batch of slow mutants cannot
    drag down a run that otherwise clears the bar."""
    # 90 killed, 10 survived, 100 timeout → 90/100 = 90.0% — exactly at gate, should pass
    exit_code = main(_make_count_fn(killed=90, survived=10, timeout=100))
    out = capsys.readouterr().out
    assert exit_code == 0


def test_the_gate_fails_when_no_mutants_were_ever_generated():
    """Zero mutants means nothing was ever proven, so the gate reports an error rather than
    letting an empty run through as a pass."""
    # 0 everything → script should exit 1 with an error
    exit_code = main(_make_count_fn(killed=0, survived=0, timeout=0))
    assert exit_code == 1


def test_the_gate_fails_when_every_single_mutant_only_timed_out():
    """An all-timeout run carries no signal in either direction, so the gate treats that
    inconclusive result as a failure rather than guessing a pass."""
    # all timeout, no killed or survived → indeterminate, should exit 1
    exit_code = main(_make_count_fn(killed=0, survived=0, timeout=50))
    assert exit_code == 1


def test_gate_fails_on_an_incomplete_run(capsys):
    """A crashed run leaves mutants untested, and a score over only the tested subset is a
    green gate over data that never existed — so any untested mutant fails the gate."""
    exit_code = main(_make_count_fn(killed=95, survived=5, timeout=0, untested=40))
    err_out = capsys.readouterr()
    assert exit_code == 1
    assert "incomplete" in (err_out.err + err_out.out).lower()


def test_gate_fails_when_results_are_flagged_as_unreliable(capsys):
    """Outcomes marked unreliable rather than a clean kill or survive cannot be trusted in
    either direction, so the gate fails the build until they are resolved."""
    exit_code = main(_make_count_fn(killed=95, survived=5, timeout=0, suspicious=3))
    assert exit_code == 1
