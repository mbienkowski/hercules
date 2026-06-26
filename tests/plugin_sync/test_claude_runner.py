"""Tests for the claude runner — environment sanitisation before exec."""

import os
from unittest.mock import patch

import pytest

from hercules.plugin_sync.claude_runner import _build_env


def test_secrets_are_stripped_from_environment_before_exec(monkeypatch):
    """HERCULES_GIT_TOKEN, HERCULES_REPO_URL, and GIT_ASKPASS must not reach the claude process."""
    # Given
    monkeypatch.setenv("HERCULES_GIT_TOKEN", "super-secret-token")
    monkeypatch.setenv("HERCULES_REPO_URL", "https://secret-internal.example.com/repo.git")
    monkeypatch.setenv("GIT_ASKPASS", "/tmp/askpass.sh")
    monkeypatch.setenv("SAFE_VAR", "should-be-kept")

    # When
    env = _build_env(claude_dir=None)

    # Then
    assert "HERCULES_GIT_TOKEN" not in env
    assert "HERCULES_REPO_URL" not in env
    assert "GIT_ASKPASS" not in env
    assert "SAFE_VAR" in env


def test_claude_config_dir_is_set_when_claude_dir_is_provided(monkeypatch):
    """--claude-dir must set CLAUDE_CONFIG_DIR in the environment passed to claude."""
    # Given
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/original/dir")

    # When
    env = _build_env(claude_dir="/my/custom/dir")

    # Then
    assert env["CLAUDE_CONFIG_DIR"] == "/my/custom/dir"


def test_claude_config_dir_is_not_set_when_claude_dir_is_none(monkeypatch):
    """When --claude-dir is not specified, CLAUDE_CONFIG_DIR is unchanged."""
    # Given
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)

    # When
    env = _build_env(claude_dir=None)

    # Then
    assert "CLAUDE_CONFIG_DIR" not in env


def test_exec_claude_exits_when_claude_not_found(capsys):
    """When claude is not on PATH, exec_claude must print an error and call sys.exit."""
    # Given
    from pathlib import Path
    from hercules.plugin_sync.claude_runner import exec_claude

    # When
    with patch("shutil.which", return_value=None), \
         pytest.raises(SystemExit) as exc_info:
        exec_claude(plugin_dir=Path("/tmp/plugin"), claude_dir=None, extra_args=[])

    # Then
    assert exc_info.value.code != 0
    assert "claude" in capsys.readouterr().err.lower()


def test_exec_claude_passes_sanitised_environment_to_child_process(monkeypatch, tmp_path):
    """exec_claude must call os.execvpe (not os.execvp) so the sanitised env reaches claude."""
    # Given
    from pathlib import Path
    import os
    from hercules.plugin_sync.claude_runner import exec_claude, _SECRETS_TO_STRIP

    monkeypatch.setenv("HERCULES_GIT_TOKEN", "should-be-stripped")
    monkeypatch.setenv("SAFE_VAR", "keep-this")

    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir()
    captured = {}

    def fake_execvpe(path, args, env):
        captured["env"] = env

    # When
    with patch("shutil.which", return_value="/usr/bin/claude"), \
         patch("os.execvpe", side_effect=fake_execvpe):
        exec_claude(plugin_dir=plugin_dir, claude_dir=None, extra_args=[])

    # Then — secrets must be absent, safe vars must be present
    assert "HERCULES_GIT_TOKEN" not in captured["env"]
    assert "SAFE_VAR" in captured["env"]


def test_exec_claude_appends_system_prompt_when_claude_md_exists(tmp_path):
    """When CLAUDE.md exists in the plugin dir, --append-system-prompt-file must be in the args."""
    # Given
    from hercules.plugin_sync.claude_runner import exec_claude

    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir()
    (plugin_dir / "CLAUDE.md").write_text("# instructions")
    captured = {}

    def fake_execvpe(path, args, env):
        captured["args"] = args

    # When
    with patch("shutil.which", return_value="/usr/bin/claude"), \
         patch("os.execvpe", side_effect=fake_execvpe):
        exec_claude(plugin_dir=plugin_dir, claude_dir=None, extra_args=[])

    # Then — flag present AND the value points to the exact CLAUDE.md path
    assert "--append-system-prompt-file" in captured["args"]
    idx = captured["args"].index("--append-system-prompt-file")
    assert captured["args"][idx + 1] == str(plugin_dir / "CLAUDE.md")
