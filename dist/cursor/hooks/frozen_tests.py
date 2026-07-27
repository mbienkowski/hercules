"""PreToolUse hook: block edits to frozen test files during an active Hercules build.

Wired by `hooks/hooks.json` on `Edit|MultiEdit|Write|NotebookEdit` and spawned in exec form as
`python3 ${CLAUDE_PLUGIN_ROOT}/hooks/frozen_tests.py`, with the payload as JSON on stdin. Exit 2
(reason on stderr) hard-blocks the tool call; exit 0 allows it.

Fails OPEN — no resolvable active build, a parse error, or no `python3` on PATH all allow the edit —
so the hook never bricks unrelated work; it blocks only when a confirmed active build owns the
target. It reads model-authored state, so enforcement is runtime-*mediated*, not tamper-proof
against a model that rewrites that state.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys

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
    """True iff an explicit user-granted `frozen_override` covers this path right now. Spec- and
    round-bound, and fails CLOSED: anything malformed, stale, or mistyped leaves the block standing.
    Parsed inside its own guard so a bad override can never disarm the wider frozen check."""
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
    """True if one frozen-test entry has drifted from its baseline (fail-closed). Three drift causes:
    the file was never baselined, every copy vanished, or a present copy's hash differs and no active
    override covers it. `entry` is already validated as a non-empty string by the caller."""
    want = baseline.get(entry)
    if not isinstance(want, str) or not want:
        return True  # active baseline but this frozen file wasn't baselined → fail-closed
    candidate_hashes = [(c, _sha256(c)) for c in frozen_candidates(entry, roots)]
    present = [(c, h) for c, h in candidate_hashes if h is not None]  # copies still on disk
    if not present:
        return True  # a frozen test that disappeared is tampering (fail-closed)
    # EVERY present copy must match the baseline; a mismatch under ANY root is drift unless the
    # user's override covers that copy (an override spans every root of the entry).
    mismatched = [(c, h) for c, h in present if h != want]
    if not mismatched:
        return False
    return any(not _override_allows(session, roots, c) for c, _ in mismatched)


def frozen_drift(session, roots) -> list:
    """The ``frozen_test_files`` entries whose on-disk bytes diverge from ``session['frozen_baseline']``
    (a ``{repo-relative-path: sha256}`` map) and that no live ``frozen_override`` covers — the
    phase-acceptance backstop run before a spec is retired, catching a tamper made by any route.

    Inactive (returns ``[]``) when no baseline was recorded. When active the direction is fail-closed:
    a vanished or never-baselined entry is drift, and an entry resolving under several roots is drift
    if **any** root's copy diverges. Never raises.
    """
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
        # EVERY matching build session keeps its guard (nested projects, shared
        # directories, paused builds) — a single-winner pick would fail the rest open.
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


# pragma: no mutate — the guard's only mutant sys.exits pytest at collection (exit 0),
# which mutmut misreads as survived; the import-side-effect and end-to-end tests cover it.
if __name__ == "__main__":  # pragma: no mutate
    sys.exit(main())
