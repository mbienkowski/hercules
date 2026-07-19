"""Cursor write-gate adapter (G1) — reuses ``hercules_state``, the canonical frozen-guard state reader.

Cursor exposes no pre-file-edit veto (``afterFileEdit`` is notification-only), so this enforces what
Cursor's hooks CAN, all keyed off the SAME frozen-test state Claude Code and OpenCode read:

- ``shell``  (``beforeShellExecution``): DENY a shell command that writes to / commits a frozen test
  path during an active build — a real hard block on the shell write-path.
- ``read``   (``beforeReadFile``): DENY reads of a frozen test file during a build.
- ``after_edit`` (``afterFileEdit``): notification-only, so REVERT a frozen edit after the fact
  (``git checkout``) as a best-effort backstop — it cannot prevent a Composer edit, only undo it.

Invoked as ``python3 hercules_gate.py <mode>`` with the Cursor event JSON on stdin; prints the Cursor
decision JSON on stdout. Fails OPEN (allow) on any error — matching the Claude frozen hook's policy, so
a gate bug never bricks an unrelated command.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hercules_state import canon, frozen_candidates, resolve_build_contexts  # noqa: E402

# Shell primitives that mutate or commit files. Coarse by necessity — the hook sees only the raw
# command string, so this is a guardrail against honest/accidental writes, not a sound sandbox.
_WRITE_PRIMITIVES = ("git add", "git commit", "git mv", "git rm", "sed -i", "tee ",
                     "mv ", "cp ", "dd ", "truncate", ">", ">>")


def _cwd(evt: dict) -> str:
    roots = evt.get("workspace_roots") or []
    return roots[0] if roots else (evt.get("cwd") or os.getcwd())


def frozen_set(cwd: str, home=None) -> set:
    """Canonical frozen-test paths guarded for *cwd* right now (empty when no build is active)."""
    frozen: set = set()
    for session, roots, project in resolve_build_contexts(cwd, home=home):
        if session.get("current_phase") != "build":
            continue
        if (project or {}).get("frozen_hook") == "off":
            continue
        for entry in session.get("frozen_test_files") or []:
            frozen |= frozen_candidates(entry, roots)
    return frozen


def _allow() -> None:
    print(json.dumps({"permission": "allow"}))


def _deny(user: str, agent: str) -> None:
    print(json.dumps({"permission": "deny", "userMessage": user, "agentMessage": agent}))


def decide(mode: str, evt: dict, home=None) -> None:
    """Emit the Cursor decision for *mode* given event *evt*. Never raises for a resolvable state."""
    cwd = _cwd(evt)
    frozen = frozen_set(cwd, home=home)
    if not frozen:
        if mode in ("shell", "read"):
            _allow()
        return
    if mode == "shell":
        cmd = evt.get("command", "")
        touches = any((os.path.basename(p) in cmd) or (p in cmd) for p in frozen)
        if touches and any(tok in cmd for tok in _WRITE_PRIMITIVES):
            _deny(f"Hercules write-gate: this command writes to a frozen test during an active build: {cmd}",
                  "BLOCKED by Hercules: frozen test files are locked during implementation — do not edit or commit them.")
        else:
            _allow()
    elif mode == "read":
        fp = evt.get("file_path")
        if fp and canon(fp) in frozen:
            _deny(f"Hercules write-gate: {fp} is a frozen test (locked during the build).",
                  "BLOCKED by Hercules: frozen test files are locked during implementation.")
        else:
            _allow()
    elif mode == "after_edit":
        fp = evt.get("file_path")
        if fp and canon(fp) in frozen:
            try:  # afterFileEdit is notification-only — revert as a best-effort backstop.
                subprocess.run(["git", "-C", cwd, "checkout", "--", fp],
                               capture_output=True, timeout=10)
            except Exception:
                pass
            print(json.dumps({"agentMessage":
                              f"Hercules reverted an edit to frozen test {fp}; do not modify frozen tests during the build."}))


def main(argv, stdin_text=None, home=None) -> int:
    mode = argv[1] if len(argv) > 1 else ""
    try:
        raw = stdin_text if stdin_text is not None else sys.stdin.read()
        evt = json.loads(raw) if raw and raw.strip() else {}
        decide(mode, evt, home=home)
    except Exception:
        if mode in ("shell", "read"):  # fail OPEN, like the Claude frozen hook
            _allow()
    return 0


if __name__ == "__main__":  # pragma: no mutate
    sys.exit(main(sys.argv))
