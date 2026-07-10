"""``hercules-build`` entry point (thin FS boundary).

``--target {claude-code|opencode|all} [--check]``. Without ``--check`` it writes ``dist/<target>/``;
with ``--check`` it renders to a temp dir and diffs against the committed ``dist/`` (exit non-zero on
drift). One code path for local dev and CI. Spec 02 lands full Claude-Code generation; OpenCode in
Spec 03.
"""
from __future__ import annotations

import argparse
import filecmp
import json
import shutil
import tempfile
from pathlib import Path

from scripts.build.layout import discover_sources
from scripts.build.serialize import registered_targets, serialize_file

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"
SRC_CONTENT = SRC / "content"
DIST = REPO_ROOT / "dist"
TARGETS = ("claude-code", "opencode")

# Per-target source→dest renames + the Claude-only byte-copied files.
_RENAMES = {"claude-code": {"persona.md": "CLAUDE.md"}}
_CLAUDE_COPIES = {
    "settings.json": "settings.json",
    "hooks/hooks.json": "hooks/hooks.json",
    "hooks/frozen_tests.py": "hooks/frozen_tests.py",
    "hooks/hercules_state.py": "hooks/hercules_state.py",
    "plugin.json": ".claude-plugin/plugin.json",
}


def _targets_for(name: str) -> list[str]:
    return list(TARGETS) if name == "all" else [name]


def _load_models() -> dict:
    path = SRC / "models.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _load_tokens(target: str) -> dict[str, str]:
    path = SRC / "targets" / target / "config.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8")).get("vars", {})


def _write(dest: Path, text: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")


def build_target(target: str, out_root: Path) -> list[str]:
    """Render *target* into *out_root*; return the sorted list of written relative paths."""
    models = _load_models()
    tokens = _load_tokens(target)
    renames = _RENAMES.get(target, {})
    written: list[str] = []
    for src in discover_sources(SRC_CONTENT):
        rel = src.relative_to(SRC_CONTENT).as_posix()
        dest_rel = renames.get(rel, rel)
        _write(out_root / dest_rel, serialize_file(target, src.read_text(encoding="utf-8"), tokens, models))
        written.append(dest_rel)
    if target == "claude-code":
        tdir = SRC / "targets" / target
        for src_rel, dest_rel in _CLAUDE_COPIES.items():
            dest = out_root / dest_rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(tdir / src_rel, dest)
            written.append(dest_rel)
    return sorted(written)


def _dir_diff(a: Path, b: Path) -> list[str]:
    cmp = filecmp.dircmp(str(a), str(b))
    diffs = list(cmp.left_only) + list(cmp.right_only) + list(cmp.diff_files)
    for sub in cmp.common_dirs:
        diffs += [f"{sub}/{d}" for d in _dir_diff(a / sub, b / sub)]
    return diffs


def check_target(target: str) -> int:
    """Render *target* to a temp dir and diff vs committed ``dist/<target>``; 0 == in sync."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / target
        out.mkdir(parents=True, exist_ok=True)
        build_target(target, out)
        committed = DIST / target
        if not committed.exists():
            return 0 if not any(out.rglob("*")) else 1
        return 1 if _dir_diff(committed, out) else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hercules-build")
    parser.add_argument("--target", default="all")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    rc = 0
    for target in _targets_for(args.target):
        if target not in registered_targets():
            continue
        if args.check:
            rc |= check_target(target)
        else:
            build_target(target, DIST / target)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
