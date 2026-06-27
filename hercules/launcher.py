"""Thin branded `hercules` launcher.

The plugin is installed and updated via the native Claude Code marketplace; this module exists only
to keep the `hercules` entry point — it execs `claude`, optionally isolating the Claude config
directory (`--claude-dir` → `CLAUDE_CONFIG_DIR`) so several setups can coexist on one machine. All
other arguments are forwarded verbatim to `claude`.
"""

from __future__ import annotations

import os
import shutil
import sys

# Stripped from the child environment so they never reach claude (harmless if unset).
_SECRETS_TO_STRIP = frozenset({"HERCULES_GIT_TOKEN", "HERCULES_REPO_URL", "GIT_ASKPASS"})


def _check_python_floor(version_info: tuple = None) -> None:
    """Exit 1 if running under Python < 3.9 (re-homed from the old `__main__` gate)."""
    vi = version_info if version_info is not None else sys.version_info
    if vi < (3, 9):
        print(
            f"Hercules requires Python 3.9 or later. "  # pragma: no mutate
            f"You have Python {vi[0]}.{vi[1]}.",  # pragma: no mutate
            file=sys.stderr,
        )
        sys.exit(1)


def _parse_args(argv: list[str]) -> tuple[str | None, list[str]]:
    """Pull out `--claude-dir/-c DIR` (and `--claude-dir=DIR`); forward the rest to claude."""
    claude_dir = None
    rest: list[str] = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("--claude-dir", "-c"):
            i += 1
            if i >= len(argv):
                print("[hercules] --claude-dir requires a directory argument", file=sys.stderr)  # pragma: no mutate
                sys.exit(1)
            claude_dir = argv[i]
        elif arg.startswith("--claude-dir="):
            claude_dir = arg.split("=", 1)[1]
        else:
            rest.append(arg)
        i += 1
    return claude_dir, rest


def _build_env(claude_dir: str | None) -> dict[str, str]:
    """Sanitised child env: secrets stripped; CLAUDE_CONFIG_DIR set when requested."""
    env = {k: v for k, v in os.environ.items() if k not in _SECRETS_TO_STRIP}
    if claude_dir:
        env["CLAUDE_CONFIG_DIR"] = claude_dir
    return env


def main(argv: list[str] | None = None) -> None:
    _check_python_floor()
    args = list(sys.argv[1:] if argv is None else argv)

    if args and args[0] in ("-v", "--version"):
        try:
            from importlib.metadata import version

            print(version("hercules"))
        except Exception:  # pragma: no cover - fallback only
            print("dev")
        return

    claude_path = shutil.which("claude")
    if not claude_path:
        print(
            "[hercules] 'claude' not found on PATH — install Claude Code, then retry.",  # pragma: no mutate
            file=sys.stderr,
        )
        sys.exit(1)

    claude_dir, rest = _parse_args(args)
    env = _build_env(claude_dir)
    os.execvpe(claude_path, [claude_path, *rest], env)  # noqa: S606 — intentional process replacement
