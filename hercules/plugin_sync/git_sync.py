"""Clone and pull the Hercules plugin repository."""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

_SYNC_TTL_SECONDS = 1800  # pragma: no mutate  (30 minutes)

_VALID_URL_RE = re.compile(
    r"^(https://[^\s]+|git@[^:]+:[^\s]+)$"
)

# A stable release tag: vX.Y.Z or X.Y.Z (no pre-release suffix).
_SEMVER_TAG_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")

_FALLBACK_BRANCH = "main"  # pragma: no mutate


class SyncMode(Enum):
    """How the plugin clone tracks upstream.

    BRANCH  — follow a named branch (``--branch``); bleeding edge / testing.
    RELEASE — follow the latest stable release tag; the default for users.
    """

    BRANCH = "branch"
    RELEASE = "release"


def sync_plugin(
    clone_root: Path,
    repo_url: str,
    branch: Optional[str] = None,
    ssh_key: str = "",  # pragma: no mutate
    git_token: str = "",  # pragma: no mutate
    force: bool = False,  # pragma: no mutate
    mode: SyncMode = SyncMode.BRANCH,
) -> None:
    """Ensure the plugin directory is up to date.

    In ``RELEASE`` mode the clone tracks the latest stable release tag; in
    ``BRANCH`` mode it follows ``branch``. Clones on first run; updates if the
    TTL has elapsed (or ``force=True``, e.g. ``hercules --sync``). Update
    failures are non-fatal warnings — cached content is used.
    """
    _validate_repo_url(repo_url)

    if not _is_git_repo(clone_root):
        ref = _resolve_clone_ref(mode, branch, repo_url, ssh_key, git_token)
        _clone(clone_root, repo_url, ref, ssh_key, git_token)
        return

    if not force and not _ttl_elapsed(clone_root):
        return

    if mode is SyncMode.RELEASE:
        _update_to_latest_release(clone_root, repo_url, ssh_key, git_token)
    else:
        _pull(clone_root, branch, ssh_key, git_token)


def _resolve_clone_ref(
    mode: SyncMode,
    branch: Optional[str],
    repo_url: str,
    ssh_key: str,
    git_token: str,
) -> str:
    """Decide which git ref to clone: the latest release tag, or a branch."""
    if mode is SyncMode.BRANCH:
        return branch or _FALLBACK_BRANCH

    tag = _resolve_latest_release(repo_url, ssh_key, git_token)
    if tag:
        return tag
    print(
        f"[hercules] No release found yet — tracking {_FALLBACK_BRANCH!r}.",  # pragma: no mutate
        file=sys.stderr,
    )
    return _FALLBACK_BRANCH


def _latest_release_tag(text: str) -> Optional[str]:
    """Return the highest stable semver tag in ``text``, or None.

    Accepts both ``git ls-remote --tags`` lines (``<sha>\\trefs/tags/v1.2.3``,
    possibly peeled with ``^{}``) and bare ``git tag -l`` names. Pre-release
    tags (e.g. ``v2.0.0-rc1``) are skipped; ordering is numeric, not lexical.
    """
    best_version = None
    best_name = None
    for raw in text.splitlines():
        token = raw.strip()
        if not token:
            continue
        if "\t" in token:
            token = token.split("\t", 1)[1].strip()
        if token.startswith("refs/tags/"):
            token = token[len("refs/tags/"):]
        if token.endswith("^{}"):
            token = token[: -len("^{}")]
        match = _SEMVER_TAG_RE.match(token)
        if not match:
            continue
        version = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
        if best_version is None or version > best_version:
            best_version = version
            best_name = token
    return best_name


def _resolve_latest_release(
    repo_url: str,
    ssh_key: str = "",
    git_token: str = "",
) -> Optional[str]:
    """Query the remote's tags and return the latest stable release, or None."""
    env = _git_env(ssh_key)
    with _GitTokenAskpass(git_token) as askpass_script:
        if askpass_script:
            env["GIT_ASKPASS"] = askpass_script  # pragma: no mutate
        result = subprocess.run(
            ["git", "ls-remote", "--tags", repo_url],  # pragma: no mutate
            env=env,
            capture_output=True,
            text=True,
        )
    if result.returncode != 0:
        return None
    return _latest_release_tag(result.stdout)


def _update_to_latest_release(
    plugin_dir: Path,
    repo_url: str,
    ssh_key: str,
    git_token: str,
) -> None:
    """Fetch tags and check out the latest release (detached). Non-fatal on failure."""
    env = _git_env(ssh_key)
    with _GitTokenAskpass(git_token) as askpass_script:
        if askpass_script:
            env["GIT_ASKPASS"] = askpass_script  # pragma: no mutate

        fetch = subprocess.run(
            ["git", "fetch", "--tags", "--quiet", "--force"],  # pragma: no mutate
            cwd=plugin_dir,
            env=env,
            capture_output=True,
        )
        if fetch.returncode != 0:
            print(
                f"[hercules] Warning: could not fetch tags: {fetch.stderr.decode()}",  # pragma: no mutate
                file=sys.stderr,
            )
            return

        listing = subprocess.run(
            ["git", "tag", "-l"],  # pragma: no mutate
            cwd=plugin_dir,
            env=env,
            capture_output=True,
            text=True,
        )
        tag = _latest_release_tag(listing.stdout) if listing.returncode == 0 else None
        if not tag:
            print(
                f"[hercules] No release found yet — staying on the current ref.",  # pragma: no mutate
                file=sys.stderr,
            )
            return

        checkout = subprocess.run(
            ["git", "checkout", "--quiet", tag],  # pragma: no mutate
            cwd=plugin_dir,
            env=env,
            capture_output=True,
        )
    if checkout.returncode != 0:
        print(
            f"[hercules] Warning: could not check out {tag}: {checkout.stderr.decode()}",  # pragma: no mutate
            file=sys.stderr,
        )
        return

    _write_timestamp(plugin_dir)


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
