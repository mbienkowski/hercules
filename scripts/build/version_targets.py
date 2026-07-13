"""The single canonical list of version-bearing files.

Consumed by **both** ``scripts/set_version.py`` (writer) and CI's ``validate`` job (reader) + the
release tag check, so writer and reader can never drift (CoC "pin both ends / one canonical list").
Adding a manifest = one entry here, no new code. ``marketplace.json`` stays version-less until it
needs one — then it is one more entry.
"""
from __future__ import annotations

import re
from pathlib import Path

# (relative path, format) — the format selects the write/read regex pair below.
VERSION_TARGETS: list[tuple[str, str]] = [
    ("pyproject.toml", "toml"),
    ("dist/claude-code/.claude-plugin/plugin.json", "json"),
    ("package.json", "json"),
]

# (write_pattern with (prefix)(suffix) groups, read_pattern capturing the value)
_PATTERNS = {
    "toml": (r'(?m)^(version\s*=\s*")[^"]+(")', r'(?m)^version\s*=\s*"([^"]+)"'),
    "json": (r'("version"\s*:\s*")[^"]+(")', r'"version"\s*:\s*"([^"]+)"'),
}


def write_version(version: str, root: Path = Path(".")) -> None:
    """Write *version* into every canonical file (in place, preserving formatting)."""
    for rel, fmt in VERSION_TARGETS:
        path = root / rel
        text = path.read_text(encoding="utf-8")
        new, n = re.subn(_PATTERNS[fmt][0], rf"\g<1>{version}\g<2>", text, count=1)
        if n != 1:
            raise SystemExit(  # pragma: no mutate - message text only
                f"version_targets: expected one version match in {rel}, found {n}"
            )
        path.write_text(new, encoding="utf-8")


def read_versions(root: Path = Path(".")) -> dict[str, str]:
    """Return ``{relative_path: version}`` read from every canonical file."""
    out: dict[str, str] = {}
    for rel, fmt in VERSION_TARGETS:
        m = re.search(_PATTERNS[fmt][1], (root / rel).read_text(encoding="utf-8"))
        if not m:
            raise SystemExit(f"version_targets: no version found in {rel}")  # pragma: no mutate
        out[rel] = m.group(1)
    return out


def check_in_sync(root: Path = Path("."), *, expected: str | None = None) -> None:
    """Raise ``SystemExit`` if the canonical files disagree, or (if given) differ from *expected*."""
    versions = read_versions(root)
    distinct = set(versions.values())
    if len(distinct) != 1:
        raise SystemExit(f"version drift across files: {versions}")  # pragma: no mutate
    actual = distinct.pop()
    if expected is not None and actual != expected:
        raise SystemExit(  # pragma: no mutate - message text only
            f"version {actual!r} != expected {expected!r} (files: {versions})"
        )
