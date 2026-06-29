#!/usr/bin/env python3
"""Generate a CHANGELOG entry from git log and write it to CHANGELOG.md.

Used by the release workflow. Reads NEW_TAG, PREV_TAG, and IS_FIRST from the
environment; PREV_TAG is empty on the first release (no previous tags).
"""

from __future__ import annotations

import os
import subprocess
from datetime import date
from pathlib import Path


def get_commits_since(prev_tag: str) -> list[str]:
    """Return all commit subjects reachable from HEAD but not from prev_tag."""
    rev_range = f"{prev_tag}..HEAD" if prev_tag else "HEAD"
    out = subprocess.run(
        ["git", "log", rev_range, "--pretty=format:%s", "--no-merges"],
        capture_output=True, text=True, check=True,
    ).stdout
    return [
        line.strip()
        for line in out.splitlines()
        if line.strip() and not line.strip().startswith("chore(release):")
    ]


def format_entry(new_tag: str, commits: list[str]) -> str:
    today = date.today().isoformat()
    header = f"## {new_tag} ({today})"
    if not commits:
        return f"{header}\n\n"
    body = "\n".join(f"* {c}" for c in commits)
    return f"{header}\n\n{body}\n\n"


def update_changelog(
    new_tag: str,
    prev_tag: str,
    is_first: bool,
    path: str = "CHANGELOG.md",
    *,
    commits: list[str] | None = None,
) -> None:
    """Write a new release entry to the changelog at *path*.

    First release: overwrites the file (clears stale entries).
    Subsequent releases: prepends the entry, keeping history below.
    Pass *commits* to skip the git-log call (useful in tests).
    """
    if commits is None:
        commits = get_commits_since(prev_tag)
    entry = format_entry(new_tag, commits)
    target = Path(path)
    if is_first:
        target.write_text(entry)
    else:
        existing = target.read_text() if target.exists() else ""
        target.write_text(entry + existing)


if __name__ == "__main__":
    update_changelog(
        new_tag=os.environ["NEW_TAG"],
        prev_tag=os.environ.get("PREV_TAG", ""),
        is_first=os.environ.get("IS_FIRST", "false").lower() == "true",
    )
