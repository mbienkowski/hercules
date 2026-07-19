"""Cursor write-gate adapter (G1) — reuses the CANONICAL frozen-guard policy, not a re-port.

Cursor exposes no pre-file-edit veto (``afterFileEdit`` is notification-only), so this enforces what
Cursor's hooks CAN, all keyed off the SAME frozen-test state and the SAME override policy Claude Code
and OpenCode read (``hercules_state`` + ``frozen_tests._override_allows``, both shipped alongside):

- ``shell`` (``beforeShellExecution``): DENY a shell command that writes to / commits a frozen test
  path during an active build — a real hard block on the shell write-path.
- ``after_edit`` (``afterFileEdit``): notification-only, so REVERT a frozen edit after the fact
  (``git checkout``) as a best-effort backstop — it cannot prevent a Composer edit, only undo it.

Reads are NOT blocked: the doctrine locks frozen tests against *edits*, not reads (the implementing
agent must read the very test it makes pass), matching Claude Code and OpenCode. A user-sanctioned
``frozen_override`` lifts the gate for its files this round — identical to the other ecosystems,
because the override check is the canonical one, not a second implementation.

Invoked as ``python3 hercules_gate.py <mode>`` with the Cursor event JSON on stdin; prints the Cursor
decision JSON on stdout. Fails OPEN (allow) on any error — matching the Claude frozen hook's policy, so
a gate bug never bricks an unrelated command.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from frozen_tests import _override_allows  # noqa: E402  (canonical override policy, reused not re-ported)
from hercules_state import canon, frozen_candidates, resolve_build_contexts  # noqa: E402

# A write/commit command at a shell command boundary, or an output redirection. Coarse by necessity —
# the hook sees only the raw command string, so this is a guardrail against honest/accidental writes,
# not a sound sandbox (``python -c``, heredocs, ``sudo`` prefixes evade it, and that is disclosed).
_WRITE_CMD = re.compile(
    r"(?:^|[\n;&|(])\s*(?:git\s+(?:add|commit|mv|rm)|sed\s+-i|rm|mv|cp|dd|tee|truncate)\b"
    r"|>>?"
)
# Quoted spans are stripped before the frozen-path scan, so a commit message that merely NAMES a frozen
# test (``git commit -m "fix test_login.py"``) is not mistaken for an operation on that file.
_QUOTED = re.compile(r"'[^']*'|\"[^\"]*\"")


def _cwd(evt: dict) -> str:
    roots = evt.get("workspace_roots") or []
    return roots[0] if roots else (evt.get("cwd") or os.getcwd())


def frozen_set(cwd: str, home=None) -> set:
    """Canonical frozen-test paths guarded for *cwd* right now (empty when no build is active).

    A path covered by a live, user-granted ``frozen_override`` is omitted — the exact same policy
    Claude/OpenCode apply, via the shared ``frozen_tests._override_allows``, so the documented
    "change test X" escape hatch works identically on Cursor.
    """
    frozen: set = set()
    for session, roots, project in resolve_build_contexts(cwd, home=home):
        if session.get("current_phase") != "build":
            continue
        if (project or {}).get("frozen_hook") == "off":
            continue
        for entry in session.get("frozen_test_files") or []:
            for cand in frozen_candidates(entry, roots):
                if not _override_allows(session, roots, cand):
                    frozen.add(cand)
    return frozen


def _allow() -> None:
    print(json.dumps({"permission": "allow"}))


def _deny(user: str, agent: str) -> None:
    print(json.dumps({"permission": "deny", "userMessage": user, "agentMessage": agent}))


def _touches(cmd: str, frozen: set) -> bool:
    """True iff a frozen test's filename appears in *cmd* as an operand (quoted spans — e.g. a commit
    message — stripped first). Basename-level by design: coarse, disclosed, and enough for the honest
    write-path this guards (a command bearing the absolute path also bears the basename)."""
    unquoted = _QUOTED.sub(" ", cmd)
    return any(os.path.basename(p) in unquoted for p in frozen)


def decide(mode: str, evt: dict, home=None) -> None:
    """Emit the Cursor decision for *mode* given event *evt*. Never raises for a resolvable state."""
    cwd = _cwd(evt)
    frozen = frozen_set(cwd, home=home)
    if not frozen:
        if mode == "shell":
            _allow()
        return
    if mode == "shell":
        cmd = evt.get("command", "")
        if _touches(cmd, frozen) and _WRITE_CMD.search(cmd):
            _deny(f"Hercules write-gate: this command writes to a frozen test during an active build: {cmd}",
                  "BLOCKED by Hercules: frozen test files are locked during implementation — do not edit or commit them.")
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
        if mode == "shell":  # fail OPEN, like the Claude frozen hook
            _allow()
    return 0


# The __main__ guard is the one mutmut footgun with no behavioural mutant (a wrapped "__main__" never
# equals the real dunder, so the branch is unreachable under test) — pragma'd like frozen_tests.py.
if __name__ == "__main__":  # pragma: no mutate
    sys.exit(main(sys.argv))
