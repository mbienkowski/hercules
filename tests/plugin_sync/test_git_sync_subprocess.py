"""Tests for git clone and pull operations using mocked subprocess."""

from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from hercules.plugin_sync.git_sync import sync_plugin


def _mock_run_ok(returncode=0):
    result = MagicMock()
    result.returncode = returncode
    result.stderr = b""
    result.stdout = b""
    return result


def test_sync_clones_on_first_run(tmp_path):
    """When the plugin directory does not exist, sync_plugin must run git clone."""
    # Given
    plugin_dir = tmp_path / "plugin"

    # When
    with patch("hercules.plugin_sync.git_sync.subprocess.run", return_value=_mock_run_ok()) as mock_run, \
         patch("hercules.plugin_sync.git_sync._write_timestamp"):
        sync_plugin(
            clone_root=plugin_dir,
            repo_url="https://github.com/mbienkowski/hercules.git",
            branch="main",
        )

    # Then — full command must include branch name and destination directory
    call_args = mock_run.call_args_list[0][0][0]
    assert call_args == [
        "git", "clone", "--quiet", "--branch", "main",
        "https://github.com/mbienkowski/hercules.git",
        str(plugin_dir),
    ]


def test_sync_skips_when_ttl_has_not_elapsed(tmp_path):
    """When the last-pull timestamp is recent, sync_plugin must not call git at all."""
    # Given
    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir()
    (plugin_dir / ".git").mkdir()

    # Write a very recent timestamp
    from datetime import datetime, timezone
    recent = datetime.now(timezone.utc).isoformat()
    (plugin_dir / ".last-pull").write_text(recent)

    # When
    with patch("hercules.plugin_sync.git_sync.subprocess.run") as mock_run:
        sync_plugin(
            clone_root=plugin_dir,
            repo_url="https://github.com/mbienkowski/hercules.git",
            branch="main",
        )

    # Then
    mock_run.assert_not_called()


def test_sync_pulls_when_ttl_has_elapsed(tmp_path):
    """When the last-pull timestamp is old, sync_plugin must run git pull."""
    # Given
    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir()
    (plugin_dir / ".git").mkdir()

    from datetime import datetime, timedelta, timezone
    old = datetime.now(timezone.utc) - timedelta(minutes=10)
    (plugin_dir / ".last-pull").write_text(old.isoformat())

    # When
    with patch("hercules.plugin_sync.git_sync.subprocess.run", return_value=_mock_run_ok()) as mock_run:
        sync_plugin(
            clone_root=plugin_dir,
            repo_url="https://github.com/mbienkowski/hercules.git",
            branch="main",
        )

    # Then — pull must use --ff-only (no rebases or merges from sync)
    commands = [call[0][0] for call in mock_run.call_args_list]
    assert ["git", "pull", "--ff-only", "--quiet"] in commands


def test_clone_failure_raises_runtime_error(tmp_path):
    """A failed git clone must raise RuntimeError so the caller can print a user-friendly message."""
    # Given
    plugin_dir = tmp_path / "plugin"

    # When / Then
    with patch("hercules.plugin_sync.git_sync.subprocess.run", return_value=_mock_run_ok(returncode=1)):
        with pytest.raises(RuntimeError, match="git clone failed"):
            sync_plugin(
                clone_root=plugin_dir,
                repo_url="https://github.com/mbienkowski/hercules.git",
                branch="main",
            )


def test_successful_pull_updates_the_last_pull_timestamp(tmp_path):
    """After a successful git pull the .last-pull file must be refreshed so TTL is reset."""
    # Given
    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir()
    (plugin_dir / ".git").mkdir()

    from datetime import datetime, timedelta, timezone
    old = datetime.now(timezone.utc) - timedelta(minutes=10)
    (plugin_dir / ".last-pull").write_text(old.isoformat())

    # When
    with patch("hercules.plugin_sync.git_sync.subprocess.run", return_value=_mock_run_ok()):
        sync_plugin(
            clone_root=plugin_dir,
            repo_url="https://github.com/mbienkowski/hercules.git",
            branch="main",
        )

    # Then — timestamp must be newer than the old one
    new_ts = datetime.fromisoformat((plugin_dir / ".last-pull").read_text().strip())
    assert new_ts > old


def test_pull_failure_is_a_non_fatal_warning(tmp_path, capsys):
    """A failed git pull must print a warning and not raise — cached content is used."""
    # Given
    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir()
    (plugin_dir / ".git").mkdir()

    from datetime import datetime, timedelta, timezone
    old = datetime.now(timezone.utc) - timedelta(minutes=10)
    (plugin_dir / ".last-pull").write_text(old.isoformat())

    checkout_ok = _mock_run_ok(returncode=0)
    pull_fail = _mock_run_ok(returncode=1)
    pull_fail.stderr = b"merge conflict"

    # When
    with patch("hercules.plugin_sync.git_sync.subprocess.run", side_effect=[checkout_ok, pull_fail]):
        sync_plugin(
            clone_root=plugin_dir,
            repo_url="https://github.com/mbienkowski/hercules.git",
            branch="main",
        )

    # Then — no exception raised
    assert "Warning" in capsys.readouterr().err
