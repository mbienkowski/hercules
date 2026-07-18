#!/usr/bin/env python3
"""Write one version into every canonical version-bearing file (keeps them in sync).

Used by the release workflow after the next version is computed from conventional commits. The list
of files lives in one place — ``scripts/build/version_targets.py`` — shared with CI's ``validate``
job so the writer and the reader can never disagree about which manifests carry the version.
"""

from __future__ import annotations

import sys
from pathlib import Path

from scripts.build.version_targets import write_version


def set_version(version: str, root: Path = Path(".")) -> None:
    """Set *version* in every file of the canonical list under *root*."""
    write_version(version, root)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: set_version.py X.Y.Z")
    set_version(sys.argv[1])
