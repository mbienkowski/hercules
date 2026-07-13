"""Spec 04 — cutover guards: no raw plugin/ path literals, marketplace resolves, drift gate, mutmut target.

Frozen for spec-04-atomic-cutover.
"""
import json
import re
from pathlib import Path

from scripts.build import cli

REPO_ROOT = Path(__file__).resolve().parents[2]
# Path-literal patterns that reach the retired plugin/ tree (NOT `.claude-plugin/`, `plugin.json`,
# the `plugin_root` fixture name, or the prose "Claude Code plugin").
_RAW_PLUGIN = re.compile(r'parents\[\d+\]\s*/\s*["\']plugin["\']|/\s*["\']plugin["\']\s*/')


def test_no_raw_plugin_path_literal_outside_conftest():
    offenders = []
    for py in list((REPO_ROOT / "tests").rglob("*.py")) + list((REPO_ROOT / "scripts").rglob("*.py")):
        if py.name == "conftest.py":
            continue
        for i, line in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
            if _RAW_PLUGIN.search(line):
                offenders.append(f"{py.relative_to(REPO_ROOT)}:{i}")
    assert offenders == [], f"raw plugin/ path literals (retired tree): {offenders}"


def test_conftest_resolves_the_artifact_root_once():
    # Positive companion: the shared fixture points at the shipped Claude tree.
    src = (REPO_ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    assert 'repo_root / "dist" / "claude-code"' in src


def test_marketplace_source_resolves_to_a_real_plugin_manifest():
    mk = json.loads((REPO_ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    entry = next(p for p in mk["plugins"] if p["name"] == "hercules")
    source = REPO_ROOT / entry["source"]
    assert (source / ".claude-plugin" / "plugin.json").is_file(), \
        f"marketplace source {entry['source']} must resolve to a plugin.json"


def test_mutmut_targets_the_migrated_hooks_source():
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "src/targets/claude-code/hooks/" in pyproject
    assert "plugin/hooks/" not in pyproject


def test_build_check_detects_stale_committed_dist(tmp_path, monkeypatch):
    committed = tmp_path / "claude-code"
    cli.build_target("claude-code", committed)
    (committed / "CLAUDE.md").write_text("STALE", encoding="utf-8")  # simulate un-rebuilt drift
    monkeypatch.setattr(cli, "DIST", tmp_path)
    assert cli.check_target("claude-code") == 1
