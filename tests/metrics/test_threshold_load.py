"""Threshold runner — config loading, validation, and load-time error messages."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from tests.metrics.threshold_runner import CheckResult, ThresholdCheck, load_thresholds
from tests.metrics.conftest import _write_thresholds


def test_a_threshold_rule_without_optional_settings_gets_safe_defaults():
    """When a threshold rule is defined without an early-warning level or a per-file mode, it
    must default to having no early warning and to checking the whole target as one unit --
    so leaving those settings out can never accidentally enable stricter behavior than intended."""
    c = ThresholdCheck(name="n", target="t", metric="token_count", op="<=", limit=1, severity="gate")
    assert c.warn_at is None
    assert c.per_file is False


def test_a_check_result_without_near_warn_specified_defaults_to_not_close_to_warning():
    """A check result created without saying whether it's close to its warning level must
    default to false, so a passing result is never mistakenly flagged as being near a breach."""
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


def test_an_early_warning_level_set_above_the_hard_limit_is_rejected_at_load_time(tmp_path: Path):
    """Configuring the early-warning level higher than the hard limit is a mistake -- a warning
    that only fires after the hard limit has already been breached is useless. This is caught
    immediately when the thresholds are loaded, not discovered later when warnings never appear."""
    threshold_file = _write_thresholds(tmp_path, [
        {"name": "bad-warn-at", "target": "x.md", "metric": "token_count",
         "op": "<=", "limit": 100, "warn_at": 200, "severity": "gate"},
    ])
    with pytest.raises(ValueError, match="warn_at"):
        load_thresholds(threshold_file)


def test_a_protocol_file_missing_its_core_section_fails_loudly_instead_of_counting_zero():
    """If a protocol document has lost the fenced 'Core' section that the token-count metric
    measures, counting must raise an error immediately rather than silently reporting a count
    of zero -- a silent zero would let the file's structure quietly break without anyone noticing."""
    # Given
    from tests.metrics.threshold_runner import _core_token_count

    # When / Then
    with pytest.raises(ValueError, match="no fenced Core block found"):
        _core_token_count("This is plain markdown\n\n## No fence here\n")


def test_unknown_comparison_operator_raises_a_clear_error_on_load(tmp_path: Path):
    """A typo in the comparison operator used by a threshold rule (e.g. '!=' where only
    supported comparisons like <=, <, or == are allowed) is caught the moment the thresholds
    are loaded, not silently ignored until the check runs."""
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


def test_a_warn_severity_level_is_accepted_when_loading_thresholds(tmp_path: Path):
    """The 'warn' severity level must be recognized as valid when thresholds are loaded, not
    rejected as an unrecognized value -- so soft warnings remain usable alongside hard gates."""
    threshold_file = _write_thresholds(
        tmp_path,
        [{"name": "w", "target": "f.md", "metric": "token_count", "op": "<=", "limit": 100, "severity": "warn"}],
    )
    checks = load_thresholds(threshold_file)
    assert checks[0].severity == "warn"


def test_an_equality_comparison_is_accepted_when_loading_thresholds(tmp_path: Path):
    """The equality comparison ('==') must be recognized as a valid way to compare a metric to
    its limit when thresholds are loaded, not rejected as an unrecognized comparison."""
    threshold_file = _write_thresholds(
        tmp_path,
        [{"name": "eq", "target": "f.md", "metric": "token_count", "op": "==", "limit": 100, "severity": "gate"}],
    )
    checks = load_thresholds(threshold_file)
    assert checks[0].op == "=="


def test_a_less_than_comparison_is_accepted_when_loading_thresholds(tmp_path: Path):
    """The less-than comparison ('<') must be recognized as a valid way to compare a metric to
    its limit when thresholds are loaded, not rejected as an unrecognized comparison."""
    threshold_file = _write_thresholds(
        tmp_path,
        [{"name": "lt", "target": "f.md", "metric": "token_count", "op": "<", "limit": 100, "severity": "gate"}],
    )
    checks = load_thresholds(threshold_file)
    assert checks[0].op == "<"


def test_a_threshold_rule_without_a_severity_defaults_to_a_hard_gate(tmp_path: Path):
    """When a threshold rule doesn't specify a severity level, it must default to 'gate' (a
    hard failure) rather than a soft warning -- so an omitted severity can never accidentally
    weaken enforcement and let a failing check pass through unnoticed."""
    threshold_file = _write_thresholds(
        tmp_path,
        [{"name": "no-sev", "target": "f.md", "metric": "token_count", "op": "<=", "limit": 100}],
    )
    checks = load_thresholds(threshold_file)
    assert checks[0].severity == "gate"
