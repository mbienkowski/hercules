"""Threshold runner — config loading, validation, and load-time error messages."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from tests.metrics.threshold_runner import CheckResult, ThresholdCheck, load_thresholds
from tests.metrics.conftest import _write_thresholds


def test_threshold_check_field_defaults():
    """A ThresholdCheck built without the optional fields defaults to warn_at=None, per_file=False."""
    c = ThresholdCheck(name="n", target="t", metric="token_count", op="<=", limit=1, severity="gate")
    assert c.warn_at is None
    assert c.per_file is False


def test_check_result_near_warn_defaults_false():
    """A CheckResult built without near_warn defaults to False."""
    r = CheckResult(name="n", value=0, passed=True, severity="gate", message="m")
    assert r.near_warn is False


def test_unknown_metric_name_raises_a_clear_error_on_load(tmp_path: Path):
    """A typo in a metric name must be caught at load time, not silently at runtime."""
    # Given
    threshold_file = _write_thresholds(
        tmp_path,
        [
            {
                "name": "bad-metric",
                "target": "x.md",
                "metric": "nonexistent_metric",
                "op": "<=",
                "limit": 100,
                "severity": "gate",
            }
        ],
    )

    # When / Then
    with pytest.raises(ValueError, match="unknown metric"):
        load_thresholds(threshold_file)


def test_unknown_severity_value_raises_a_clear_error_on_load(tmp_path: Path):
    """A typo in severity (e.g. 'error' instead of 'gate') is caught at load time."""
    # Given
    threshold_file = _write_thresholds(
        tmp_path,
        [
            {
                "name": "bad-severity",
                "target": "x.md",
                "metric": "token_count",
                "op": "<=",
                "limit": 100,
                "severity": "error",
            }
        ],
    )

    # When / Then
    with pytest.raises(ValueError, match="unknown severity"):
        load_thresholds(threshold_file)


def test_warn_at_greater_than_limit_raises_a_clear_error_on_load(tmp_path: Path):
    """warn_at above the hard limit is a config mistake — caught at load time."""
    threshold_file = _write_thresholds(tmp_path, [
        {"name": "bad-warn-at", "target": "x.md", "metric": "token_count",
         "op": "<=", "limit": 100, "warn_at": 200, "severity": "gate"},
    ])
    with pytest.raises(ValueError, match="warn_at"):
        load_thresholds(threshold_file)


def test_core_token_count_raises_when_no_fenced_block_exists():
    """_core_token_count must raise ValueError when the text has no fenced A2A Core block.

    Guards against silent zero-count results if the protocol file loses its fenced block.
    """
    # Given
    from tests.metrics.threshold_runner import _core_token_count

    # When / Then
    with pytest.raises(ValueError, match="no fenced Core block found"):
        _core_token_count("This is plain markdown\n\n## No fence here\n")


def test_unknown_op_raises_a_clear_error_on_load(tmp_path: Path):
    """A typo in op (e.g. '==' vs '=') is caught at load time, not silently at runtime."""
    # Given
    threshold_file = _write_thresholds(
        tmp_path,
        [
            {
                "name": "bad-op",
                "target": "x.md",
                "metric": "token_count",
                "op": "!=",
                "limit": 100,
                "severity": "gate",
            }
        ],
    )

    # When / Then
    with pytest.raises(ValueError, match="unknown op"):
        load_thresholds(threshold_file)


def test_valid_severity_warn_is_accepted_by_load_thresholds(tmp_path: Path):
    """Severity 'warn' must be accepted (not treated as unknown) by load_thresholds."""
    threshold_file = _write_thresholds(
        tmp_path,
        [{"name": "w", "target": "f.md", "metric": "token_count", "op": "<=", "limit": 100, "severity": "warn"}],
    )
    checks = load_thresholds(threshold_file)
    assert checks[0].severity == "warn"


def test_valid_op_equality_is_accepted_by_load_thresholds(tmp_path: Path):
    """Op '==' must be accepted (not treated as unknown) by load_thresholds."""
    threshold_file = _write_thresholds(
        tmp_path,
        [{"name": "eq", "target": "f.md", "metric": "token_count", "op": "==", "limit": 100, "severity": "gate"}],
    )
    checks = load_thresholds(threshold_file)
    assert checks[0].op == "=="


def test_valid_op_less_than_is_accepted_by_load_thresholds(tmp_path: Path):
    """Op '<' must be accepted (not treated as unknown) by load_thresholds."""
    threshold_file = _write_thresholds(
        tmp_path,
        [{"name": "lt", "target": "f.md", "metric": "token_count", "op": "<", "limit": 100, "severity": "gate"}],
    )
    checks = load_thresholds(threshold_file)
    assert checks[0].op == "<"


def test_severity_defaults_to_gate_when_not_specified(tmp_path: Path):
    """A threshold row without 'severity' must default to 'gate'."""
    threshold_file = _write_thresholds(
        tmp_path,
        [{"name": "no-sev", "target": "f.md", "metric": "token_count", "op": "<=", "limit": 100}],
    )
    checks = load_thresholds(threshold_file)
    assert checks[0].severity == "gate"
