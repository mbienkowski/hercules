"""Tests for the git sync module — URL validation, TTL checks, and timestamp handling."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from hercules.plugin_sync.git_sync import (
    _git_env,
    _is_git_repo,
    _ttl_elapsed,
    _validate_repo_url,
    _write_timestamp,
)


def test_https_url_is_accepted():
    """A standard HTTPS GitHub URL must be accepted without raising."""
    # Given / When / Then
    _validate_repo_url("https://github.com/mbienkowski/hercules.git")


def test_git_at_ssh_url_is_accepted():
    """An SSH git@ URL must be accepted."""
    # Given / When / Then
    _validate_repo_url("git@github.com:mbienkowski/hercules.git")


def test_ext_double_colon_scheme_is_rejected():
    """ext:: URLs are a git remote-helper exploit vector and must be rejected."""
    # Given / When / Then
    with pytest.raises(ValueError, match="Unsafe"):
        _validate_repo_url("ext::sh -c 'rm -rf /'")


def test_file_scheme_url_is_rejected():
    """file:// URLs allow arbitrary local path access and must be rejected."""
    # Given / When / Then
    with pytest.raises(ValueError, match="Unsafe"):
        _validate_repo_url("file:///etc/passwd")


def test_is_git_repo_returns_true_when_dot_git_exists(tmp_path):
    """A directory with a .git entry is a git repository."""
    # Given
    (tmp_path / ".git").mkdir()

    # When / Then
    assert _is_git_repo(tmp_path) is True


def test_is_git_repo_returns_false_when_dot_git_is_absent(tmp_path):
    """A plain directory without .git is not a git repository."""
    # Given / When / Then
    assert _is_git_repo(tmp_path) is False


def test_ttl_elapsed_returns_true_when_last_pull_file_is_missing(tmp_path):
    """No timestamp file means we have never synced — TTL is always elapsed."""
    # Given / When / Then
    assert _ttl_elapsed(tmp_path) is True


def test_ttl_elapsed_returns_false_when_last_pull_is_recent(tmp_path):
    """A recent pull timestamp means the TTL has not elapsed."""
    # Given
    recent = datetime.now(timezone.utc) - timedelta(seconds=10)
    (tmp_path / ".last-pull").write_text(recent.isoformat())

    # When / Then
    assert _ttl_elapsed(tmp_path) is False


def test_ttl_elapsed_returns_true_when_last_pull_is_old(tmp_path):
    """A pull timestamp older than 30 minutes means the TTL has elapsed."""
    # Given
    old = datetime.now(timezone.utc) - timedelta(minutes=40)
    (tmp_path / ".last-pull").write_text(old.isoformat())

    # When / Then
    assert _ttl_elapsed(tmp_path) is True


def test_write_timestamp_creates_parseable_file(tmp_path):
    """The timestamp file written by _write_timestamp must parse back as a UTC datetime."""
    # Given / When
    _write_timestamp(tmp_path)
    content = (tmp_path / ".last-pull").read_text().strip()

    # Then
    parsed = datetime.fromisoformat(content)
    assert parsed.tzinfo is not None  # must be timezone-aware


def test_git_env_always_sets_no_interactive_prompt(monkeypatch):
    """GIT_TERMINAL_PROMPT=0 must always be set to prevent interactive fallback in CI."""
    # Given
    monkeypatch.delenv("GIT_TERMINAL_PROMPT", raising=False)

    # When
    env = _git_env(ssh_key="")

    # Then
    assert env["GIT_TERMINAL_PROMPT"] == "0"


def test_git_env_sets_ssh_command_when_key_is_provided():
    """When an SSH key path is given, GIT_SSH_COMMAND must be set in the environment."""
    # Given / When
    env = _git_env(ssh_key="/home/user/.ssh/id_ed25519")

    # Then
    assert "GIT_SSH_COMMAND" in env
    assert "/home/user/.ssh/id_ed25519" in env["GIT_SSH_COMMAND"]


def test_git_env_does_not_set_ssh_command_when_no_key():
    """When no SSH key is given, GIT_SSH_COMMAND must not be set."""
    # Given / When
    env = _git_env(ssh_key="")

    # Then
    assert "GIT_SSH_COMMAND" not in env


def test_askpass_context_creates_executable_script_for_token_auth(tmp_path):
    """With a non-empty token, _askpass_context must write a script file and clean it up on exit."""
    # Given
    from hercules.plugin_sync.git_sync import _GitTokenAskpass as _askpass_context
    import os

    # When
    captured_script = None
    with _askpass_context("my-secret-token") as script_path:
        captured_script = script_path
        assert script_path is not None
        assert os.path.exists(script_path)
        assert os.access(script_path, os.X_OK)

    # Then — files are cleaned up on exit
    assert not os.path.exists(captured_script)


def test_askpass_context_returns_none_when_no_token():
    """With an empty token, _askpass_context must yield None and not create any files."""
    # Given
    from hercules.plugin_sync.git_sync import _GitTokenAskpass as _askpass_context

    # When / Then
    with _askpass_context("") as script_path:
        assert script_path is None


def test_askpass_context_cleanup_survives_oserror_on_remove():
    """If os.remove raises OSError during cleanup, __exit__ must not propagate the error.

    A token auth failure on cleanup must never crash the caller.
    """
    # Given
    from hercules.plugin_sync.git_sync import _GitTokenAskpass as _askpass_context
    from unittest.mock import patch

    # When / Then — no exception must escape the context manager
    with patch("os.remove", side_effect=OSError("read-only filesystem")):
        try:
            with _askpass_context("my-secret-token") as script_path:
                assert script_path is not None
        except OSError:
            pytest.fail("_askpass_context.__exit__ propagated OSError — must be silent")


def test_ttl_elapsed_returns_true_when_timestamp_file_is_corrupted(tmp_path):
    """A corrupt timestamp file must be treated as elapsed so we do a fresh sync."""
    # Given
    (tmp_path / ".last-pull").write_text("not-a-valid-iso-date")

    # When / Then
    assert _ttl_elapsed(tmp_path) is True


def test_ttl_elapsed_returns_false_at_exactly_1799_seconds(tmp_path, monkeypatch):
    """At 1799 seconds old (< TTL), the TTL has not yet elapsed — distinguishes >= from >."""
    import hercules.plugin_sync.git_sync as gs_mod

    fixed_now = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
    ts = fixed_now - timedelta(seconds=1799)
    (tmp_path / ".last-pull").write_text(ts.isoformat())

    class _MockDatetime:
        @staticmethod
        def now(tz=None):
            return fixed_now
        @staticmethod
        def fromisoformat(s):
            return datetime.fromisoformat(s)

    monkeypatch.setattr(gs_mod, "datetime", _MockDatetime)
    assert gs_mod._ttl_elapsed(tmp_path) is False


def test_ttl_elapsed_returns_true_at_exactly_1800_seconds(tmp_path, monkeypatch):
    """At exactly 1800 seconds (== TTL), elapsed >= TTL is True; distinguishes >= from >."""
    import hercules.plugin_sync.git_sync as gs_mod

    fixed_now = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
    ts = fixed_now - timedelta(seconds=1800)
    (tmp_path / ".last-pull").write_text(ts.isoformat())

    class _MockDatetime:
        @staticmethod
        def now(tz=None):
            return fixed_now
        @staticmethod
        def fromisoformat(s):
            return datetime.fromisoformat(s)

    monkeypatch.setattr(gs_mod, "datetime", _MockDatetime)
    assert gs_mod._ttl_elapsed(tmp_path) is True


def test_clone_calls_git_with_correct_args(tmp_path):
    """_clone must invoke 'git clone --quiet --branch <branch> <url> <dir>'."""
    from unittest.mock import MagicMock, call, patch
    from hercules.plugin_sync.git_sync import _clone

    mock_result = MagicMock()
    mock_result.returncode = 0

    with patch("subprocess.run", return_value=mock_result) as mock_run, \
         patch("hercules.plugin_sync.git_sync._write_timestamp"):
        _clone(tmp_path, "https://github.com/user/repo.git", "main", "", "")

    args = mock_run.call_args[0][0]
    assert args[0] == "git"
    assert "clone" in args
    assert "--branch" in args
    assert "main" in args
    assert "https://github.com/user/repo.git" in args


def test_clone_raises_on_nonzero_exit(tmp_path):
    """_clone must raise RuntimeError when git clone returns a non-zero exit code."""
    from unittest.mock import MagicMock, patch
    from hercules.plugin_sync.git_sync import _clone

    mock_result = MagicMock()
    mock_result.returncode = 1

    with patch("subprocess.run", return_value=mock_result):
        with pytest.raises(RuntimeError, match="git clone failed"):
            _clone(tmp_path, "https://github.com/user/repo.git", "main", "", "")


def test_clone_writes_timestamp_on_success(tmp_path):
    """_clone must write the .last-pull timestamp after a successful clone."""
    from unittest.mock import MagicMock, patch
    from hercules.plugin_sync.git_sync import _clone

    mock_result = MagicMock()
    mock_result.returncode = 0

    with patch("subprocess.run", return_value=mock_result):
        _clone(tmp_path, "https://github.com/user/repo.git", "main", "", "")

    assert (tmp_path / ".last-pull").exists()


def test_pull_runs_checkout_then_pull(tmp_path):
    """_pull must run 'git checkout <branch>' followed by 'git pull --ff-only'."""
    from unittest.mock import MagicMock, call, patch
    from hercules.plugin_sync.git_sync import _pull

    mock_ok = MagicMock()
    mock_ok.returncode = 0
    mock_ok.stderr = b""

    calls_made = []

    def side_effect(cmd, **kwargs):
        calls_made.append(cmd)
        return mock_ok

    with patch("subprocess.run", side_effect=side_effect):
        _pull(tmp_path, "main", "", "")

    assert any("checkout" in c for c in calls_made)
    assert any("pull" in c for c in calls_made)


def test_askpass_token_file_has_restricted_permissions():
    """The token file written by _askpass_context must have 0o600 permissions."""
    import os
    import stat
    from hercules.plugin_sync.git_sync import _GitTokenAskpass as _askpass_context

    with _askpass_context("secret-token") as script_path:
        token_file_mode = None
        # find the token file via the script content
        script_content = open(script_path).read()
        # script is: #!/bin/sh\ncat '<token_file_path>'\n
        import re as _re
        m = _re.search(r"cat '(.+)'", script_content)
        if m:
            token_file_mode = stat.S_IMODE(os.stat(m.group(1)).st_mode)

    assert token_file_mode == 0o600


def test_askpass_script_file_has_executable_permissions():
    """The ASKPASS script written by _askpass_context must have 0o700 permissions."""
    import os
    import stat
    from hercules.plugin_sync.git_sync import _GitTokenAskpass as _askpass_context

    with _askpass_context("secret-token") as script_path:
        mode = stat.S_IMODE(os.stat(script_path).st_mode)

    assert mode == 0o700


def test_pull_continues_after_checkout_failure(tmp_path):
    """_pull must continue to run git pull even when checkout returns non-zero (just warns)."""
    from unittest.mock import MagicMock, patch
    from hercules.plugin_sync.git_sync import _pull

    checkout_fail = MagicMock()
    checkout_fail.returncode = 1
    checkout_fail.stderr = b""

    pull_ok = MagicMock()
    pull_ok.returncode = 0
    pull_ok.stderr = b""

    call_num = [0]

    def side_effect(cmd, **kwargs):
        call_num[0] += 1
        if "checkout" in cmd:
            return checkout_fail
        return pull_ok

    with patch("subprocess.run", side_effect=side_effect):
        _pull(tmp_path, "feat/new", "", "")

    # pull must have been called even after checkout failure
    assert call_num[0] == 2


def test_pull_does_not_write_timestamp_on_failure(tmp_path):
    """_pull must not write .last-pull when git pull fails (non-zero returncode)."""
    from unittest.mock import MagicMock, patch
    from hercules.plugin_sync.git_sync import _pull

    ok = MagicMock()
    ok.returncode = 0
    ok.stderr = b""

    fail = MagicMock()
    fail.returncode = 1
    fail.stderr = b"error"

    def side_effect(cmd, **kwargs):
        if "pull" in cmd:
            return fail
        return ok

    with patch("subprocess.run", side_effect=side_effect):
        _pull(tmp_path, "main", "", "")

    assert not (tmp_path / ".last-pull").exists()


def test_git_env_sets_correct_ssh_command_format():
    """GIT_SSH_COMMAND must include -i flag and StrictHostKeyChecking=accept-new."""
    env = _git_env(ssh_key="/home/user/.ssh/id_ed25519")
    cmd = env["GIT_SSH_COMMAND"]
    # Must start with 'ssh -i' (not 'XXssh...' mutations)
    assert cmd.startswith("ssh -i")
    assert "StrictHostKeyChecking=accept-new" in cmd
    assert "BatchMode=yes" in cmd


def test_git_env_escapes_single_quotes_in_ssh_key_path():
    """A key path with single quotes must be shell-quoted in GIT_SSH_COMMAND."""
    env = _git_env(ssh_key="/home/user/my'key.pem")
    cmd = env["GIT_SSH_COMMAND"]
    # shlex.quote escapes ' as '"'"' (close single-quote, double-quoted literal, reopen)
    assert "my'\"'\"'key.pem" in cmd
    # The raw unescaped form (single quote immediately followed by 'k') must not appear
    assert "my'key.pem" not in cmd


def test_pull_warns_when_checkout_fails(tmp_path, capsys):
    """_pull must print a warning when checkout returns non-zero."""
    from unittest.mock import MagicMock, patch
    from hercules.plugin_sync.git_sync import _pull

    checkout_fail = MagicMock()
    checkout_fail.returncode = 2  # non-zero, not 1, to distinguish != 0 from != 1
    checkout_fail.stderr = b""

    pull_ok = MagicMock()
    pull_ok.returncode = 0
    pull_ok.stderr = b""

    def side_effect(cmd, **kwargs):
        if "checkout" in cmd:
            return checkout_fail
        return pull_ok

    with patch("subprocess.run", side_effect=side_effect):
        _pull(tmp_path, "main", "", "")

    err = capsys.readouterr().err
    assert "Warning" in err or "branch" in err.lower()


def test_pull_does_not_warn_when_checkout_succeeds(tmp_path, capsys):
    """_pull must NOT print a warning when checkout returns 0."""
    from unittest.mock import MagicMock, patch
    from hercules.plugin_sync.git_sync import _pull

    ok = MagicMock()
    ok.returncode = 0
    ok.stderr = b""

    with patch("subprocess.run", return_value=ok):
        _pull(tmp_path, "main", "", "")

    err = capsys.readouterr().err
    assert "Warning" not in err or "branch" not in err.lower()


# ---------------------------------------------------------------------------
# T6 — GIT_ASKPASS must reach subprocess.run
# ---------------------------------------------------------------------------

def test_clone_passes_git_askpass_env_to_subprocess_when_token_given(tmp_path):
    """_clone must set GIT_ASKPASS in the env dict passed to subprocess.run when a token is given."""
    from unittest.mock import MagicMock, patch
    from hercules.plugin_sync.git_sync import _clone

    captured_env = {}
    mock_result = MagicMock()
    mock_result.returncode = 0

    def capture_env(cmd, env, **kwargs):
        captured_env.update(env)
        return mock_result

    with patch("subprocess.run", side_effect=capture_env), \
         patch("hercules.plugin_sync.git_sync._write_timestamp"):
        _clone(tmp_path, "https://github.com/user/repo.git", "main", "", "my-token")

    assert "GIT_ASKPASS" in captured_env


def test_pull_passes_git_askpass_env_to_subprocess_when_token_given(tmp_path):
    """_pull must set GIT_ASKPASS in the env dict passed to subprocess.run when a token is given."""
    from unittest.mock import MagicMock, patch
    from hercules.plugin_sync.git_sync import _pull

    captured_envs = []
    mock_ok = MagicMock()
    mock_ok.returncode = 0
    mock_ok.stderr = b""

    def capture_env(cmd, env=None, **kwargs):
        if env:
            captured_envs.append(dict(env))
        return mock_ok

    with patch("subprocess.run", side_effect=capture_env):
        _pull(tmp_path, "main", "", "my-token")

    assert any("GIT_ASKPASS" in e for e in captured_envs)


# ---------------------------------------------------------------------------
# force refresh (Stage 4) — bypasses the TTL on demand (hercules --sync)
# ---------------------------------------------------------------------------

def test_force_true_updates_even_when_ttl_is_fresh(tmp_path):
    """force=True must run the update path even if the last pull was just now."""
    from unittest.mock import patch
    import hercules.plugin_sync.git_sync as gs
    (tmp_path / ".git").mkdir()
    recent = datetime.now(timezone.utc) - timedelta(seconds=5)
    (tmp_path / ".last-pull").write_text(recent.isoformat())

    with patch.object(gs, "_pull") as mock_pull:
        gs.sync_plugin(
            clone_root=tmp_path,
            repo_url="https://github.com/mbienkowski/hercules.git",
            branch="main",
            force=True,
        )
    mock_pull.assert_called_once()


def test_force_false_skips_update_when_ttl_is_fresh(tmp_path):
    """force=False (default) must respect the TTL and skip the update."""
    from unittest.mock import patch
    import hercules.plugin_sync.git_sync as gs
    (tmp_path / ".git").mkdir()
    recent = datetime.now(timezone.utc) - timedelta(seconds=5)
    (tmp_path / ".last-pull").write_text(recent.isoformat())

    with patch.object(gs, "_pull") as mock_pull:
        gs.sync_plugin(
            clone_root=tmp_path,
            repo_url="https://github.com/mbienkowski/hercules.git",
            branch="main",
            force=False,
        )
    mock_pull.assert_not_called()
