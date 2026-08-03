"""Patch named fields in Hercules' machine-local record of one project — keys in one session
(`--set`/`--unset`) or a service's repository path (`--set-repository`) — wherever delivery prose
would otherwise ask an agent to "write atomically, preserving other sessions". Every write proves
its neighbours untouched, reading back what it wrote to confirm every OTHER session and project
still holds its exact prior value; the failure it exists to prevent is a naive rewrite dropping a
sibling. It fails CLOSED, `apply` needs `--confirm`, and a slug is a lookup, never a path fragment.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_UNCONFIRMED = 2
EXIT_INTERNAL = 3
EXIT_NOT_FOUND = 4


class Ambiguous(Exception):
    """A project slug or session id named on the command line matched nothing. Carries the candidate
    list so the caller can offer a choice rather than guess."""

    def __init__(self, candidates, message: str):
        super().__init__(message)
        self.candidates = candidates
        self.message = message


class Refused(Exception):
    """A safety rule rejected the requested patch. Carries the rule identifier and the scripted
    message the command relays verbatim."""

    def __init__(self, rule: str, message: str):
        super().__init__(message)
        self.rule = rule
        self.message = message


class Internal(Exception):
    """The record could not be read, written or verified. Never a reason to retry automatically."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


# ── Reading the registry and state ────────────────────────────────────────────────────────────

def hercules_home(home=None) -> Path:
    """The state tree root. Tests pass an explicit `home`; there is deliberately no flag for it, so
    a caller cannot redirect the tool at another tree."""
    return (Path(home) if home else Path.home()) / ".hercules"


def read_json(path: Path):
    """Parse a JSON file. Raises `Internal` on a missing or malformed file — the caller refuses
    rather than patching content it could not fully understand."""
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


# ── Resolution — a slug or a session id is a dictionary lookup, never a path ──────────────────

def _project_candidates(projects: dict) -> list:
    """Every registered project, as a refusal renders them when it has to ask for one."""
    return [
        {"slug": slug, "directory": entry.get("directory", "")}
        for slug, entry in sorted(projects.items()) if isinstance(entry, dict)
    ]


def resolve_project(projects: dict, slug: str):
    """Return `(slug, entry)`, or raise `Ambiguous` carrying every registered project when `slug`
    names none of them."""
    entry = projects.get(slug)
    if isinstance(entry, dict):
        return slug, entry
    raise Ambiguous(_project_candidates(projects),
                    "No project of that name is registered. Choose one of the projects listed.")


def _session_candidates(state: dict) -> list:
    """Every session on record with its phase, as a refusal renders them when it has to ask."""
    sessions = state.get("sessions") or {}
    return [{"id": key, "current_phase": (value or {}).get("current_phase", "unknown")}
            for key, value in sorted(sessions.items())]


def resolve_session(state: dict, session_id: str):
    """Return `(session_id, session)`, or raise `Ambiguous` carrying every session on record when
    `session_id` names none of them."""
    session = (state.get("sessions") or {}).get(session_id)
    if isinstance(session, dict):
        return session_id, session
    raise Ambiguous(_session_candidates(state),
                    f"No session '{session_id}' is recorded for this project. Choose one of the "
                    "sessions listed.")


# ── Parsing and validating the requested changes ──────────────────────────────────────────────

def parse_value(raw: str):
    """A `--set` value as JSON when it parses as JSON, otherwise the raw string — so `true` lands as
    a boolean and a plain word like `low` lands as the string the session field expects."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def parse_set(raw: str) -> tuple:
    """One `--set key=value` argument, split on the first `=`. Refuses a missing separator or a
    blank key rather than silently patching nothing."""
    if "=" not in raw:
        raise Refused("malformed_set", f"'--set {raw}' is missing '='. Use --set key=value.")
    key, _, value = raw.partition("=")
    key = key.strip()
    if not key:
        raise Refused("malformed_set", f"'--set {raw}' has no key before '='. Use --set key=value.")
    return key, parse_value(value)


def parse_unset(raw: str) -> str:
    """One `--unset key` argument. Refuses a blank key."""
    key = raw.strip()
    if not key:
        raise Refused("malformed_unset", "'--unset' needs a key name. Use --unset key.")
    return key


def parse_repository(raw: str) -> tuple:
    """One `--set-repository service=path` argument, split on the first `=`. Refuses a missing
    separator, a blank service name, or a blank path."""
    if "=" not in raw:
        raise Refused("malformed_set_repository",
                      f"'--set-repository {raw}' is missing '='. Use --set-repository service=path.")
    service, _, path = raw.partition("=")
    service = service.strip()
    if not service:
        raise Refused("malformed_set_repository",
                      f"'--set-repository {raw}' has no service name before '='. "
                      "Use --set-repository service=path.")
    if not path.strip():
        raise Refused("malformed_set_repository",
                      f"'--set-repository {raw}' has no path after '='. "
                      "Use --set-repository service=path.")
    return service, path


def check_repository_path(service: str, raw_path: str) -> None:
    """A repository must already exist on disk — this tool records a path, it never creates one."""
    if not Path(raw_path).expanduser().is_dir():
        raise Refused("repository_path_missing",
                      f"The directory for '{service}' ({raw_path}) does not exist. Nothing was "
                      "changed. Create it or correct the path, then run this again.")


def build_changes(args) -> dict:
    """The whole requested patch as plain data, every repository path validated — a later `--set` for
    the same key silently wins. Refuses a key in both `--set` and `--unset`, and an empty request."""
    sets: dict = {}
    for raw in args.set:
        key, value = parse_set(raw)
        sets[key] = value
    unsets: list = []
    seen_unset = set()
    for raw in args.unset:
        key = parse_unset(raw)
        if key not in seen_unset:
            unsets.append(key)
            seen_unset.add(key)
    conflicts = sorted(set(sets) & seen_unset)
    if conflicts:
        raise Refused("key_set_and_unset",
                      f"'{conflicts[0]}' is both set and unset in the same run. Choose one, then "
                      "run this again.")
    set_repository: dict = {}
    for raw in args.set_repository:
        service, path = parse_repository(raw)
        check_repository_path(service, path)
        set_repository[service] = path
    if not sets and not unsets and not set_repository:
        raise Refused("no_changes_requested",
                      "Nothing was specified to change. Add --set, --unset, or --set-repository, "
                      "then run this again.")
    return {"set": sets, "unset": unsets, "set_repository": set_repository}


# ── Atomic edits to the record ────────────────────────────────────────────────────────────────

def atomic_write_json(path: Path, data) -> None:
    """Write JSON through a temporary file in the SAME directory: flush, fsync, copy the original's
    permission bits, then `os.replace` — atomic on POSIX and Windows, unlike `os.rename`."""
    payload = json.dumps(data, indent=2, ensure_ascii=True) + "\n"
    try:
        mode = os.stat(path).st_mode & 0o777
        handle, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".state_patch.")
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


def patch_session(session: dict, changes: dict) -> dict:
    """One session, `--unset` keys removed and `--set` keys applied, on top of a copy — every other
    key in the session is carried through untouched."""
    updated = dict(session)
    for key in changes["unset"]:
        updated.pop(key, None)
    updated.update(changes["set"])
    return updated


def patch_sessions_map(state: dict, session_id: str, changes: dict) -> dict:
    """The whole state file with exactly one session replaced by its patched copy."""
    updated = dict(state)
    sessions = dict(state.get("sessions") or {})
    sessions[session_id] = patch_session(sessions[session_id], changes)
    updated["sessions"] = sessions
    return updated


def patch_repositories(entry: dict, set_repository: dict) -> dict:
    """One registry entry with its `repositories` map merged, not replaced — an existing service
    path not named on the command line survives."""
    repositories = dict(entry.get("repositories") or {})
    repositories.update(set_repository)
    return {**entry, "repositories": repositories}


def verify_session_patch(path: Path, session_id: str, changes: dict, before_state: dict) -> bool:
    """Re-read the written state and confirm the patch landed AND every other session and top-level
    key survived unchanged. A false result is an internal error, never a reason to retry."""
    after = read_json(path)
    sessions = after.get("sessions")
    if not isinstance(sessions, dict):
        return False
    patched = sessions.get(session_id)
    if not isinstance(patched, dict):
        return False
    if any(patched.get(k) != v for k, v in changes["set"].items()):
        return False
    if any(k in patched for k in changes["unset"]):
        return False
    before_sessions = before_state.get("sessions") or {}
    for key, value in before_sessions.items():
        if key != session_id and sessions.get(key) != value:
            return False
    return all(after.get(key) == value for key, value in before_state.items() if key != "sessions")


def verify_repository_patch(after_projects: dict, slug: str, set_repository: dict,
                            before_projects: dict) -> bool:
    """Re-read the written registry and confirm the patch landed AND every other service path, field,
    and project survived unchanged."""
    patched = after_projects.get(slug)
    if not isinstance(patched, dict):
        return False
    repositories = patched.get("repositories") or {}
    if any(repositories.get(k) != v for k, v in set_repository.items()):
        return False
    before_entry = before_projects.get(slug) or {}
    if any(patched.get(key) != value for key, value in before_entry.items() if key != "repositories"):
        return False
    before_repositories = before_entry.get("repositories") or {}
    for key, value in before_repositories.items():
        if key not in set_repository and repositories.get(key) != value:
            return False
    return all(after_projects.get(slug2) == entry2
              for slug2, entry2 in before_projects.items() if slug2 != slug)


# ── The two modes ─────────────────────────────────────────────────────────────────────────────

def build_plan(slug: str, entry: dict, session_id: str, session: dict, changes: dict) -> dict:
    """What a patch would do: the resolved project and session (named, never their private
    content), and exactly the change requested. Writes nothing; safe to call repeatedly."""
    return {
        "project": {"slug": slug, "directory": entry.get("directory", "")},
        "session": {"id": session_id, "current_phase": session.get("current_phase", "unknown")},
        "changes": changes,
    }


def apply_patch(home, slug: str, entry: dict, session_id: str, changes: dict, state: dict) -> dict:
    """Perform the patch. Resolves the registry write's own target fresh, right before writing it,
    so it never acts on a copy an earlier step in this same run might have made stale."""
    verified = True
    if changes["set"] or changes["unset"]:
        path = state_path(home, entry, slug)
        atomic_write_json(path, patch_sessions_map(state, session_id, changes))
        verified = verify_session_patch(path, session_id, changes, state) and verified
    if changes["set_repository"]:
        config_path = hercules_home(home) / "config.json"
        config = read_json(config_path)
        before_projects = dict(config.get("projects") or {})
        config["projects"] = dict(before_projects,
                                  **{slug: patch_repositories(before_projects[slug],
                                                              changes["set_repository"])})
        atomic_write_json(config_path, config)
        after_projects = read_json(config_path).get("projects") or {}
        verified = verify_repository_patch(after_projects, slug, changes["set_repository"],
                                           before_projects) and verified
    return {
        "project": {"slug": slug, "directory": entry.get("directory", "")},
        "session": {"id": session_id},
        "applied": changes,
        "verified": verified,
    }


# ── Command line ──────────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    """The whole argument surface: a mode, the project and session, the three kinds of change, and
    `--confirm`. The one path it accepts, a repository directory, is only ever stat'd."""
    parser = argparse.ArgumentParser(prog="state_patch", add_help=False)
    parser.add_argument("mode", choices=("plan", "apply"))
    parser.add_argument("--project-slug", dest="project_slug", required=True)
    parser.add_argument("--session-id", dest="session_id", required=True)
    parser.add_argument("--set", action="append", default=[])
    parser.add_argument("--unset", action="append", default=[])
    parser.add_argument("--set-repository", dest="set_repository", action="append", default=[])
    parser.add_argument("--confirm", action="store_true")
    return parser


def emit(payload: dict, mode: str, code: int) -> int:
    """Print the payload as JSON on stdout and return the exit code. Every path emits, including
    refusals, so the command parses one shape and never has to guess."""
    print(json.dumps(dict({"mode": mode}, **payload), indent=2))
    return code


def _run(args, home) -> tuple:
    """Resolve and dispatch. Raises the three carrier exceptions; `main` renders them."""
    projects = load_registry(home)
    slug, entry = resolve_project(projects, args.project_slug)
    state = read_json(state_path(home, entry, slug))
    session_id, session = resolve_session(state, args.session_id)
    changes = build_changes(args)
    if args.mode == "plan":
        return build_plan(slug, entry, session_id, session, changes), EXIT_OK
    if not args.confirm:
        return {"error": "unconfirmed",
                "message": "Nothing was changed. This step needs an explicit confirmation."}, \
            EXIT_UNCONFIRMED
    return apply_patch(home, slug, entry, session_id, changes, state), EXIT_OK


def main(argv=None, home=None) -> int:
    """Resolve, dispatch, and turn every failure into a scripted refusal — nothing escapes as a
    traceback. `home` is a parameter, never a flag, so no caller can redirect the tool."""
    try:
        args = build_parser().parse_args(list(argv) if argv is not None else None)
    except SystemExit:
        return emit({"error": "usage", "message": "The arguments were not understood."}, "plan",
                    EXIT_INTERNAL)
    mode = args.mode
    try:
        payload, code = _run(args, home)
    except Ambiguous as exc:
        return emit({"error": "ambiguous", "candidates": exc.candidates, "message": exc.message},
                    mode, EXIT_NOT_FOUND)
    except Refused as exc:
        return emit({"error": "refused", "rule": exc.rule, "message": exc.message}, mode,
                    EXIT_REFUSED)
    except Internal as exc:
        return emit({"error": "internal", "message": exc.message}, mode, EXIT_INTERNAL)
    except Exception as exc:  # fail closed: an unclassified error changes nothing
        return emit({"error": "internal", "message": f"Nothing was changed. {exc}"}, mode,
                    EXIT_INTERNAL)
    if payload.get("verified") is False:
        return emit(payload, mode, EXIT_INTERNAL)
    return emit(payload, mode, code)


if __name__ == "__main__":  # pragma: no cover - exercised via main() in tests
    sys.exit(main())
