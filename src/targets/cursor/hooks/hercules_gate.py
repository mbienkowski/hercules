"""Cursor write-gate adapter (G1) — reuses the CANONICAL frozen-guard policy, not a re-port.

Cursor exposes no pre-file-edit veto (``afterFileEdit`` is notification-only), so this enforces what
Cursor's hooks CAN, all keyed off the SAME frozen-test state and the SAME override policy Claude Code
and OpenCode read (``hercules_state`` + ``frozen_tests._override_allows``, both shipped alongside):

- ``shell`` (``beforeShellExecution``): DENY a shell command that writes to / commits a frozen test
  path during an active build — a real hard block on the shell write-path. Coarse *guardrail*, not a
  sound sandbox (``python -c``/heredocs/cross-pipe evade it — disclosed in CAPABILITIES.md).
- ``mcp`` (``beforeMCPExecution``): DENY a *write-ish* MCP tool call whose arguments name a frozen test
  during a build — closes the "an MCP git/filesystem server commits around the shell gate" hole. Also a
  coarse guardrail: it can only see the serialized arguments the MCP server exposes.
- ``after_edit`` (``afterFileEdit``): notification-only — Cursor has already applied the edit. Behaviour
  is **runtime-aware** (``HERCULES_RUNTIME_MODE``):
    * **interactive IDE (default)** — Hercules does **not** touch your working tree; it surfaces a loud,
      plain-language ``userMessage`` and lets you decide (undo it, or grant a ``frozen_override``). The
      human owns their tree; a silent revert would fight Cursor's model (least-astonishment).
    * **headless** (``HERCULES_RUNTIME_MODE=headless``, set by Hercules when it drives ``cursor-agent -p``
      — no human present) — restore the frozen path via ``git checkout`` and say so **only if it actually
      succeeded** (never a false "reverted" claim on an untracked file / non-git tree).

Shell/MCP block messages reuse the CANONICAL ``frozen_tests._reason`` — the exact wording Claude Code and
OpenCode emit. The IDE after-edit advisory is Cursor-specific plain-language copy (there is no Claude/
OpenCode equivalent surface), but it carries the SAME ``frozen_override`` escape hatch.

Reads are NOT blocked: the doctrine locks frozen tests against *edits*, not reads (the implementing
agent must read the very test it makes pass), matching Claude Code and OpenCode. A user-sanctioned
``frozen_override`` lifts the gate for its files this round — identical to the other ecosystems,
because the override check is the canonical one, not a second implementation.

Invoked as ``python3 hercules_gate.py <mode>`` with the Cursor event JSON on stdin; prints the Cursor
decision JSON on stdout. Fails OPEN (allow / no-op) on any error or missing ``python3`` — matching the
Claude frozen hook's policy, so a gate bug never bricks an unrelated command (disclosed in CAPABILITIES).
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
# A *write-ish* MCP tool name (an MCP git/filesystem server) — used to avoid blocking pure reads of a
# frozen test (the doctrine allows reads), while catching write/commit MCP ops on frozen paths.
_MCP_WRITE_HINT = re.compile(
    r"(write|commit|edit|create|delete|remove|put|add|move|rename|patch|apply|stash|checkout|reset"
    r"|save|update|append|insert|push)", re.I)


def _is_headless() -> bool:
    """Headless (autonomous, no human) iff Hercules declared it via env. Default = interactive IDE, the
    safe non-mutating direction — the hook can't tell the two apart from Cursor's event payload, so mode
    is *declared* by whoever owns the invocation (Hercules sets it when it drives ``cursor-agent -p``)."""
    return os.environ.get("HERCULES_RUNTIME_MODE") == "headless"


def _restore(cwd: str, fp: str) -> bool:
    """Restore *fp* to its committed content via ``git checkout`` (CoC-sanctioned working-tree mutation).
    Returns True ONLY if git actually restored it — so the caller never claims a revert that didn't
    happen (an untracked frozen test or a non-git tree fails here, honestly)."""
    try:
        r = subprocess.run(["git", "-C", cwd, "checkout", "--", fp],
                           capture_output=True, timeout=10)
        return r.returncode == 0
    except Exception:
        return False


def _ide_advisory(fp: str) -> str:
    """Cursor-specific, plain-language advisory for the interactive IDE (no working-tree mutation)."""
    return (
        f"Hercules: {os.path.basename(fp)} is a locked acceptance test for this Build. "
        "The goal is to write code that makes it pass — not to change the test, which would let the "
        "acceptance criteria drift to force a green. Your edit is still on disk and Hercules did NOT "
        "touch it. Undo it (Ctrl+Z) and implement against the test, OR grant an override by telling "
        'Hercules: "change test ' + os.path.basename(fp) + ' — <reason>".'
    )


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


def _mcp_hits_frozen(evt: dict, frozen: dict):
    """Return the frozen canon-path a *write-ish* MCP call targets, or None.

    Coarse guardrail (like the shell scan): it can only see what the MCP server exposes. It fires when
    the tool NAME looks mutating (``_MCP_WRITE_HINT`` — write/commit/edit/…) AND a frozen test's basename
    appears in the serialized arguments — so a pure read/list/get MCP call (which the doctrine allows) is
    not blocked, while an MCP git-commit or filesystem-write on a frozen path is. Name/arg field names
    vary by server, so several candidates are checked defensively."""
    name = ""
    # Cursor's exact beforeMCPExecution payload keys aren't firmly documented, so accept the plausible
    # snake_case AND camelCase spellings; if none match, the tool name stays "" and we fail OPEN (allow)
    # — the disclosed guardrail posture. CAPABILITIES.md notes this dependence on the server's payload.
    for key in ("tool_name", "toolName", "name", "tool", "method", "server_name", "serverName", "server"):
        v = evt.get(key)
        if isinstance(v, str) and v:
            name = v
            break
    if not _MCP_WRITE_HINT.search(name):
        return None
    args = None
    for key in ("tool_input", "toolInput", "arguments", "input", "params", "args"):
        if key in evt:
            args = evt[key]
            break
    try:
        blob = json.dumps(args, default=str) if args is not None else ""
    except Exception:
        blob = str(args)
    for p in frozen:
        if os.path.basename(p) in blob:
            return p
    return None


def decide(mode: str, evt: dict, home=None) -> None:
    """Emit the Cursor decision for *mode* given event *evt*. Never raises for a resolvable state."""
    cwd = _cwd(evt)
    frozen = frozen_map(cwd, home=home)
    if not frozen:
        if mode in ("shell", "mcp"):
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
    elif mode == "mcp":
        hit = _mcp_hits_frozen(evt, frozen)
        if hit is not None:
            reason = _reason(hit, frozen[hit])
            _deny(reason, reason)
        else:
            _allow()
    elif mode == "after_edit":
        fp = evt.get("file_path")
        c = canon(fp) if fp else None
        if c is not None and c in frozen:
            # afterFileEdit is notification-only (the edit already landed). Runtime-aware:
            if _is_headless():
                # No human present — restore, but say so ONLY if git actually did it (no false claim).
                if _restore(cwd, fp):
                    note = (_reason(fp, frozen[c])
                            + " (No human was present, so Hercules restored the file from git.)")
                else:
                    note = (_reason(fp, frozen[c])
                            + " (Hercules could NOT auto-restore it — not a git repo, or the test is "
                              "untracked. Revert it manually before continuing.)")
                print(json.dumps({"userMessage": note, "agentMessage": note}))
            else:
                # Interactive IDE — never mutate the user's tree; advise loudly and let them decide.
                note = _ide_advisory(fp)
                print(json.dumps({"userMessage": note, "agentMessage": note}))


def main(argv, stdin_text=None, home=None) -> int:
    mode = argv[1] if len(argv) > 1 else ""
    try:
        raw = stdin_text if stdin_text is not None else sys.stdin.read()
        evt = json.loads(raw) if raw and raw.strip() else {}
        decide(mode, evt, home=home)
    except Exception:
        if mode in ("shell", "mcp"):  # fail OPEN, like the Claude frozen hook (a gate bug never bricks
            _allow()                    # an unrelated command); after_edit fails open by emitting nothing
    return 0


# The __main__ guard is the one mutmut footgun with no behavioural mutant (a wrapped "__main__" never
# equals the real dunder, so the branch is unreachable under test) — pragma'd like frozen_tests.py.
if __name__ == "__main__":  # pragma: no mutate
    sys.exit(main(sys.argv))
