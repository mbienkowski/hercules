"""Tests for the Hercules CLI entry point — flag parsing and integration scenarios."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Version flag
# ---------------------------------------------------------------------------

def test_version_flag_prints_version_and_exits(capsys):
    """--version must print the current version string and return without launching claude."""
    # Given
    from hercules.cli import main

    # When
    with patch("sys.argv", ["hercules", "--version"]):
        main()

    # Then — must match the VERSION constant exactly (not an error message)
    from hercules.cli import VERSION
    out = capsys.readouterr().out.strip()
    assert out == VERSION


# ---------------------------------------------------------------------------
# --uninstall
# ---------------------------------------------------------------------------

def test_uninstall_flag_prints_removal_instructions(capsys):
    """--uninstall prints how to remove Hercules without executing anything."""
    # Given
    from hercules.cli import main

    # When
    with patch("sys.argv", ["hercules", "--uninstall"]):
        main()

    # Then — both removal steps must be present
    out = capsys.readouterr().out
    assert "pipx uninstall hercules" in out
    assert "pip uninstall hercules --break-system-packages" in out
    assert "rm" in out


# ---------------------------------------------------------------------------
# --update
# ---------------------------------------------------------------------------

def test_update_flag_triggers_self_update(capsys):
    """--update must print the pip upgrade command (real run_self_update, no mock)."""
    # Given
    from hercules.cli import main

    # When
    with patch("sys.argv", ["hercules", "--update"]), \
         patch("hercules.cli._print_banner"):
        main()

    # Then — exact output pins the command name and format (pipx, never bare pip)
    out = capsys.readouterr().out
    assert out.strip() == "Run: pipx upgrade hercules"


# ---------------------------------------------------------------------------
# Missing dependency checks
# ---------------------------------------------------------------------------

def test_missing_git_exits_with_error(capsys):
    """If 'git' is not on PATH, hercules must print a clear error and exit non-zero."""
    # Given
    from hercules.cli import main

    # When
    with patch("sys.argv", ["hercules"]), \
         patch("shutil.which", side_effect=lambda x: None if x == "git" else "/usr/bin/claude"), \
         patch("hercules.cli._print_banner"):
        with pytest.raises(SystemExit) as exc_info:
            main()

    # Then
    assert exc_info.value.code != 0
    assert "git" in capsys.readouterr().err


def test_missing_claude_exits_with_error(capsys):
    """If 'claude' is not on PATH, hercules must print a clear error and exit non-zero."""
    # Given
    from hercules.cli import main

    # When
    with patch("sys.argv", ["hercules"]), \
         patch("shutil.which", side_effect=lambda x: "/usr/bin/git" if x == "git" else None), \
         patch("hercules.cli._print_banner"):
        with pytest.raises(SystemExit) as exc_info:
            main()

    # Then
    assert exc_info.value.code != 0
    assert "claude" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Banner suppression
# ---------------------------------------------------------------------------

def test_banner_is_suppressed_when_no_color_is_set(monkeypatch, capsys):
    """NO_COLOR environment variable must suppress the banner output."""
    # Given
    from hercules.cli import _print_banner
    monkeypatch.setenv("NO_COLOR", "1")

    # When
    _print_banner("v1.0.0", "main")

    # Then
    assert capsys.readouterr().err == ""


# ---------------------------------------------------------------------------
# Flag parsing
# ---------------------------------------------------------------------------

def test_branch_flag_sets_plugin_branch(cli_harness):
    """--branch sets the branch used for git clone/pull."""
    # Given
    from hercules.cli import main
    captured = {}
    cli_harness.sync.side_effect = lambda **kw: captured.update({"branch": kw["branch"]})

    # When
    with patch("sys.argv", ["hercules", "--branch", "feat/test"]):
        main()

    # Then
    assert captured["branch"] == "feat/test"


def test_git_token_from_environment_is_used_when_no_flag_given(cli_harness):
    """HERCULES_GIT_TOKEN env var must be picked up when --git-token is not specified."""
    # Given
    from hercules.cli import main
    captured = {}
    cli_harness.sync.side_effect = lambda **kw: captured.update({"git_token": kw.get("git_token", "")})

    # When
    with patch("sys.argv", ["hercules"]), \
         patch.dict(os.environ, {"HERCULES_GIT_TOKEN": "env-token"}):
        main()

    # Then
    assert captured["git_token"] == "env-token"


def test_cli_flag_takes_priority_over_environment_variable(cli_harness):
    """--git-token flag must override HERCULES_GIT_TOKEN environment variable."""
    # Given
    from hercules.cli import main
    captured = {}
    cli_harness.sync.side_effect = lambda **kw: captured.update({"git_token": kw.get("git_token", "")})

    # When
    with patch("sys.argv", ["hercules", "--git-token", "flag-token"]), \
         patch.dict(os.environ, {"HERCULES_GIT_TOKEN": "env-token"}):
        main()

    # Then
    assert captured["git_token"] == "flag-token"


# ---------------------------------------------------------------------------
# Lock behaviour
# ---------------------------------------------------------------------------

def test_sync_is_skipped_when_another_session_holds_the_lock(capsys):
    """When the lock is held by another process, plugin sync must be skipped gracefully."""
    # Given
    from hercules.cli import main

    # When
    with patch("sys.argv", ["hercules"]), \
         patch("shutil.which", return_value="/usr/bin/mock"), \
         patch("hercules.cli._print_banner"), \
         patch("hercules.cli.load_config", return_value=MagicMock(repo_url="", ssh_key="", git_token="")), \
         patch("hercules.cli.ensure_config"), \
         patch("hercules.cli.run_onboarding"), \
         patch("hercules.cli.Lock") as MockLock, \
         patch("hercules.cli.sync_plugin") as mock_sync, \
         patch("hercules.cli.exec_claude"), \
         patch("pathlib.Path.exists", return_value=True):
        mock_lock_instance = MagicMock()
        mock_lock_instance.acquire.return_value = False
        MockLock.return_value = mock_lock_instance
        main()

    # Then
    mock_sync.assert_not_called()
    assert "skipping" in capsys.readouterr().err.lower()


def test_sync_failure_exits_with_error_and_releases_lock(capsys):
    """A sync failure must release the lock and exit with a non-zero code."""
    # Given
    from hercules.cli import main

    # When
    with patch("sys.argv", ["hercules"]), \
         patch("shutil.which", return_value="/usr/bin/mock"), \
         patch("hercules.cli._print_banner"), \
         patch("hercules.cli.load_config", return_value=MagicMock(repo_url="", ssh_key="", git_token="")), \
         patch("hercules.cli.Lock") as MockLock, \
         patch("hercules.cli.sync_plugin", side_effect=RuntimeError("network error")):
        mock_lock_instance = MagicMock()
        mock_lock_instance.acquire.return_value = True
        MockLock.return_value = mock_lock_instance
        with pytest.raises(SystemExit) as exc_info:
            main()

    # Then
    assert exc_info.value.code != 0
    mock_lock_instance.release.assert_called_once()


# ---------------------------------------------------------------------------
# Extra args pass-through
# ---------------------------------------------------------------------------

def test_extra_arguments_are_passed_through_to_claude():
    """Arguments not consumed by hercules must be forwarded unchanged to the claude process."""
    # Given
    from hercules.cli import main
    captured = {}

    def mock_exec(plugin_dir, claude_dir, extra_args):
        captured["extra_args"] = extra_args

    # When
    with patch("sys.argv", ["hercules", "--model", "opus", "--no-tools"]), \
         patch("shutil.which", return_value="/usr/bin/mock"), \
         patch("hercules.cli._print_banner"), \
         patch("hercules.cli.load_config", return_value=MagicMock(repo_url="", ssh_key="", git_token="")), \
         patch("hercules.cli.ensure_config"), \
         patch("hercules.cli.run_onboarding"), \
         patch("hercules.cli.Lock") as MockLock, \
         patch("hercules.cli.sync_plugin"), \
         patch("hercules.cli.exec_claude", side_effect=mock_exec), \
         patch("pathlib.Path.exists", return_value=True):
        mock_lock_instance = MagicMock()
        mock_lock_instance.acquire.return_value = True
        MockLock.return_value = mock_lock_instance
        main()

    # Then
    assert "--model" in captured["extra_args"]
    assert "opus" in captured["extra_args"]


def test_claude_dir_flag_is_forwarded_to_exec():
    """--claude-dir must be forwarded to exec_claude as the claude_dir argument."""
    # Given
    from hercules.cli import main
    captured = {}

    def mock_exec(plugin_dir, claude_dir, extra_args):
        captured["claude_dir"] = claude_dir

    # When
    with patch("sys.argv", ["hercules", "--claude-dir", "/tmp/my-claude"]), \
         patch("shutil.which", return_value="/usr/bin/mock"), \
         patch("hercules.cli._print_banner"), \
         patch("hercules.cli.load_config", return_value=MagicMock(repo_url="", ssh_key="", git_token="")), \
         patch("hercules.cli.ensure_config"), \
         patch("hercules.cli.run_onboarding"), \
         patch("hercules.cli.Lock") as MockLock, \
         patch("hercules.cli.sync_plugin"), \
         patch("hercules.cli.exec_claude", side_effect=mock_exec), \
         patch("pathlib.Path.exists", return_value=True):
        mock_lock_instance = MagicMock()
        mock_lock_instance.acquire.return_value = True
        MockLock.return_value = mock_lock_instance
        main()

    # Then
    assert captured["claude_dir"] == "/tmp/my-claude"


# ---------------------------------------------------------------------------
# Plugin dir guard
# ---------------------------------------------------------------------------

def test_missing_plugin_directory_after_sync_exits_with_error(capsys, tmp_path):
    """If the plugin directory is still absent after sync, hercules must exit with an error."""
    # Given
    from hercules.cli import main

    non_existent_plugin = tmp_path / "nonexistent-plugin"

    # When
    with patch("sys.argv", ["hercules"]), \
         patch("shutil.which", return_value="/usr/bin/mock"), \
         patch("hercules.cli._print_banner"), \
         patch("hercules.cli.load_config", return_value=MagicMock(repo_url="", ssh_key="", git_token="")), \
         patch("hercules.cli.Lock") as MockLock, \
         patch("hercules.cli.sync_plugin"), \
         patch("hercules.plugin_sync.claude_runner.Path.home", return_value=tmp_path):
        mock_lock_instance = MagicMock()
        mock_lock_instance.acquire.return_value = True
        MockLock.return_value = mock_lock_instance
        # Override plugin_dir in the main function
        with patch("pathlib.Path.exists", return_value=False):
            with pytest.raises(SystemExit) as exc_info:
                main()

    # Then
    assert exc_info.value.code != 0


def test_missing_git_exits_with_code_1(capsys):
    """When 'git' is missing, exit code must be exactly 1."""
    from hercules.cli import main

    with patch("sys.argv", ["hercules"]), \
         patch("shutil.which", side_effect=lambda x: None if x == "git" else "/usr/bin/claude"), \
         patch("hercules.cli._print_banner"):
        with pytest.raises(SystemExit) as exc_info:
            main()

    assert exc_info.value.code == 1


def test_missing_claude_exits_with_code_1(capsys):
    """When 'claude' is missing, exit code must be exactly 1."""
    from hercules.cli import main

    with patch("sys.argv", ["hercules"]), \
         patch("shutil.which", side_effect=lambda x: "/usr/bin/git" if x == "git" else None), \
         patch("hercules.cli._print_banner"):
        with pytest.raises(SystemExit) as exc_info:
            main()

    assert exc_info.value.code == 1


def test_hercules_repo_url_env_var_is_used_as_effective_url(cli_harness):
    """HERCULES_REPO_URL must be picked up as the effective repository URL."""
    from hercules.cli import main
    captured = {}
    cli_harness.sync.side_effect = lambda **kw: captured.update({"repo_url": kw["repo_url"]})

    with patch("sys.argv", ["hercules"]), \
         patch.dict(os.environ, {"HERCULES_REPO_URL": "https://custom.example.com/repo.git"}):
        main()

    assert captured["repo_url"] == "https://custom.example.com/repo.git"


def test_setup_flag_runs_wizard_and_saves_config(capsys):
    """--setup must run the wizard, save the config, and print the config path."""
    from hercules.cli import main
    from hercules.plugin_sync.config import Config

    with patch("sys.argv", ["hercules", "--setup"]), \
         patch("hercules.cli._print_banner"), \
         patch("hercules.cli.run_wizard", return_value=Config(repo_url="https://x.com/r.git")), \
         patch("hercules.cli.save_config") as mock_save, \
         patch("hercules.cli.save_token") as mock_save_token, \
         patch("hercules.cli.config_path", return_value=Path("/tmp/config.json")):
        main()

    mock_save.assert_called_once()
    mock_save_token.assert_called_once()
    assert "config" in capsys.readouterr().err.lower()


def test_status_reports_initialized_onboarded_and_last_sync(capsys, tmp_path):
    """--status derives initialized/last-sync from the real clone and prints onboarded_at."""
    from hercules.cli import main
    from hercules.plugin_sync.config import Config

    home = tmp_path
    clone = home / ".hercules"
    (clone / ".git").mkdir(parents=True)
    (clone / ".last-pull").write_text("2026-06-26T09:00:00+00:00")

    with patch("sys.argv", ["hercules", "--status"]), \
         patch("pathlib.Path.home", return_value=home), \
         patch("hercules.cli.load_config", return_value=Config(onboarded_at="2026-06-26T08:00:00+00:00")):
        main()

    out = capsys.readouterr().out
    assert "initialized: yes" in out
    assert "2026-06-26T08:00:00+00:00" in out  # onboarded
    assert "2026-06-26T09:00:00+00:00" in out  # last sync


def test_uninstall_prints_hercules_home_directory(capsys):
    """--uninstall output must include the exact '.hercules' directory (not a mutated variant)."""
    from hercules.cli import main

    with patch("sys.argv", ["hercules", "--uninstall"]):
        main()

    out = capsys.readouterr().out
    # Use path separator to pin the exact directory name (not XX.herculesXX variants)
    assert "/.hercules" in out


def test_sync_failure_exits_with_code_1(capsys):
    """A sync failure must exit with code 1 exactly."""
    from hercules.cli import main

    with patch("sys.argv", ["hercules"]), \
         patch("shutil.which", return_value="/usr/bin/mock"), \
         patch("hercules.cli._print_banner"), \
         patch("hercules.cli.load_config", return_value=MagicMock(repo_url="", ssh_key="", git_token="")), \
         patch("hercules.cli.Lock") as MockLock, \
         patch("hercules.cli.sync_plugin", side_effect=RuntimeError("network error")):
        mock_lock_instance = MagicMock()
        mock_lock_instance.acquire.return_value = True
        MockLock.return_value = mock_lock_instance
        with pytest.raises(SystemExit) as exc_info:
            main()

    assert exc_info.value.code == 1


def test_missing_plugin_dir_after_sync_exits_with_code_1_exactly(tmp_path, capsys):
    """plugin_dir missing after sync must exit with code 1 (not 2 or any other code)."""
    from hercules.cli import main

    with patch("sys.argv", ["hercules"]), \
         patch("shutil.which", return_value="/usr/bin/mock"), \
         patch("hercules.cli._print_banner"), \
         patch("hercules.cli.load_config", return_value=MagicMock(repo_url="", ssh_key="", git_token="")), \
         patch("hercules.cli.Lock") as MockLock, \
         patch("hercules.cli.sync_plugin"), \
         patch("pathlib.Path.exists", return_value=False):
        mock_lock_instance = MagicMock()
        mock_lock_instance.acquire.return_value = True
        MockLock.return_value = mock_lock_instance
        with pytest.raises(SystemExit) as exc_info:
            main()

    assert exc_info.value.code == 1


def test_default_tracks_release_with_no_branch(cli_harness):
    """When --branch is not specified, Hercules tracks the latest release (branch=None)."""
    from hercules.cli import main
    from hercules.plugin_sync.git_sync import SyncMode
    captured = {}
    cli_harness.sync.side_effect = lambda **kw: captured.update(
        {"branch": kw.get("branch"), "mode": kw.get("mode")}
    )

    with patch("sys.argv", ["hercules"]):
        main()

    assert captured["branch"] is None
    assert captured["mode"] == SyncMode.RELEASE


def test_effective_url_falls_back_to_default_when_no_source_set(cli_harness):
    """When no URL is given via flag, env var, or config, DEFAULT_REPO_URL is used."""
    from hercules.cli import main, DEFAULT_REPO_URL
    captured = {}
    cli_harness.sync.side_effect = lambda **kw: captured.update({"repo_url": kw["repo_url"]})

    with patch("sys.argv", ["hercules"]):
        main()

    assert captured["repo_url"] == DEFAULT_REPO_URL


# ---------------------------------------------------------------------------
# Retry path (T4)
# ---------------------------------------------------------------------------

def test_retry_sync_when_plugin_dir_missing_but_clone_root_exists(tmp_path):
    """When plugin/ is absent but clone_root exists, .last-pull is removed and sync retries."""
    from hercules.cli import main

    # clone_root exists but plugin/ does not
    clone_root = tmp_path / ".hercules"
    clone_root.mkdir()
    last_pull = clone_root / ".last-pull"
    last_pull.write_text("2024-01-01T00:00:00+00:00")

    sync_calls = []

    def mock_sync(clone_root, repo_url, branch=None, ssh_key="", git_token="", force=False, mode=None):
        sync_calls.append("called")

    with patch("sys.argv", ["hercules"]), \
         patch("shutil.which", return_value="/usr/bin/mock"), \
         patch("hercules.cli._print_banner"), \
         patch("hercules.cli.load_config", return_value=MagicMock(repo_url="", ssh_key="", git_token="")), \
         patch("hercules.cli.Lock") as MockLock, \
         patch("hercules.cli.sync_plugin", side_effect=mock_sync), \
         patch("pathlib.Path.home", return_value=tmp_path):
        # First sync acquires lock; second sync is the retry path
        mock_lock_instance = MagicMock()
        mock_lock_instance.acquire.return_value = True
        MockLock.return_value = mock_lock_instance
        # plugin_dir = clone_root / "plugin" — does not exist
        # clone_root exists → retry branch runs
        with pytest.raises(SystemExit):
            main()  # exits because plugin_dir still doesn't exist after retry

    # .last-pull must be deleted before the retry
    assert not last_pull.exists()
    # sync_plugin must have been called at least twice (initial + retry)
    assert len(sync_calls) >= 2


# ---------------------------------------------------------------------------
# Claude version check is advisory (Stage 2) — warns but never blocks launch
# ---------------------------------------------------------------------------

def test_old_claude_version_warns_but_still_launches(cli_harness, monkeypatch, capsys):
    """An old Claude Code must produce a warning yet still exec claude."""
    import types as _types
    from hercules.cli import main
    from hercules.plugin_sync import config as config_mod

    # Isolate the throttle's config writes to the harness's temp home.
    monkeypatch.setattr(config_mod, "HERCULES_HOME", cli_harness.home / ".hercules")
    monkeypatch.setattr(
        "hercules.plugin_sync.claude_version.subprocess.run",
        lambda *a, **k: _types.SimpleNamespace(stdout="2.1.0", stderr="", returncode=0),
    )

    with patch("sys.argv", ["hercules"]):
        main()

    cli_harness.exec.assert_called_once()  # launched despite the old version
    assert "2.1.0" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Manual --sync (Stage 4) — force a refresh now, then exit without launching
# ---------------------------------------------------------------------------

def test_sync_flag_forces_refresh_and_exits(cli_harness):
    """--sync must force a sync (bypass TTL) and exit without exec'ing claude."""
    from hercules.cli import main
    with patch("sys.argv", ["hercules", "--sync"]):
        main()
    assert cli_harness.sync.call_args.kwargs.get("force") is True
    cli_harness.exec.assert_not_called()


def test_sync_flag_composes_with_branch(cli_harness):
    """--sync --branch main must force a refresh of the named branch."""
    from hercules.cli import main
    with patch("sys.argv", ["hercules", "--sync", "--branch", "main"]):
        main()
    kwargs = cli_harness.sync.call_args.kwargs
    assert kwargs.get("force") is True
    assert kwargs.get("branch") == "main"


def test_normal_run_does_not_force_sync(cli_harness):
    """A plain launch must not force a sync (TTL still governs)."""
    from hercules.cli import main
    with patch("sys.argv", ["hercules"]):
        main()
    assert cli_harness.sync.call_args.kwargs.get("force") is False
    cli_harness.exec.assert_called_once()


# ---------------------------------------------------------------------------
# Tracking mode (Stage 5) — default tracks the latest release, not `main`
# ---------------------------------------------------------------------------

def test_no_branch_flag_selects_release_mode(cli_harness):
    """With no --branch, Hercules tracks the latest release (RELEASE mode)."""
    from hercules.cli import main
    from hercules.plugin_sync.git_sync import SyncMode
    with patch("sys.argv", ["hercules"]):
        main()
    kwargs = cli_harness.sync.call_args.kwargs
    assert kwargs.get("mode") == SyncMode.RELEASE
    assert kwargs.get("branch") is None


def test_branch_flag_selects_branch_mode(cli_harness):
    """An explicit --branch opts into BRANCH mode tracking that branch."""
    from hercules.cli import main
    from hercules.plugin_sync.git_sync import SyncMode
    with patch("sys.argv", ["hercules", "--branch", "main"]):
        main()
    kwargs = cli_harness.sync.call_args.kwargs
    assert kwargs.get("mode") == SyncMode.BRANCH
    assert kwargs.get("branch") == "main"


def test_banner_shows_release_tracking_by_default(monkeypatch, capsys):
    """The banner reflects RELEASE tracking when no branch is given."""
    from hercules.cli import _print_banner
    from hercules.plugin_sync.git_sync import SyncMode
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr("sys.stderr.isatty", lambda: True)
    _print_banner("v1.0.0", None, SyncMode.RELEASE)
    assert "latest release" in capsys.readouterr().err.lower()


def test_banner_shows_branch_tracking_when_branch_given(monkeypatch, capsys):
    """The banner names the branch when one is tracked."""
    from hercules.cli import _print_banner
    from hercules.plugin_sync.git_sync import SyncMode
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr("sys.stderr.isatty", lambda: True)
    _print_banner("v1.0.0", "feat/x", SyncMode.BRANCH)
    assert "feat/x" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# --show-onboarding (Stage 6) — replay the first-run explainer, no state change
# ---------------------------------------------------------------------------

def test_show_onboarding_prints_and_does_not_mark(monkeypatch, tmp_path, capsys):
    from hercules.cli import main
    from hercules.plugin_sync import config as config_mod
    from hercules.plugin_sync.config import load_config
    monkeypatch.setattr(config_mod, "HERCULES_HOME", tmp_path / ".hercules")
    monkeypatch.setattr(config_mod, "_LEGACY_CONFIG_PATH", tmp_path / "legacy.json")

    with patch("sys.argv", ["hercules", "--show-onboarding"]):
        main()

    err = capsys.readouterr().err
    assert "code" in err.lower() and "conduct" in err.lower()
    assert load_config().onboarded_at is None


# Stage 4/5 hardening — banner is shown on a normal launch, suppressed on --sync

def test_normal_run_prints_banner(cli_harness):
    from hercules.cli import main
    with patch("hercules.cli._print_banner") as banner, patch("sys.argv", ["hercules"]):
        main()
    banner.assert_called_once()


def test_sync_flag_suppresses_banner(cli_harness):
    from hercules.cli import main
    with patch("hercules.cli._print_banner") as banner, patch("sys.argv", ["hercules", "--sync"]):
        main()
    banner.assert_not_called()
