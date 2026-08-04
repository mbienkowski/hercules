"""Retire one delivered spec: delete its file and clear its build-round bookkeeping from
`~/.hercules/state/{slug}.json`, as one command rather than a sequence an agent can reorder. The
ORDER is the safety property, enforced in code — (1) re-run the acceptance backstop and refuse the
whole retire on a tampered or unresolvable frozen test; (2) delete the spec file, `git rm` when git
tracks it and a plain unlink otherwise, skipped under `--keep-specs`; (3) only then patch the
session. It fails CLOSED throughout, and `apply` acts only behind an explicit `--confirm`.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_UNCONFIRMED = 2
EXIT_INTERNAL = 3
EXIT_NOT_FOUND = 4
EXIT_FROZEN_DRIFT = 5

_GIT_TIMEOUT_SECONDS = 10


class Ambiguous(Exception):
    """A project slug or session id named on the command line matched nothing. Carries the
    candidate list so the caller can offer a choice rather than guess."""

    def __init__(self, candidates, message: str):
        super().__init__(message)
        self.candidates = candidates
        self.message = message


class Refused(Exception):
    """A safety rule rejected the retire before anything ran. Carries the rule identifier and the
    scripted message the command relays verbatim."""

    def __init__(self, rule: str, message: str):
        super().__init__(message)
        self.rule = rule
        self.message = message


class FrozenDrift(Exception):
    """The acceptance backstop found a tampered, vanished, or unresolvable frozen test. Nothing is
    deleted or patched when this is raised — step 1 blocking steps 2 and 3 is the whole point."""

    def __init__(self, drifted_files, message: str):
        super().__init__(message)
        self.drifted_files = drifted_files
        self.message = message


class Internal(Exception):
    """The record, the spec file, or the backstop module could not be read, written, run, or
    verified. Never a reason to retry automatically."""

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
    rather than acting on content it could not fully understand."""
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


def canon(p) -> str:
    """Canonicalise a path for comparison: expand ~, resolve symlinks/.., fold case — the
    fail-closed direction on macOS/Windows, where differently-cased paths name the same file."""
    try:
        resolved = os.path.realpath(os.path.expanduser(str(p)))
    except Exception:
        resolved = str(p)
    if sys.platform == "darwin":
        return resolved.lower()
    return os.path.normcase(resolved)


def is_within(child_c: str, root_c: str) -> bool:
    """True when `child_c` IS `root_c` or lives inside it, matching whole path components."""
    return child_c == root_c or child_c.startswith(root_c + os.sep)


# ── Resolution — a slug, a session, and a spec name are dictionary lookups, never path fragments ───

def _project_candidates(projects: dict) -> list:
    """Every registered project, as a refusal renders them when it has to ask for one."""
    return [
        {"slug": slug, "directory": entry.get("directory", "")}
        for slug, entry in sorted(projects.items()) if isinstance(entry, dict)
    ]


def resolve_project(projects: dict, slug: str):
    """Return `(slug, entry)`, or raise `Ambiguous` carrying every registered project."""
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
    """Return `(session_id, session)`, or raise `Ambiguous` carrying every session on record."""
    session = (state.get("sessions") or {}).get(session_id)
    if isinstance(session, dict):
        return session_id, session
    raise Ambiguous(_session_candidates(state),
                    f"No session '{session_id}' is recorded for this project. Choose one of the "
                    "sessions listed.")


def _resolved_docs_root(entry: dict):
    """This project's documents root as a real, comparable path.

    `docs_root` in the registry defaults to `"docs"` and is usually RELATIVE — same-repo docs live
    under the project's own `directory` (see `hercules-reference § Artifact root resolution`). A
    bare `canon()` of a relative string resolves it against whatever directory THIS PROCESS happens
    to be running in, which is only ever correct by coincidence; join it to `directory` explicitly
    instead, so containment is fixed by the registry, never by the caller's shell state. A
    separate-repo `docs_root` is already an absolute, user-confirmed path by the time it reaches the
    registry (resolved once, interactively, at Discover) and passes through unchanged.

    Returns `None` only when `docs_root` is relative and `directory` is not on record — the one
    genuinely unresolvable case. This tool cannot prompt interactively; the caller turns that `None`
    into a refusal whose message tells the AGENT to ask the user, the same indirection every other
    refusal here already uses."""
    docs_root = entry.get("docs_root") or "docs"
    root = Path(docs_root).expanduser()
    if root.is_absolute():
        return root
    directory = entry.get("directory")
    if not directory:
        return None
    return Path(directory).expanduser() / docs_root


def resolve_spec(entry: dict, session: dict, spec_file_arg: str):
    """The spec's basename and on-disk path, matched against the session's OWN record rather than
    trusted from the argument. Refuses a blank name, an unrecognised spec, an unresolvable documents
    root, or a path outside it."""
    if not str(spec_file_arg).strip():
        raise Refused("spec_file_blank",
                      "No spec file was named. Nothing was changed. Pass --spec-file, then run "
                      "this again.")
    spec_path = Path(spec_file_arg).expanduser()
    spec_name = spec_path.name
    pending = session.get("pending_specs") or []
    if spec_name != session.get("current_spec") and spec_name not in pending:
        raise Refused("unknown_spec",
                      f"'{spec_name}' is not this session's current spec or one of its pending "
                      "specs. Nothing was changed. Name a recognised spec, then run this again.")
    docs_root = _resolved_docs_root(entry)
    if docs_root is None:
        raise Refused("docs_root_unresolvable",
                      "This project's documents root could not be resolved automatically — "
                      "docs_root is relative and no directory is on record for it. Nothing was "
                      "changed. Ask the user for the documents-root path, record it in the "
                      "project's registry entry, then run this again.")
    if not is_within(canon(spec_path), canon(docs_root)):
        raise Refused("spec_outside_docs_root",
                      f"'{spec_file_arg}' resolves outside this project's documents root. Nothing "
                      "was changed. Pass a path inside the documents root, then run this again.")
    return spec_name, spec_path


# ── Step 1 — the acceptance backstop ──────────────────────────────────────────────────────────

def _load_frozen_tests():
    """Load the sibling `hooks/frozen_tests.py` by file path, never a package import, so `tools/` and
    `hooks/` stay independently copyable. Raises `Internal`: an unverifiable retire never proceeds."""
    hooks_path = Path(__file__).resolve().parent.parent / "hooks" / "frozen_tests.py"
    try:
        spec = importlib.util.spec_from_file_location("_retire_spec_frozen_tests", hooks_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception as exc:
        raise Internal(
            f"Could not load the acceptance backstop ({hooks_path}). Nothing was changed. {exc}"
        ) from exc


def run_frozen_check(project_slug: str, session_id: str, home) -> tuple:
    """`(exit_code, payload)` from the same `frozen_drift()` the live hook uses, run deliberately by
    this tool rather than triggered by a live edit."""
    module = _load_frozen_tests()
    return module.check_command(project_slug, session_id, home=home)


# ── Step 2 — delete the spec file ─────────────────────────────────────────────────────────────

def _git_tracks(repo_dir: Path, name: str) -> bool:
    """Whether git tracks `name` inside `repo_dir`. False on anything but a clean answer — no repo,
    no git binary, and an untracked file all take the plain-delete path. Never raises."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_dir), "ls-files", "--error-unmatch", "--", name],
            capture_output=True, text=True, timeout=_GIT_TIMEOUT_SECONDS,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _delete_file(path: Path) -> str:
    """Remove one file — `git rm` when git tracks it (staging the removal), a plain unlink
    otherwise — and report which route was taken. Already absent counts as done, so a re-run
    resumes. The shared body behind `delete_spec_file` and `delete_report_file`: the same file
    can be the spec or its review, and the safety property is identical either way."""
    if not path.exists():
        return "already_absent"
    repo_dir = path.parent
    if _git_tracks(repo_dir, path.name):
        try:
            result = subprocess.run(
                ["git", "-C", str(repo_dir), "rm", "--quiet", "--", path.name],
                capture_output=True, text=True, timeout=_GIT_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise Internal(f"'git rm' could not run for {path}. Nothing else was changed. "
                          f"{exc}") from exc
        if result.returncode != 0:
            raise Internal(
                f"'git rm' failed for {path}: {result.stderr.strip() or 'unknown error'}. "
                "Nothing else was changed."
            )
        return "git_rm"
    try:
        path.unlink()
    except OSError as exc:
        raise Internal(
            f"Could not delete {path}. Nothing else was changed. {exc.strerror or exc}"
        ) from exc
    return "unlink"


def delete_spec_file(spec_path: Path) -> str:
    """Remove the spec file. Named apart from `_delete_file` because a test monkeypatches this
    exact name to simulate an unclassified failure — keep the name stable even though the body
    is shared."""
    return _delete_file(spec_path)


def delete_report_file(spec_path: Path) -> str:
    """Remove the spec's review, `{stem}-report.json` beside it, regardless of `keep_specs`.

    The report is transient working evidence for the falsification and coverage gates, never the
    permanent artifact `keep_specs` protects — a report proves ONE draft was reviewed, and once that
    draft is superseded (deleted, or refreshed under `keep_specs`), the report is not just stale, it
    is actively misleading: it would keep saying `proceed` about a document it never actually read.
    Absent counts as done, so a spec retired before review reports existed is not an error."""
    return _delete_file(spec_path.with_name(spec_path.stem + "-report.json"))


# ── Step 3 — patch state ──────────────────────────────────────────────────────────────────────

def atomic_write_json(path: Path, data) -> None:
    """Write JSON through a temporary file in the SAME directory: flush, fsync, copy the original's
    permission bits, then `os.replace` — atomic on POSIX and Windows, unlike `os.rename`."""
    payload = json.dumps(data, indent=2, ensure_ascii=True) + "\n"
    try:
        mode = os.stat(path).st_mode & 0o777
        handle, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".retire_spec.")
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


def patch_retired_session(session: dict, spec_name: str) -> dict:
    """The session with this spec's freeze bookkeeping cleared and the spec moved from `pending_specs`
    to `delivered_specs` (the pending key omitted once empty). Every other key survives untouched."""
    updated = dict(session)
    for key in ("frozen_test_files", "frozen_baseline", "frozen_override"):
        updated.pop(key, None)
    pending = [s for s in (session.get("pending_specs") or []) if s != spec_name]
    if pending:
        updated["pending_specs"] = pending
    else:
        updated.pop("pending_specs", None)
    delivered = list(session.get("delivered_specs") or [])
    if spec_name not in delivered:
        delivered.append(spec_name)
    updated["delivered_specs"] = delivered
    return updated


def verify_retired_session(path: Path, session_id: str, spec_name: str, before_state: dict) -> bool:
    """Re-read the written state and confirm the retire landed AND every other session and top-level
    key survived unchanged. A false result is an internal error, never a reason to retry."""
    after = read_json(path)
    sessions = after.get("sessions")
    if not isinstance(sessions, dict):
        return False
    patched = sessions.get(session_id)
    if not isinstance(patched, dict):
        return False
    if any(key in patched for key in ("frozen_test_files", "frozen_baseline", "frozen_override")):
        return False
    if spec_name in (patched.get("pending_specs") or []):
        return False
    if spec_name not in (patched.get("delivered_specs") or []):
        return False
    before_sessions = before_state.get("sessions") or {}
    for key, value in before_sessions.items():
        if key != session_id and sessions.get(key) != value:
            return False
    return all(after.get(key) == value for key, value in before_state.items() if key != "sessions")


# ── The two modes ─────────────────────────────────────────────────────────────────────────────

def build_plan(slug, entry, session_id, session, spec_name, spec_path, keep_specs,
              check_payload) -> dict:
    """What a retire would do: the resolved project, session and spec, the backstop's current
    verdict, and exactly what step 2/3 would change. Writes nothing; safe to call repeatedly."""
    return {
        "project": {"slug": slug, "directory": entry.get("directory", "")},
        "session": {"id": session_id, "current_phase": session.get("current_phase", "unknown")},
        "spec": {"name": spec_name, "path": str(spec_path), "keep_specs": bool(keep_specs)},
        "frozen_check": check_payload,
        "would_retire": {
            "delete_spec_file": not keep_specs,
            "delete_report_file": True,
            "clears": ["frozen_test_files", "frozen_baseline", "frozen_override"],
            "drops_from_pending_specs": spec_name,
            "appends_to_delivered_specs": spec_name,
        },
    }


def apply_retire(home, slug, entry, session_id, session, spec_name, spec_path, keep_specs) -> dict:
    """Perform the retire IN ORDER: the backstop, which raises `FrozenDrift` and stops everything on
    a tampered test; then the file delete, skipped under `keep_specs`; then the state patch."""
    check_code, check_payload = run_frozen_check(slug, session_id, home)
    if check_code != 0:
        raise FrozenDrift(
            check_payload.get("drifted_files") or [],
            "The acceptance backstop found a tampered or unresolvable frozen test. Nothing was "
            "deleted or changed. Inspect the drifted files, then run this again."
        )
    deletion = "kept" if keep_specs else delete_spec_file(spec_path)
    report_deletion = delete_report_file(spec_path)
    path = state_path(home, entry, slug)
    before_state = read_json(path)
    updated_state = dict(before_state)
    sessions = dict(before_state.get("sessions") or {})
    sessions[session_id] = patch_retired_session(session, spec_name)
    updated_state["sessions"] = sessions
    atomic_write_json(path, updated_state)
    verified = verify_retired_session(path, session_id, spec_name, before_state)
    return {
        "project": {"slug": slug, "directory": entry.get("directory", "")},
        "session": {"id": session_id},
        "spec": {"name": spec_name, "deletion": deletion, "report_deletion": report_deletion},
        "frozen_check": check_payload,
        "verified": verified,
    }


# ── Command line ──────────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    """The whole argument surface: a mode, the project/session/spec being retired, `--keep-specs`,
    and `--confirm`."""
    parser = argparse.ArgumentParser(prog="retire_spec", add_help=False)
    parser.add_argument("mode", choices=("plan", "apply"))
    parser.add_argument("--project-slug", dest="project_slug", required=True)
    parser.add_argument("--session-id", dest="session_id", required=True)
    parser.add_argument("--spec-file", dest="spec_file", required=True)
    parser.add_argument("--keep-specs", dest="keep_specs", action="store_true")
    parser.add_argument("--confirm", action="store_true")
    return parser


def emit(payload: dict, mode: str, code: int) -> int:
    """Print the payload as JSON on stdout and return the exit code. Every path emits, including
    refusals, so the command parses one shape and never has to guess."""
    print(json.dumps(dict({"mode": mode}, **payload), indent=2))
    return code


def _run(args, home) -> tuple:
    """Resolve and dispatch. Raises the carrier exceptions; `main` renders them."""
    projects = load_registry(home)
    slug, entry = resolve_project(projects, args.project_slug)
    state = read_json(state_path(home, entry, slug))
    session_id, session = resolve_session(state, args.session_id)
    spec_name, spec_path = resolve_spec(entry, session, args.spec_file)
    if args.mode == "plan":
        check_code, check_payload = run_frozen_check(slug, session_id, home)
        return build_plan(slug, entry, session_id, session, spec_name, spec_path, args.keep_specs,
                          check_payload), EXIT_OK
    if not args.confirm:
        return {"error": "unconfirmed",
                "message": "Nothing was changed. This step needs an explicit confirmation."}, \
            EXIT_UNCONFIRMED
    return apply_retire(home, slug, entry, session_id, session, spec_name, spec_path,
                        args.keep_specs), EXIT_OK


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
    except FrozenDrift as exc:
        return emit({"error": "frozen_drift", "drifted_files": exc.drifted_files,
                     "message": exc.message}, mode, EXIT_FROZEN_DRIFT)
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
