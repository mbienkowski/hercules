"""Gemini CLI write-gate adapter (G1) — reuses the CANONICAL frozen-guard policy, not a re-port.

Gemini's ``BeforeTool`` hook fires BEFORE a tool touches disk and can veto it — the same shape as
Claude Code's ``PreToolUse``. This adapter therefore enforces a real pre-write block (unlike Cursor,
whose edit hook is notification-only): it maps Gemini's file-mutating tools to the canonical guard's
tool vocabulary and delegates the verdict to ``frozen_tests.decide`` — the SAME frozen-test state and
the SAME ``frozen_override`` policy Claude Code, OpenCode, and Cursor read (both modules ship alongside,
byte-identical). On a frozen-test edit during an active build it prints Gemini's block decision
(``{"decision": "deny", "reason": ...}``); otherwise it prints nothing and Gemini proceeds.

Gemini's file-mutating tools are ``write_file`` (arg ``file_path``) and ``replace`` (arg ``file_path``);
both send ``tool_input.file_path`` and a top-level ``cwd`` — the exact keys the canonical guard reads —
so only the tool NAME is translated. Read tools are never blocked (the doctrine locks frozen tests
against edits, not reads — the implementing agent must read the very test it makes pass).

Invoked as ``python3 hercules_gate.py`` with the Gemini ``BeforeTool`` event JSON on stdin. Fails OPEN
(prints nothing, exit 0) on any error, malformed input, or missing ``python3`` — matching the Claude
frozen hook's policy, so a gate bug never bricks an unrelated edit (disclosed in CAPABILITIES.md).
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from frozen_tests import decide  # noqa: E402  (canonical guard entry point — one source of truth)

# Gemini's file-mutating tools → the canonical guard's tool names. A tool absent here is not a write,
# so it is allowed silently (reads included). ``replace`` is Gemini's in-place edit; ``write_file`` its
# whole-file write — both carry the target path in ``tool_input.file_path``, which the guard reads.
_MUTATING = {"write_file": "Write", "replace": "Edit"}

# The exact literal Gemini expects on stdout to veto a tool call (``block`` is a documented alias;
# ``deny`` is the value the official docs' example uses). Hardcoded so a mutant flipping it is caught.
_DENY = "deny"


def decide_gemini(evt, home=None):
    """Return the Gemini ``BeforeTool`` decision dict to BLOCK *evt*, or ``None`` to allow silently."""
    if not isinstance(evt, dict):
        return None
    mapped = _MUTATING.get(evt.get("tool_name"))
    if mapped is None:
        return None
    payload = {
        "tool_name": mapped,
        "tool_input": evt.get("tool_input") or {},
        "cwd": evt.get("cwd") or os.getcwd(),
    }
    code, reason = decide(payload, home=home)
    if code == 2:
        return {"decision": _DENY, "reason": reason}
    return None


def main(stdin_text=None, home=None) -> int:
    try:
        raw = stdin_text if stdin_text is not None else sys.stdin.read()
        evt = json.loads(raw) if raw and raw.strip() else {}
        decision = decide_gemini(evt, home=home)
        if decision is not None:
            print(json.dumps(decision))
    except Exception:
        pass  # fail OPEN — a gate bug never bricks an edit; Gemini proceeds with no decision
    return 0


# The __main__ guard has no behavioural mutant (a wrapped "__main__" never equals the real dunder),
# so it is pragma'd like frozen_tests.py / the Cursor adapter.
if __name__ == "__main__":  # pragma: no mutate
    sys.exit(main())
