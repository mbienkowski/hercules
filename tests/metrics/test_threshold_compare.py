"""Threshold runner — compare_value operators and boundary behaviour."""

from __future__ import annotations

import pytest

from tests.metrics.threshold_runner import compare_value


def test_compare_value_evaluates_all_supported_operators():
    """compare_value must handle ==, <=, >=, <, > correctly and reject unknown operators."""
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
def test_compare_value_operator_boundaries(value, op, limit, expected):
    """All comparison operators must handle boundary cases correctly."""
    assert compare_value(value, op, limit) == (expected, "")


def test_compare_value_unknown_op_returns_false_not_true():
    """compare_value with unknown op must return (False, err) — not (True, err) — and the
    error must name the actual unrecognized op, not just be non-empty."""
    passed, err = compare_value(1, "??", 1)
    assert passed is False
    assert err.startswith("unknown op")
