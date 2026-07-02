"""Unit tests for the data-driven threshold runner."""

import json
from pathlib import Path

import pytest

from tests.metrics.threshold_runner import (
    CheckResult,
    ThresholdCheck,
    compare_value,
    load_thresholds,
    resolve_targets,
    run_threshold_checks,
)


def test_threshold_check_field_defaults():
    """A ThresholdCheck built without the optional fields defaults to warn_at=None, per_file=False."""
    c = ThresholdCheck(name="n", target="t", metric="token_count", op="<=", limit=1, severity="gate")
    assert c.warn_at is None
    assert c.per_file is False


def test_check_result_near_warn_defaults_false():
    """A CheckResult built without near_warn defaults to False."""
    r = CheckResult(name="n", value=0, passed=True, severity="gate", message="m")
    assert r.near_warn is False


def _write_thresholds(tmp_path: Path, checks: list[dict]) -> Path:
    f = tmp_path / "thresholds.json"
    f.write_text(json.dumps(checks))
    return f


def test_thresholds_with_valid_config_all_pass(tmp_path: Path):
    """A threshold file with correct config loads and all passing checks are reported as passed."""
    # Given
    threshold_file = _write_thresholds(
        tmp_path,
        [
            {
                "name": "test-instruction-count",
                "target": "some.md",
                "metric": "instruction_count",
                "op": "<=",
                "limit": 100,
                "severity": "gate",
            }
        ],
    )
    target = tmp_path / "some.md"
    target.write_text("- bullet one\n- bullet two\n")

    # When
    checks = load_thresholds(threshold_file)
    results = run_threshold_checks(tmp_path, checks)

    # Then
    assert len(results) == 1
    assert results[0].passed is True


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
    # Given
    threshold_file = _write_thresholds(
        tmp_path,
        [
            {
                "name": "bad-warn-at",
                "target": "x.md",
                "metric": "token_count",
                "op": "<=",
                "limit": 100,
                "warn_at": 200,
                "severity": "gate",
            }
        ],
    )

    # When / Then
    with pytest.raises(ValueError, match="warn_at"):
        load_thresholds(threshold_file)


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


def test_check_fails_gracefully_when_target_pattern_matches_no_files(tmp_path: Path):
    """A threshold whose target glob matches nothing must produce a failed result, not an error."""
    # Given
    threshold_file = _write_thresholds(
        tmp_path,
        [
            {
                "name": "missing-target",
                "target": "nonexistent/*.md",
                "metric": "instruction_count",
                "op": "<=",
                "limit": 100,
                "severity": "gate",
            }
        ],
    )

    # When
    checks = load_thresholds(threshold_file)
    results = run_threshold_checks(tmp_path, checks)

    # Then
    assert len(results) == 1
    assert results[0].passed is False
    assert "matched no files" in results[0].message


def test_warn_at_threshold_triggers_warning_when_value_is_between_warn_at_and_limit(tmp_path: Path):
    """When a value exceeds warn_at but is below limit, the check must pass but mark as a warning."""
    # Given
    threshold_file = _write_thresholds(
        tmp_path,
        [
            {
                "name": "warn-check",
                "target": "agent.md",
                "metric": "token_count",
                "op": "<=",
                "limit": 5000,
                "warn_at": 10,
                "severity": "gate",
            }
        ],
    )
    # Write enough text to exceed warn_at=10 tokens but stay under limit=5000
    (tmp_path / "agent.md").write_text("This is a test file with some content.\n" * 5)

    # When
    checks = load_thresholds(threshold_file)
    results = run_threshold_checks(tmp_path, checks)

    # Then
    assert len(results) == 1
    assert results[0].passed is True
    assert results[0].near_warn is True


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


def test_warn_at_equal_to_limit_triggers_warning(tmp_path: Path):
    """warn_at == limit means the boundary itself triggers a warning."""
    # Given
    threshold_file = _write_thresholds(
        tmp_path,
        [
            {
                "name": "warn-equals-limit",
                "target": "f.md",
                "metric": "instruction_count",
                "op": "<=",
                "limit": 2,
                "warn_at": 2,
                "severity": "gate",
            }
        ],
    )
    (tmp_path / "f.md").write_text("- one\n- two\n")

    # When
    checks = load_thresholds(threshold_file)
    results = run_threshold_checks(tmp_path, checks)

    # Then
    assert results[0].passed is True
    assert results[0].near_warn is True


def test_no_files_result_has_value_zero(tmp_path: Path):
    """A failed 'no files matched' result must report value=0, not an arbitrary number."""
    # Given
    threshold_file = _write_thresholds(
        tmp_path,
        [
            {
                "name": "empty-target",
                "target": "missing/*.md",
                "metric": "instruction_count",
                "op": "<=",
                "limit": 100,
                "severity": "gate",
            }
        ],
    )

    # When
    checks = load_thresholds(threshold_file)
    results = run_threshold_checks(tmp_path, checks)

    # Then
    assert results[0].value == 0


def test_near_warn_not_set_when_value_below_warn_at(tmp_path: Path):
    """near_warn must be False when value has not yet reached warn_at."""
    # Given
    threshold_file = _write_thresholds(
        tmp_path,
        [
            {
                "name": "well-below-warn",
                "target": "g.md",
                "metric": "instruction_count",
                "op": "<=",
                "limit": 1000,
                "warn_at": 500,
                "severity": "gate",
            }
        ],
    )
    (tmp_path / "g.md").write_text("- one bullet\n")

    # When
    checks = load_thresholds(threshold_file)
    results = run_threshold_checks(tmp_path, checks)

    # Then
    assert results[0].near_warn is False


def test_result_message_is_non_empty_string(tmp_path: Path):
    """Every check result must have a non-empty message string."""
    # Given
    threshold_file = _write_thresholds(
        tmp_path,
        [
            {
                "name": "msg-check",
                "target": "h.md",
                "metric": "instruction_count",
                "op": "<=",
                "limit": 100,
                "severity": "gate",
            }
        ],
    )
    (tmp_path / "h.md").write_text("- item\n")

    # When
    checks = load_thresholds(threshold_file)
    results = run_threshold_checks(tmp_path, checks)

    # Then
    assert results[0].message is not None
    assert len(results[0].message) > 0


def test_resolve_targets_handles_comma_separated_paths(tmp_path: Path):
    """A comma-separated target list must resolve to all matching files."""
    from tests.metrics.threshold_runner import resolve_targets as _resolve_targets

    # Given
    (tmp_path / "a.md").write_text("a")
    (tmp_path / "b.md").write_text("b")

    # When
    targets = _resolve_targets(tmp_path, "a.md,b.md")

    # Then
    names = {t.name for t in targets}
    assert names == {"a.md", "b.md"}


def test_resolve_targets_handles_glob_pattern(tmp_path: Path):
    """A glob pattern must expand to all matching files."""
    from tests.metrics.threshold_runner import resolve_targets as _resolve_targets

    # Given
    (tmp_path / "x.md").write_text("x")
    (tmp_path / "y.md").write_text("y")

    # When
    targets = _resolve_targets(tmp_path, "*.md")

    # Then
    assert len(targets) == 2


def test_resolve_targets_returns_empty_for_no_match(tmp_path: Path):
    """A glob that matches nothing must return an empty list."""
    from tests.metrics.threshold_runner import resolve_targets as _resolve_targets

    # When
    targets = _resolve_targets(tmp_path, "nonexistent/*.md")

    # Then
    assert targets == []


def test_resolve_targets_deduplicates_overlapping_patterns(tmp_path: Path):
    """A file matched by multiple patterns must appear only once."""
    from tests.metrics.threshold_runner import resolve_targets as _resolve_targets

    # Given
    (tmp_path / "z.md").write_text("z")

    # When — same file listed explicitly and via glob
    targets = _resolve_targets(tmp_path, "z.md,*.md")

    # Then
    assert len(targets) == 1


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


def test_valid_op_greater_than_is_accepted_by_load_thresholds(tmp_path: Path):
    """Op '>' must be accepted (not treated as unknown) by load_thresholds."""
    threshold_file = _write_thresholds(
        tmp_path,
        [{"name": "gt", "target": "f.md", "metric": "token_count", "op": ">", "limit": 0, "severity": "gate"}],
    )
    checks = load_thresholds(threshold_file)
    assert checks[0].op == ">"


def test_severity_defaults_to_gate_when_not_specified(tmp_path: Path):
    """A threshold row without 'severity' must default to 'gate'."""
    threshold_file = _write_thresholds(
        tmp_path,
        [{"name": "no-sev", "target": "f.md", "metric": "token_count", "op": "<=", "limit": 100}],
    )
    checks = load_thresholds(threshold_file)
    assert checks[0].severity == "gate"


def test_compare_value_unknown_op_returns_false_not_true():
    """compare_value with unknown op must return (False, err) — not (True, err)."""
    passed, err = compare_value(1, "??", 1)
    assert passed is False
    assert err != ""


def test_multiple_checks_all_run_even_if_first_target_is_missing(tmp_path: Path):
    """When first check has no matching target, remaining checks must still run (continue not break)."""
    threshold_file = _write_thresholds(
        tmp_path,
        [
            {"name": "missing", "target": "nonexistent/*.md", "metric": "instruction_count", "op": "<=", "limit": 100, "severity": "gate"},
            {"name": "present", "target": "real.md", "metric": "instruction_count", "op": "<=", "limit": 100, "severity": "gate"},
        ],
    )
    (tmp_path / "real.md").write_text("- one\n")

    checks = load_thresholds(threshold_file)
    results = run_threshold_checks(tmp_path, checks)

    assert len(results) == 2
    assert results[0].passed is False  # missing target
    assert results[1].passed is True   # present target


def test_totals_accumulate_across_multiple_target_files(tmp_path: Path):
    """When a target matches multiple files, instruction counts must add up (not be replaced)."""
    threshold_file = _write_thresholds(
        tmp_path,
        [{"name": "multi", "target": "*.md", "metric": "instruction_count", "op": "<=", "limit": 1000, "severity": "gate"}],
    )
    (tmp_path / "a.md").write_text("- one\n- two\n")  # 2 instructions
    (tmp_path / "b.md").write_text("- three\n")       # 1 instruction

    checks = load_thresholds(threshold_file)
    results = run_threshold_checks(tmp_path, checks)

    assert results[0].value == 3  # must sum both files


def test_resolve_targets_detects_question_mark_glob(tmp_path: Path):
    """A pattern with '?' must be treated as a glob, not a literal path."""
    from tests.metrics.threshold_runner import resolve_targets as _resolve_targets

    (tmp_path / "ab.md").write_text("x")
    (tmp_path / "ac.md").write_text("y")

    targets = _resolve_targets(tmp_path, "a?.md")
    assert len(targets) == 2


def test_resolve_targets_detects_bracket_glob(tmp_path: Path):
    """A pattern with '[' must be treated as a glob, not a literal path."""
    from tests.metrics.threshold_runner import resolve_targets as _resolve_targets

    (tmp_path / "a1.md").write_text("x")
    (tmp_path / "a2.md").write_text("y")

    targets = _resolve_targets(tmp_path, "a[12].md")
    assert len(targets) == 2


def test_resolve_targets_skips_empty_patterns_from_double_comma(tmp_path: Path):
    """An empty pattern (from trailing/double comma) must be skipped, not stop iteration."""
    from tests.metrics.threshold_runner import resolve_targets as _resolve_targets

    (tmp_path / "a.md").write_text("x")
    (tmp_path / "b.md").write_text("y")

    # Double comma creates an empty pattern in the middle — must be skipped (continue), not stop (break)
    targets = _resolve_targets(tmp_path, "a.md,,b.md")
    names = {t.name for t in targets}
    assert names == {"a.md", "b.md"}


def test_no_files_result_has_near_warn_false(tmp_path: Path):
    """A 'no files matched' result must have near_warn=False (not True as initial default might be)."""
    threshold_file = _write_thresholds(
        tmp_path,
        [{"name": "empty", "target": "missing/*.md", "metric": "instruction_count", "op": "<=", "limit": 100, "severity": "gate"}],
    )
    checks = load_thresholds(threshold_file)
    results = run_threshold_checks(tmp_path, checks)

    assert results[0].near_warn is False


def test_load_thresholds_preserves_check_name(tmp_path: Path):
    """The 'name' field from thresholds.json must be stored on the ThresholdCheck object."""
    threshold_file = _write_thresholds(
        tmp_path,
        [{"name": "my-special-check", "target": "f.md", "metric": "token_count", "op": "<=", "limit": 100, "severity": "gate"}],
    )
    checks = load_thresholds(threshold_file)
    assert checks[0].name == "my-special-check"


def test_no_target_match_message_starts_with_target(tmp_path: Path):
    """The 'no files' message must start with 'target' (not 'XXtarget...')."""
    threshold_file = _write_thresholds(
        tmp_path,
        [{"name": "miss", "target": "gone/*.md", "metric": "instruction_count", "op": "<=", "limit": 100, "severity": "gate"}],
    )
    checks = load_thresholds(threshold_file)
    results = run_threshold_checks(tmp_path, checks)

    assert results[0].message.startswith("target ")


def test_per_file_passes_when_every_file_is_under_limit(tmp_path: Path):
    """per_file applies the limit to each matched file individually; all under → pass."""
    # Given
    (tmp_path / "a.md").write_text("aaa")
    (tmp_path / "b.md").write_text("bb")
    threshold_file = _write_thresholds(tmp_path, [{
        "name": "per-file-tokens", "target": "*.md", "metric": "token_count",
        "op": "<=", "limit": 50, "severity": "gate", "per_file": True,
    }])

    # When
    results = run_threshold_checks(tmp_path, load_thresholds(threshold_file))

    # Then
    assert results[0].passed


def test_per_file_fails_and_names_only_the_offender(tmp_path: Path):
    """per_file fails if ANY file exceeds the limit, and the message names the offender(s)."""
    # Given
    (tmp_path / "small.md").write_text("a")
    (tmp_path / "big.md").write_text("word " * 100)
    threshold_file = _write_thresholds(tmp_path, [{
        "name": "per-file-tokens", "target": "*.md", "metric": "token_count",
        "op": "<=", "limit": 5, "severity": "gate", "per_file": True,
    }])

    # When
    results = run_threshold_checks(tmp_path, load_thresholds(threshold_file))

    # Then
    assert not results[0].passed
    assert "big.md" in results[0].message
    assert "small.md" not in results[0].message


def test_per_file_defaults_false_and_sums_across_files(tmp_path: Path):
    """Without per_file the metric is summed across files (the default combined-budget behaviour)."""
    # Given — two 1-token files; summed = 2 > limit 1, so it must fail (proves summing).
    (tmp_path / "a.md").write_text("a")
    (tmp_path / "b.md").write_text("b")
    threshold_file = _write_thresholds(tmp_path, [{
        "name": "sum-tokens", "target": "*.md", "metric": "token_count",
        "op": "<=", "limit": 1, "severity": "gate",
    }])

    # When
    checks = load_thresholds(threshold_file)
    results = run_threshold_checks(tmp_path, checks)

    # Then
    assert checks[0].per_file is False
    assert not results[0].passed


def test_per_file_reports_worst_value_and_flags_near_warn(tmp_path: Path):
    """per_file reports the worst (max) per-file value — not the sum — and flags near_warn off it."""
    # Given
    from tests.metrics.token_counter import count_tokens
    big, small = "alpha beta gamma delta epsilon", "x"
    (tmp_path / "big.md").write_text(big)
    (tmp_path / "small.md").write_text(small)
    worst = max(count_tokens(big), count_tokens(small))
    threshold_file = _write_thresholds(tmp_path, [{
        "name": "pf", "target": "*.md", "metric": "token_count", "op": "<=",
        "limit": worst + 5, "warn_at": worst, "severity": "gate", "per_file": True,
    }])

    # When
    result = run_threshold_checks(tmp_path, load_thresholds(threshold_file))[0]

    # Then
    assert result.passed
    assert result.value == worst, "per_file must report the worst per-file value, not the sum"
    assert result.near_warn is True, "near_warn fires when the worst value reaches warn_at"


def test_per_file_does_not_flag_near_warn_below_warn_at(tmp_path: Path):
    """per_file leaves near_warn False when every file is below warn_at."""
    # Given
    (tmp_path / "a.md").write_text("x")
    threshold_file = _write_thresholds(tmp_path, [{
        "name": "pf", "target": "*.md", "metric": "token_count", "op": "<=",
        "limit": 100, "warn_at": 50, "severity": "gate", "per_file": True,
    }])

    # When
    result = run_threshold_checks(tmp_path, load_thresholds(threshold_file))[0]

    # Then
    assert result.passed and result.near_warn is False


def test_compare_value_less_than_and_greater_than_boundaries():
    """The < and > operators evaluate correctly at their boundaries."""
    assert compare_value(1, "<", 2) == (True, "")
    assert compare_value(2, "<", 2) == (False, "")
    assert compare_value(3, ">", 2) == (True, "")
    assert compare_value(2, ">", 2) == (False, "")


def test_per_file_worst_is_zero_for_an_empty_file(tmp_path: Path):
    """An empty file has 0 tokens, and per_file must report a worst of exactly 0 (not 1)."""
    (tmp_path / "empty.md").write_text("")
    threshold_file = _write_thresholds(tmp_path, [{
        "name": "pf", "target": "*.md", "metric": "token_count", "op": "<=",
        "limit": 5, "severity": "gate", "per_file": True,
    }])
    result = run_threshold_checks(tmp_path, load_thresholds(threshold_file))[0]
    assert result.passed and result.value == 0


def test_per_file_message_lists_all_offenders_comma_separated(tmp_path: Path):
    """A per_file failure names every offending file, comma-separated, and only the offenders."""
    (tmp_path / "big1.md").write_text("word " * 100)
    (tmp_path / "big2.md").write_text("word " * 100)
    (tmp_path / "ok.md").write_text("x")
    threshold_file = _write_thresholds(tmp_path, [{
        "name": "pf", "target": "*.md", "metric": "token_count", "op": "<=",
        "limit": 5, "severity": "gate", "per_file": True,
    }])
    result = run_threshold_checks(tmp_path, load_thresholds(threshold_file))[0]
    assert not result.passed
    assert "big1.md" in result.message and "big2.md" in result.message
    assert "ok.md" not in result.message
    assert ", " in result.message, "multiple offenders must be comma-separated"
    assert "XX" not in result.message


def test_run_raises_with_check_prefixed_message_on_invalid_op(tmp_path: Path):
    """An invalid op reaching run_threshold_checks raises a 'check '-prefixed error (both branches)."""
    (tmp_path / "a.md").write_text("x")
    bad_sum = ThresholdCheck(name="bad", target="a.md", metric="token_count",
                             op="??", limit=1, severity="gate")
    with pytest.raises(ValueError) as e_sum:
        run_threshold_checks(tmp_path, [bad_sum])
    assert str(e_sum.value).startswith("check")

    bad_pf = ThresholdCheck(name="badpf", target="a.md", metric="token_count",
                            op="??", limit=1, severity="gate", per_file=True)
    with pytest.raises(ValueError) as e_pf:
        run_threshold_checks(tmp_path, [bad_pf])
    assert str(e_pf.value).startswith("check")


def test_resolve_targets_plain_path_returns_path_even_when_missing(tmp_path: Path):
    """A plain (non-glob) target resolves to its path even if the file is absent — not via glob."""
    assert resolve_targets(tmp_path, "nope.md") == [tmp_path / "nope.md"]


def test_compare_value_unknown_op_error_starts_with_unknown():
    """compare_value error string must start with 'unknown op' (rejects XX-prefixed mutations)."""
    _, err = compare_value(1, "??", 1)
    assert err.startswith("unknown op")


def test_threshold_check_annotations_are_well_formed():
    """The dataclass annotations are lazily evaluated (PEP 563) — resolve them explicitly so a
    malformed annotation (e.g. `int & None`) fails here instead of silently never evaluating."""
    import typing

    hints = typing.get_type_hints(ThresholdCheck)
    assert hints["warn_at"] == typing.Optional[int]
    assert hints["limit"] is int


def test_passing_per_file_message_carries_no_offenders_suffix(tmp_path: Path):
    """A passing per-file check reports exactly the check summary — no offenders tail."""
    (tmp_path / "a.md").write_text("- one bullet\n")
    check = ThresholdCheck(name="pf", target="a.md", metric="instruction_count",
                           op="<=", limit=10, severity="gate", per_file=True)
    (result,) = run_threshold_checks(tmp_path, [check])
    assert result.passed is True
    assert result.message == "pf: per-file instruction_count(a.md) want <= 10"


def test_summed_check_message_states_value_and_want(tmp_path: Path):
    """The summed-check message is the exact `name: metric(target)=N, want op limit` shape —
    it is what CI prints on failure, so its format is a contract."""
    (tmp_path / "a.md").write_text("- one\n- two\n- three\n")
    check = ThresholdCheck(name="summed", target="a.md", metric="instruction_count",
                           op="<=", limit=2, severity="gate")
    (result,) = run_threshold_checks(tmp_path, [check])
    assert result.passed is False
    assert result.message == "summed: instruction_count(a.md)=3, want <= 2"


def test_plain_path_containing_x_is_not_treated_as_a_glob(tmp_path: Path):
    """Only *, ?, and [ mark a target as a glob — ordinary letters never do. A plain missing
    path resolves to itself (the caller reports it); a glob would silently resolve to []."""
    assert resolve_targets(tmp_path, "Xnope.md") == [tmp_path / "Xnope.md"]
