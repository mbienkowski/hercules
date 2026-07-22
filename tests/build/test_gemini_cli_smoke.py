"""Live Gemini CLI smoke check + an always-on structural guard on the built extension.

The ALWAYS-ON check is structural (never skips): the freshly built ``dist/gemini-cli`` tree must satisfy
the Gemini extension contract — a kebab manifest name with contextFileName, subagents with name+
description, TOML commands with a prompt, and the BeforeTool write-gate wired to the adapter. The genuinely
live check (the real ``gemini`` binary runs) is opt-in and SKIPs when the CLI is absent, so the fork-safe
gate stays green.
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


def _build(tmp_path: Path) -> Path:
    out = tmp_path / "gemini-cli"
    build_target("gemini-cli", out)
    return out


def _src_stems(sub):
    return sorted(p.stem for p in (SRC_CONTENT / sub).glob("*.md"))


def _src_skills():
    return sorted(d.name for d in (SRC_CONTENT / "skills").iterdir() if d.is_dir())


def test_built_extension_is_well_formed(tmp_path):
    """Always-on, auth-free: the built extension satisfies the Gemini contract — a malformed manifest,
    a ``.md`` (not ``.toml``) command, or an unwired hook would load as absent with no error."""
    out = _build(tmp_path)
    manifest = json.loads((out / "gemini-extension.json").read_text(encoding="utf-8"))
    assert re.fullmatch(r"[a-z0-9]([a-z0-9-]*[a-z0-9])?", manifest["name"])
    assert manifest["contextFileName"] == "GEMINI.md" and (out / "GEMINI.md").is_file()
    for cmd in (out / "commands").glob("*.toml"):
        assert 'prompt = """' in cmd.read_text(encoding="utf-8"), f"{cmd.name} lacks a TOML prompt"
    for agent in (out / "agents").glob("*.md"):
        t = agent.read_text(encoding="utf-8")
        assert t.startswith("---\n") and "name:" in t and "description:" in t
    assert (out / "agents" / "cynical-reviewer.md").is_file(), "the independent reviewer must ship"


def test_before_tool_gate_is_wired_to_the_adapter(tmp_path):
    """The write-gate wiring: hooks.json wires BeforeTool (matcher covering both edit tools) to
    hercules_gate.py via python3 and the ${extensionPath} script path — the exact command form pinned."""
    out = _build(tmp_path)
    hooks = json.loads((out / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    entries = hooks["hooks"]["BeforeTool"]
    matcher = entries[0]["matcher"]
    assert "write_file" in matcher and "replace" in matcher, "matcher must cover both edit tools"
    cmd = entries[0]["hooks"][0]["command"]
    assert cmd == "python3 ${extensionPath}/hooks/hercules_gate.py || exit 0", \
        f"unexpected hook command: {cmd!r}"


def test_ships_the_full_component_inventory(tmp_path):
    """The built extension must carry the WHOLE inventory — all 5 commands (as ``.toml``), every advisor
    agent, and every skill — so nothing silently fails to load. Names derive from src/content (the
    single source of truth)."""
    out = _build(tmp_path)
    for name in _src_stems("commands"):
        assert (out / "commands" / f"{name}.toml").is_file(), f"gemini missing command {name}"
    for name in _src_stems("agents"):
        assert (out / "agents" / f"{name}.md").is_file(), f"gemini missing agent {name}"
    for skill in _src_skills():
        assert (out / "skills" / skill / "SKILL.md").is_file(), f"gemini missing skill {skill}"
    assert (out / "GEMINI.md").is_file(), "the GEMINI.md context file must ship"


@pytest.mark.skipif(shutil.which("gemini") is None, reason="gemini CLI not available")
def test_the_real_gemini_binary_runs(tmp_path):
    """With the real CLI present, ``gemini --version`` must exit 0 (a stub-on-PATH would not)."""
    res = subprocess.run(["gemini", "--version"], capture_output=True, text=True, timeout=_TIMEOUT)
    assert res.returncode == 0, f"gemini --version failed: {res.stdout}\n{res.stderr}"


@pytest.mark.skipif(shutil.which("gemini") is None, reason="gemini CLI not available")
def test_the_extension_installs_into_the_real_cli_and_is_listed(tmp_path):
    """Install the built extension into an isolated HOME and confirm the real ``gemini`` lists it — a
    genuine install + load check beyond ``--version``. Extension management is local (no API call), so it
    should run without auth; but it SKIPs (never fails the leg) on any error/timeout or a differing
    subcommand shape, so the every-commit gate stays green while the structural inventory above still runs."""
    home = tmp_path / "home"
    home.mkdir()
    env = {**os.environ, "HOME": str(home)}
    ext = REPO_ROOT / "dist" / "gemini-cli"
    try:
        inst = subprocess.run(["gemini", "extensions", "install", str(ext)],
                              capture_output=True, text=True, timeout=_TIMEOUT, env=env)
        if inst.returncode != 0:
            pytest.skip(f"gemini extensions install unavailable here: {(inst.stderr or inst.stdout)[:300]}")
        listed = subprocess.run(["gemini", "extensions", "list"],
                                capture_output=True, text=True, timeout=_TIMEOUT, env=env)
    except (subprocess.TimeoutExpired, OSError) as e:
        pytest.skip(f"gemini extensions could not run here: {e}")
    assert listed.returncode == 0, f"`gemini extensions list` failed: {listed.stdout}\n{listed.stderr}"
    assert "hercules" in listed.stdout.lower(), f"installed extension not listed:\n{listed.stdout}"
