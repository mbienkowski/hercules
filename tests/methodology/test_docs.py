"""Docs match the shipped (marketplace) reality, and contributor rules are recorded (spec 04)."""

from __future__ import annotations

import json
import re


def test_readme_documents_marketplace_install(read_file):
    """README must document the native marketplace install path."""
    content = read_file("README.md")
    assert "/plugin marketplace add" in content, "README must show the marketplace-add command"
    assert "/plugin install" in content, "README must show the plugin-install command"


def test_readme_has_no_removed_cli_references(read_file):
    """README must not reference the removed auto-sync CLI surface."""
    content = read_file("README.md")
    for banned in ["install.sh", "--sync", "--branch ", "auto-sync", "every 30 min"]:
        assert banned not in content, f"README still references removed CLI surface: {banned!r}"


def test_code_of_conduct_whats_tested_rows_point_at_existing_files(repo_root, read_file):
    """Every test path named in CODE_OF_CONDUCT.md must exist (no stale 'what's covered' rows)."""
    content = read_file("CODE_OF_CONDUCT.md")
    referenced = set(re.findall(r"tests/[\w/]+\.py", content))
    missing = [p for p in referenced if not (repo_root / p).exists()]
    assert not missing, f"CODE_OF_CONDUCT.md references non-existent test files: {sorted(missing)}"


def test_code_of_conduct_states_contributor_invariants(read_file):
    """CODE_OF_CONDUCT.md must record the contributor invariants this migration relies on."""
    content = read_file("CODE_OF_CONDUCT.md").lower()
    assert "owning test" in content, "CoC must require every shipped artifact to have an owning test"
    assert "launcher" in content and "python" in content, \
        "CoC must record that the launcher is a Python module (so coverage + mutation see it)"
    assert "single source" in content or "single-source" in content, \
        "CoC must record version single-sourcing across pyproject and the plugin manifest"


def test_plugin_version_is_single_sourced(repo_root, read_file):
    """pyproject version must equal the shipped plugin manifest version (no drift)."""
    py = read_file("pyproject.toml")
    m = re.search(r'(?m)^version\s*=\s*"([^"]+)"', py)
    assert m, "pyproject.toml must declare a version"
    plugin_version = json.loads(
        (repo_root / "plugin" / ".claude-plugin" / "plugin.json").read_text()
    )["version"]
    assert m.group(1) == plugin_version, (
        f"version drift: pyproject {m.group(1)!r} != plugin manifest {plugin_version!r}"
    )


def test_plugin_claude_md_describes_a_plugin_not_a_wrapper(read_file):
    """plugin/CLAUDE.md must describe Hercules as a plugin, not a Python CLI wrapper."""
    content = read_file("plugin/CLAUDE.md")
    assert "Python wrapper for the `claude` CLI" not in content, \
        "plugin/CLAUDE.md must not call Hercules a Python wrapper for the claude CLI"
