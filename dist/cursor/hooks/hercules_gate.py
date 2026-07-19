"""Cursor write-gate adapter (G1) — reuses the CANONICAL frozen-guard policy, not a re-port.

Cursor exposes no pre-file-edit veto (``afterFileEdit`` is notification-only), so this enforces what
Cursor's hooks CAN, all keyed off the SAME frozen-test state and the SAME override policy Claude Code
and OpenCode read (``hercules_state`` + ``frozen_tests._override_allows``, both shipped alongside):

- ``shell`` (``beforeShellExecution``): DENY a shell command that writes to / commits a frozen test
  path during an active build — a real hard block on the shell write-path.
- ``after_edit`` (``afterFileEdit``): notification-only, so REVERT a frozen edit after the fact by
  ``git stash`` (recoverable, not a destructive discard) as a best-effort backstop — it cannot prevent
  a Composer edit, only undo it, and the user can ``git stash pop`` to get their change back.

Block/revert messages reuse the CANONICAL ``frozen_tests._reason`` — the exact wording Claude Code and
OpenCode emit — so the guidance (including the "change this test" unblock) is identical everywhere.

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
from frozen_tests import _override_allows, _reason  # noqa: E402  (canonical override policy + block message)
from hercules_state import canon, frozen_candidates, resolve_build_contexts  # noqa: E402

# Command wrappers that may precede the real verb — consumed so ``time git add …`` / ``xargs rm …`` /
# ``env X=1 sed -i …`` are still caught. Covers known wrappers, their flags, env assignments, numbers.
_WRAP = r"(?:(?:sudo|time|nice|env|stdbuf|xargs|nohup|command|\w+=\S+|-\S+|\d+)\s+)*"
# A write/delete/commit command at the START of a pipeline segment (after optional wrappers). Coarse by
# necessity — the hook sees only the raw command string, so this is a guardrail against honest/accidental
# writes, not a sound sandbox: ``python -c``, heredocs, and cross-segment data flow (e.g.
# ``find … test_x.py | xargs rm``) still evade it. CAPABILITIES.md discloses this coarseness.
_SEG_WRITE = re.compile(
    r"^\s*" + _WRAP +
    r"(?:git\s+(?:add|commit|mv|rm)|sed\s+-i|rm|mv|cp|dd|tee|truncate|install|ln|patch)\b"
)
_FIND_DELETE = re.compile(r"\bfind\b.*\s-delete\b")  # `find … -delete` carries no `rm` token
_SEGMENT = re.compile(r"[\n;|&()]")                  # shell separators between pipeline segments
_REDIRECT = re.compile(r">>?\s*(\S+)")               # output redirection and its target
# Quoted spans are stripped before the frozen-path scan, so a commit message that merely NAMES a frozen
# test (``git commit -m "fix test_login.py"``) is not mistaken for an operation on that file.
_QUOTED = re.compile(r"'[^']*'|\"[^\"]*\"")


def _cwd(evt: dict) -> str:
    roots = evt.get("workspace_roots") or []
    return roots[0] if roots else (evt.get("cwd") or os.getcwd())


def frozen_map(cwd: str, home=None) -> dict:
    """Map each canonical frozen-test path guarded for *cwd* right now → its owning session (empty when
    no build is active), so a block can quote that session's spec/round via the canonical ``_reason``.

    A path covered by a live, user-granted ``frozen_override`` is omitted — the exact same policy
    Claude/OpenCode apply, via the shared ``frozen_tests._override_allows``, so the documented
    "change this test" escape hatch works identically on Cursor.
    """
    frozen: dict = {}
    for session, roots, project in resolve_build_contexts(cwd, home=home):
        if session.get("current_phase") != "build":
            continue
        if (project or {}).get("frozen_hook") == "off":
            continue
        for entry in session.get("frozen_test_files") or []:
            for cand in frozen_candidates(entry, roots):
                if not _override_allows(session, roots, cand):
                    frozen.setdefault(cand, session)
    return frozen


def _allow() -> None:
    print(json.dumps({"permission": "allow"}))


def _deny(user: str, agent: str) -> None:
    print(json.dumps({"permission": "deny", "userMessage": user, "agentMessage": agent}))


def _writes_frozen(cmd: str, frozen: dict):
    """Return the frozen canon-path *cmd* writes to / deletes, or None. Coarse and basename-level by
    design: quoted spans (a commit message) are stripped first; an output redirection counts only when
    its TARGET is the frozen file (so ``pytest test_x.py > log`` is allowed); and a write/delete verb
    counts only when a frozen filename shares its pipeline segment (so ``pytest test_x.py | tee log`` —
    read here, write there — is not a write)."""
    unquoted = _QUOTED.sub(" ", cmd)
    by_base = {}
    for p in frozen:
        by_base.setdefault(os.path.basename(p), p)
    for m in _REDIRECT.finditer(unquoted):          # (a) a redirection whose target is a frozen file
        b = os.path.basename(m.group(1))
        if b in by_base:
            return by_base[b]
    for seg in _SEGMENT.split(unquoted):            # (b) a write/delete verb naming a frozen file in
        if _SEG_WRITE.search(seg) or _FIND_DELETE.search(seg):  # the SAME pipeline segment
            for b, p in by_base.items():
                if b in seg:
                    return p
    return None


def decide(mode: str, evt: dict, home=None) -> None:
    """Emit the Cursor decision for *mode* given event *evt*. Never raises for a resolvable state."""
    cwd = _cwd(evt)
    frozen = frozen_map(cwd, home=home)
    if not frozen:
        if mode == "shell":
            _allow()
        return
    if mode == "shell":
        cmd = evt.get("command", "")
        hit = _writes_frozen(cmd, frozen)
        if hit is not None:
            reason = _reason(hit, frozen[hit])  # the canonical block message Claude/OpenCode also emit
            _deny(reason, reason)
        else:
            _allow()
    elif mode == "after_edit":
        fp = evt.get("file_path")
        c = canon(fp) if fp else None
        if c is not None and c in frozen:
            # afterFileEdit can't veto — stash the single frozen path (RECOVERABLE, unlike a hard
            # discard that would destroy the user's work) as a best-effort backstop.
            try:
                subprocess.run(["git", "-C", cwd, "stash", "push",
                                "-m", f"hercules: reverted frozen test {os.path.basename(fp)}", "--", fp],
                               capture_output=True, timeout=10)
            except Exception:
                pass
            print(json.dumps({"agentMessage": _reason(fp, frozen[c])
                              + " (Your edit was stashed, not discarded — run `git stash pop` to recover it.)"}))


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
