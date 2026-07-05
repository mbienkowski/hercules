"""Regression tests for scripts/check_mutation_gate.py.

The gate script uses mutmut result-ids to count killed/survived/timeout
mutants and exits 1 if the kill rate falls below GATE (90%).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from check_mutation_gate import main  # noqa: E402


def _make_count_fn(killed: int, survived: int, timeout: int, untested: int = 0,
                   suspicious: int = 0):
    counts = {"killed": killed, "survived": survived, "timeout": timeout,
              "untested": untested, "suspicious": suspicious}
    return counts.__getitem__


def test_gate_passes_when_kill_rate_above_threshold(capsys):
    # 96 killed, 4 survived → 96.0% kill rate, above gate (90%) and warn (95%)
    exit_code = main(_make_count_fn(killed=96, survived=4, timeout=0))
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "OK" in out
    assert "WARNING" not in out


def test_gate_warns_when_kill_rate_between_gate_and_warn(capsys):
    # 92 killed, 8 survived → 92.0% — above gate (90%), below warn (95%)
    exit_code = main(_make_count_fn(killed=92, survived=8, timeout=0))
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "WARNING" in out
    assert "OK" in out


def test_gate_fails_when_kill_rate_below_threshold(capsys):
    # 80 killed, 20 survived → 80.0% — below gate (90%)
    exit_code = main(_make_count_fn(killed=80, survived=20, timeout=0))
    assert exit_code == 1


def test_gate_excludes_timeouts_from_denominator(capsys):
    # 90 killed, 10 survived, 100 timeout → 90/100 = 90.0% — exactly at gate, should pass
    exit_code = main(_make_count_fn(killed=90, survived=10, timeout=100))
    out = capsys.readouterr().out
    assert exit_code == 0


def test_gate_fails_when_no_mutants_generated():
    # 0 everything → script should exit 1 with an error
    exit_code = main(_make_count_fn(killed=0, survived=0, timeout=0))
    assert exit_code == 1


def test_gate_fails_when_only_timeouts():
    # all timeout, no killed or survived → indeterminate, should exit 1
    exit_code = main(_make_count_fn(killed=0, survived=0, timeout=50))
    assert exit_code == 1


def test_gate_fails_on_an_incomplete_run(capsys):
    """A crashed or interrupted mutmut run leaves mutants untested; computing the kill
    rate over the tested subset and printing OK is a green gate over data that never
    existed. Any untested mutant must fail the gate loudly."""
    exit_code = main(_make_count_fn(killed=95, survived=5, timeout=0, untested=40))
    err_out = capsys.readouterr()
    assert exit_code == 1
    assert "incomplete" in (err_out.err + err_out.out).lower()


def test_gate_fails_on_suspicious_mutants(capsys):
    """mutmut marks nondeterministic outcomes 'suspicious' — a kill rate that silently
    ignores them cannot be trusted either way."""
    exit_code = main(_make_count_fn(killed=95, survived=5, timeout=0, suspicious=3))
    assert exit_code == 1
