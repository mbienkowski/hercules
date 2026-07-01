"""PreToolUse hook: block edits to frozen test files during an active Hercules build.

Wired by `plugin/hooks/hooks.json` on `Edit|MultiEdit|Write`. Reads the PreToolUse
payload as JSON on stdin. Exit 2 (with a plain-language reason on stderr) hard-blocks the
tool call; exit 0 allows it.

Enforcement scope (honest): this hardens the frozen-test guarantee against accidental,
lazy, and pressure-tested deviation by a cooperative model. It reads model-authored state,
so it is harness-*mediated*, not tamper-proof against a model that rewrites its own state.

Fail policy: fail OPEN (allow) whenever no active build session resolves — a fresh repo, a
non-Hercules repo, Hercules's own development, or any parse error — so the hook never bricks
an unrelated edit. It only blocks when a confirmed active build owns the target as a frozen
test. Invoked as `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/frozen_tests.py"` (no shebang, so
interpreter resolution is the harness's PATH lookup — portable to Windows).
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hercules_state import canon, frozen_candidates, resolve_session  # noqa: E402

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
    rnd = session.get("current_spec_round", "?")
    return (
        f"Hercules: {path} is a frozen test for {spec} (build round {rnd}/3). "
        "Frozen tests are not edited during implementation — the guarantee is that acceptance "
        "criteria can't be weakened to force a pass. To change it legitimately: finish the round "
        'limit and choose "correct the test" to re-enter /hercules:design, or say "start fresh".'
    )


def decide(payload, home=None):
    """Return `(exit_code, reason)` — 2 blocks, 0 allows. Never raises (guards a live edit)."""
    try:
        if not isinstance(payload, dict) or payload.get("tool_name") not in _MUTATING_TOOLS:
            return 0, ""
        session, roots = resolve_session(payload.get("cwd") or os.getcwd(), home=home)
        if not session or session.get("current_phase") != "build":
            return 0, ""  # fail-open: nothing active to protect
        frozen = session.get("frozen_test_files") or []
        if not frozen:
            return 0, ""
        frozen_set = set()
        for entry in frozen:
            frozen_set |= frozen_candidates(entry, roots)
        for path in _target_paths(payload.get("tool_input")):
            if canon(path) in frozen_set:
                return 2, _reason(path, session)
        return 0, ""
    except Exception:
        return 0, ""


def main(stdin_text=None, home=None) -> int:
    raw = stdin_text if stdin_text is not None else sys.stdin.read()
    try:
        payload = json.loads(raw) if raw and raw.strip() else {}
    except Exception:
        return 0
    code, reason = decide(payload, home=home)
    if code == 2:
        print(reason, file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
