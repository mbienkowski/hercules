"""Leaf filesystem primitives for the build — no target knowledge.

Extracted from ``cli.py`` so per-target modules can emit their non-content artifacts without
importing the orchestrator. Pure I/O: write a text file, or byte-copy a ``src → dest`` map.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

_VERSION_TOKEN = re.compile(r"\$\{version\}")


def write(dest: Path, text: str) -> None:
    """Write *text* to *dest* (UTF-8), creating parent dirs."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")


def copy_versioned(src: Path, dest: Path, version: str) -> None:
    """Copy *src* to *dest*, substituting the single ``${version}`` token with *version*.

    Deliberately NOT routed through ``render.py`` (whose token pass is fail-*open*: an unknown/absent
    token survives verbatim, which for a version field would silently ship the literal ``${version}``
    into a release manifest). This does a targeted text substitution and raises if the token count is
    not exactly one — the same fail-*loud* contract as ``version_targets.write_version``. Pure string
    replace (no JSON re-serialize) so every other byte — key order, indentation, trailing newline — is
    preserved exactly, keeping ``dist/`` byte-identical.
    """
    text = src.read_text(encoding="utf-8")
    new, n = _VERSION_TOKEN.subn(version, text)
    if n != 1:
        raise SystemExit(  # pragma: no mutate - message text only
            f"emit.copy_versioned: expected exactly one ${{version}} token in {src}, found {n}"
        )
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(new, encoding="utf-8")


def copy_map(src_dir: Path, out_root: Path, mapping: dict[str, str]) -> list[str]:
    """Byte-copy each ``src_dir/<src>`` to ``out_root/<dest>``; return the written dest rels."""
    written = []
    for src_rel, dest_rel in mapping.items():
        dest = out_root / dest_rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src_dir / src_rel, dest)
        written.append(dest_rel)
    return written
