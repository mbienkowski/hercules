"""Stage 5 — track the latest GitHub release tag instead of the moving `main`."""

from __future__ import annotations

import types
from unittest.mock import patch

import hercules.plugin_sync.git_sync as gs
from hercules.plugin_sync.git_sync import (
    SyncMode,
    _latest_release_tag,
    sync_plugin,
)


def _ok(stdout="", returncode=0):
    return types.SimpleNamespace(stdout=stdout, stderr=b"", returncode=returncode)


# ── _latest_release_tag (pure) ───────────────────────────────────────────────

def test_latest_tag_orders_numerically_not_lexically():
    out = "aaa\trefs/tags/v1.9.0\nbbb\trefs/tags/v1.10.0\n"
    assert _latest_release_tag(out) == "v1.10.0"


def test_latest_tag_ignores_non_semver():
    out = "aaa\trefs/tags/latest\nbbb\trefs/tags/v1.0.0\n"
    assert _latest_release_tag(out) == "v1.0.0"


def test_latest_tag_dedupes_peeled_refs():
    out = "aaa\trefs/tags/v1.0.0\naaa\trefs/tags/v1.0.0^{}\n"
    assert _latest_release_tag(out) == "v1.0.0"


def test_latest_tag_skips_prereleases():
    out = "aaa\trefs/tags/v2.0.0-rc1\nbbb\trefs/tags/v1.10.0\n"
    assert _latest_release_tag(out) == "v1.10.0"


def test_latest_tag_parses_bare_tag_list_format():
    # `git tag -l` output: one bare name per line.
    assert _latest_release_tag("v1.0.0\nv1.2.0\nv1.1.5\n") == "v1.2.0"


def test_latest_tag_returns_none_when_empty():
    assert _latest_release_tag("") is None


def test_latest_tag_returns_none_when_no_semver():
    assert _latest_release_tag("refs/tags/nightly\nrefs/tags/stable\n") is None


# ── _resolve_latest_release (ls-remote) ──────────────────────────────────────

def test_resolve_latest_release_returns_tag():
    with patch.object(gs.subprocess, "run", return_value=_ok(stdout="x\trefs/tags/v3.1.0\n")):
        assert gs._resolve_latest_release("https://example.com/r.git") == "v3.1.0"


def test_resolve_latest_release_none_when_no_tags():
    with patch.object(gs.subprocess, "run", return_value=_ok(stdout="")):
        assert gs._resolve_latest_release("https://example.com/r.git") is None


def test_resolve_latest_release_none_on_command_failure():
    with patch.object(gs.subprocess, "run", return_value=_ok(returncode=1)):
        assert gs._resolve_latest_release("https://example.com/r.git") is None


# ── clone path (release mode) ────────────────────────────────────────────────

def test_clone_release_mode_checks_out_latest_tag(tmp_path):
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return _ok()

    with patch.object(gs, "_resolve_latest_release", return_value="v1.4.2"), \
         patch.object(gs.subprocess, "run", side_effect=fake_run):
        sync_plugin(clone_root=tmp_path, repo_url="https://example.com/r.git",
                    mode=SyncMode.RELEASE)

    clone = next(c for c in calls if "clone" in c)
    assert "--branch" in clone and "v1.4.2" in clone


def test_clone_release_mode_falls_back_to_main_when_no_releases(tmp_path, capsys):
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return _ok()

    with patch.object(gs, "_resolve_latest_release", return_value=None), \
         patch.object(gs.subprocess, "run", side_effect=fake_run):
        sync_plugin(clone_root=tmp_path, repo_url="https://example.com/r.git",
                    mode=SyncMode.RELEASE)

    clone = next(c for c in calls if "clone" in c)
    assert "main" in clone
    assert "no release" in capsys.readouterr().err.lower()


# ── update path (release mode) ───────────────────────────────────────────────

def test_update_release_mode_fetches_tags_and_checks_out_latest(tmp_path):
    (tmp_path / ".git").mkdir()
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        if "tag" in cmd:
            return _ok(stdout="v2.0.0\nv2.1.0\n")
        return _ok()

    with patch.object(gs.subprocess, "run", side_effect=fake_run):
        sync_plugin(clone_root=tmp_path, repo_url="https://example.com/r.git",
                    mode=SyncMode.RELEASE, force=True)

    assert any("fetch" in c for c in calls)
    checkout = next(c for c in calls if "checkout" in c)
    assert "v2.1.0" in checkout
    assert not any("pull" in c for c in calls)  # release mode never `git pull`


def test_update_release_mode_checkout_failure_is_non_fatal(tmp_path, capsys):
    (tmp_path / ".git").mkdir()

    def fake_run(cmd, **kw):
        if "tag" in cmd:
            return _ok(stdout="v2.1.0\n")
        if "checkout" in cmd:
            return _ok(returncode=1)
        return _ok()

    # Must not raise.
    with patch.object(gs.subprocess, "run", side_effect=fake_run):
        sync_plugin(clone_root=tmp_path, repo_url="https://example.com/r.git",
                    mode=SyncMode.RELEASE, force=True)


def test_update_release_mode_fetch_failure_is_non_fatal(tmp_path, capsys):
    (tmp_path / ".git").mkdir()
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        if "fetch" in cmd:
            return types.SimpleNamespace(stdout="", stderr=b"network down", returncode=1)
        return _ok()

    with patch.object(gs.subprocess, "run", side_effect=fake_run):
        sync_plugin(clone_root=tmp_path, repo_url="https://example.com/r.git",
                    mode=SyncMode.RELEASE, force=True)

    assert "could not fetch tags" in capsys.readouterr().err.lower()
    assert not any("checkout" in c for c in calls)  # bailed before checkout


def test_update_release_mode_no_tags_stays_put(tmp_path, capsys):
    (tmp_path / ".git").mkdir()
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        if "tag" in cmd:
            return _ok(stdout="")  # no tags at all
        return _ok()

    with patch.object(gs.subprocess, "run", side_effect=fake_run):
        sync_plugin(clone_root=tmp_path, repo_url="https://example.com/r.git",
                    mode=SyncMode.RELEASE, force=True)

    assert "no release found" in capsys.readouterr().err.lower()
    assert not any("checkout" in c for c in calls)


# Stage 5 hardening — kill semver-ordering, peeled-strip, branch-ref, timestamp mutants

def test_latest_tag_orders_across_major_version():
    assert _latest_release_tag("a\trefs/tags/v1.9.0\nb\trefs/tags/v2.1.0\n") == "v2.1.0"


def test_latest_tag_distinguishes_minor_from_patch():
    # If minor/patch were swapped, v1.2.10 would wrongly beat v1.10.2.
    assert _latest_release_tag("a\trefs/tags/v1.2.10\nb\trefs/tags/v1.10.2\n") == "v1.10.2"


def test_latest_tag_uses_peeled_ref_when_it_is_the_only_form():
    # The highest version appears only as a peeled ref — the ^{} strip must run.
    out = "a\trefs/tags/v2.0.0^{}\nb\trefs/tags/v1.0.0\n"
    assert _latest_release_tag(out) == "v2.0.0"


def test_clone_branch_mode_uses_the_named_branch(tmp_path):
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return _ok()

    with patch.object(gs.subprocess, "run", side_effect=fake_run):
        sync_plugin(clone_root=tmp_path, repo_url="https://example.com/r.git",
                    branch="develop", mode=SyncMode.BRANCH)

    clone = next(c for c in calls if "clone" in c)
    assert "develop" in clone
    assert "main" not in clone  # must not fall back to release/main in BRANCH mode


def test_update_release_mode_writes_timestamp_on_success(tmp_path):
    (tmp_path / ".git").mkdir()

    def fake_run(cmd, **kw):
        if "tag" in cmd:
            return _ok(stdout="v2.1.0\n")
        return _ok()  # fetch + checkout succeed

    with patch.object(gs.subprocess, "run", side_effect=fake_run):
        sync_plugin(clone_root=tmp_path, repo_url="https://example.com/r.git",
                    mode=SyncMode.RELEASE, force=True)

    assert (tmp_path / ".last-pull").exists()  # success path must stamp the sync time


# Stage 5 hardening (round 2) — env/kwargs, empty-line skip, equal-version order, _pull cmd

def test_latest_tag_skips_blank_lines_without_stopping():
    # A blank line must `continue`, not `break` (else a later, higher tag is missed).
    assert _latest_release_tag("v1.0.0\n\nv2.0.0\n") == "v2.0.0"


def test_latest_tag_keeps_first_of_equal_versions():
    # v1.0.0 and 1.0.0 parse equal; '>' keeps the first seen (not '>=' → last).
    assert _latest_release_tag("a\trefs/tags/v1.0.0\nb\trefs/tags/1.0.0\n") == "v1.0.0"


def test_resolve_latest_release_passes_real_env_and_captures_output():
    captured = {}

    def rec(cmd, **kw):
        captured.update(kw)
        return _ok(stdout="x\trefs/tags/v1.0.0\n")

    with patch.object(gs.subprocess, "run", side_effect=rec):
        gs._resolve_latest_release("https://example.com/r.git")

    assert isinstance(captured.get("env"), dict)               # env must not be None
    assert captured["env"].get("GIT_TERMINAL_PROMPT") == "0"   # it's a real git env
    assert captured["capture_output"] is True
    assert captured["text"] is True


def test_update_release_passes_real_env_and_captures_on_each_call(tmp_path):
    (tmp_path / ".git").mkdir()
    calls = []

    def rec(cmd, **kw):
        calls.append((cmd, kw))
        return _ok(stdout="v2.1.0\n") if "tag" in cmd else _ok()

    with patch.object(gs.subprocess, "run", side_effect=rec):
        sync_plugin(clone_root=tmp_path, repo_url="https://example.com/r.git",
                    mode=SyncMode.RELEASE, force=True)

    for cmd, kw in calls:
        assert isinstance(kw.get("env"), dict)  # env must be a real dict on every call
    fetch = next(kw for cmd, kw in calls if "fetch" in cmd)
    listing = next(kw for cmd, kw in calls if "tag" in cmd)
    checkout = next(kw for cmd, kw in calls if "checkout" in cmd)
    assert fetch["capture_output"] is True
    assert listing["capture_output"] is True and listing["text"] is True
    assert checkout["capture_output"] is True


def test_pull_checkout_command_uses_git_and_quiet(tmp_path):
    calls = []

    def rec(cmd, **kw):
        calls.append(cmd)
        return _ok()

    with patch.object(gs.subprocess, "run", side_effect=rec):
        gs._pull(tmp_path, "main", "", "")

    checkout = calls[0]
    assert checkout[0] == "git"
    assert "checkout" in checkout and "--quiet" in checkout and "main" in checkout
