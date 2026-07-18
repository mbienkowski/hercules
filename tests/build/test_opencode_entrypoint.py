"""Spec 03 — the OpenCode plugin.js entry-point smoke (adapted from PR #11's node probe).

Counts are derived from the roster/config, not the magic 16/5 literals. Frozen for spec-03-opencode-target.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.build.cli import build_target

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not available")


def test_opencode_plugin_starts_up_with_every_agent_and_command_registered(tmp_path):
    """After building the OpenCode target, the generated plugin loads in OpenCode and registers
    every agent and command from the roster, with the default agent set to hercules -- so a
    user installing the OpenCode plugin gets the complete, correctly wired toolset, not a
    partial or stale one."""
    out = tmp_path / "opencode"
    build_target("opencode", out)
    n_agents = len(list((SRC / "content" / "agents").glob("*.md")))
    n_commands = len(list((SRC / "content" / "commands").glob("*.md")))

    probe = f"""
    const p = require({json.dumps(str(out / "plugin.js"))});
    p().then(r => {{ const cfg = {{}}; r.config(cfg);
      console.log(JSON.stringify({{
        default_agent: cfg.default_agent,
        instructions: cfg.instructions.length,
        skills: cfg.skills.paths.length,
        agents: Object.keys(cfg.agent).length,
        commands: Object.keys(cfg.command).length,
      }}));
    }}).catch(e => {{ console.error(String(e)); process.exit(1); }});
    """
    res = subprocess.run(["node", "-e", probe], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    emitted = json.loads(res.stdout.strip().splitlines()[-1])
    assert emitted["default_agent"] == "hercules"
    assert emitted["instructions"] >= 1 and emitted["skills"] >= 1
    assert emitted["agents"] == n_agents
    assert emitted["commands"] == n_commands


def test_opencode_plugin_refuses_to_start_if_its_bundled_files_are_missing(tmp_path):
    """If one of the files that must ship alongside the built OpenCode plugin (like the
    instructions file) is missing, the plugin fails to start with a clear error instead of
    silently running with incomplete instructions -- this holds no matter how deep the plugin
    is installed on disk, so a broken install is caught immediately rather than misbehaving
    quietly for the user."""
    out = tmp_path / "opencode"
    build_target("opencode", out)
    (out / "instructions.md").unlink()
    res = subprocess.run(["node", "-e", f"require({json.dumps(str(out / 'plugin.js'))})()"],
                         capture_output=True, text=True)
    assert res.returncode != 0 and "missing asset" in res.stderr
