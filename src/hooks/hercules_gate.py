"""The ONE write-gate adapter (G1) — generic, parameterized by the ecosystem's ``hooks/gate.json``.

Every ecosystem's gate is this same file; what differs per host is DATA, emitted at build time from
the ecosystem descriptor (``src/ecosystems/<name>.json`` → ``gate``) into a ``gate.json`` beside it.
The verdict logic is never re-implemented per host: everything delegates to the CANONICAL guard
shipped alongside (``frozen_tests`` + ``hercules_state``, byte-identical on every ecosystem), so the
frozen set, the block message, and the user-granted ``frozen_override`` escape hatch are identical
across Claude Code, OpenCode, Cursor, Gemini CLI, Copilot CLI, and Grok Build.

Two named protocols (a closed set — a new host behavior is a new named protocol in THIS file, with
tests, never logic in the JSON):

- ``pre_tool`` — a real pre-write veto (Gemini's ``BeforeTool``, Copilot's ``preToolUse``). The
  config maps host tool names to the canonical guard's vocabulary, lists the argument keys a target
  path may arrive under (JS hosts vary casing/shape; a JSON-string payload and nested edit lists are
  handled), and gives the host's decision shapes: an optional ``allow`` object (Copilot always emits
  a decision; Gemini stays silent to allow) and a ``deny`` object + ``reason_key`` carrying the
  canonical block message.
- ``event_guards`` — the guard set for IDE-class hosts with shell/MCP/after-edit hook surfaces
  (``shell`` / ``mcp`` / ``after_edit`` selected via argv), including the runtime-aware after-edit
  path: advisory in the interactive IDE (no working-tree mutation), an honest ``git checkout``
  restore only in headless runs (``HERCULES_RUNTIME_MODE=headless``). The host's decision shapes
  (allow/deny objects, user/agent message keys) are config data; the guard algorithms are shared.

Invoked as ``python3 hercules_gate.py [<mode>]`` with the host event JSON on stdin. Fails OPEN on
any error, malformed input, or missing/unreadable config — matching the canonical frozen hook's
policy, so a gate bug never bricks an unrelated edit (disclosed per ecosystem in CAPABILITIES.md).
Reads are never blocked: the doctrine locks frozen tests against edits, not reads.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from frozen_tests import _override_allows, _reason, decide  # noqa: E402  (canonical policy — one source of truth)
from hercules_state import canon, frozen_candidates, resolve_build_contexts  # noqa: E402


def _read_config():
    """Load ``gate.json`` from this script's own directory (how the shipped copy finds its host
    parameters). Returns None — fail OPEN — when absent or unreadable."""
    try:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gate.json")
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


# ── protocol: pre_tool (Gemini BeforeTool / Copilot preToolUse — a true pre-write veto) ─────────

def _extract_path(args, path_keys, nested_keys):
    """Return the target file path from a host tool's arguments, or None. Accepts a dict or an
    unparsed JSON string, and recurses into nested edit lists (``nested_keys``) so a batched
    multi-edit is still seen. Never raises."""
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except Exception:
            return None
    if isinstance(args, dict):
        for key in path_keys:
            value = args.get(key)
            if isinstance(value, str) and value:
                return value
        for key in nested_keys:
            seq = args.get(key)
            if isinstance(seq, list):
                for item in seq:
                    found = _extract_path(item, path_keys, nested_keys)
                    if found:
                        return found
    return None


def _emit_pre_tool(cfg, reason) -> None:
    """Print the host's decision: the ``deny`` shape with the canonical *reason* under
    ``reason_key``, or the ``allow`` shape — omitted entirely for hosts (Gemini) whose silence
    means allow."""
    if reason is None:
        allow = cfg.get("allow")
        if allow is not None:
            print(json.dumps(allow))
        return
    denial = dict(cfg["deny"])
    denial[cfg["reason_key"]] = reason
    print(json.dumps(denial))


def _pre_tool_reason(cfg, evt, home=None):
    """The canonical block reason for *evt*, or None to allow. Accepts both payload casings
    (``tool_name``/``tool_input`` and ``toolName``/``toolArgs``) — a casing difference must never
    silently no-op the veto."""
    if not isinstance(evt, dict):
        return None
    mapped = cfg["tools"].get(evt.get("tool_name") or evt.get("toolName") or "")
    if mapped is None:
        return None
    args = evt.get("tool_input") if evt.get("tool_input") is not None else evt.get("toolArgs")
    path = _extract_path(args, cfg["path_keys"], cfg.get("nested_keys") or [])
    if not path:
        return None
    payload = {"tool_name": mapped, "tool_input": {"file_path": path}, "cwd": evt.get("cwd") or os.getcwd()}
    code, reason = decide(payload, home=home)
    if code == 2:
        return reason
    return None


# ── protocol: event_guards (shell / mcp write-guards + runtime-aware after-edit) ────────────────

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
_REDIRECT = re.compile(r">>?[|&]?\s*(\S+)")           # output redirection (incl. >| clobber, >&) + target
# Quoted spans are stripped before the frozen-path scan, so a commit message that merely NAMES a frozen
# test (``git commit -m "fix test_login.py"``) is not mistaken for an operation on that file.
_QUOTED = re.compile(r"'[^']*'|\"[^\"]*\"")
# A *write-ish* MCP tool name (an MCP git/filesystem server) — used to avoid blocking pure reads of a
# frozen test (the doctrine allows reads), while catching write/commit MCP ops on frozen paths.
_MCP_WRITE_HINT = re.compile(
    r"(write|commit|edit|create|delete|remove|put|add|move|rename|patch|apply|stash|checkout|reset"
    r"|save|update|append|insert|push)", re.I)

# Git write/commit subcommands, plus git's own GLOBAL options that may sit between ``git`` and the
# subcommand. _SEG_WRITE anchors the verb immediately after ``git`` and so misses ``git -C . add`` /
# ``git -c k=v commit`` / ``git --git-dir=… rm`` — ordinary forms (the gate itself runs ``git -C`` in
# _restore). _git_write_seg tokenises past the global options so those are caught too.
_GIT_WRITE_SUBCMDS = {"add", "commit", "mv", "rm"}
_GIT_OPT_TAKES_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env"}
_LEAD_WRAP = re.compile(r"^\s*" + _WRAP)  # strip time/env/sudo/… wrappers before the ``git`` token


def _git_write_seg(seg: str) -> bool:
    """True if *seg* is a ``git`` add/commit/mv/rm even when git GLOBAL OPTIONS precede the subcommand.
    Value-taking options (``-C <path>``, ``-c <k=v>``, ``--git-dir <p>``) consume their argument so the
    first non-option token is classified as the subcommand. Coarse like the rest of the gate — it closes
    the documented global-option evasion, it is not a sandbox."""
    toks = _LEAD_WRAP.sub("", seg).strip().split()
    if not toks or toks[0] != "git":
        return False
    i = 1
    while i < len(toks):
        t = toks[i]
        if not t.startswith("-"):
            return t in _GIT_WRITE_SUBCMDS       # first non-option token = the subcommand
        if "=" not in t and t in _GIT_OPT_TAKES_VALUE:
            i += 1                                # ``-C path`` form — skip the separate value token
        i += 1
    return False


def _seg_names(seg: str, base: str) -> bool:
    """True if basename *base* appears in *seg* as a whole path component / filename, not as a substring
    of a longer name — so a frozen ``test_login.py`` is not matched inside ``mytest_login.py.bak``. A
    path separator before it is fine; a word / dot / dash char on either edge is not."""
    return re.search(r"(?:^|[^\w.\-])" + re.escape(base) + r"(?![\w.\-])", seg) is not None


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
    """Plain-language advisory for the interactive IDE (no working-tree mutation)."""
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
    every ecosystem applies, via the shared ``frozen_tests._override_allows``, so the documented
    "change this test" escape hatch works identically on every host.
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


def _guards_allow(cfg) -> None:
    print(json.dumps(cfg["allow"]))


def _guards_deny(cfg, user: str, agent: str) -> None:
    decision = dict(cfg["deny"])
    decision[cfg["user_key"]] = user
    decision[cfg["agent_key"]] = agent
    print(json.dumps(decision))


def _guards_notify(cfg, note: str) -> None:
    print(json.dumps({cfg["user_key"]: note, cfg["agent_key"]: note}))


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
        if _SEG_WRITE.search(seg) or _git_write_seg(seg) or _FIND_DELETE.search(seg):  # the SAME segment
            for b, p in by_base.items():
                if _seg_names(seg, b):
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


def _event_guards_decide(cfg, mode: str, evt: dict, home=None) -> None:
    """Emit the host's decision for *mode* given event *evt*. Never raises for a resolvable state."""
    cwd = _cwd(evt)
    frozen = frozen_map(cwd, home=home)
    if not frozen:
        if mode in ("shell", "mcp"):
            _guards_allow(cfg)
        return
    if mode == "shell":
        cmd = evt.get("command", "")
        hit = _writes_frozen(cmd, frozen)
        if hit is not None:
            reason = _reason(hit, frozen[hit])  # the canonical block message every ecosystem emits
            _guards_deny(cfg, reason, reason)
        else:
            _guards_allow(cfg)
    elif mode == "mcp":
        hit = _mcp_hits_frozen(evt, frozen)
        if hit is not None:
            reason = _reason(hit, frozen[hit])
            _guards_deny(cfg, reason, reason)
        else:
            _guards_allow(cfg)
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
                _guards_notify(cfg, note)
            else:
                # Interactive IDE — never mutate the user's tree; advise loudly and let them decide.
                note = _ide_advisory(fp)
                _guards_notify(cfg, note)


# ── entry point ─────────────────────────────────────────────────────────────────────────────────

def main(argv=None, stdin_text=None, home=None, config=None) -> int:
    argv = argv if argv is not None else sys.argv
    mode = argv[1] if len(argv) > 1 else ""
    cfg = config if config is not None else _read_config()
    if not isinstance(cfg, dict):
        return 0  # no readable host config → fail OPEN (never brick an edit)
    protocol = cfg.get("protocol")
    try:
        raw = stdin_text if stdin_text is not None else sys.stdin.read()
        evt = json.loads(raw) if raw and raw.strip() else {}
        if protocol == "pre_tool":
            _emit_pre_tool(cfg, _pre_tool_reason(cfg, evt, home=home))
        elif protocol == "event_guards":
            _event_guards_decide(cfg, mode, evt if isinstance(evt, dict) else {}, home=home)
    except Exception:
        # Fail OPEN per protocol: hosts that expect an explicit allow get one; silent hosts get silence.
        if protocol == "pre_tool":
            _emit_pre_tool(cfg, None)
        elif protocol == "event_guards" and mode in ("shell", "mcp"):
            _guards_allow(cfg)
    return 0


# The __main__ guard carries no behavioural mutant under test (a wrapped "__main__" never equals the
# real dunder), so it is pragma'd like frozen_tests.py.
if __name__ == "__main__":  # pragma: no mutate
    sys.exit(main())
