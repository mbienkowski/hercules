"""Stage 2 — Claude Code version check (warn-only, never blocks)."""

from __future__ import annotations

import types

import pytest

from hercules.plugin_sync import claude_version as cv
from hercules.plugin_sync import config as config_mod
from hercules.plugin_sync.config import Config, load_config, save_config


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch):
    """Redirect the Hercules home so the throttle never touches a real ~/.hercules."""
    monkeypatch.setattr(config_mod, "HERCULES_HOME", tmp_path / ".hercules")
    monkeypatch.setattr(config_mod, "_LEGACY_CONFIG_PATH", tmp_path / "legacy.json")
    monkeypatch.delenv("HERCULES_GIT_TOKEN", raising=False)


def _fake_run(stdout="", stderr="", returncode=0, raises=None):
    def _run(*_args, **_kwargs):
        if raises is not None:
            raise raises
        return types.SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)
    return _run


# ── parse_claude_version ─────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("2.1.128", (2, 1, 128)),
    ("v2.1.128 (Claude Code)", (2, 1, 128)),
    ("claude 2.1.200 final", (2, 1, 200)),
    ("Claude Code 2.10.3\n", (2, 10, 3)),
    ("2.1", None),
    ("garbage", None),
    ("", None),
])
def test_parse_claude_version(text, expected):
    assert cv.parse_claude_version(text) == expected


# ── meets_minimum ────────────────────────────────────────────────────────────

def test_meets_minimum_exact_boundary():
    assert cv.meets_minimum((2, 1, 128), (2, 1, 128)) is True


def test_meets_minimum_below():
    assert cv.meets_minimum((2, 1, 127), (2, 1, 128)) is False


def test_meets_minimum_above():
    assert cv.meets_minimum((2, 1, 129), (2, 1, 128)) is True


def test_min_constant_is_2_1_128():
    assert cv.MIN_CLAUDE_VERSION == (2, 1, 128)


# ── verify_claude_version (warn-only) ────────────────────────────────────────

def test_below_min_warns_but_does_not_exit(capsys):
    cv.verify_claude_version(run=_fake_run(stdout="2.1.100"))
    err = capsys.readouterr().err
    assert "2.1.100" in err and "2.1.128" in err  # detected + required


def test_at_or_above_min_is_silent(capsys):
    cv.verify_claude_version(run=_fake_run(stdout="2.1.128"))
    assert capsys.readouterr().err == ""


def test_unparseable_output_is_silent(capsys):
    cv.verify_claude_version(run=_fake_run(stdout="no version here"))
    assert capsys.readouterr().err == ""


def test_missing_binary_is_silent_and_non_fatal(capsys):
    # Must not raise even though the binary is absent.
    cv.verify_claude_version(run=_fake_run(raises=FileNotFoundError()))
    assert capsys.readouterr().err == ""


def test_warning_is_throttled_per_detected_version(capsys):
    cv.verify_claude_version(run=_fake_run(stdout="2.1.100"))
    first = capsys.readouterr().err
    assert "2.1.100" in first
    # Second run, same version → no repeat warning.
    cv.verify_claude_version(run=_fake_run(stdout="2.1.100"))
    assert capsys.readouterr().err == ""
    # A different old version warns again.
    cv.verify_claude_version(run=_fake_run(stdout="2.1.50"))
    assert "2.1.50" in capsys.readouterr().err


def test_throttle_persists_detected_version_to_config():
    save_config(Config())
    cv.verify_claude_version(run=_fake_run(stdout="2.1.100"))
    assert load_config().options.get("claude_version_warned") == "2.1.100"


# Stage 2 hardening — kill subprocess-arg and stderr-path mutants

def test_verify_invokes_claude_version_with_capture_and_text():
    captured = {}

    def rec(cmd, **kwargs):
        captured["cmd"] = cmd
        captured.update(kwargs)
        return types.SimpleNamespace(stdout="2.1.128", stderr="", returncode=0)

    cv.verify_claude_version(run=rec)
    assert captured["cmd"] == ["claude", "--version"]
    assert captured["capture_output"] is True
    assert captured["text"] is True


def test_below_min_reported_via_stderr_also_warns(capsys):
    # Some tools print --version to stderr; the check must read both streams.
    cv.verify_claude_version(run=_fake_run(stdout="", stderr="2.1.100"))
    assert "2.1.100" in capsys.readouterr().err


def test_verify_uses_subprocess_run_by_default(monkeypatch, capsys):
    # With no injected run, it must resolve subprocess.run at call time.
    monkeypatch.setattr(
        cv.subprocess, "run",
        lambda *a, **k: types.SimpleNamespace(stdout="2.1.0", stderr="", returncode=0),
    )
    cv.verify_claude_version()  # no run= → default path
    assert "2.1.0" in capsys.readouterr().err
