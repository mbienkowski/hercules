"""The CI smoke matrix (scripts/ci/smoke_matrix.py) — the fork-safety + registry-drift gate.

A non-npm (curl-installed) CLI runs unpinned remote code, so its leg must appear ONLY on main, never
on a fork PR; the npm legs run everywhere. This pins that decision so a regression can't silently
either (a) run the curl installer on an untrusted fork runner, or (b) drop the npm smoke legs.

The matrix derives from the build's target registry (the single source of truth), so it also fails
closed on drift: a registered ecosystem missing its smoke.json, or a smoke.json for an unregistered
ecosystem, is a hard error — never a silently-skipped (== green) leg.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from scripts.ci import smoke_matrix
from scripts.ci.smoke_matrix import build_matrix

CI = (Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")


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


def test_the_matrix_targets_come_from_the_build_registry(monkeypatch):
    """The smoke legs are exactly the registered ecosystems (single source of truth), not an
    independently-maintained list that could drift from what actually ships."""
    from scripts.build.targets import registered_target_names
    legs = _targets({"GITHUB_REF": "refs/heads/main"}, monkeypatch)
    assert set(legs) == set(registered_target_names())


def test_a_registered_ecosystem_missing_its_smoke_json_fails_closed(monkeypatch):
    """A registered ecosystem with no smoke.json is untestable — the matrix must error, not silently
    ship a leg-less (== green) gate for it."""
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    monkeypatch.setattr(smoke_matrix, "registered_target_names",
                        lambda: ["claude-code", "opencode", "cursor", "ghost-ecosystem"])
    with pytest.raises(SystemExit, match="no smoke.json"):
        build_matrix()


def test_a_smoke_json_for_an_unregistered_ecosystem_fails_closed(monkeypatch):
    """A smoke.json whose ecosystem is not registered is a phantom leg — the matrix must error rather
    than smoke-test a target the build never produces."""
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    monkeypatch.setattr(smoke_matrix, "registered_target_names", lambda: ["claude-code", "opencode"])
    with pytest.raises(SystemExit, match="unregistered ecosystems"):
        build_matrix()  # cursor/smoke.json exists on disk but cursor is not in the (mocked) registry


# ── CI gating graph (Spec 07): smoke is a peer; mutation waits for ALL three to SUCCEED ──
def test_smoke_is_a_peer_of_test_and_validate():
    """Smoke fans out right after build (needs only build), not gated behind the unit suite."""
    assert re.search(r"^  smoke:\n(?:.*\n)*?    needs:\s*\[build\]\s*$", CI, re.MULTILINE), \
        "smoke must need only [build] (peer of test/validate)"


def test_mutation_waits_for_test_validate_and_smoke():
    """The 40-min job must not start until all three quick gates are present as needs."""
    m = re.search(r"^  mutation:\n(?:.*\n)*?    needs:\s*\[([^\]]*)\]", CI, re.MULTILINE)
    assert m and {"test", "validate", "smoke"} <= {x.strip() for x in m.group(1).split(",")}, \
        "mutation must need test, validate, and smoke"


def test_mutation_if_explicitly_checks_each_need_succeeded():
    """A custom `if:` REPLACES the implicit `if: success()`, so gating on needs requires spelling out
    the success checks — otherwise mutation would launch even when a need failed."""
    for job in ("test", "validate", "smoke"):
        assert f"needs.{job}.result == 'success'" in CI, \
            f"mutation.if must require needs.{job}.result == 'success'"


def test_there_is_no_separate_discover_job():
    """The smoke matrix is a build output; a standalone discovery node would be a second source of
    truth to drift out of sync."""
    assert not re.search(r"^  discover:\s*$", CI, re.MULTILINE), "the discover job should be gone"
