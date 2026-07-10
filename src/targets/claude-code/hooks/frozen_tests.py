"""PreToolUse hook: block edits to frozen test files during an active Hercules build.

Wired by `plugin/hooks/hooks.json` on `Edit|MultiEdit|Write|NotebookEdit`. Reads the
PreToolUse payload as JSON on stdin. Exit 2 (with a plain-language reason on stderr)
hard-blocks the tool call; exit 0 allows it.

Enforcement scope (honest): this hardens the frozen-test guarantee against accidental,
lazy, and pressure-tested deviation by a cooperative model. It reads model-authored state,
so it is runtime-*mediated*, not tamper-proof against a model that rewrites its own state.

Fail policy: fail OPEN (allow) whenever no active build session resolves — a fresh repo, a
non-Hercules repo, Hercules's own development, or any parse error — so the hook never bricks
an unrelated edit. It only blocks when a confirmed active build owns the target as a frozen
test. Invoked in hook exec form (`command: "python3"`, `args:
["${CLAUDE_PLUGIN_ROOT}/hooks/frozen_tests.py"]`) — Claude Code spawns `python3` directly (no
shebang, no shell), resolving it on PATH. Where no `python3` is found — e.g. stock Windows,
which ships `python`/`py` — the spawn fails, Claude Code proceeds, and the guard is absent by
the fail-open policy rather than broken.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hercules_state import canon, frozen_candidates, resolve_build_contexts  # noqa: E402

_MUTATING_TOOLS = {"Edit", "MultiEdit", "Write", "NotebookEdit"}


def _target_paths(tool_input):
    """Every file path a mutating tool would touch.

    Edit/Write/MultiEdit use a single top-level `file_path` (MultiEdit's `edits[]` share it);
    NotebookEdit uses `notebook_path`. Also tolerate a per-edit `file_path` defensively.
    """
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
    """True iff an explicit user-granted `frozen_override` covers this path right now.

    The override is spec- and round-bound and fails CLOSED: anything malformed, stale,
    or mistyped leaves the block standing. Parsed inside its own guard so a bad override
    can never disarm the wider frozen check.
    """
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
        targets = []
        for path in _target_paths(payload.get("tool_input")):
            p = str(path)
            if not os.path.isabs(p):
                p = os.path.join(cwd, p)  # the payload's cwd, never the hook process's
            targets.append((path, canon(p)))
        for session, roots, project in contexts:
            frozen_set = set()
            for frozen_entry in session.get("frozen_test_files") or []:
                frozen_set |= frozen_candidates(frozen_entry, roots)
            for raw, target in targets:
                if target in frozen_set and not _override_allows(session, roots, target):
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
