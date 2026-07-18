"""Threshold runner — resolve_targets: glob, comma-separated, dedup, plain-path."""

from __future__ import annotations

from pathlib import Path

from tests.metrics.threshold_runner import resolve_targets


def test_a_comma_separated_list_of_files_is_treated_as_multiple_targets(tmp_path: Path):
    """When target files are given as a comma-separated list, every file named in the list is
    picked up individually, so a single configuration line can cover several files at once."""
    from tests.metrics.threshold_runner import resolve_targets as _resolve_targets

    # Given
    (tmp_path / "a.md").write_text("a")
    (tmp_path / "b.md").write_text("b")

    # When
    targets = _resolve_targets(tmp_path, "a.md,b.md")

    # Then
    names = {t.name for t in targets}
    assert names == {"a.md", "b.md"}


def test_a_wildcard_pattern_expands_to_every_matching_file(tmp_path: Path):
    """When a target is written as a wildcard pattern instead of a literal filename, every file
    that fits the pattern is picked up automatically, so new matching files don't need to be
    added to a config by hand."""
    from tests.metrics.threshold_runner import resolve_targets as _resolve_targets

    # Given
    (tmp_path / "x.md").write_text("x")
    (tmp_path / "y.md").write_text("y")

    # When
    targets = _resolve_targets(tmp_path, "*.md")

    # Then
    assert len(targets) == 2


def test_a_wildcard_pattern_matching_nothing_yields_no_targets(tmp_path: Path):
    """If a wildcard pattern doesn't match any existing files, the run simply ends up with no
    targets for it instead of erroring out -- for example when an optional group of files
    hasn't been created yet."""
    from tests.metrics.threshold_runner import resolve_targets as _resolve_targets

    # When
    targets = _resolve_targets(tmp_path, "nonexistent/*.md")

    # Then
    assert targets == []


def test_a_file_matched_by_two_overlapping_targets_is_only_counted_once(tmp_path: Path):
    """When the same file is reachable through more than one entry in the target list, it only
    shows up once in the result, so that file isn't accidentally checked -- or its results
    counted -- twice."""
    from tests.metrics.threshold_runner import resolve_targets as _resolve_targets

    # Given
    (tmp_path / "z.md").write_text("z")

    # When — same file listed explicitly and via glob
    targets = _resolve_targets(tmp_path, "z.md,*.md")

    # Then
    assert len(targets) == 1


def test_a_single_character_placeholder_in_a_target_matches_multiple_files(tmp_path: Path):
    """A target containing '?' is treated as a placeholder for any one character, not as part of
    a literal filename, so it correctly picks up every file that fits the pattern rather than
    looking for a file named exactly that."""
    from tests.metrics.threshold_runner import resolve_targets as _resolve_targets

    (tmp_path / "ab.md").write_text("x")
    (tmp_path / "ac.md").write_text("y")

    targets = _resolve_targets(tmp_path, "a?.md")
    assert len(targets) == 2


def test_a_bracketed_character_choice_in_a_target_matches_multiple_files(tmp_path: Path):
    """A target containing bracketed options like '[12]' is treated as 'match any one of these
    characters here', not as part of a literal filename, so it correctly picks up every file
    whose name fits one of the listed choices."""
    from tests.metrics.threshold_runner import resolve_targets as _resolve_targets

    (tmp_path / "a1.md").write_text("x")
    (tmp_path / "a2.md").write_text("y")

    targets = _resolve_targets(tmp_path, "a[12].md")
    assert len(targets) == 2


def test_an_accidental_double_comma_in_the_target_list_does_not_drop_later_files(tmp_path: Path):
    """A stray extra comma in a comma-separated target list -- an easy typo -- leaves an empty
    entry that is simply skipped, so the files listed after it are still picked up instead of
    the whole list quietly stopping short."""
    from tests.metrics.threshold_runner import resolve_targets as _resolve_targets

    (tmp_path / "a.md").write_text("x")
    (tmp_path / "b.md").write_text("y")

    # Double comma creates an empty pattern in the middle — must be skipped (continue), not stop (break)
    targets = _resolve_targets(tmp_path, "a.md,,b.md")
    names = {t.name for t in targets}
    assert names == {"a.md", "b.md"}


def test_a_missing_file_named_directly_is_still_reported_as_a_target(tmp_path: Path):
    """When a target is an ordinary filename (no wildcard) and that file doesn't actually exist,
    it is still returned as a target rather than being silently dropped -- so the caller can
    flag it as missing instead of pretending it was never asked for."""
    assert resolve_targets(tmp_path, "nope.md") == [tmp_path / "nope.md"]


def test_an_ordinary_filename_is_never_mistaken_for_a_wildcard_pattern(tmp_path: Path):
    """Only the special characters *, ?, and [ mark a target as a wildcard -- ordinary letters,
    even one like 'X' that resembles a pattern character, never do. A missing plain file is
    still reported as a target so the caller can flag it; a wildcard would have silently
    resolved to nothing instead."""
    assert resolve_targets(tmp_path, "Xnope.md") == [tmp_path / "Xnope.md"]


def test_every_shipped_skill_has_a_token_budget_check_configured(repo_root: Path):
    """Every skill that ships in the product must have a token-budget check covering it. The
    shared coverage pattern was narrowed to name files explicitly so one skill could be given a
    larger budget without loosening the limit for the rest -- this test fails if a new skill,
    or that narrowing, ends up leaving a skill with no budget check at all."""
    from tests.metrics.threshold_runner import load_thresholds

    checks = load_thresholds(repo_root / "tests" / "testdata" / "thresholds.json")
    covered: set[Path] = set()
    for check in checks:
        if check.metric == "token_count":
            covered.update(resolve_targets(repo_root, check.target))

    skills = set((repo_root / "dist" / "claude-code" / "skills").glob("*/SKILL.md"))
    missing = skills - covered
    assert not missing, \
        f"skills with no token-budget row: {sorted(str(m.relative_to(repo_root)) for m in missing)}"
