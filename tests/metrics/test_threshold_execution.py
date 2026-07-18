"""Threshold runner — running checks: summed and per_file modes, warn_at, results, messages."""

from __future__ import annotations

from pathlib import Path
import pytest

from tests.metrics.threshold_runner import ThresholdCheck, load_thresholds, run_threshold_checks
from tests.metrics.conftest import _run_one_check, _write_thresholds


def test_a_valid_threshold_file_passes_all_its_checks(tmp_path: Path):
    """A well-formed threshold file loads successfully, and every check whose measured value meets
    its limit is reported as passed."""
    results = _run_one_check(
        tmp_path,
        {"name": "test-instruction-count", "target": "some.md", "metric": "instruction_count",
         "op": "<=", "limit": 100, "severity": "gate"},
        {"some.md": "- bullet one\n- bullet two\n"},
    )
    assert len(results) == 1
    assert results[0].passed is True


def test_a_check_with_no_matching_files_fails_instead_of_crashing(tmp_path: Path):
    """When a check's file pattern matches nothing in the project, it is reported as a failed
    check with a clear explanation -- rather than crashing the whole run with an error."""
    results = _run_one_check(
        tmp_path,
        {"name": "missing-target", "target": "nonexistent/*.md", "metric": "instruction_count",
         "op": "<=", "limit": 100, "severity": "gate"},
    )
    assert len(results) == 1
    assert results[0].passed is False
    assert "matched no files" in results[0].message


def test_a_value_past_the_warning_level_but_under_the_limit_still_passes_but_gets_flagged(tmp_path: Path):
    """When a measured value has crossed the early-warning level but is still under the hard
    limit, the check must pass, but it is flagged so a developer can see it is trending toward
    a future failure."""
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


def test_a_value_exactly_at_the_limit_is_still_flagged_as_a_warning(tmp_path: Path):
    """If the early-warning level is set equal to the hard limit, reaching the limit itself must
    still trigger the warning flag rather than being silently treated as fine."""
    results = _run_one_check(
        tmp_path,
        {"name": "warn-equals-limit", "target": "f.md", "metric": "instruction_count",
         "op": "<=", "limit": 2, "warn_at": 2, "severity": "gate"},
        {"f.md": "- one\n- two\n"},
    )
    assert results[0].passed is True
    assert results[0].near_warn is True


def test_a_check_with_no_matching_files_reports_a_measured_value_of_zero(tmp_path: Path):
    """When no files match a check's target, the reported measurement must be exactly zero,
    not a leftover or arbitrary number, so downstream reports aren't misleading."""
    results = _run_one_check(
        tmp_path,
        {"name": "empty-target", "target": "missing/*.md", "metric": "instruction_count",
         "op": "<=", "limit": 100, "severity": "gate"},
    )
    assert results[0].value == 0


def test_a_value_comfortably_below_the_warning_level_is_not_flagged(tmp_path: Path):
    """When a measured value is well below the early-warning level, the check must not be
    flagged as approaching its limit."""
    results = _run_one_check(
        tmp_path,
        {"name": "well-below-warn", "target": "g.md", "metric": "instruction_count",
         "op": "<=", "limit": 1000, "warn_at": 500, "severity": "gate"},
        {"g.md": "- one bullet\n"},
    )
    assert results[0].near_warn is False


def test_a_later_check_still_runs_after_an_earlier_check_finds_no_files(tmp_path: Path):
    """If an earlier check in the list can't find any matching files, that failure must not stop
    the checks listed after it -- every configured check still gets evaluated."""
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


def test_a_check_spanning_multiple_files_adds_up_their_counts(tmp_path: Path):
    """When a check's target matches several files, their individual counts are summed into one
    total, rather than the total ending up as just the last file's count."""
    threshold_file = _write_thresholds(
        tmp_path,
        [{"name": "multi", "target": "*.md", "metric": "instruction_count", "op": "<=", "limit": 1000, "severity": "gate"}],
    )
    (tmp_path / "a.md").write_text("- one\n- two\n")  # 2 instructions
    (tmp_path / "b.md").write_text("- three\n")       # 1 instruction

    checks = load_thresholds(threshold_file)
    results = run_threshold_checks(tmp_path, checks)

    assert results[0].value == 3  # must sum both files


def test_a_check_with_no_matching_files_is_never_flagged_as_approaching_its_limit(tmp_path: Path):
    """A check that fails because no files matched its target must not also be flagged as
    'nearing the limit' -- that flag should only ever mean a real value came close to a real
    limit, never be left over from some other default."""
    threshold_file = _write_thresholds(
        tmp_path,
        [{"name": "empty", "target": "missing/*.md", "metric": "instruction_count", "op": "<=", "limit": 100, "severity": "gate"}],
    )
    checks = load_thresholds(threshold_file)
    results = run_threshold_checks(tmp_path, checks)

    assert results[0].near_warn is False


def test_a_per_file_limit_passes_when_every_individual_file_is_under_it(tmp_path: Path):
    """When a limit is applied file-by-file rather than to a combined total, the check passes
    as long as each individual matched file stays under the limit on its own."""
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


def test_a_per_file_limit_failure_names_only_the_files_that_broke_it(tmp_path: Path):
    """When at least one file exceeds a per-file limit, the check fails and its message names
    the offending file(s) specifically, without implicating files that were actually fine."""
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


def test_files_are_combined_into_one_total_unless_a_per_file_limit_is_requested(tmp_path: Path):
    """By default, a check's measurement adds up the values from every matching file into one
    combined total, so the limit is breached once the combined usage across files is too high --
    not just when any single file is."""
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


def test_a_per_file_limit_reports_the_single_worst_file_and_flags_a_warning_off_it(tmp_path: Path):
    """When checking files individually, the reported value is the single worst (highest) file,
    not the sum of all of them, and the early-warning flag is based on that worst file too."""
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


def test_a_per_file_limit_is_not_flagged_when_every_file_stays_below_the_warning_level(tmp_path: Path):
    """When checking files individually, the check is not flagged as approaching its limit
    unless at least one file has actually reached the early-warning level."""
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


def test_an_empty_file_counts_as_exactly_zero_under_a_per_file_limit(tmp_path: Path):
    """An empty file must be measured as having zero content, and a per-file check reports that
    zero as the worst value, rather than mistakenly counting an empty file as size one."""
    (tmp_path / "empty.md").write_text("")
    threshold_file = _write_thresholds(tmp_path, [{
        "name": "pf", "target": "*.md", "metric": "token_count", "op": "<=",
        "limit": 5, "severity": "gate", "per_file": True,
    }])
    result = run_threshold_checks(tmp_path, load_thresholds(threshold_file))[0]
    assert result.passed and result.value == 0


def test_a_per_file_failure_lists_every_offending_file_separated_by_commas(tmp_path: Path):
    """When multiple files individually break a per-file limit, the failure message lists every
    offender, separated by commas, and leaves out any file that was actually within limits."""
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


def test_an_unrecognized_comparison_operator_produces_a_clearly_labeled_error(tmp_path: Path):
    """If a check is configured with a comparison operator Hercules doesn't recognize, running it
    raises an error whose message identifies which check caused it, for both the combined-total
    and the per-file evaluation modes -- so a bad config file is easy to diagnose."""
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


def test_a_passing_per_file_check_reports_a_clean_summary_with_no_offender_list(tmp_path: Path):
    """When a per-file check passes, its message is just the plain check summary -- it must not
    tack on an empty or stray list of offending files that could confuse the reader."""
    (tmp_path / "a.md").write_text("- one bullet\n")
    check = ThresholdCheck(name="pf", target="a.md", metric="instruction_count",
                           op="<=", limit=10, severity="gate", per_file=True)
    (result,) = run_threshold_checks(tmp_path, [check])
    assert result.passed is True
    assert result.message == "pf: per-file instruction_count(a.md) want <= 10"


def test_a_failing_checks_message_reports_the_measured_value_and_the_required_limit(tmp_path: Path):
    """A failing check's message follows the exact `name: metric(target)=value, want operator
    limit` wording, because this is the line CI prints to tell a developer what broke and by
    how much -- so its exact format is a contract that must not silently drift."""
    (tmp_path / "a.md").write_text("- one\n- two\n- three\n")
    check = ThresholdCheck(name="summed", target="a.md", metric="instruction_count",
                           op="<=", limit=2, severity="gate")
    (result,) = run_threshold_checks(tmp_path, [check])
    assert result.passed is False
    assert result.message == "summed: instruction_count(a.md)=3, want <= 2"
