"""Parity fixture runner, Python side. Temporary — deleted with the Python compiler.

Reads one fixture (JSON on stdin), calls the named build function, and prints a CANONICAL result to
stdout. The TypeScript runner (scripts-ts/bin/parityRun.mts) speaks the identical protocol, so
`make parity` can byte-diff the two without knowing anything about the functions involved.

Fixture shape::

    {
      "module": "parse",              # build module
      "fn": "parse_frontmatter",      # snake_case here; the TS runner maps to its own
      "files": {"a.md": "..."},       # OPTIONAL workspace; a value may be {"text":..,"mode":"755"}
      "symlinks": {"l.md": "a.md"},   # OPTIONAL symlinks, created after files
      "args": ["a.md"],               # positional args; workspace-relative paths are absolutised
      "pathArgs": [0],                # OPTIONAL indices of args that are workspace paths
      "capture": ["out/a.json"]       # OPTIONAL files whose digest+mode are reported afterwards
    }

Result shape (stdout, canonical JSON)::

    {"ok": true,  "result": <value>, "files": {"out/a.json": {"sha256": "..", "mode": "644"}}}
    {"ok": false, "error": "<message>"}

Only the MESSAGE is compared on the error path, not the exception class: the Python original raises
``SystemExit`` in places where idiomatic TypeScript raises a named Error, and forcing one runtime to
mimic the other's exception taxonomy would be mimicry rather than parity. Message text IS
contractual — the code-of-conduct requires every failure to name its remedy — so that is what the
harness pins. Exception TYPE is pinned by each side's own unit tests.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.build import emit, layout, model_map, parse, render, version_targets  # noqa: E402

_MODULES = {
    "parse": parse,
    "render": render,
    "model_map": model_map,
    "layout": layout,
    "emit": emit,
    "version_targets": version_targets,
}


# Fixtures carry ordered [key, value] PAIR LISTS wherever a mapping is involved, because a JSON
# object cannot preserve the order of integer-like keys on the JavaScript side. Each runner adapts
# that neutral wire format to its own calling convention here; the TypeScript runner's FUNCTIONS map
# is the mirror of this table.
# An adapter returns (positional_args, keyword_args).
_ARG_ADAPTERS = {
    "parse.render_frontmatter": lambda args: ([dict(args[0])], {}),
    # `expected` is keyword-only in the Python original; the fixture carries it positionally so the
    # wire format stays engine-neutral.
    "version_targets.check_in_sync": lambda args: ([args[0]], {"expected": args[1]}),
}


def _canonical(value):
    """Normalise a return value into something both runtimes serialise identically.

    Dicts become ordered [key, value] PAIR LISTS, never JSON objects: Python preserves insertion
    order while JavaScript hoists integer-like keys to the front, so a frontmatter block whose first
    key is "1" would round-trip differently through an object on the two sides.
    """
    if isinstance(value, dict):
        return [[k, _canonical(v)] for k, v in value.items()]
    if isinstance(value, (list, tuple)):
        return [_canonical(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    return value


def _tree(root: Path, capture: list[str]) -> dict:
    out = {}
    for rel in sorted(capture):
        path = root / rel
        if not path.exists():
            out[rel] = None
            continue
        data = path.read_bytes()
        out[rel] = {
            "sha256": hashlib.sha256(data).hexdigest(),
            # Mode is captured because content comparison CANNOT see it: shutil.copyfile leaves the
            # destination at the umask while Node's copyFileSync propagates the source's bits, and
            # every file in dist/ is 100644 so the divergence is invisible to diff -r.
            "mode": oct(path.stat().st_mode & 0o777)[2:],
        }
    return out


def main() -> int:
    fixture = json.load(sys.stdin)
    module = _MODULES[fixture["module"]]
    fn = getattr(module, fixture["fn"])

    tmp_ctx = tempfile.TemporaryDirectory()
    root = Path(tmp_ctx.name).resolve()
    with tmp_ctx:
        for rel, spec in (fixture.get("files") or {}).items():
            dest = root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            # A value is either the file's text, or {"text": ..., "mode": "755"} when the fixture
            # needs a specific source mode — which is how the copy-mode divergence is exercised.
            text = spec if isinstance(spec, str) else spec["text"]
            dest.write_text(text, encoding="utf-8")
            if not isinstance(spec, str) and "mode" in spec:
                dest.chmod(int(spec["mode"], 8))
        for link_rel, target_rel in (fixture.get("symlinks") or {}).items():
            link = root / link_rel
            link.parent.mkdir(parents=True, exist_ok=True)
            link.symlink_to(root / target_rel)

        args = list(fixture.get("args", []))
        for index in fixture.get("pathArgs", []):
            args[index] = root / args[index]
        kwargs = {}
        adapter = _ARG_ADAPTERS.get(f"{fixture['module']}.{fixture['fn']}")
        if adapter is not None:
            args, kwargs = adapter(args)

        try:
            result = fn(*args, **kwargs)
        except BaseException as exc:  # noqa: BLE001 - the message IS the contract under test
            payload = {"ok": False, "error": str(exc)}
        else:
            payload = {"ok": True, "result": _canonical(result)}
            capture = fixture.get("capture")
            if capture:
                payload["files"] = _tree(root, capture)

    # The workspace is a fresh mkdtemp on each side, so its path differs between the two runners
    # and would show up as a false divergence in any result that echoes a path (an error message
    # naming the offending file, or discover_sources' absolute results). Normalising it keeps the
    # comparison about behaviour. Done on the serialised form so it reaches nested values too.
    text = json.dumps(payload, indent=1, ensure_ascii=False, sort_keys=True)
    sys.stdout.write(text.replace(str(root), "<workspace>") + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
