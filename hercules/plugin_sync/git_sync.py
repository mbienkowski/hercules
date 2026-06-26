"""Clone and pull the Hercules plugin repository."""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

_SYNC_TTL_SECONDS = 300  # pragma: no mutate

_VALID_URL_RE = re.compile(
    r"^(https://[^\s]+|git@[^:]+:[^\s]+)$"
)


def sync_plugin(
    clone_root: Path,
    repo_url: str,
    branch: str,
    ssh_key: str = "",  # pragma: no mutate
    git_token: str = "",  # pragma: no mutate
) -> None:
    """Ensure the plugin directory is up to date.

    Clones on first run; pulls if the TTL has elapsed on subsequent runs.
    Pull failures are non-fatal warnings — cached content is used.
    """
    _validate_repo_url(repo_url)

    if not _is_git_repo(clone_root):
        _clone(clone_root, repo_url, branch, ssh_key, git_token)
        return

    if not _ttl_elapsed(clone_root):
        return

    _pull(clone_root, branch, ssh_key, git_token)


def _validate_repo_url(url: str) -> None:
    if not _VALID_URL_RE.match(url):
        raise ValueError(
            f"Unsafe or unsupported repo URL: {url!r}. "  # pragma: no mutate
            "Must start with 'https://' or 'git@host:path'."  # pragma: no mutate
        )


def _clone(
    plugin_dir: Path,
    repo_url: str,
    branch: str,
    ssh_key: str,
    git_token: str,
) -> None:
    print(f"[hercules] Installing (branch: {branch})...", file=sys.stderr)  # pragma: no mutate
    env = _git_env(ssh_key)
    with _GitTokenAskpass(git_token) as askpass_script:
        if askpass_script:
            env["GIT_ASKPASS"] = askpass_script  # pragma: no mutate
        result = subprocess.run(
            ["git", "clone", "--quiet", "--branch", branch, repo_url, str(plugin_dir)],
            env=env,
            capture_output=False,  # pragma: no mutate
        )
    if result.returncode != 0:
        raise RuntimeError(f"git clone failed (exit {result.returncode})")  # pragma: no mutate
    _write_timestamp(plugin_dir)


def _pull(
    plugin_dir: Path,
    branch: str,
    ssh_key: str,
    git_token: str,
) -> None:
    env = _git_env(ssh_key)
    with _GitTokenAskpass(git_token) as askpass_script:
        if askpass_script:
            env["GIT_ASKPASS"] = askpass_script  # pragma: no mutate

        checkout = subprocess.run(
            ["git", "checkout", "--quiet", branch],
            cwd=plugin_dir,
            env=env,
            capture_output=True,  # pragma: no mutate
        )
        if checkout.returncode != 0:
            print(
                f"[hercules] Warning: branch {branch!r} not found, staying on current branch",  # pragma: no mutate
                file=sys.stderr,
            )

        pull = subprocess.run(
            ["git", "pull", "--ff-only", "--quiet"],
            cwd=plugin_dir,
            env=env,
            capture_output=True,  # pragma: no mutate
        )
    if pull.returncode != 0:
        print(
            f"[hercules] Warning: could not update plugins: {pull.stderr.decode()}",  # pragma: no mutate
            file=sys.stderr,
        )
        return  # non-fatal: use cached content

    _write_timestamp(plugin_dir)


def _git_env(ssh_key: str) -> dict[str, str]:
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    if ssh_key:
        env["GIT_SSH_COMMAND"] = (
            f"ssh -i {shlex.quote(ssh_key)} -o StrictHostKeyChecking=accept-new -o BatchMode=yes"
        )
    return env


class _GitTokenAskpass:
    """Context manager that writes a git ASKPASS script for token auth."""

    def __init__(self, git_token: str) -> None:
        self._token = git_token
        self._token_file: str | None = None  # pragma: no mutate
        self._script_file: str | None = None  # pragma: no mutate

    def __enter__(self) -> str | None:  # pragma: no mutate
        if not self._token:
            return None
        fd, self._token_file = tempfile.mkstemp(prefix="hercules-token-")  # pragma: no mutate
        os.close(fd)
        Path(self._token_file).write_text(self._token)  # mkstemp already creates at 0o600

        escaped = self._token_file.replace("'", "'\\''")
        script = f"#!/bin/sh\ncat '{escaped}'\n"  # pragma: no mutate
        fd2, self._script_file = tempfile.mkstemp(prefix="hercules-askpass-")  # pragma: no mutate
        os.close(fd2)
        Path(self._script_file).write_text(script)
        os.chmod(self._script_file, 0o700)
        return self._script_file

    def __exit__(self, *_: object) -> None:
        for f in (self._script_file, self._token_file):
            if f:
                try:
                    os.remove(f)
                except OSError:
                    pass


def _ttl_elapsed(plugin_dir: Path) -> bool:
    ts_file = plugin_dir / ".last-pull"
    if not ts_file.exists():
        return True
    try:
        ts = datetime.fromisoformat(ts_file.read_text().strip())
        elapsed = (datetime.now(timezone.utc) - ts).total_seconds()
        return elapsed >= _SYNC_TTL_SECONDS
    except (ValueError, OSError):
        return True


def _write_timestamp(plugin_dir: Path) -> None:
    ts_file = plugin_dir / ".last-pull"
    now = datetime.now(timezone.utc).isoformat()
    ts_file.write_text(now)


def _is_git_repo(directory: Path) -> bool:
    return (directory / ".git").exists()
