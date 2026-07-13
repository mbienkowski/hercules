"""Threshold runner — resolve_targets: glob, comma-separated, dedup, plain-path."""

from __future__ import annotations

from pathlib import Path

from tests.metrics.threshold_runner import resolve_targets


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


def test_resolve_targets_plain_path_returns_path_even_when_missing(tmp_path: Path):
    """A plain (non-glob) target resolves to its path even if the file is absent — not via glob."""
    assert resolve_targets(tmp_path, "nope.md") == [tmp_path / "nope.md"]


def test_plain_path_containing_x_is_not_treated_as_a_glob(tmp_path: Path):
    """Only *, ?, and [ mark a target as a glob — ordinary letters never do. A plain missing
    path resolves to itself (the caller reports it); a glob would silently resolve to []."""
    assert resolve_targets(tmp_path, "Xnope.md") == [tmp_path / "Xnope.md"]


def test_every_skill_has_a_token_budget_row(repo_root: Path):
    """Every shipped skill must be covered by a token_count threshold row. The shared skill glob
    was narrowed to explicit files so code-of-conduct-generator can carry a larger budget without
    loosening the others — this guard fails if a new skill (or that narrowing) leaves one uncovered."""
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
