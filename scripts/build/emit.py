"""Leaf filesystem primitives for the build — no target knowledge.

Extracted from ``cli.py`` so per-target modules can emit their non-content artifacts without
importing the orchestrator. Pure I/O: write a text file, or byte-copy a ``src → dest`` map.
"""
from __future__ import annotations

import shutil
from pathlib import Path


def write(dest: Path, text: str) -> None:
    """Write *text* to *dest* (UTF-8), creating parent dirs."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")


def copy_map(src_dir: Path, out_root: Path, mapping: dict[str, str]) -> list[str]:
    """Byte-copy each ``src_dir/<src>`` to ``out_root/<dest>``; return the written dest rels."""
    written = []
    for src_rel, dest_rel in mapping.items():
        dest = out_root / dest_rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src_dir / src_rel, dest)
        written.append(dest_rel)
    return written
