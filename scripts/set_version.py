#!/usr/bin/env python3
"""Write a single version into pyproject.toml and the plugin manifest (keeps them in sync).

Used by the release workflow after the next version is computed from conventional commits.
Edits in place via regex so the surrounding file formatting is preserved exactly.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def _replace_version(path: Path, pattern: str, version: str) -> None:
    text = path.read_text()
    new_text, n = re.subn(pattern, rf"\g<1>{version}\g<2>", text, count=1)
    if n != 1:
        raise SystemExit(f"set_version: expected exactly one version match in {path}, found {n}")
    path.write_text(new_text)


def set_version(version: str, root: Path = Path(".")) -> None:
    """Set *version* in pyproject.toml, dist/claude-code/.claude-plugin/plugin.json, and package.json under *root*."""
    _replace_version(root / "pyproject.toml", r'(?m)^(version\s*=\s*")[^"]+(")', version)
    _replace_version(
        root / "dist" / "claude-code" / ".claude-plugin" / "plugin.json",
        r'("version"\s*:\s*")[^"]+(")',
        version,
    )
    _replace_version(
        root / "package.json",
        r'("version"\s*:\s*")[^"]+(")',
        version,
    )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: set_version.py X.Y.Z")
    set_version(sys.argv[1])
