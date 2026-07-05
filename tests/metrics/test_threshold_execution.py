"""Threshold runner — running checks: summed and per_file modes, warn_at, results, messages."""

from __future__ import annotations

from pathlib import Path
import pytest

from tests.metrics.threshold_runner import ThresholdCheck, load_thresholds, run_threshold_checks
from tests.metrics.conftest import _run_one_check, _write_thresholds


def test_thresholds_with_valid_config_all_pass(tmp_path: Path):
    """A threshold file with correct config loads and all passing checks are reported as passed."""
    results = _run_one_check(
        tmp_path,
        {"name": "test-instruction-count", "target": "some.md", "metric": "instruction_count",
         "op": "<=", "limit": 100, "severity": "gate"},
        {"some.md": "- bullet one\n- bullet two\n"},
    )
    assert len(results) == 1
    assert results[0].passed is True


def test_check_fails_gracefully_when_target_pattern_matches_no_files(tmp_path: Path):
    """A threshold whose target glob matches nothing must produce a failed result, not an error."""
    results = _run_one_check(
        tmp_path,
        {"name": "missing-target", "target": "nonexistent/*.md", "metric": "instruction_count",
         "op": "<=", "limit": 100, "severity": "gate"},
    )
    assert len(results) == 1
    assert results[0].passed is False
    assert "matched no files" in results[0].message


def test_warn_at_threshold_triggers_warning_when_value_is_between_warn_at_and_limit(tmp_path: Path):
    """When a value exceeds warn_at but is below limit, the check must pass but mark as a warning."""
    # 5× the sentence exceeds warn_at=10 tokens but stays under limit=5000.
    results = _run_one_check(
        tmp_path,
        {"name": "warn-check", "target": "agent.md", "metric": "token_count",
         "op": "<=", "limit": 5000, "warn_at": 10, "severity": "gate"},
        {"agent.md": "This is a test file with some content.\n" * 5},
    )
    assert len(results) == 1
    assert results[0].passed is True
    assert results[0].near_warn is True


def test_warn_at_equal_to_limit_triggers_warning(tmp_path: Path):
    """warn_at == limit means the boundary itself triggers a warning."""
    results = _run_one_check(
        tmp_path,
        {"name": "warn-equals-limit", "target": "f.md", "metric": "instruction_count",
         "op": "<=", "limit": 2, "warn_at": 2, "severity": "gate"},
        {"f.md": "- one\n- two\n"},
    )
    assert results[0].passed is True
    assert results[0].near_warn is True


def test_no_files_result_has_value_zero(tmp_path: Path):
    """A failed 'no files matched' result must report value=0, not an arbitrary number."""
    results = _run_one_check(
        tmp_path,
        {"name": "empty-target", "target": "missing/*.md", "metric": "instruction_count",
         "op": "<=", "limit": 100, "severity": "gate"},
    )
    assert results[0].value == 0


def test_near_warn_not_set_when_value_below_warn_at(tmp_path: Path):
    """near_warn must be False when value has not yet reached warn_at."""
    results = _run_one_check(
        tmp_path,
        {"name": "well-below-warn", "target": "g.md", "metric": "instruction_count",
         "op": "<=", "limit": 1000, "warn_at": 500, "severity": "gate"},
        {"g.md": "- one bullet\n"},
    )
    assert results[0].near_warn is False


def test_result_message_is_non_empty_string(tmp_path: Path):
    """Every check result must have a non-empty message string."""
    results = _run_one_check(
        tmp_path,
        {"name": "msg-check", "target": "h.md", "metric": "instruction_count",
         "op": "<=", "limit": 100, "severity": "gate"},
        {"h.md": "- item\n"},
    )
    assert results[0].message is not None
    assert len(results[0].message) > 0


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


def test_no_files_result_has_near_warn_false(tmp_path: Path):
    """A 'no files matched' result must have near_warn=False (not True as initial default might be)."""
    threshold_file = _write_thresholds(
        tmp_path,
        [{"name": "empty", "target": "missing/*.md", "metric": "instruction_count", "op": "<=", "limit": 100, "severity": "gate"}],
    )
    checks = load_thresholds(threshold_file)
    results = run_threshold_checks(tmp_path, checks)

    assert results[0].near_warn is False


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
