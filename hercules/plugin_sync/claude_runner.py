"""Replace the current process with claude, stripping secrets from the environment first."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

_SECRETS_TO_STRIP = frozenset({"HERCULES_GIT_TOKEN", "HERCULES_REPO_URL", "GIT_ASKPASS"})


def exec_claude(
    plugin_dir: Path,
    claude_dir: str | None,
    extra_args: list[str],
) -> None:
    """Replace the current process with claude.

    Strips secret environment variables before exec — they must not reach the
    claude process. Releases all locks BEFORE this function is called (no finally runs).
    """
    claude_path = shutil.which("claude")
    if not claude_path:
        print(
            "[hercules] 'claude' not found on PATH — try opening a new terminal or check your PATH",
            file=sys.stderr,
        )
        sys.exit(1)

    args = [claude_path, "--plugin-dir", str(plugin_dir), "--add-dir", str(plugin_dir)]

    claude_md = plugin_dir / "CLAUDE.md"
    if claude_md.exists():
        args += ["--append-system-prompt-file", str(claude_md)]

    args += extra_args

    env = _build_env(claude_dir)
    os.execvpe(claude_path, args, env)  # noqa: S606 — intentional process replacement


def _build_env(claude_dir: str | None) -> dict[str, str]:
    """Return a sanitised environment: secrets stripped, CLAUDE_CONFIG_DIR optionally set."""
    env = {k: v for k, v in os.environ.items() if k not in _SECRETS_TO_STRIP}
    if claude_dir:
        env["CLAUDE_CONFIG_DIR"] = claude_dir
    return env
