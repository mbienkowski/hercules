"""Detect the installed Claude Code version and warn (never block) when it is
below the minimum Hercules recommends.

This is deliberately *advisory*: a future change to ``claude --version`` output,
a missing binary, or any subprocess error must never stop Hercules from
launching. Every failure path returns quietly; only a positively-parsed,
below-minimum version produces a one-time warning.
"""

from __future__ import annotations

import re
import subprocess
import sys
from typing import Callable, Optional, Tuple

from hercules.plugin_sync.config import load_config, save_config

MIN_CLAUDE_VERSION = (2, 1, 128)  # pragma: no mutate
_UPGRADE_URL = "https://docs.claude.com/claude-code"  # pragma: no mutate

_VERSION_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")

Version = Tuple[int, int, int]  # pragma: no mutate


def parse_claude_version(output: str) -> Optional[Version]:
    """Extract the first ``X.Y.Z`` from ``claude --version`` output, or None.

    Tolerates a leading ``v``, surrounding text, and parentheses. A two-part
    string (``2.1``) or non-numeric output yields None.
    """
    match = _VERSION_RE.search(output)
    if not match:
        return None
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def meets_minimum(version: Version, minimum: Version = MIN_CLAUDE_VERSION) -> bool:
    """True when ``version`` is at least ``minimum`` (tuple comparison)."""
    return version >= minimum


def verify_claude_version(
    run: Optional[Callable] = None,
    min_version: Version = MIN_CLAUDE_VERSION,
) -> None:
    """Warn once if the installed Claude Code is older than ``min_version``.

    Never raises and never exits. ``run`` is injectable for testing; it defaults
    to ``subprocess.run`` resolved at call time (so it can be monkeypatched).
    """
    if run is None:
        run = subprocess.run
    try:
        result = run(
            ["claude", "--version"],  # pragma: no mutate
            capture_output=True,
            text=True,
            timeout=10,  # pragma: no mutate
        )
    except Exception:  # binary missing, timeout, OS error — all non-fatal
        return

    output = (getattr(result, "stdout", "") or "") + (getattr(result, "stderr", "") or "")  # pragma: no mutate
    version = parse_claude_version(output)
    if version is None:
        return
    if meets_minimum(version, min_version):
        return
    _warn_once(version, min_version)


def _warn_once(version: Version, min_version: Version) -> None:
    """Print the recommendation once per detected version (throttled via config)."""
    detected = ".".join(str(part) for part in version)
    required = ".".join(str(part) for part in min_version)

    cfg = load_config()
    if cfg.options.get("claude_version_warned") == detected:
        return

    print(
        f"[hercules] Claude Code {detected} detected; Hercules recommends "  # pragma: no mutate
        f">= {required}. Some features may not work — upgrade: {_UPGRADE_URL}",  # pragma: no mutate
        file=sys.stderr,
    )
    cfg.options["claude_version_warned"] = detected
    save_config(cfg)
