"""Tests that verify plugin file hygiene and shared settings correctness."""

import json
import warnings
import re
from pathlib import Path

import pytest

from tests.metrics.threshold_runner import load_thresholds, run_threshold_checks
from tests.metrics.token_counter import count_tokens


_CONTENT_DIRS = ["dist/claude-code/commands", "dist/claude-code/agents", "dist/claude-code/skills"]
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
    # warn_at exists to give a pre-limit signal — surface it, or it is a dead feature.
    for r in results:
        if r.near_warn:
            warnings.warn(f"approaching budget limit: {r.message}", stacklevel=1)


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
    plugin_json = repo_root / "dist" / "claude-code" / ".claude-plugin" / "plugin.json"

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
    """dist/claude-code/.claude-plugin/plugin.json must be valid JSON and carry the required metadata."""
    # Given
    scoped = repo_root / "dist" / "claude-code" / ".claude-plugin" / "plugin.json"

    # When
    data = json.loads(scoped.read_text())

    # Then
    for required in ["name", "version", "description", "author"]:
        assert required in data and data[required], (
            f"plugin-scoped manifest missing required field: {required}"
        )


def test_no_shipped_artifact_references_agent_teams(repo_root):
    """No shipped plugin artifact may depend on the experimental agent-teams flag.

    Hercules' debates are orchestrator-mediated (sub-agents spawned via the Agent/Task tool and
    relayed between rounds), which needs no flag — so the shipped plugin must not reference it.
    """
    # Given
    flag = "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"
    plugin_dir = repo_root / "dist" / "claude-code"
    offenders = []

    # When
    for path in plugin_dir.rglob("*"):
        if path.is_file() and path.suffix in {".md", ".json"} and flag in path.read_text(errors="ignore"):
            offenders.append(str(path.relative_to(repo_root)))

    # Then
    assert not offenders, f"shipped plugin artifacts must not reference {flag}: {offenders}"


def test_plugin_permissions_section_exists_in_readme(read_file):
    """README must have a Plugin permissions section documenting all four capability areas."""
    content = read_file("README.md")
    assert "## Plugin permissions" in content, "README must have a '## Plugin permissions' section"
    assert "~/.hercules/" in content, "Plugin permissions must document the ~/.hercules/ write location"
    assert "no credentials" in content.lower(), "Plugin permissions must state no credentials are stored"
    assert "no direct api calls" in content.lower() or "no separate network channel" in content.lower(), \
        "Plugin permissions must state no direct API calls or separate network channel"


def test_plugin_files_claim_no_external_network_calls(repo_root):
    """No plugin Markdown file should claim to make direct API calls or open external network channels."""
    for path in (repo_root / "dist" / "claude-code").rglob("*.md"):
        content = path.read_text(encoding="utf-8").lower()
        assert "direct api call" not in content, f"{path} claims direct API calls"
        assert "external network channel" not in content, f"{path} claims external network channel"


def test_plugin_only_external_write_location_is_hercules_dir(repo_root, read_file):
    """The Plugin permissions section must name ~/.hercules/ as the ONLY external home-dir write location.

    Scoped to the '## Plugin permissions' section only — the rest of the README legitimately mentions
    ~/.claude/settings.json (documenting Claude Code's own config location), which must not be flagged.
    """
    readme = read_file("README.md")
    claude_md = read_file("dist/claude-code/CLAUDE.md").lower()
    assert "~/.hercules/" in readme.lower(), "README must document the ~/.hercules/ write location"
    assert "~/.hercules/" in claude_md, "dist/claude-code/CLAUDE.md must reference ~/.hercules/"

    match = re.search(r"## Plugin permissions\n(.*?)(?=\n## |\Z)", readme, re.DOTALL)
    assert match, "README must contain a '## Plugin permissions' section"
    perms_section = match.group(1).lower()

    home_writes = re.findall(r"~/\.[a-z][a-z0-9_-]+/", perms_section)
    assert all(p == "~/.hercules/" for p in home_writes), (
        f"Plugin permissions section references unexpected home-dir locations: "
        f"{set(home_writes) - {'~/.hercules/'}}"
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
