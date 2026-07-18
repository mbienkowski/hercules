"""Spec 06 — a live Claude Code CLI smoke check: does the built plugin actually install and
register with the real tool, not just look correct on disk?

Every other test in this suite checks that the shipped markdown/JSON is well-formed and says
the right things. None of them prove the `claude` binary itself can install this plugin from a
local checkout and see its skills, agents, and hooks — that's exactly the gap RELEASE.md's manual
smoke checklist exists to cover today. These tests replace the structural half of that checklist
(the "does it load and register" half) with a fast, free check: `claude plugin validate/
marketplace/install/list/details` are documented as local, schema/config-only operations that
spend no tokens and need no login. The behavioral half (does hercules answer in character, does
a specialist actually spawn) still needs a live, paid session and stays a manual release-time
check.

Every `claude` subprocess call runs in an isolated $HOME (never the real developer's ~/.claude)
with auto-update and telemetry explicitly disabled, so this can't hang on a background network
call and can't pollute a maintainer's real plugin config when run locally via `make test-smoke`.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN = REPO_ROOT / "dist" / "claude-code"
MARKETPLACE_NAME = json.loads((REPO_ROOT / ".claude-plugin" / "marketplace.json").read_text())["name"]
PLUGIN_ID = f"hercules@{MARKETPLACE_NAME}"

pytestmark = pytest.mark.skipif(shutil.which("claude") is None, reason="claude CLI not available")

# No CI runner should ever be waiting more than this for a purely-local, no-network command.
_TIMEOUT = 30


@pytest.fixture
def isolated_claude_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A scratch $HOME so these tests can never touch a real developer's ~/.claude config,
    and can never block on the auto-updater or telemetry reaching out over the network."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("DISABLE_AUTOUPDATER", "1")
    monkeypatch.setenv("CLAUDE_CODE_ENABLE_TELEMETRY", "0")
    return home


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["claude", *args], capture_output=True, text=True, timeout=_TIMEOUT, cwd=REPO_ROOT,
    )


def test_the_built_plugin_manifest_validates_without_errors(isolated_claude_home):
    """The built dist/claude-code plugin must pass Claude Code's own manifest validator — the
    same check the plugin marketplace review pipeline runs on every submission — so a structural
    mistake (a malformed plugin.json, a broken agent/command/skill frontmatter field) is caught
    in seconds, before a user ever tries to install a broken plugin."""
    res = _run("plugin", "validate", str(PLUGIN))
    assert res.returncode == 0, f"stdout={res.stdout}\nstderr={res.stderr}"


def test_the_marketplace_manifest_validates_without_errors(isolated_claude_home):
    """The repo's own marketplace.json — the file a user's `claude plugin marketplace add`
    actually reads — must also pass validation on its own, independent of the plugin manifest
    check above; a marketplace-level mistake (bad source path, malformed plugin entry) would
    otherwise only surface as a confusing install failure for a real user."""
    res = _run("plugin", "validate", str(REPO_ROOT))
    assert res.returncode == 0, f"stdout={res.stdout}\nstderr={res.stderr}"


def test_the_plugin_installs_from_a_local_checkout_and_shows_up_enabled(isolated_claude_home):
    """A developer installing straight from a cloned checkout (the exact flow documented in
    CONTRIBUTING.md: marketplace add, then install) must end up with the plugin actually listed
    and enabled -- not just a silent no-op -- since this local-install path is how every
    contributor and CI smoke check exercises the plugin before it ever reaches a real
    marketplace."""
    add = _run("plugin", "marketplace", "add", "./")
    assert add.returncode == 0, f"stdout={add.stdout}\nstderr={add.stderr}"

    install = _run("plugin", "install", PLUGIN_ID)
    assert install.returncode == 0, f"stdout={install.stdout}\nstderr={install.stderr}"

    listed = _run("plugin", "list", "--json")
    assert listed.returncode == 0, f"stdout={listed.stdout}\nstderr={listed.stderr}"
    plugins = json.loads(listed.stdout)
    entry = next((p for p in plugins if p["id"] == PLUGIN_ID), None)
    assert entry is not None, f"{PLUGIN_ID} not found in `claude plugin list --json`: {plugins}"
    assert entry["enabled"] is True


def test_the_installed_plugin_declares_its_full_component_inventory(
    isolated_claude_home, skill_files, agent_files, command_files,
):
    """Once installed, Claude Code's own component inventory for this plugin must list every
    skill, command, and agent actually shipped on disk -- not a stale or partial subset -- so a
    user browsing `claude plugin details` sees the real toolset they're about to load into every
    session, matching exactly what the repo ships (derived from the real file counts, not a
    magic number that would silently go stale). Claude Code's own "Skills" inventory line counts
    both SKILL.md files and slash commands together -- a real, confirmed categorization detail of
    the CLI's own vocabulary, not a bug in this repo's skills/ vs commands/ split."""
    _run("plugin", "marketplace", "add", "./")
    _run("plugin", "install", PLUGIN_ID)

    details = _run("plugin", "details", PLUGIN_ID)
    assert details.returncode == 0, f"stdout={details.stdout}\nstderr={details.stderr}"

    skills_line = next(ln for ln in details.stdout.splitlines() if ln.strip().startswith("Skills"))
    agents_line = next(ln for ln in details.stdout.splitlines() if ln.strip().startswith("Agents"))
    assert f"({len(skill_files) + len(command_files)})" in skills_line, skills_line
    assert f"({len(agent_files)})" in agents_line, agents_line
    assert "hercules" in agents_line
