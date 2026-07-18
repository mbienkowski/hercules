"""Spec 04 — cutover guards: no raw plugin/ path literals, marketplace resolves, drift gate, mutmut target.

Frozen for spec-04-atomic-cutover.
"""
import json
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
# Path-literal patterns that reach the retired plugin/ tree (NOT `.claude-plugin/`, `plugin.json`,
# the `plugin_root` fixture name, or the prose "Claude Code plugin").
_RAW_PLUGIN = re.compile(r'parents\[\d+\]\s*/\s*["\']plugin["\']|/\s*["\']plugin["\']\s*/')
# Markdown reference to the retired `plugin/` tree. The lookbehind excludes the legitimate
# `.claude-plugin/` (and `opencode-plugin/`) — a bare `plugin/` segment is the retired path.
_RETIRED_PLUGIN_MD = re.compile(r"(?<![-.\w])plugin/")
# Generated / not-authored-here markdown the guard must not police.
_MD_GUARD_SKIP = {"CHANGELOG.md"}


def test_source_files_never_hardcode_a_path_into_the_retired_plugin_folder():
    """No test or script file (other than the shared setup file) may hard-code a path segment
    pointing into the old plugin/ folder layout that was retired during the migration. If one
    slipped back in, that test or script would silently point at files that no longer exist."""
    offenders = []
    for py in list((REPO_ROOT / "tests").rglob("*.py")) + list((REPO_ROOT / "scripts").rglob("*.py")):
        if py.name == "conftest.py":
            continue
        for i, line in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
            if _RAW_PLUGIN.search(line):
                offenders.append(f"{py.relative_to(REPO_ROOT)}:{i}")
    assert offenders == [], f"raw plugin/ path literals (retired tree): {offenders}"


def test_project_documentation_never_points_readers_to_the_retired_plugin_folder():
    """Every markdown file checked into the repository (excluding generated files such as the
    changelog) must reference the current src/ plus dist/ layout, not the old plugin/ folder
    that was retired. A stray reference would send contributors looking for files in a place
    that no longer exists."""
    # Contributor-facing docs must point at the src/+dist/ layout, not the retired flat `plugin/` tree.
    # git-tracked only (so the gitignored root CLAUDE.md is never swept); .claude-plugin/ is excluded
    # by the pattern's lookbehind.
    tracked = subprocess.run(
        ["git", "ls-files", "*.md"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout.split()
    offenders = []
    for rel in tracked:
        if Path(rel).name in _MD_GUARD_SKIP:
            continue
        for i, line in enumerate((REPO_ROOT / rel).read_text(encoding="utf-8").splitlines(), 1):
            if _RETIRED_PLUGIN_MD.search(line):
                offenders.append(f"{rel}:{i}: {line.strip()[:100]}")
    assert offenders == [], "retired plugin/ tree referenced in tracked markdown:\n" + "\n".join(offenders)


def test_shared_test_setup_points_at_the_shipped_claude_code_tree():
    """The shared test setup helper must resolve its artifact root to the built dist/claude-code
    output rather than some stale or alternate location, since every test relying on that helper
    depends on it finding the actual shipped files."""
    # Positive companion: the shared fixture points at the shipped Claude tree.
    src = (REPO_ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    assert 'repo_root / "dist" / "claude-code"' in src


def test_marketplace_listing_points_to_a_plugin_that_actually_exists():
    """The hercules entry in the marketplace catalog must point at a folder that contains a real
    plugin manifest. If that listed source were wrong or stale, anyone installing hercules from
    the marketplace would end up with a broken or missing plugin."""
    mk = json.loads((REPO_ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    entry = next(p for p in mk["plugins"] if p["name"] == "hercules")
    source = REPO_ROOT / entry["source"]
    assert (source / ".claude-plugin" / "plugin.json").is_file(), \
        f"marketplace source {entry['source']} must resolve to a plugin.json"


def test_mutation_testing_targets_the_current_hooks_location_not_the_retired_one():
    """The mutation-testing configuration must scan the hooks code at its current, migrated
    location and must not still reference the old, retired location. Otherwise mutation testing
    would silently exercise the wrong (or no longer existing) files, giving false confidence in
    how well the real hooks code is covered."""
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "src/targets/claude-code/hooks/" in pyproject
    assert "plugin/hooks/" not in pyproject

