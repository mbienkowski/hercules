"""``hercules-build`` entry point (thin FS boundary).

``--target {<name>|all} [--check]``. Without ``--check`` it writes ``dist/<target>/``; with
``--check`` it renders to a temp dir and diffs against the committed ``dist/`` (exit non-zero on
drift). One code path for local dev and CI. The accepted target names derive from the target
registry, so ``all`` and the valid values extend automatically as targets are registered.
"""
from __future__ import annotations

import argparse
import filecmp
import sys
import tempfile
from pathlib import Path

from scripts.build import descriptor, emit, targets
from scripts.build.layout import discover_sources
from scripts.build.serialize import serialize_file
from scripts.build.targets.base import ExtrasContext
from scripts.build.version_targets import read_canonical_version

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"
SRC_CONTENT = SRC / "content"
DIST = REPO_ROOT / "dist"
# The canonical frozen-test guard + the one generic write-gate adapter live in the NEUTRAL
# src/hooks/ tree; every ecosystem ships byte-copies, so the write-gate logic has one source of truth.
_SHARED_HOOKS_SRC = SRC / "hooks"
# The one authoritative ecosystem list — every accepted --target value and `all` derive from it.
TARGETS = tuple(targets.registered_target_names())


def _targets_for(name: str) -> list[str]:
    return list(TARGETS) if name == "all" else [name]


def _load_models() -> dict:
    """Every ecosystem's model-tier row, from the descriptors (the one per-ecosystem source)."""
    return {name: dict(d.models) for name, d in descriptor.discover().items()}


def _load_tokens(target: str) -> dict[str, str]:
    """The target's token ``vars`` from its descriptor; ``{}`` for an unknown target (test stubs)."""
    found = descriptor.discover().get(target)
    return dict(found.vars) if found else {}


def build_target(target: str, out_root: Path) -> list[str]:
    """Render *target* into *out_root*; return the sorted list of written relative paths.

    The body holds no per-ecosystem branches: the content loop relocates each source via the target's
    ``dest`` and the non-content artifacts come from the target's ``emit_extras``.
    """
    models = _load_models()
    tokens = _load_tokens(target)
    spec = targets.get(target)
    written: list[str] = []
    for src in discover_sources(SRC_CONTENT):
        rel = src.relative_to(SRC_CONTENT).as_posix()
        emit.write(out_root / spec.dest(rel),
                   serialize_file(target, src.read_text(encoding="utf-8"), tokens, models, rel))
        written.append(spec.dest(rel))
    ctx = ExtrasContext(
        out_root=out_root,
        src_target_dir=SRC / "ecosystems",
        shared_hooks_src=_SHARED_HOOKS_SRC,
        src_content=SRC_CONTENT,
        tokens=tokens,
        version=read_canonical_version(REPO_ROOT),
    )
    written += spec.emit_extras(ctx)
    return sorted(written)


def _rel_files(root: Path) -> set[str]:
    return {
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and not p.name.endswith(".pyc")
    }


def _dir_diff(a: Path, b: Path) -> list[str]:
    """Relative paths that differ between *a* and *b*, compared by CONTENT.

    Uses ``filecmp.cmp(..., shallow=False)`` so same-size files are always byte-compared. The stdlib
    ``filecmp.dircmp`` compares shallowly (stat signature), which can miss a same-size, same-mtime
    hand-edit to a committed ``dist/`` file — this walk closes that hole.
    """
    a_files, b_files = _rel_files(a), _rel_files(b)
    diffs = sorted(a_files ^ b_files)
    diffs += [rel for rel in sorted(a_files & b_files)
              if not filecmp.cmp(a / rel, b / rel, shallow=False)]
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
        if target not in targets.registered_target_names():
            continue
        if args.check:
            rc |= check_target(target)
        else:
            build_target(target, DIST / target)
    if args.check and rc != 0:
        print(
            "dist/ is stale — regenerate it with `make build` and commit the result.",
            file=sys.stderr,
        )
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
