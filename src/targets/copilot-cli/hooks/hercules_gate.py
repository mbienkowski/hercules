"""Copilot CLI write-gate adapter (G1) — reuses the CANONICAL frozen-guard policy, not a re-port.

Copilot CLI's ``preToolUse`` hook is a real pre-write veto: before a tool runs, this adapter reads the
event on stdin, and if the tool would edit a frozen acceptance test during an active Hercules build it
returns ``permissionDecision: "deny"`` — which Copilot honors by blocking the edit before it lands. The
decision is made by the SAME canonical guard every other ecosystem uses (``frozen_tests.decide`` +
``frozen_tests._override_allows``, both shipped byte-identical alongside), so the frozen set, the block
message, and the user-granted ``frozen_override`` escape hatch are identical across Claude/OpenCode/
Cursor/Copilot — never a second implementation.

Copilot delivers the ``preToolUse`` payload in one of two shapes; this adapter accepts both:

- native camelCase — ``{ toolName, toolArgs, cwd }`` (the ``preToolUse`` event name);
- VS Code compatible snake_case — ``{ tool_name, tool_input, cwd }`` (the ``PreToolUse`` event name).

The write tools it gates are Copilot's file-mutating tools (``create``, ``edit``, ``str_replace_editor``,
``apply_patch`` — and their Claude aliases ``Write``/``Edit``); a read tool (``view``/``Read``) is never
blocked, matching the doctrine that a frozen test may be READ (the agent must read the test it makes
pass), only not edited. The target path is extracted from the tool arguments (whose key varies by tool,
so several candidates are checked defensively) and handed to the canonical guard as a Claude-shaped
payload.

Invoked as ``python3 hercules_gate.py preToolUse`` with the Copilot event JSON on stdin; prints exactly
one decision object on stdout. Fails OPEN (allow) on any error, missing state, or unrecognised payload —
matching the canonical frozen hook — so a gate bug never bricks an unrelated edit. The shipped
``hooks.json`` additionally guards the shell invocation (``|| exit 0``) so a missing ``python3`` also
fails OPEN rather than tripping Copilot's fail-CLOSED-on-nonzero-exit rule (disclosed in CAPABILITIES).
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from frozen_tests import decide  # noqa: E402  (the canonical block decision — one source of truth)

# Copilot's file-mutating tools (native runtime names + their Claude aliases). A read tool (``view`` /
# ``Read``) is deliberately absent — the doctrine allows reading a frozen test, only not editing it.
_WRITE_TOOLS = frozenset({
    "create", "edit", "str_replace_editor", "apply_patch", "write",
    "Write", "Edit", "MultiEdit", "NotebookEdit",
})

# Argument keys a Copilot write tool may carry the target path under. Coarse by necessity: the adapter
# sees only the serialized arguments the tool exposes, and the key varies by tool — so several plausible
# spellings are tried. If none match, the adapter fails OPEN (allow), disclosed in CAPABILITIES.md.
_PATH_KEYS = (
    "path", "file_path", "filePath", "filename", "fileName", "file",
    "notebook_path", "notebookPath", "target_file", "targetFile",
    "absolute_path", "absolutePath",
)


def _extract_path(args):
    """Return the target file path from a Copilot tool's arguments, or None. Accepts a dict, or a JSON
    string (Copilot may deliver ``tool_input`` as an unparsed JSON string), and recurses into a nested
    edit list so a batched multi-edit is still seen. Never raises."""
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except Exception:
            return None
    if isinstance(args, dict):
        for key in _PATH_KEYS:
            value = args.get(key)
            if isinstance(value, str) and value:
                return value
        for key in ("edits", "changes", "operations"):
            seq = args.get(key)
            if isinstance(seq, list):
                for item in seq:
                    found = _extract_path(item)
                    if found:
                        return found
    return None


def _allow() -> None:
    print(json.dumps({"permissionDecision": "allow"}))


def _deny(reason: str) -> None:
    print(json.dumps({"permissionDecision": "deny", "permissionDecisionReason": reason}))


def evaluate(evt: dict, home=None) -> None:
    """Emit the Copilot decision for one ``preToolUse`` event *evt*. Never raises for resolvable state.

    Reads the tool name and arguments (either payload shape), and — only for a write tool naming a real
    path — asks the canonical guard whether that path is a frozen test under an active build. A frozen
    hit (canonical exit code 2) DENIES with the canonical block message; everything else ALLOWS.
    """
    name = evt.get("toolName") or evt.get("tool_name") or ""
    if name not in _WRITE_TOOLS:
        _allow()
        return
    path = _extract_path(evt.get("toolArgs") if evt.get("toolArgs") is not None else evt.get("tool_input"))
    if not path:
        _allow()
        return
    payload = {"tool_name": "Edit", "tool_input": {"file_path": path}, "cwd": evt.get("cwd") or os.getcwd()}
    code, reason = decide(payload, home=home)
    if code == 2:
        _deny(reason)
    else:
        _allow()


def main(argv, stdin_text=None, home=None) -> int:
    try:
        raw = stdin_text if stdin_text is not None else sys.stdin.read()
        evt = json.loads(raw) if raw and raw.strip() else {}
        evaluate(evt, home=home)
    except Exception:
        _allow()  # fail OPEN — a gate bug never bricks an edit (decision rides on stdout, exit stays 0)
    return 0


# The __main__ guard carries no behavioural mutant under test (a wrapped "__main__" never equals the real
# dunder), so it is pragma'd like frozen_tests.py / the Cursor adapter.
if __name__ == "__main__":  # pragma: no mutate
    sys.exit(main(sys.argv))
