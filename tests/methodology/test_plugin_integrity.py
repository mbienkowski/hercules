"""Tests that verify plugin file hygiene and shared settings correctness."""

import json
import re
from pathlib import Path

import pytest

from hercules.methodology.threshold_runner import load_thresholds, run_threshold_checks
from hercules.methodology.token_counter import count_tokens


_CONTENT_DIRS = ["plugin/commands", "plugin/agents", "plugin/skills"]
_LOWERCASE_EXCEPT = {"SKILL.md"}


def _walk_markdown(repo_root: Path):
    """Yield all markdown files under commands/, agents/, skills/."""
    for d in _CONTENT_DIRS:
        base = repo_root / d
        if base.exists():
            yield from base.rglob("*.md")


def test_all_token_budgets_are_within_defined_limits(repo_root):
    """All token-budget threshold checks in thresholds.json must pass against the current files."""
    # Given
    threshold_file = repo_root / "tests" / "testdata" / "thresholds.json"
    checks = load_thresholds(threshold_file)

    # When
    results = run_threshold_checks(repo_root, checks)

    # Then
    failures = [r for r in results if not r.passed and r.severity == "gate"]
    assert not failures, "Token budget gate failures:\n" + "\n".join(
        f"  {r.message}" for r in failures
    )


def test_plugin_files_all_use_lowercase_names(repo_root):
    """Lowercase filenames ensure cross-platform compatibility (Linux is case-sensitive)."""
    # Given
    violations = []

    # When
    for path in _walk_markdown(repo_root):
        name = path.name
        if name in _LOWERCASE_EXCEPT:
            continue
        if name != name.lower():
            violations.append(str(path.relative_to(repo_root)))

    # Then
    assert not violations, f"Uppercase filenames found (will fail to load on Linux): {violations}"


def test_no_empty_placeholder_files_exist_in_plugin(repo_root):
    """Every plugin markdown file must open with a frontmatter block or heading — not a bare stub."""
    # Given
    bare_files = []

    # When
    for path in _walk_markdown(repo_root):
        content = path.read_text()
        if not content.strip():
            bare_files.append(str(path.relative_to(repo_root)) + " (empty)")
            continue
        first_line = content.lstrip().splitlines()[0]
        if not (first_line.startswith("---") or first_line.startswith("#")):
            bare_files.append(str(path.relative_to(repo_root)) + " (no frontmatter/heading)")

    # Then
    assert not bare_files, "Plugin markdown files with insufficient structure:\n" + \
        "\n".join(f"  {f}" for f in bare_files)


def test_plugin_json_has_all_required_metadata_fields(repo_root):
    """plugin.json must be valid JSON with name, version, description, and author fields."""
    # Given
    plugin_json = repo_root / ".claude-plugin" / "plugin.json"

    # When
    fields = json.loads(plugin_json.read_text())

    # Then
    for required in ["name", "version", "description", "author"]:
        assert required in fields and fields[required], (
            f"plugin.json missing required field: {required}"
        )


def test_marketplace_manifest_lists_the_hercules_plugin(repo_root):
    """marketplace.json must list the hercules plugin with a source that resolves to a plugin manifest."""
    # Given
    marketplace = repo_root / ".claude-plugin" / "marketplace.json"

    # When
    data = json.loads(marketplace.read_text())

    # Then
    assert data.get("name"), "marketplace.json missing 'name'"
    plugins = data.get("plugins") or []
    entry = next((p for p in plugins if p.get("name") == "hercules"), None)
    assert entry is not None, "marketplace.json does not list a plugin named 'hercules'"
    source = entry.get("source", "")
    assert source, "hercules plugin entry missing 'source'"
    source_dir = (repo_root / source).resolve()
    assert (source_dir / ".claude-plugin" / "plugin.json").is_file(), (
        f"marketplace source {source!r} must resolve to a dir containing .claude-plugin/plugin.json"
    )


def test_plugin_scoped_manifest_exists_with_metadata(repo_root):
    """plugin/.claude-plugin/plugin.json must be valid, carry required metadata, and match the root version."""
    # Given
    scoped = repo_root / "plugin" / ".claude-plugin" / "plugin.json"
    root = repo_root / ".claude-plugin" / "plugin.json"

    # When
    data = json.loads(scoped.read_text())
    root_data = json.loads(root.read_text())

    # Then
    for required in ["name", "version", "description", "author"]:
        assert required in data and data[required], (
            f"plugin-scoped manifest missing required field: {required}"
        )
    assert data["version"] == root_data["version"], (
        f"plugin-scoped version {data['version']!r} != root manifest version {root_data['version']!r}"
    )


def test_agent_teams_feature_is_switched_on_in_shared_settings(repo_root):
    """CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 must be set — it enables multi-agent debates."""
    # Given
    settings = json.loads((repo_root / ".claude" / "settings.json").read_text())

    # When
    value = settings.get("env", {}).get("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS")

    # Then
    assert value == "1", (
        f"expected CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 in .claude/settings.json, got {value!r}"
    )


def test_agent_frontmatter_name_uses_only_lowercase_characters(repo_root, agent_files):
    """Agent frontmatter `name:` values must be lowercase (used as URL-safe identifiers)."""
    # Given
    name_re = re.compile(r"(?m)^name:\s*(\S+)\s*$")
    violations = []

    # When
    for path in agent_files:
        m = name_re.search(path.read_text())
        if m and m.group(1) != m.group(1).lower():
            violations.append(f"{path.name}: name={m.group(1)!r}")

    # Then
    assert not violations, f"Agent frontmatter name fields with uppercase: {violations}"
