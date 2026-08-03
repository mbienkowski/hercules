"""Blocks edits to a frozen test file while a Hercules build owns it, so acceptance criteria cannot
drift to force a green. Reads model-authored state: enforcement is mediated, not tamper-proof.
Two modes, opposite postures. As a PreToolUse hook (event JSON on stdin, exit 2 blocks) it fails
OPEN — an unresolvable build, a parse error, or a missing `python3` all allow the edit, so a hook
bug never bricks unrelated work. As `check --project-slug S [--session-id ID]` it is the retire-time
backstop and fails CLOSED: anything it cannot resolve is reported as blocking, never as clean.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hercules_state import canon, frozen_candidates, resolve_build_contexts  # noqa: E402

_MUTATING_TOOLS = {"Edit", "MultiEdit", "Write", "NotebookEdit"}


def _target_paths(tool_input):
    """Every file path a mutating tool would touch: the top-level `file_path`/`notebook_path`, plus
    a per-edit `file_path` inside `edits[]` when a host supplies one."""
    paths = []
    if isinstance(tool_input, dict):
        for key in ("file_path", "notebook_path"):
            if tool_input.get(key):
                paths.append(tool_input[key])
        for edit in tool_input.get("edits") or []:
            if isinstance(edit, dict) and edit.get("file_path"):
                paths.append(edit["file_path"])
    return paths


def _reason(path, session) -> str:
    """The refusal a person and an agent both read: which test, which spec and round, and the two
    ways to unblock it — a user-granted override for this turn, or a project-wide opt-out."""
    spec = session.get("current_spec") or "the current spec"
    rnd = session.get("current_spec_round") or 1
    return (
        f"Hercules: {path} is a frozen test for {spec} (build round {rnd}/3). "
        "Tests stay frozen during implementation so acceptance criteria can't drift to force "
        'a pass. User: saying "change this test — <why>" unblocks it this turn; or ask to turn '
        "the guard off for this project. Agent: on that instruction, record frozen_override in "
        "the session state with all four fields — files (this path), spec, current round, and "
        "the user's words quoted — then retry in the same turn; or finish the round and decide "
        "at the round-limit stop (correct the test, rework the design, adjust scope, more "
        'rounds, or accept with a reason). Project-wide opt-out: frozen_hook: "off" in the '
        "registry."
    )


def _override_allows(session, roots, target_canon) -> bool:
    """True iff a user-granted `frozen_override` covers this path right now — spec- and round-bound.
    Fails CLOSED: anything malformed, stale, or mistyped leaves the block standing."""
    try:
        ov = session.get("frozen_override")
        if not isinstance(ov, dict):
            return False
        rnd = ov.get("round")
        if not isinstance(rnd, int) or rnd != session.get("current_spec_round"):
            return False
        if not (isinstance(ov.get("reason"), str) and ov["reason"].strip()):
            return False  # the quoted user grant is part of the contract, not decoration
        if ov.get("spec") != session.get("current_spec"):
            return False
        files = ov.get("files")
        if not isinstance(files, list):
            return False
        allowed = set()
        for f in files:
            allowed |= frozen_candidates(f, roots)  # junk entries resolve to nothing
        return target_canon in allowed
    except Exception:
        return False


def _sha256(path) -> str | None:
    """SHA-256 of a file's bytes, or None if it can't be read (missing/unreadable). Never raises."""
    try:
        with open(path, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()
    except Exception:
        return None


def _entry_drifted(entry, baseline, session, roots) -> bool:
    """True if one frozen-test entry has drifted from its baseline. Fail-closed: never baselined,
    every copy vanished, or a surviving copy's hash differs with no override covering it."""
    want = baseline.get(entry)
    if not isinstance(want, str) or not want:
        return True  # active baseline but this frozen file wasn't baselined → fail-closed
    candidate_hashes = [(c, _sha256(c)) for c in frozen_candidates(entry, roots)]
    present = [(c, h) for c, h in candidate_hashes if h is not None]  # copies still on disk
    if not present:
        return True  # a frozen test that disappeared is tampering (fail-closed)

    # A mismatch under ANY root is drift unless the user's override covers that copy.
    mismatched = [(c, h) for c, h in present if h != want]
    if not mismatched:
        return False
    return any(not _override_allows(session, roots, c) for c, _ in mismatched)


def frozen_drift(session, roots) -> list:
    """The frozen tests whose bytes diverge from the session's baseline with no override covering
    them — the backstop before a spec retires. Inactive until baselined, fail-closed once it is."""
    try:
        baseline = session.get("frozen_baseline")
        if not isinstance(baseline, dict) or not baseline:
            return []  # backstop inactive for this session (nothing was baselined)
        entries = session.get("frozen_test_files")
        if not isinstance(entries, list) or not entries:
            entries = list(baseline)  # fall back to the baselined paths
        drifted = []
        for entry in entries:
            if isinstance(entry, str) and entry and _entry_drifted(entry, baseline, session, roots):
                drifted.append(entry)
        return drifted
    except Exception:
        return []


def _canonical_targets(tool_input, cwd):
    """Each target path a tool names, as `(raw, canonical)`. A relative path resolves against the
    payload's cwd (never the hook process's)."""
    targets = []
    for path in _target_paths(tool_input):
        p = str(path)
        if not os.path.isabs(p):
            p = os.path.join(cwd, p)
        targets.append((path, canon(p)))
    return targets


def _blocked_target(contexts, targets):
    """The first `(raw_path, session)` where a target hits a frozen test no override covers, or None
    when nothing is blocked. Every matching build context is checked (fail-closed for the rest)."""
    for session, roots, _project in contexts:
        frozen_set = set()
        for frozen_entry in session.get("frozen_test_files") or []:
            frozen_set |= frozen_candidates(frozen_entry, roots)
        for raw, target in targets:
            if target in frozen_set and not _override_allows(session, roots, target):
                return raw, session
    return None


def decide(payload, home=None):
    """Return `(exit_code, reason)` — 2 blocks, 0 allows. Never raises (guards a live edit)."""
    try:
        if not isinstance(payload, dict) or payload.get("tool_name") not in _MUTATING_TOOLS:
            return 0, ""
        cwd = payload.get("cwd") or os.getcwd()

        # EVERY matching build session keeps its guard — a single-winner pick fails the rest open.
        contexts = [
            (session, roots, project)
            for session, roots, project in resolve_build_contexts(cwd, home=home)
            if session.get("current_phase") == "build"
            and (project or {}).get("frozen_hook") != "off"
            and session.get("frozen_test_files")
        ]
        if not contexts:
            return 0, ""  # fail-open: nothing active to protect
        targets = _canonical_targets(payload.get("tool_input"), cwd)
        hit = _blocked_target(contexts, targets)
        if hit is not None:
            raw, session = hit
            return 2, _reason(raw, session)
        return 0, ""
    except Exception:
        return 0, ""


def main(stdin_text=None, home=None) -> int:
    """Hook entry point: read the host's event from stdin, print any refusal on stderr, and return
    the exit code that blocks (2) or allows (0). Unreadable input allows, the fail-OPEN direction."""
    try:
        if stdin_text is not None:
            raw = stdin_text
        else:
            raw = sys.stdin.buffer.read().decode("utf-8", "replace")  # pragma: no mutate
        payload = json.loads(raw) if raw and raw.strip() else {}
    except Exception:
        return 0
    code, reason = decide(payload, home=home)
    if code == 2:
        print(reason, file=sys.stderr)
    return code


def _load_registry(home=None) -> dict:
    """The `projects` map from `config.json`, or `{}` when it cannot be read — the caller reports
    that as a resolution failure rather than raising, fail-closed either way."""
    try:
        config = json.loads(((Path(home) if home else Path.home()) / ".hercules" / "config.json")
                            .read_text())
    except Exception:
        return {}
    projects = config.get("projects")
    return projects if isinstance(projects, dict) else {}


def _resolve_check_session(projects, slug, session_id, home):
    """The session `check` re-hashes and the roots its paths resolve under. A slug is a dictionary
    lookup, never a path fragment; an unresolvable one raises `ValueError`, which the caller blocks on."""
    entry = projects.get(slug)
    if not isinstance(entry, dict):
        raise ValueError(f"No project '{slug}' is registered.")
    state_file = entry.get("state_file") or f"{slug}.json"
    if os.path.basename(state_file) != state_file:
        raise ValueError(f"The state pointer for '{slug}' escapes the record directory.")
    home_dir = Path(home) if home else Path.home()
    state = json.loads((home_dir / ".hercules" / "state" / state_file).read_text())
    resolved_id = session_id or state.get("active_session")
    session = (state.get("sessions") or {}).get(resolved_id)
    if not isinstance(session, dict):
        raise ValueError(f"No session '{resolved_id}' is recorded for project '{slug}'.")
    roots = [canon(r) for r in [entry.get("directory")] + list((entry.get("repositories") or {}).values()) if r]
    return resolved_id, session, roots


def check_command(project_slug, session_id=None, home=None) -> tuple:
    """Run the drift backstop for one session by command. `(exit_code, payload)`: 0 with no drifted
    files is clean; 2 is real drift OR an unresolvable project/session — unverifiable must block."""
    try:
        resolved_id, session, roots = _resolve_check_session(_load_registry(home), project_slug,
                                                              session_id, home)
    except Exception as exc:
        return 2, {"project": project_slug, "session": session_id, "drifted_files": [],
                   "error": str(exc)}
    drifted = frozen_drift(session, roots)
    payload = {"project": project_slug, "session": resolved_id, "drifted_files": drifted,
              "error": None}
    return (2 if drifted else 0), payload


def _build_check_parser() -> argparse.ArgumentParser:
    """`check`'s whole argument surface: the project being retired, and optionally which session."""
    parser = argparse.ArgumentParser(prog="frozen_tests check", add_help=False)
    parser.add_argument("--project-slug", dest="project_slug", required=True)
    parser.add_argument("--session-id", dest="session_id", default=None)
    return parser


def cli_main(argv, home=None) -> int:
    """`check`'s entry point: print the verdict as JSON and return its exit code. Kept apart from
    `main()` so the live hook's stdin-JSON contract stays untouched."""
    args = _build_check_parser().parse_args(list(argv))
    code, payload = check_command(args.project_slug, args.session_id, home=home)
    print(json.dumps(payload, indent=2))
    return code


# pragma: no mutate — this guard's only mutant sys.exits pytest at collection, which mutmut misreads as survived; the end-to-end tests cover it.
if __name__ == "__main__":  # pragma: no mutate
    if len(sys.argv) > 1 and sys.argv[1] == "check":
        sys.exit(cli_main(sys.argv[2:]))
    sys.exit(main())
