"""Clear Hercules' machine-local record of one project — the tool behind `project-reset`: report what
a project holds and, on explicit confirmation, remove a chosen subset of its feature records, its
configurable settings, and its documents folder. Two properties are not negotiable. It takes NO path
from its caller — every path is re-derived from the registry it reads itself, so a slug or a feature
key is a dictionary lookup, never a path fragment. And it fails CLOSED: any exception, ambiguous read
or failed check deletes nothing. `canon` is duplicated rather than imported — `tools/` ships alone.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

# Bumped only when the argument surface or JSON shape breaks; the command passes the version it was written against, and a mismatch refuses.
CONTRACT_VERSION = 1

EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_CONTRACT = 2
EXIT_UNCONFIRMED = 3
EXIT_INTERNAL = 4
EXIT_NOTHING = 5

# The four registry fields a person may clear and set again; the match key and the state pointer are structural, survive, and so orphan no state file.
CONFIGURABLE_FIELDS = ("docs_root", "repositories", "frozen_hook", "keep_specs")


class Ambiguous(Exception):
    """No project, or more than one, matched the working directory. Carries the candidate list so
    the command can ask rather than guess."""

    def __init__(self, candidates, message):
        super().__init__(message)
        self.candidates = candidates
        self.message = message


class Refused(Exception):
    """A safety rule rejected a target. Carries the rule identifier and the scripted message the
    command relays verbatim."""

    def __init__(self, rule: str, message: str):
        super().__init__(message)
        self.rule = rule
        self.message = message


class Internal(Exception):
    """The record could not be read, written or verified. Never a reason to retry automatically."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


# ── Path canonicalisation ────────────────────────────────────────────────────────────────────

def canon(p) -> str:
    """Canonicalise a path for comparison: expand ~, resolve symlinks/.., fold case on macOS and
    Windows where two casings name one file. Falls back to the raw string, so it never throws."""
    try:
        resolved = os.path.realpath(os.path.expanduser(str(p)))
    except Exception:
        resolved = str(p)
    if sys.platform == "darwin":
        return resolved.lower()
    return os.path.normcase(resolved)


def is_within(child_c: str, root_c: str) -> bool:
    """True when `child_c` IS `root_c` or lives inside it, matching whole path components so
    `/a/proj` is not treated as inside `/a/project`."""
    return child_c == root_c or child_c.startswith(root_c + os.sep)


def is_strict_descendant(child_c: str, root_c: str) -> bool:
    """True when `child_c` lives strictly inside `root_c` — equality is False."""
    return child_c != root_c and child_c.startswith(root_c + os.sep)


# ── Reading the registry and state ────────────────────────────────────────────────────────────

def hercules_home(home=None) -> Path:
    """The state tree root. Tests pass an explicit `home`; there is deliberately no flag for it, so
    a caller cannot redirect the tool at another tree."""
    return (Path(home) if home else Path.home()) / ".hercules"


def read_json(path: Path):
    """Parse a JSON file. Raises `Internal` on a missing or malformed file — the caller refuses
    rather than editing content it could not fully understand."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:
        raise Internal(
            f"Could not read {path}. Nothing was changed. Inspect that file, then run this again."
        ) from exc


def load_registry(home=None) -> dict:
    """The `projects` map from `config.json`."""
    config = read_json(hercules_home(home) / "config.json")
    projects = config.get("projects") if isinstance(config, dict) else None
    return projects if isinstance(projects, dict) else {}


def state_path(home, entry: dict, slug: str) -> Path:
    """The state file for one project. A `state_file` pointer containing a separator is refused —
    it would escape `~/.hercules/state`."""
    name = entry.get("state_file") or f"{slug}.json"
    if os.path.basename(name) != name:
        raise Internal(f"The state pointer for '{slug}' escapes the record directory.")
    return hercules_home(home) / "state" / name


# ── Project resolution ────────────────────────────────────────────────────────────────────────

def entry_match_roots(entry: dict) -> list:
    """The canonical roots that identify a project: its `directory` AND its `docs_root` — matching
    `directory` alone resolves nothing when the documents live in their own repository."""
    raw = [entry.get("directory"), entry.get("docs_root")]
    return [canon(r) for r in raw if r]


def matching_slugs(projects: dict, cwd_c: str) -> list:
    """Every project slug whose roots contain `cwd_c`, deepest match first."""
    scored = []
    for slug, entry in projects.items():
        if not isinstance(entry, dict):
            continue
        depths = [len(r) for r in entry_match_roots(entry) if is_within(cwd_c, r)]
        if depths:
            scored.append((max(depths), slug))
    scored.sort(key=lambda row: (-row[0], row[1]))
    return [slug for _, slug in scored]


def _candidates(projects: dict) -> list:
    """Every registered project, as the command renders them when it has to ask."""
    return [
        {"slug": slug, "directory": entry.get("directory", ""),
         "docs_root": entry.get("docs_root", "")}
        for slug, entry in sorted(projects.items()) if isinstance(entry, dict)
    ]


def resolve_project(projects: dict, cwd, requested_slug=None):
    """The project this run acts on as `(slug, entry)`, else `Ambiguous` carrying the candidates.
    `requested_slug` is honoured only as a key of `projects` — membership, never a path."""
    if requested_slug is not None:
        if requested_slug in projects:
            return requested_slug, projects[requested_slug]
        raise Ambiguous(_candidates(projects),
                        "No project of that name is registered. Choose one of the projects listed.")
    matches = matching_slugs(projects, canon(cwd))
    if len(matches) == 1:
        return matches[0], projects[matches[0]]
    shown = [c for c in _candidates(projects) if c["slug"] in matches] if matches else _candidates(projects)
    raise Ambiguous(shown, "This directory does not identify one project. "
                           "Run this again naming one of the projects listed.")


# ── Inventory — what the project holds ────────────────────────────────────────────────────────

def feature_rows(state: dict) -> list:
    """Each feature as `{"key", "stage"}` — the name and the phase, and nothing from inside the
    record. Build narratives, handover notes and quoted instructions are never surfaced."""
    sessions = state.get("sessions") or {}
    return [{"key": key, "stage": (value or {}).get("current_phase", "unknown")}
            for key, value in sorted(sessions.items())]


def settings_row(entry: dict) -> dict:
    """The four configurable fields, with absent optional ones rendered as their effective value."""
    return {
        "docs_root": entry.get("docs_root", ""),
        "repositories": sorted((entry.get("repositories") or {})),
        "frozen_hook": "off" if entry.get("frozen_hook") == "off" else "on",
        "keep_specs": bool(entry.get("keep_specs")),
    }


def documents_row(entry: dict) -> dict:
    """The documents path, whether it sits inside the code repository, and how many feature folders
    it holds. The in-repository flag drives a warning the person must see before choosing."""
    raw = entry.get("docs_root") or ""
    path = Path(raw) if raw else None
    inside = bool(raw) and is_strict_descendant(canon(raw), canon(entry.get("directory") or ""))

    # Feature folders only: a person reads this as "N feature folders", and `.git` is not one.
    folders = 0
    if path is not None and path.is_dir():
        folders = sum(1 for child in path.iterdir()
                      if child.is_dir() and not child.name.startswith("."))
    return {"path": raw, "inside_code_repo": inside, "folders": folders}


# ── Refusal rules — checked in order, first match refuses ─────────────────────────────────────

def rule_blank(raw, ctx) -> bool:
    """Empty, whitespace, `.` or `..` — checked BEFORE canonicalisation. `os.path.realpath("")`
    silently returns the working directory, so a post-resolution check would let it through."""
    return str(raw).strip() in ("", ".", "..")


def rule_filesystem_root(raw, ctx) -> bool:
    """The filesystem root, a Windows drive root, or a UNC root."""
    resolved = Path(canon(raw))
    return resolved == resolved.parent


def rule_home_directory(raw, ctx) -> bool:
    """The user's home directory."""
    return canon(raw) == canon(ctx["home_dir"])


def rule_hercules_home(raw, ctx) -> bool:
    """`~/.hercules` itself — the tool edits files inside it but never removes the tree."""
    return canon(raw) == canon(ctx["record_dir"])


def rule_project_directory(raw, ctx) -> bool:
    """The project's own `directory`."""
    return canon(raw) == ctx["project_c"]


def rule_contains_project_directory(raw, ctx) -> bool:
    """The target CONTAINS the project directory. A documents folder inside the code repository is
    legitimate and stays deletable; a documents root that contains the code is not."""
    return is_strict_descendant(ctx["project_c"], canon(raw))


def rule_registered_elsewhere(raw, ctx) -> bool:
    """Any other registered project's `directory`, `docs_root`, or `repositories` value."""
    return canon(raw) in ctx["foreign"]


def rule_outside_permitted_roots(raw, ctx) -> bool:
    """Not this project's own documents root, nor anything inside it, nor inside the record's state
    directory. The positive control — the only rule that matters on its own."""
    target = canon(raw)
    return not any(is_within(target, root) for root in ctx["permitted"])


REFUSAL_RULES = (
    ("target_is_blank", rule_blank),
    ("target_is_filesystem_root", rule_filesystem_root),
    ("target_is_home_directory", rule_home_directory),
    ("target_is_hercules_home", rule_hercules_home),
    ("target_is_project_directory", rule_project_directory),
    ("target_contains_project_directory", rule_contains_project_directory),
    ("target_is_registered_elsewhere", rule_registered_elsewhere),
    ("target_outside_permitted_roots", rule_outside_permitted_roots),
)

_RULE_MESSAGES = {
    "target_is_blank":
        "The documents folder is not set for this project, so there is nothing safe to remove. "
        "Nothing was deleted. Set it, then run this again.",
    "target_is_filesystem_root":
        "The documents folder resolves to the root of the filesystem. Nothing was deleted. "
        "Correct that setting before running this again.",
    "target_is_home_directory":
        "The documents folder resolves to your home directory. Nothing was deleted. "
        "Correct that setting before running this again.",
    "target_is_hercules_home":
        "The documents folder resolves to the record directory itself. Nothing was deleted. "
        "Correct that setting before running this again.",
    "target_is_project_directory":
        "The documents folder resolves to the project directory itself, which holds your code. "
        "Nothing was deleted. Correct that setting before running this again.",
    "target_contains_project_directory":
        "The documents folder contains your project directory, so removing it would remove your "
        "code. Nothing was deleted. Correct that setting before running this again.",
    "target_is_registered_elsewhere":
        "The documents folder belongs to another project Hercules knows about. Nothing was "
        "deleted. Correct that setting before running this again.",
    "target_outside_permitted_roots":
        "The documents folder lies outside everything this project owns. Nothing was deleted. "
        "Correct that setting before running this again.",
}


def check_target(raw, ctx) -> None:
    """Run every rule in order against a candidate deletion target. Raises `Refused` on the first
    match; returns None when the target is safe."""
    for name, rule in REFUSAL_RULES:
        if rule(raw, ctx):
            raise Refused(name, _RULE_MESSAGES[name])


def safety_context(home, slug: str, entry: dict, projects: dict) -> dict:
    """Everything the rules compare against, resolved once so no rule re-derives a path."""
    record = hercules_home(home)
    foreign = set()
    for other_slug, other in projects.items():
        if other_slug == slug or not isinstance(other, dict):
            continue
        for value in [other.get("directory"), other.get("docs_root")] + list(
                (other.get("repositories") or {}).values()):
            if value:
                foreign.add(canon(value))
    docs = entry.get("docs_root") or ""
    return {
        "home_dir": Path(home) if home else Path.home(),
        "record_dir": record,
        "project_c": canon(entry.get("directory") or ""),
        "foreign": foreign,
        "permitted": [canon(docs)] if docs else [],
    }


# ── Deletion ──────────────────────────────────────────────────────────────────────────────────

def _remove_leaf(path: Path, failures: list) -> None:
    """Remove one file, link or empty directory, recording rather than raising on refusal."""
    try:
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            path.rmdir()
    except FileNotFoundError:
        return
    except OSError as exc:
        failures.append({"path": str(path), "reason": exc.strerror or str(exc)})


def _is_on_root_filesystem(child: Path, root_dev: int) -> bool:
    """Whether `child` sits on the same filesystem as the validated root. A link answers True without
    being followed, and so does an unreadable entry, which the walk must still offer for removal."""
    if child.is_symlink():
        return True
    try:
        return child.stat().st_dev == root_dev
    except OSError:
        return True


def _walk_bottom_up(root: Path, root_dev: int, root_c: str):
    """Yield every entry under `root`, deepest first, never following a link and never leaving the
    validated root or its filesystem — the mid-walk equivalent of `rm --one-file-system`."""
    for parent, dirs, files in os.walk(root, topdown=False, followlinks=False):
        parent_path = Path(parent)
        if not is_within(canon(parent_path), root_c):
            continue
        for name in files + dirs:
            child = parent_path / name
            if _is_on_root_filesystem(child, root_dev):
                yield child
        yield parent_path


def delete_tree(root: Path) -> list:
    """Remove `root` and everything under it, bottom-up, never following links; returns what could
    not be removed. An already-absent entry counts as satisfied, so a re-run finishes the job."""
    if not root.exists() and not root.is_symlink():
        return []
    failures: list = []
    root_c = canon(root)
    try:
        root_dev = root.stat().st_dev
    except OSError as exc:
        return [{"path": str(root), "reason": exc.strerror or str(exc)}]
    seen = set()
    for entry in _walk_bottom_up(root, root_dev, root_c):
        if str(entry) in seen:
            continue
        seen.add(str(entry))
        _remove_leaf(entry, failures)
    return failures


# ── Atomic edits to the record ────────────────────────────────────────────────────────────────

def atomic_write_json(path: Path, data) -> None:
    """Write JSON through a temporary file in the SAME directory: flush, fsync, copy the original's
    permission bits, then `os.replace` — atomic on POSIX and Windows, unlike `os.rename`."""
    payload = json.dumps(data, indent=2, ensure_ascii=True) + "\n"
    try:
        mode = os.stat(path).st_mode & 0o777
        handle, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".project_reset.")
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


def drop_sessions(state: dict, keys) -> dict:
    """Remove the named feature records and unset `active_session` when it pointed at one of them.
    Every other key is carried through untouched."""
    updated = dict(state)
    sessions = dict(state.get("sessions") or {})
    for key in keys:
        sessions.pop(key, None)
    updated["sessions"] = sessions
    if updated.get("active_session") in set(keys):
        updated["active_session"] = None
    return updated


def drop_settings(entry: dict) -> dict:
    """Remove the four configurable fields, preserving the match key and the state pointer."""
    return {k: v for k, v in entry.items() if k not in CONFIGURABLE_FIELDS}


def verify_removed(path: Path, removed_keys, container: str, before: dict) -> bool:
    """Re-read the written file and confirm the named keys are gone AND every other key survived
    unchanged. A false result is an internal error, never a reason to retry."""
    after = read_json(path)
    holder = after.get(container) if container else after
    if not isinstance(holder, dict):
        return False
    if any(key in holder for key in removed_keys):
        return False
    original = (before.get(container) if container else before) or {}
    survivors = {k: v for k, v in original.items() if k not in set(removed_keys)}
    return all(holder.get(k) == v for k, v in survivors.items())


# ── The two modes ─────────────────────────────────────────────────────────────────────────────

def _selected_features(selection: dict, state: dict) -> list:
    """The feature keys this run acts on. A named key is a dictionary lookup against the record —
    never joined into a path — so an invented name simply matches nothing."""
    sessions = state.get("sessions") or {}
    if selection["all_features"]:
        return sorted(sessions)
    return [key for key in selection["features"] if key in sessions]


def _would_delete(slug, entry, state, selection) -> dict:
    """Exactly what a selection would remove, as the command renders it."""
    features = _selected_features(selection, state)
    registry_keys = [f"projects.{slug}.{f}" for f in CONFIGURABLE_FIELDS
                     if selection["settings"] and f in entry]
    paths = [entry.get("docs_root")] if selection["documents"] and entry.get("docs_root") else []
    return {
        "state_keys": [f"sessions.{key}" for key in features],
        "registry_keys": registry_keys,
        "paths": [p for p in paths if p],
    }


def build_plan(slug, entry, state, selection) -> dict:
    """Compute the inventory and, for a non-empty selection, exactly what would be removed. Writes
    nothing; safe to call repeatedly."""
    return {
        "project": {"slug": slug, "directory": entry.get("directory", "")},
        "features": feature_rows(state),
        "settings": settings_row(entry),
        "documents": documents_row(entry),
        "selection": {
            "features": _selected_features(selection, state),
            "settings": selection["settings"],
            "documents": selection["documents"],
        },
        "would_delete": _would_delete(slug, entry, state, selection),
    }


def _apply_state(home, slug, entry, state, features) -> bool:
    """Remove the chosen feature records and prove the result. Returns whether it verified."""
    if not features:
        return True
    path = state_path(home, entry, slug)
    atomic_write_json(path, drop_sessions(state, features))
    return verify_removed(path, features, "sessions", state)


def _apply_settings(home, slug, projects) -> bool:
    """Clear the configurable fields and prove the neighbours survived."""
    config = read_json(hercules_home(home) / "config.json")
    before = dict(config.get("projects") or {})
    config["projects"] = dict(before, **{slug: drop_settings(before[slug])})
    path = hercules_home(home) / "config.json"
    atomic_write_json(path, config)
    after = read_json(path).get("projects") or {}
    return all(after.get(k) == v for k, v in before.items() if k != slug)


def apply_plan(home, slug, entry, state, projects, selection) -> dict:
    """Perform the deletion, trusting nothing a prior `plan` returned: every path is re-derived and
    every refusal rule re-run here, and all targets resolve before the first thing is cleared."""
    features = _selected_features(selection, state)
    docs = entry.get("docs_root") or ""
    plan = _would_delete(slug, entry, state, selection)
    if selection["documents"]:
        check_target(docs, safety_context(home, slug, entry, projects))
    failures = delete_tree(Path(docs)) if selection["documents"] and docs else []
    verified = _apply_state(home, slug, entry, state, features)
    if selection["settings"]:
        verified = _apply_settings(home, slug, projects) and verified
    kept = len((state.get("sessions") or {})) - len(features)
    return {"deleted": plan, "kept": {"features": kept}, "failed": failures, "verified": verified}


# ── Command line ──────────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    """The whole argument surface: a mode, the contract version, an optional project slug, the
    selection flags, and `--confirm`. Deliberately no path argument and no force flag."""
    parser = argparse.ArgumentParser(prog="project_reset", add_help=False)
    parser.add_argument("mode", choices=("plan", "apply"))
    parser.add_argument("--contract", type=int, required=True)
    parser.add_argument("--project", default=None)
    parser.add_argument("--feature", action="append", default=[])
    parser.add_argument("--all-features", action="store_true")
    parser.add_argument("--settings", action="store_true")
    parser.add_argument("--documents", action="store_true")
    parser.add_argument("--confirm", action="store_true")
    return parser


def selection_from(args) -> dict:
    """The chosen items as plain data. Absent flags mean not selected — there is no maximal
    default, so nothing is ever cleared because a flag was forgotten."""
    return {"features": list(args.feature), "all_features": args.all_features,
            "settings": args.settings, "documents": args.documents}


def emit(payload: dict, mode: str, code: int) -> int:
    """Print the payload as JSON on stdout and return the exit code. Every path emits, including
    refusals, so the command parses one shape and never has to guess."""
    print(json.dumps(dict({"contract": CONTRACT_VERSION, "mode": mode}, **payload), indent=2))
    return code


def _run(args, home, cwd) -> tuple:
    """Resolve and dispatch. Raises the three carrier exceptions; `main` renders them."""
    projects = load_registry(home)
    slug, entry = resolve_project(projects, cwd, args.project)
    state = read_json(state_path(home, entry, slug))
    selection = selection_from(args)
    if args.mode == "plan":
        return build_plan(slug, entry, state, selection), EXIT_OK
    if not args.confirm:
        return {"error": "unconfirmed",
                "message": "Nothing was deleted. This step needs an explicit confirmation."}, \
            EXIT_UNCONFIRMED
    return apply_plan(home, slug, entry, state, projects, selection), EXIT_OK


def main(argv=None, home=None, cwd=None) -> int:
    """Resolve, dispatch, and turn every failure into a scripted refusal — nothing escapes as a
    traceback. `home` and `cwd` are parameters, never flags, so no caller can redirect the tool."""
    try:
        args = build_parser().parse_args(list(argv) if argv is not None else None)
    except SystemExit:
        return emit({"error": "usage", "message": "The arguments were not understood."}, "plan",
                    EXIT_INTERNAL)
    mode = args.mode
    if args.contract != CONTRACT_VERSION:
        return emit({"error": "contract",
                     "message": f"This tool speaks version {CONTRACT_VERSION}; the command asked "
                                f"for {args.contract}. Update the plugin, then run this again."},
                    mode, EXIT_CONTRACT)
    try:
        payload, code = _run(args, home, cwd or os.getcwd())
    except Ambiguous as exc:
        return emit({"error": "ambiguous_project", "candidates": exc.candidates,
                     "message": exc.message}, mode, EXIT_NOTHING)
    except Refused as exc:
        return emit({"error": "refused", "rule": exc.rule, "message": exc.message}, mode,
                    EXIT_REFUSED)
    except Internal as exc:
        return emit({"error": "internal", "message": exc.message}, mode, EXIT_INTERNAL)
    except Exception as exc:  # fail closed: an unclassified error deletes nothing
        return emit({"error": "internal", "message": f"Nothing was changed. {exc}"}, mode,
                    EXIT_INTERNAL)
    if payload.get("failed") or payload.get("verified") is False:
        return emit(payload, mode, EXIT_INTERNAL)
    return emit(payload, mode, code)


if __name__ == "__main__":  # pragma: no cover - exercised via main() in tests
    sys.exit(main())
