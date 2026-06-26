"""Hercules CLI entry point — a pure coordinator that delegates to plugin_sync submodules."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

from hercules.plugin_sync.config import (
    DEFAULT_REPO_URL,
    Config,
    config_path,
    ensure_config,
    load_config,
    run_wizard,
    save_config,
    save_token,
)
from hercules.plugin_sync.lock import Lock
from hercules.plugin_sync.git_sync import sync_plugin
from hercules.plugin_sync.claude_runner import exec_claude
from hercules.plugin_sync.self_update import run_self_update
from hercules.plugin_sync.onboarding import run_onboarding
from hercules.plugin_sync.claude_version import verify_claude_version

VERSION = "dev"  # pragma: no mutate

_BANNER = (
    "██╗  ██╗███████╗██████╗  ██████╗██╗   ██╗██╗     ███████╗███████╗\n"  # pragma: no mutate
    "██║  ██║██╔════╝██╔══██╗██╔════╝██║   ██║██║     ██╔════╝██╔════╝\n"  # pragma: no mutate
    "███████║█████╗  ██████╔╝██║     ██║   ██║██║     █████╗  ███████╗\n"  # pragma: no mutate
    "██╔══██║██╔══╝  ██╔══██╗██║     ██║   ██║██║     ██╔══╝  ╚════██║\n"  # pragma: no mutate
    "██║  ██║███████╗██║  ██║╚██████╗╚██████╔╝███████╗███████╗███████║\n"  # pragma: no mutate
    "╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚═════╝ ╚══════╝╚══════╝╚══════╝"  # pragma: no mutate
)


def _print_banner(version: str, branch: str) -> None:
    if os.environ.get("NO_COLOR") or not sys.stderr.isatty():  # pragma: no mutate
        return
    print(file=sys.stderr)
    for line in _BANNER.split("\n"):
        print(f"\x1b[38;5;214m{line}\x1b[0m", file=sys.stderr)  # pragma: no mutate
    label = f"version: branch {branch}" if branch != "main" else f"version: {version}"  # pragma: no mutate
    print(f"\n\x1b[38;5;242m  {label}\x1b[0m\n", file=sys.stderr)  # pragma: no mutate


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="hercules",  # pragma: no mutate
        description="Hercules — Claude Code plugin with AI-assisted delivery methodology",  # pragma: no mutate
    )
    parser.add_argument("-v", "--version", action="store_true", help="Print version and exit")  # pragma: no mutate
    parser.add_argument("-b", "--branch", default="main", help="Plugin git branch (default: main)")
    parser.add_argument("-c", "--claude-dir", dest="claude_dir", metavar="DIR",  # pragma: no mutate
                        help="Override CLAUDE_CONFIG_DIR for this session")  # pragma: no mutate
    parser.add_argument("--repo-url", dest="repo_url", metavar="URL",  # pragma: no mutate
                        help="Plugin repository URL")  # pragma: no mutate
    parser.add_argument("--ssh-key", dest="ssh_key", metavar="PATH",  # pragma: no mutate
                        help="SSH private key path")  # pragma: no mutate
    parser.add_argument("--git-token", dest="git_token", metavar="TOKEN",  # pragma: no mutate
                        help="HTTPS personal access token")  # pragma: no mutate
    parser.add_argument("--update", action="store_true", help="Upgrade Hercules via pipx")  # pragma: no mutate
    parser.add_argument("--setup", action="store_true", help="Run first-time setup wizard")  # pragma: no mutate
    parser.add_argument("--status", action="store_true", help="Show install status and exit")  # pragma: no mutate
    parser.add_argument("--uninstall", action="store_true", help="Print uninstall instructions")  # pragma: no mutate

    args, claude_args = parser.parse_known_args()

    if args.version:
        print(VERSION)
        return

    if args.uninstall:
        _print_uninstall()
        return

    if args.status:
        _print_status()
        return

    _print_banner(VERSION, args.branch)

    if args.update:
        run_self_update()
        return

    if args.setup:
        cfg = run_wizard(DEFAULT_REPO_URL)
        save_config(cfg)
        save_token(cfg.git_token)
        print(f"[hercules] Config saved to {config_path()}", file=sys.stderr)  # pragma: no mutate
        return

    if not shutil.which("git"):
        print("[hercules] Error: 'git' not found on PATH", file=sys.stderr)  # pragma: no mutate
        sys.exit(1)
    if not shutil.which("claude"):
        print(
            "[hercules] Error: 'claude' not found on PATH\n"  # pragma: no mutate
            "[hercules] Tip: try opening a new terminal or check your PATH",  # pragma: no mutate
            file=sys.stderr,
        )
        sys.exit(1)

    # Advisory only — warns if Claude Code is older than recommended, never blocks.
    verify_claude_version()

    clone_root = Path.home() / ".hercules"
    plugin_dir = clone_root / "plugin"
    lock_dir = Path(os.environ.get("TMPDIR", "/tmp")) / "hercules.lock"  # pragma: no mutate

    persisted = load_config()
    effective_url, ssh_key, git_token = _resolve_credentials(args, persisted)

    lock = Lock(lock_dir)
    acquired = lock.acquire()

    if acquired:
        try:
            sync_plugin(
                clone_root=clone_root,
                repo_url=effective_url,
                branch=args.branch,
                ssh_key=ssh_key,
                git_token=git_token,
            )
        except Exception as exc:
            lock.release()
            print(f"[hercules] Could not sync plugins: {exc}", file=sys.stderr)  # pragma: no mutate
            print("[hercules] Check your network connection and try again.", file=sys.stderr)  # pragma: no mutate
            sys.exit(1)
        lock.release()  # Must release BEFORE exec — no finally after exec
    else:
        print("[hercules] Another session is syncing plugins, skipping...", file=sys.stderr)  # pragma: no mutate

    if not plugin_dir.exists() and clone_root.exists():
        # plugin/ dir is missing but the repo root exists — re-clone into a clean state
        (clone_root / ".last-pull").unlink(missing_ok=True)
        try:
            sync_plugin(
                clone_root=clone_root,
                repo_url=effective_url,
                branch=args.branch,
                ssh_key=ssh_key,
                git_token=git_token,
            )
        except Exception as exc:
            print(f"[hercules] Recovery sync failed: {exc}", file=sys.stderr)  # pragma: no mutate

    if not plugin_dir.exists():
        print("[hercules] Error: plugin directory missing and could not be downloaded.", file=sys.stderr)  # pragma: no mutate
        print("[hercules] Check your network connection and try again.", file=sys.stderr)  # pragma: no mutate
        sys.exit(1)

    # The clone now exists, so it is safe to create the (gitignored) config file
    # inside ~/.hercules; then onboard once on first run.
    ensure_config()
    run_onboarding()

    exec_claude(plugin_dir=plugin_dir, claude_dir=args.claude_dir, extra_args=claude_args)


def _resolve_credentials(
    args: argparse.Namespace,
    cfg: Config,
) -> tuple[str, str, str]:
    """Return (effective_url, ssh_key, git_token) from CLI args, env vars, and config."""
    effective_url = (
        args.repo_url
        or os.environ.get("HERCULES_REPO_URL")
        or cfg.repo_url
        or DEFAULT_REPO_URL
    )
    ssh_key = args.ssh_key or cfg.ssh_key or ""
    git_token = (
        args.git_token
        or os.environ.get("HERCULES_GIT_TOKEN")
        or cfg.git_token
        or ""
    )
    return effective_url, ssh_key, git_token


def _print_uninstall() -> None:
    clone_root = Path.home() / ".hercules"
    print("To uninstall hercules, run the following commands:")  # pragma: no mutate
    print(f"\n  pipx uninstall hercules                         # if installed via pipx")  # pragma: no mutate
    print(f"  pip uninstall hercules --break-system-packages  # if installed via pip")  # pragma: no mutate
    print(f"  rm -rf {clone_root}\n")  # pragma: no mutate
    print("This removes the plugin clone, config, and credentials.")  # pragma: no mutate


def _print_status() -> None:
    """Print install status, derived from the real sources (no duplicated state)."""
    clone_root = Path.home() / ".hercules"
    cfg = load_config()
    initialized = (clone_root / ".git").exists()
    last_pull = clone_root / ".last-pull"
    last_sync = last_pull.read_text().strip() if last_pull.exists() else "never"  # pragma: no mutate
    onboarded = cfg.onboarded_at or "no"  # pragma: no mutate
    print("Hercules status:")  # pragma: no mutate
    print(f"  home:        {clone_root}")  # pragma: no mutate
    print(f"  initialized: {'yes' if initialized else 'no'}")  # pragma: no mutate
    print(f"  onboarded:   {onboarded}")  # pragma: no mutate
    print(f"  last sync:   {last_sync}")  # pragma: no mutate
