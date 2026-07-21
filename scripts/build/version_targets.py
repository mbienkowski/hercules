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
# Only files that MUST carry a literal version belong here: ``pyproject.toml`` (setuptools reads it at
# build) and ``package.json`` (npm/OpenCode read it as-is). ``pyproject.toml`` is the canonical source
# (``read_canonical_version``); ``package.json`` is cross-checked against it every CI ``validate`` run.
# The plugin manifests (claude-code, cursor) are deliberately NOT here: they're build *outputs'* sources
# that carry a ``${version}`` token, injected from the canonical version at build (``emit.copy_versioned``)
# — so a human never sees a literal version in ``src/targets/<eco>/plugin.json`` to forget to bump.
VERSION_TARGETS: list[tuple[str, str]] = [
    ("pyproject.toml", "toml"),
    ("package.json", "json"),
]

# (write_pattern with (prefix)(suffix) groups, read_pattern capturing the value)
_PATTERNS = {
    "toml": (r'(?m)^(version\s*=\s*")[^"]+(")', r'(?m)^version\s*=\s*"([^"]+)"'),
    "json": (r'("version"\s*:\s*")[^"]+(")', r'"version"\s*:\s*"([^"]+)"'),
}


def _sole_version_match(text: str, fmt: str, rel: str) -> re.Match:
    """The one version match in *text*, or a loud ``SystemExit``.

    Guards against BOTH a missing version line and a *second* one: ``re.subn(count=1)`` /
    ``re.search`` silently accept a duplicate (capping at, or picking, the first) — so a future field
    like a nested ``"engines": {"version": …}`` could be mis-read/mis-written with no signal. We count
    every occurrence and require exactly one.
    """
    matches = list(re.finditer(_PATTERNS[fmt][1], text))
    if len(matches) != 1:
        raise SystemExit(  # pragma: no mutate - message text only
            f"version_targets: expected exactly one version in {rel}, found {len(matches)}"
        )
    return matches[0]


def write_version(version: str, root: Path = Path(".")) -> None:
    """Write *version* into every canonical file (in place, preserving formatting)."""
    for rel, fmt in VERSION_TARGETS:
        path = root / rel
        text = path.read_text(encoding="utf-8")
        _sole_version_match(text, fmt, rel)  # fail loud on zero or duplicate version fields
        new = re.sub(_PATTERNS[fmt][0], rf"\g<1>{version}\g<2>", text, count=1)
        path.write_text(new, encoding="utf-8")


def read_versions(root: Path = Path(".")) -> dict[str, str]:
    """Return ``{relative_path: version}`` read from every canonical file."""
    out: dict[str, str] = {}
    for rel, fmt in VERSION_TARGETS:
        text = (root / rel).read_text(encoding="utf-8")
        out[rel] = _sole_version_match(text, fmt, rel).group(1)
    return out


def read_canonical_version(root: Path = Path(".")) -> str:
    """The single source of truth for the build's version: ``pyproject.toml``.

    Build-consumed manifests (``dist/<eco>/…/plugin.json``) are *injected* from this at build time
    (see ``emit.copy_versioned``), never restating it — so a human reading ``src/targets/<eco>/plugin.json``
    sees a ``${version}`` token, not a literal they'd have to remember to bump (CoC single-source rule).
    """
    return read_versions(root)["pyproject.toml"]


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
