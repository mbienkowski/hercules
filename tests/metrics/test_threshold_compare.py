"""Threshold runner — compare_value operators and boundary behaviour."""

from __future__ import annotations

import pytest

from tests.metrics.threshold_runner import compare_value


def test_every_supported_comparison_rule_gives_the_right_pass_fail_verdict():
    """Each way a metric can be checked against a limit -- equals, at most, at least, strictly
    less than, strictly greater than -- must produce the correct pass/fail result, and a rule
    that isn't recognized at all must be reported as an error rather than silently accepted."""
    # Given / When / Then
    assert compare_value(7, "==", 7) == (True, "")
    assert compare_value(8, "==", 7) == (False, "")
    assert compare_value(7, "<=", 20) == (True, "")
    assert compare_value(21, "<=", 20) == (False, "")
    assert compare_value(130, ">=", 100) == (True, "")
    assert compare_value(5, "<", 10) == (True, "")
    assert compare_value(10, "<", 10) == (False, "")
    assert compare_value(10, ">", 9) == (True, "")

    _, err = compare_value(1, "??", 1)
    assert err != ""  # unknown operator must return an error message


@pytest.mark.parametrize("value,op,limit,expected", [
    (20, "<=", 20, True),   # at boundary
    (21, "<=", 20, False),  # over boundary
    (100, ">=", 100, True), # at boundary
    (99, ">=", 100, False), # under boundary
    (42, "==", 42, True),   # exact match
    (42, "==", 43, False),  # off by one (value < limit)
    (43, "==", 42, False),  # off by one (value > limit)
    (9, "<", 10, True),     # strictly below
    (10, "<", 10, False),   # at limit — must fail for strict <
    (11, ">", 10, True),    # strictly above
    (10, ">", 10, False),   # at limit — must fail for strict >
])
def test_a_metric_exactly_at_its_limit_is_judged_consistently(value, op, limit, expected):
    """A metric that lands exactly on its allowed threshold must be judged the same way
    every time, whether the rule is 'at least' or 'at most' -- an off-by-one here would let
    a failing metric through or reject a passing one."""
    assert compare_value(value, op, limit) == (expected, "")


def test_an_unrecognized_comparison_rule_fails_safe_with_a_clear_reason():
    """If a threshold check names a comparison rule the system doesn't know, that check must
    come back as failed (never mistakenly treated as passed), and the reason given must
    actually name the unrecognized rule so someone debugging it isn't left guessing."""
    passed, err = compare_value(1, "??", 1)
    assert passed is False
    assert err.startswith("unknown op")
