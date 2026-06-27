"""Tests for the thin branded `hercules` launcher (spec 02).

Covers the behaviour re-homed from the deleted sync CLI: `--claude-dir`→`CLAUDE_CONFIG_DIR`,
secret stripping before exec, the Python 3.9 floor, plus arg passthrough and the missing-claude error.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from hercules import launcher


def test_launcher_forwards_args_and_version(capsys):
    """`hercules --version` prints a version and returns; other args are forwarded to claude."""
    # Given/When — the version path returns without exec
    launcher.main(["--version"])
    assert capsys.readouterr().out.strip(), "expected --version to print a version string"

    # And — arbitrary args are forwarded verbatim to the claude executable
    captured = {}

    def fake_execvpe(path, args, env):
        captured["args"] = args

    with patch("shutil.which", return_value="/usr/bin/claude"), \
         patch("os.execvpe", side_effect=fake_execvpe):
        launcher.main(["chat", "--model", "opus"])

    assert captured["args"] == ["/usr/bin/claude", "chat", "--model", "opus"]


def test_claude_dir_flag_sets_claude_config_dir(monkeypatch):
    """--claude-dir X sets CLAUDE_CONFIG_DIR=X in the child env and is NOT forwarded to claude."""
    # Given
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/original")
    captured = {}

    def fake_execvpe(path, args, env):
        captured["args"] = args
        captured["env"] = env

    # When
    with patch("shutil.which", return_value="/usr/bin/claude"), \
         patch("os.execvpe", side_effect=fake_execvpe):
        launcher.main(["--claude-dir", "/my/dir", "foo"])

    # Then
    assert captured["env"]["CLAUDE_CONFIG_DIR"] == "/my/dir"
    assert captured["args"] == ["/usr/bin/claude", "foo"]


def test_claude_config_dir_unchanged_when_flag_absent(monkeypatch):
    """Without --claude-dir, CLAUDE_CONFIG_DIR is not injected into the child env."""
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    assert "CLAUDE_CONFIG_DIR" not in launcher._build_env(None)


def test_secrets_stripped_before_launching_claude(monkeypatch):
    """HERCULES_* / GIT_ASKPASS secrets must not reach the claude process; safe vars stay."""
    # Given
    monkeypatch.setenv("HERCULES_GIT_TOKEN", "secret")
    monkeypatch.setenv("HERCULES_REPO_URL", "https://secret/repo.git")
    monkeypatch.setenv("GIT_ASKPASS", "/tmp/askpass")
    monkeypatch.setenv("SAFE_VAR", "keep")

    # When
    env = launcher._build_env(None)

    # Then
    assert "HERCULES_GIT_TOKEN" not in env
    assert "HERCULES_REPO_URL" not in env
    assert "GIT_ASKPASS" not in env
    assert env["SAFE_VAR"] == "keep"


def test_launcher_errors_when_claude_not_on_path(capsys):
    """If claude is not installed, the launcher exits non-zero with a clear message."""
    with patch("shutil.which", return_value=None), pytest.raises(SystemExit) as exc:
        launcher.main(["chat"])
    assert exc.value.code != 0
    assert "claude" in capsys.readouterr().err.lower()


def test_claude_dir_equals_form_sets_config_dir():
    """The `--claude-dir=DIR` form is accepted and not forwarded to claude."""
    captured = {}

    def fake_execvpe(path, args, env):
        captured["args"] = args
        captured["env"] = env

    with patch("shutil.which", return_value="/usr/bin/claude"), \
         patch("os.execvpe", side_effect=fake_execvpe):
        launcher.main(["--claude-dir=/x", "foo"])

    assert captured["env"]["CLAUDE_CONFIG_DIR"] == "/x"
    assert captured["args"] == ["/usr/bin/claude", "foo"]


def test_claude_dir_without_value_errors(capsys):
    """`--claude-dir` with no directory argument exits non-zero with a clear message."""
    with patch("shutil.which", return_value="/usr/bin/claude"), pytest.raises(SystemExit) as exc:
        launcher.main(["--claude-dir"])
    assert exc.value.code != 0
    assert "--claude-dir" in capsys.readouterr().err


def test_python_floor_rejects_below_39(capsys):
    """Python < 3.9 triggers the version gate: error message naming 3.9 and exit code 1."""
    with pytest.raises(SystemExit) as exc:
        launcher._check_python_floor((3, 8, 0))
    assert exc.value.code == 1
    assert "3.9" in capsys.readouterr().err


def test_python_floor_accepts_39_and_above():
    """Python 3.9 and 3.10 pass the gate (boundary pinned so `< (3,9)` can't drift)."""
    assert launcher._check_python_floor((3, 9, 0)) is None
    assert launcher._check_python_floor((3, 10, 0)) is None
