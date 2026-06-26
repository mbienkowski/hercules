"""Shared fixtures for plugin_sync tests."""

from __future__ import annotations

import contextlib
import types
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def cli_harness(tmp_path):
    """Standard patch set for CLI integration tests.

    Patches all common collaborators so each test only specifies what varies.
    A plugin/ directory is pre-created under tmp_path so the normal success path
    reaches exec_claude rather than exiting early.

    Yields a namespace with:
      .sync  — MagicMock for sync_plugin (override .side_effect to capture args)
      .exec  — MagicMock for exec_claude
      .lock  — the mock Lock instance (acquire returns True by default)
      .home  — the tmp_path used as Path.home()
    """
    (tmp_path / ".hercules" / "plugin").mkdir(parents=True)

    mock_lock = MagicMock()
    mock_lock.acquire.return_value = True

    with contextlib.ExitStack() as stack:
        stack.enter_context(patch("shutil.which", return_value="/usr/bin/mock"))
        stack.enter_context(patch("hercules.cli._print_banner"))
        stack.enter_context(
            patch(
                "hercules.cli.load_config",
                return_value=MagicMock(
                    repo_url="", ssh_key="", git_token="",
                    onboarded_at="2026-01-01T00:00:00+00:00",
                ),
            )
        )
        stack.enter_context(patch("hercules.cli.ensure_config"))
        stack.enter_context(patch("hercules.cli.run_onboarding"))
        MockLock = stack.enter_context(patch("hercules.cli.Lock"))
        MockLock.return_value = mock_lock
        mock_sync = stack.enter_context(patch("hercules.cli.sync_plugin"))
        mock_exec = stack.enter_context(patch("hercules.cli.exec_claude"))
        stack.enter_context(patch("pathlib.Path.home", return_value=tmp_path))

        yield types.SimpleNamespace(
            sync=mock_sync,
            exec=mock_exec,
            lock=mock_lock,
            home=tmp_path,
        )
