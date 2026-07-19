"""The CI smoke matrix (scripts/ci/smoke_matrix.py) — the fork-safety gate.

A non-npm (curl-installed) CLI runs unpinned remote code, so its leg must appear ONLY on main, never
on a fork PR; the npm legs run everywhere. This pins that decision so a regression can't silently
either (a) run the curl installer on an untrusted fork runner, or (b) drop the npm smoke legs.
"""
from __future__ import annotations

import pytest

from scripts.ci.smoke_matrix import build_matrix


def _targets(env, monkeypatch):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    legs = build_matrix()["include"]
    return {leg["target"]: leg for leg in legs}


def test_fork_pr_runs_npm_legs_but_not_the_curl_installed_cursor_leg(monkeypatch):
    """On a fork PR (ref is not main), the script-install (curl) Cursor leg is excluded while the
    pinned npm legs still run — the curl installer never executes on an untrusted runner."""
    legs = _targets({"GITHUB_REF": "refs/pull/1/merge"}, monkeypatch)
    assert "claude-code" in legs and "opencode" in legs, "npm smoke legs must run on every PR"
    assert "cursor" not in legs, "the curl-installed cursor leg must be main-only"


def test_main_includes_every_ecosystem_including_the_script_installed_one(monkeypatch):
    """On main (a trusted runner) every ecosystem runs, including the script-install Cursor leg."""
    legs = _targets({"GITHUB_REF": "refs/heads/main"}, monkeypatch)
    assert {"claude-code", "opencode", "cursor"} <= set(legs)
    assert legs["cursor"]["install_method"] == "script"
    assert legs["claude-code"]["install_method"] == "npm"


def test_every_leg_carries_the_fields_the_install_and_run_scripts_read(monkeypatch):
    """install_cli.sh / run_smoke.sh read these keys from the matrix; a missing one breaks the leg."""
    legs = _targets({"GITHUB_REF": "refs/heads/main"}, monkeypatch)
    for leg in legs.values():
        assert set(leg) >= {"target", "cli", "test", "install_method"}
