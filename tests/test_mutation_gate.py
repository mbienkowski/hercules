"""Regression tests for scripts/check_mutation_gate.py.

The gate script uses mutmut result-ids to count killed/survived/timeout
mutants and exits 1 if the kill rate falls below GATE (85%).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from check_mutation_gate import main  # noqa: E402


def _make_count_fn(killed: int, survived: int, timeout: int):
    counts = {"killed": killed, "survived": survived, "timeout": timeout}
    return counts.__getitem__


def test_gate_passes_when_kill_rate_above_threshold(capsys):
    # 90 killed, 10 survived → 90.0% kill rate, above gate (85%) and warn (90%)
    exit_code = main(_make_count_fn(killed=90, survived=10, timeout=0))
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "OK" in out


def test_gate_warns_when_kill_rate_between_gate_and_warn(capsys):
    # 87 killed, 13 survived → 87.0% — above gate (85%), below warn (90%)
    exit_code = main(_make_count_fn(killed=87, survived=13, timeout=0))
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "WARNING" in out
    assert "OK" in out


def test_gate_fails_when_kill_rate_below_threshold(capsys):
    # 80 killed, 20 survived → 80.0% — below gate (85%)
    exit_code = main(_make_count_fn(killed=80, survived=20, timeout=0))
    assert exit_code == 1


def test_gate_excludes_timeouts_from_denominator(capsys):
    # 85 killed, 15 survived, 100 timeout → 85/100 = 85.0% — exactly at gate, should pass
    exit_code = main(_make_count_fn(killed=85, survived=15, timeout=100))
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
