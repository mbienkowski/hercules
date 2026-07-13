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


def test_plugin_js_loads_and_registers_the_full_roster(tmp_path):
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


def test_plugin_js_asserts_missing_assets(tmp_path):
    # The generated entry throws if its sibling assets are absent (depth-independent PLUGIN_ROOT).
    out = tmp_path / "opencode"
    build_target("opencode", out)
    (out / "instructions.md").unlink()
    res = subprocess.run(["node", "-e", f"require({json.dumps(str(out / 'plugin.js'))})()"],
                         capture_output=True, text=True)
    assert res.returncode != 0 and "missing asset" in res.stderr
