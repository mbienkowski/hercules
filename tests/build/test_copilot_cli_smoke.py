"""Live Copilot CLI smoke check: does the real ``copilot`` binary run, and is the built plugin tree
structurally loadable?

The ALWAYS-ON check is structural (never skips): re-validate the built ``dist/copilot-cli`` plugin
against the plugin contract (kebab manifest name, per-type frontmatter, ``.agent.md`` agents,
``.prompt.md`` commands, the ``preToolUse`` write-gate, the reviewer subagent). The genuinely live check
(the real ``copilot`` binary executes) is opt-in — it SKIPs (never fails) when the CLI is not installed,
so the fork-safe gate stays green.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.build.cli import build_target

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_CONTENT = REPO_ROOT / "src" / "content"
_TIMEOUT = 60


def _src_stems(sub):
    return sorted(p.stem for p in (SRC_CONTENT / sub).glob("*.md"))


def _src_skills():
    return sorted(d.name for d in (SRC_CONTENT / "skills").iterdir() if d.is_dir())


def test_the_built_plugin_is_well_formed(tmp_path):
    """The freshly built plugin must satisfy the Copilot plugin contract — this is the load-bearing,
    auth-free, never-skipping guard (a malformed agent/command loads as absent with no error)."""
    out = tmp_path / "copilot-cli"
    build_target("copilot-cli", out)

    manifest = json.loads((out / "plugin.json").read_text(encoding="utf-8"))
    assert re.fullmatch(r"[a-z0-9]([a-z0-9-]*[a-z0-9])?", manifest["name"])

    def _fm(p: Path) -> str:
        t = p.read_text(encoding="utf-8")
        assert t.startswith("---\n"), f"{p.name} lacks frontmatter"
        return t

    for agent in (out / "agents").glob("*.agent.md"):
        t = _fm(agent)
        assert "name:" in t and "description:" in t
    for cmd in (out / "commands").glob("*.prompt.md"):
        assert "description:" in _fm(cmd)
    assert (out / "AGENTS.md").is_file(), "the persona instructions must ship"
    assert (out / "agents" / "cynical-reviewer.agent.md").is_file(), "the independent reviewer must ship"
    hooks = json.loads((out / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    assert hooks["hooks"]["preToolUse"], "the preToolUse write-gate must be wired"


def test_ships_the_full_component_inventory(tmp_path):
    """The built plugin must carry the WHOLE inventory — all 5 commands (as ``.prompt.md``), every advisor
    agent (as ``.agent.md``), and every skill — so nothing silently fails to load. Names derive from
    src/content (the single source of truth)."""
    out = tmp_path / "copilot-cli"
    build_target("copilot-cli", out)
    for name in _src_stems("commands"):
        assert (out / "commands" / f"{name}.prompt.md").is_file(), f"copilot missing command {name}"
    for name in _src_stems("agents"):
        assert (out / "agents" / f"{name}.agent.md").is_file(), f"copilot missing agent {name}"
    for skill in _src_skills():
        assert (out / "skills" / skill / "SKILL.md").is_file(), f"copilot missing skill {skill}"
    assert (out / "AGENTS.md").is_file(), "the AGENTS.md persona instructions must ship"


@pytest.mark.skipif(shutil.which("copilot") is None, reason="copilot CLI not available")
def test_the_real_copilot_binary_runs(tmp_path):
    """With the CLI installed, the real ``copilot --version`` must exit 0 (a stub-on-PATH would not)."""
    res = subprocess.run(["copilot", "--version"], capture_output=True, text=True, timeout=_TIMEOUT)
    assert res.returncode == 0, f"copilot --version failed: {res.stdout}\n{res.stderr}"


@pytest.mark.skipif(shutil.which("copilot") is None, reason="copilot CLI not available")
def test_the_plugin_installs_into_the_real_cli_and_is_listed(tmp_path):
    """Add the repo's local marketplace, install the plugin, then confirm the real ``copilot`` lists it —
    a genuine install + load check beyond ``--version``. Copilot plugin management may require a login,
    so it SKIPs (never fails the leg) on any error/timeout; the structural inventory above runs every
    commit regardless. If install+list DO succeed, the plugin MUST be listed (a real bug otherwise)."""
    home = tmp_path / "home"
    home.mkdir()
    env = {**os.environ, "HOME": str(home)}
    try:
        add = subprocess.run(["copilot", "plugin", "marketplace", "add", str(REPO_ROOT)],
                             capture_output=True, text=True, timeout=_TIMEOUT, env=env)
        if add.returncode != 0:
            pytest.skip(f"copilot marketplace add unavailable here: {(add.stderr or add.stdout)[:300]}")
        inst = subprocess.run(["copilot", "plugin", "install", "hercules@hercules"],
                              capture_output=True, text=True, timeout=_TIMEOUT, env=env)
        if inst.returncode != 0:
            pytest.skip(f"copilot plugin install unavailable here: {(inst.stderr or inst.stdout)[:300]}")
        listed = subprocess.run(["copilot", "plugin", "list"],
                                capture_output=True, text=True, timeout=_TIMEOUT, env=env)
    except (subprocess.TimeoutExpired, OSError) as e:
        pytest.skip(f"copilot plugin management could not run here: {e}")
    assert listed.returncode == 0, f"`copilot plugin list` failed: {listed.stdout}\n{listed.stderr}"
    assert "hercules" in listed.stdout.lower(), f"installed plugin not listed:\n{listed.stdout}"
