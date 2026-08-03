"""Answer which project owns a directory, and self-heal `~/.hercules/config.json`: read-only
`resolve --cwd <path>`, and fail-CLOSED `repair plan|apply [--confirm]`. `repair` corrects a
`state_file` pointer naming a file that does not exist when the conventional `{slug}.json` does —
the pointer half of a torn two-file write — and restores a valid empty registry when `config.json`
is gone. It never invents a project: `directory` lives ONLY in the registry, so a state file with no
entry is reported, not reconstructed. Path canonicalisation is loaded from `hooks/hercules_state.py`.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

EXIT_OK = 0
EXIT_AMBIGUOUS = 1
EXIT_UNCONFIRMED = 2
EXIT_INTERNAL = 3


class Internal(Exception):
    """The record could not be read, written, or verified. Never a reason to retry automatically."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


# ── Reading the registry ──────────────────────────────────────────────────────────────────────

def hercules_home(home=None) -> Path:
    """The state tree root. Tests pass an explicit `home`; there is deliberately no flag for it, so
    a caller cannot redirect the tool at another tree."""
    return (Path(home) if home else Path.home()) / ".hercules"


def read_json(path: Path):
    """Parse a JSON file. Raises `Internal` only on an unreadable one; a missing or malformed file
    returns None, because healing exactly those is what `repair` is for."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise Internal(
            f"Could not read {path}. Nothing was changed. {exc.strerror or exc}"
        ) from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def load_registry(home=None) -> dict:
    """The `projects` map from `config.json` — `{}` when the file is missing or unparseable."""
    config = read_json(hercules_home(home) / "config.json")
    projects = config.get("projects") if isinstance(config, dict) else None
    return projects if isinstance(projects, dict) else {}


# ── The one shared canonicaliser — loaded, never re-derived ───────────────────────────────────

def _load_hercules_state():
    """Load the sibling `hooks/hercules_state.py` by file path, never a package import, so `tools/`
    and `hooks/` stay independently copyable. Raises `Internal` when it cannot be loaded."""
    hooks_path = Path(__file__).resolve().parent.parent / "hooks" / "hercules_state.py"
    try:
        spec = importlib.util.spec_from_file_location("_registry_sync_hercules_state", hooks_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception as exc:
        raise Internal(
            f"Could not load the path resolver ({hooks_path}). Nothing was changed. {exc}"
        ) from exc


def is_within(child_c: str, root_c: str) -> bool:
    """True when `child_c` IS `root_c` or lives inside it, matching whole path components."""
    return child_c == root_c or child_c.startswith(root_c + os.sep)


def project_roots(entry: dict, canon) -> list:
    """Every canonical path that identifies a project — `directory`, `docs_root`, and each cross-repo
    `repositories` path — the widest set, since this answers a general-purpose "which project" query."""
    raw = [entry.get("directory"), entry.get("docs_root")] + \
        list((entry.get("repositories") or {}).values())
    return [canon(r) for r in raw if r]


def matching_projects(projects: dict, cwd_c: str, canon) -> list:
    """`[(slug, entry), ...]` for every project whose roots contain `cwd_c`, deepest match first."""
    scored = []
    for slug, entry in projects.items():
        if not isinstance(entry, dict):
            continue
        roots = project_roots(entry, canon)
        depths = [len(r) for r in roots if is_within(cwd_c, r)]
        if depths:
            scored.append((max(depths), slug, entry))
    scored.sort(key=lambda row: (-row[0], row[1]))
    return [(slug, entry) for _, slug, entry in scored]


# ── `resolve` — read-only ─────────────────────────────────────────────────────────────────────

def resolve_command(cwd: str, home=None) -> dict:
    """Every registered project whose roots contain `cwd`, deepest first, and the single resolved
    project when there is exactly one. Never writes."""
    hercules_state = _load_hercules_state()
    projects = load_registry(home)
    cwd_c = hercules_state.canon(cwd)
    matches = matching_projects(projects, cwd_c, hercules_state.canon)
    candidates = [{"slug": slug, "directory": entry.get("directory", ""),
                   "docs_root": entry.get("docs_root", "")} for slug, entry in matches]
    return {"cwd": str(cwd), "candidates": candidates,
            "resolved": candidates[0] if len(candidates) == 1 else None}


# ── `repair` — fail closed ────────────────────────────────────────────────────────────────────

def stale_pointer_repairs(projects: dict, state_dir: Path) -> list:
    """Every project whose `state_file` pointer names a missing file while the conventional
    `{slug}.json` exists. A pointer escaping the state directory is a different problem, left alone."""
    rows = []
    for slug, entry in sorted(projects.items()):
        if not isinstance(entry, dict):
            continue
        pointer = entry.get("state_file") or f"{slug}.json"
        if os.path.basename(pointer) != pointer:
            continue
        if (state_dir / pointer).is_file():
            continue
        conventional = f"{slug}.json"
        if pointer != conventional and (state_dir / conventional).is_file():
            rows.append({"slug": slug, "from": pointer, "to": conventional})
    return rows


def orphaned_state_files(projects: dict, state_dir: Path) -> list:
    """Every `state/*.json` file no registry entry points at — a project the registry lost. Reported
    only, never repaired: `directory` is not stored in state, and inventing one would be worse."""
    if not state_dir.is_dir():
        return []
    pointed = {(entry.get("state_file") or f"{slug}.json")
              for slug, entry in projects.items() if isinstance(entry, dict)}
    return sorted(p.name for p in state_dir.glob("*.json") if p.name not in pointed)


def build_repair_plan(home) -> dict:
    """The registry's health: whether `config.json` parses, every fix `apply` would make, and every
    orphan it would report but not touch. Writes nothing; safe to call repeatedly."""
    config_path = hercules_home(home) / "config.json"
    state_dir = hercules_home(home) / "state"
    config = read_json(config_path)
    healthy = isinstance(config, dict) and isinstance(config.get("projects"), dict)
    projects = config.get("projects") if healthy else {}
    return {
        "config_readable": healthy,
        "pointer_fixes": stale_pointer_repairs(projects, state_dir),
        "orphaned_state_files": orphaned_state_files(projects, state_dir),
    }


def atomic_write_json(path: Path, data) -> None:
    """Write JSON through a temporary file in the SAME directory — flush, fsync, carry the original's
    permission bits, then `os.replace`, which is atomic on POSIX and Windows unlike `os.rename`."""
    payload = json.dumps(data, indent=2, ensure_ascii=True) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        mode = os.stat(path).st_mode & 0o777 if path.exists() else 0o644
        handle, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".registry_sync.")
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except OSError as exc:
        raise Internal(
            f"Could not write {path}. The original is unchanged. {exc.strerror or exc}"
        ) from exc


def verify_repair(path: Path, pointer_fixes: list, before: dict) -> bool:
    """Re-read the written registry and confirm every fixed pointer landed, every OTHER field of a
    fixed entry survived, and every OTHER project survived — untouched, byte for byte."""
    after = read_json(path)
    after_projects = after.get("projects") if isinstance(after, dict) else None
    after_projects = after_projects if isinstance(after_projects, dict) else {}
    before_projects = before.get("projects") if isinstance(before, dict) else None
    before_projects = before_projects if isinstance(before_projects, dict) else {}
    fixed = {row["slug"]: row["to"] for row in pointer_fixes}
    for slug, target in fixed.items():
        entry = after_projects.get(slug)
        if not isinstance(entry, dict) or entry.get("state_file") != target:
            return False
        before_entry = before_projects.get(slug) or {}
        if any(entry.get(k) != v for k, v in before_entry.items() if k != "state_file"):
            return False
    for slug, entry in before_projects.items():
        if slug not in fixed and after_projects.get(slug) != entry:
            return False
    return True


def apply_repair(home) -> dict:
    """Perform the repair: correct every stale `state_file` pointer, and restore a valid empty
    registry when `config.json` is unreadable. A registry with nothing to fix is left untouched."""
    plan = build_repair_plan(home)
    path = hercules_home(home) / "config.json"
    if not plan["pointer_fixes"] and plan["config_readable"]:
        return {**plan, "written": False, "verified": True}
    before = read_json(path)
    before = before if isinstance(before, dict) else {"schema_version": 1, "projects": {}}
    projects = dict(before.get("projects") or {})
    for row in plan["pointer_fixes"]:
        entry = dict(projects[row["slug"]])
        entry["state_file"] = row["to"]
        projects[row["slug"]] = entry
    after_config = dict(before, projects=projects)
    atomic_write_json(path, after_config)
    verified = verify_repair(path, plan["pointer_fixes"], before)
    return {**plan, "written": True, "verified": verified}


# ── Command line ──────────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    """Two subcommands: read-only `resolve --cwd <path>`, and fail-closed `repair plan|apply
    [--confirm]`."""
    parser = argparse.ArgumentParser(prog="registry_sync", add_help=False)
    subparsers = parser.add_subparsers(dest="command", required=True)

    resolve_parser = subparsers.add_parser("resolve", add_help=False)
    resolve_parser.add_argument("--cwd", required=True)

    repair_parser = subparsers.add_parser("repair", add_help=False)
    repair_parser.add_argument("mode", choices=("plan", "apply"))
    repair_parser.add_argument("--confirm", action="store_true")

    return parser


def emit(payload: dict, command: str, code: int) -> int:
    """Print the payload as JSON on stdout and return the exit code. Every path emits, including
    refusals, so the caller parses one shape and never has to guess."""
    print(json.dumps(dict({"command": command}, **payload), indent=2))
    return code


def _run(args, home) -> tuple:
    """Dispatch to the named command. Raises `Internal`; `main` renders it."""
    if args.command == "resolve":
        payload = resolve_command(args.cwd, home)
        return payload, (EXIT_OK if payload["resolved"] is not None else EXIT_AMBIGUOUS)
    # command == "repair"
    if args.mode == "plan":
        return build_repair_plan(home), EXIT_OK
    if not args.confirm:
        return {"error": "unconfirmed",
                "message": "Nothing was changed. This step needs an explicit confirmation."}, \
            EXIT_UNCONFIRMED
    return apply_repair(home), EXIT_OK


def main(argv=None, home=None) -> int:
    """Resolve, dispatch, and turn every failure into a scripted refusal — nothing escapes as a
    traceback. `home` is a parameter, never a flag, so no caller can redirect the tool."""
    try:
        args = build_parser().parse_args(list(argv) if argv is not None else None)
    except SystemExit:
        return emit({"error": "usage", "message": "The arguments were not understood."},
                    "unknown", EXIT_INTERNAL)
    command = args.command
    mode = getattr(args, "mode", command)
    try:
        payload, code = _run(args, home)
    except Internal as exc:
        return emit({"error": "internal", "message": exc.message}, command, EXIT_INTERNAL)
    except Exception as exc:  # fail closed: an unclassified error changes nothing
        return emit({"error": "internal", "message": f"Nothing was changed. {exc}"}, command,
                    EXIT_INTERNAL)
    if payload.get("verified") is False:
        return emit(payload, command, EXIT_INTERNAL)
    return emit(dict(payload, mode=mode) if command == "repair" else payload, command, code)


if __name__ == "__main__":  # pragma: no cover - exercised via main() in tests
    sys.exit(main())
