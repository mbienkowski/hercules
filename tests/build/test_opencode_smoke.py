"""Spec 06 — a live OpenCode CLI smoke check: does the built plugin actually load in the real
tool, not just in a Node `require()` probe?

`test_opencode_entrypoint.py` proves the generated plugin.js is internally self-consistent
(config() populates the right agent/command/skill counts) by requiring it directly in Node. That
is NOT the same as proving OpenCode's own plugin loader accepts the file. It didn't, twice over:
manually installing the real `opencode-ai` CLI and pointing it at this repo's built plugin.js
reproduced two real, reproducible failures the Node-based probe could not see --
https://github.com/mbienkowski/hercules/issues/15 has the full root-cause diagnosis for both:

1. "Plugin export is not a function" -- Node's CJS/ESM interop for a bare
   `module.exports = <function>` differs from Bun's (which is what the real `opencode` binary is
   compiled with): Bun spreads the function's own `length`/`name` properties into the imported
   module's namespace, and the loader throws on the first one that isn't a valid plugin export.
2. Once fixed to export `{ server: fn }` instead, a second, previously-unknown failure surfaced
   only by running the real binary: "must export id" -- a path-installed plugin also requires a
   top-level `id` field that the Node probe never exercised.

Both are now fixed in `src/ecosystems/opencode.template.plugin.js` (exports
`{ id: "hercules", server: fn }`), verified against the real installed `opencode` binary before
this test's `xfail` marker was removed.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.build.cli import build_target

REPO_ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.skipif(shutil.which("opencode") is None, reason="opencode CLI not available")

# 60s (matching the cursor/gemini/copilot smoke legs): a cold `opencode agent list` warms the Bun
# runtime and loads the plugin on first invocation, which can exceed a tight 30s on a loaded CI runner
# (a real timeout there was a flake, not a plugin defect — the built bytes are drift-gate-pinned).
_TIMEOUT = 60


@pytest.fixture
def opencode_project_with_plugin_installed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A scratch OpenCode project with a freshly-built plugin.js placed exactly where OpenCode's
    own load-order convention expects it -- the project-level `plugins` folder under the hidden
    OpenCode config directory; OpenCode has no flag to load an arbitrary path, unlike Claude Code
    -- and an isolated config/cache home so this can never touch a real developer's OpenCode
    setup."""
    out = tmp_path / "opencode-dist"
    build_target("opencode", out)

    project = tmp_path / "project"
    plugins_dir = project / ".opencode" / "plugins"
    plugins_dir.mkdir(parents=True)
    (plugins_dir / "hercules.js").symlink_to(out / "plugin.js")

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(home / ".cache"))
    return project


def test_the_real_opencode_cli_loads_the_plugin_and_lists_its_agents(opencode_project_with_plugin_installed):
    """Running the actual `opencode` binary against a project with this plugin installed must
    successfully list hercules among the available agents -- proving the plugin loads the way a
    real user's OpenCode session would load it, not just the way a Node script loading its JS
    module directly would."""
    res = subprocess.run(
        ["opencode", "agent", "list"],
        capture_output=True, text=True, timeout=_TIMEOUT,
        cwd=opencode_project_with_plugin_installed,
    )
    assert res.returncode == 0, f"stdout={res.stdout}\nstderr={res.stderr}"
    # A loose "hercules" substring check would trivially pass on skill-path noise alone (every
    # agent's permission dump references the shipped `hercules-reference` skill path); only a
    # line naming the agent itself proves it actually registered.
    agent_lines = [ln.strip() for ln in res.stdout.splitlines() if ln.strip().lower().startswith("hercules ")]
    assert agent_lines, f"no 'hercules' agent line in `opencode agent list` output:\n{res.stdout}"
