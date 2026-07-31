"""The ONE write-gate adapter — generic, parameterized by the ecosystem's ``hooks/gate.json``.

Every ecosystem's gate is this same file; only ``gate.json`` differs per host (the tool-name mapping,
the argument keys a target path may arrive under, and the allow/deny decision shapes), emitted at
build time from ``src/targets/<name>.json`` → ``gate``. Verdicts always delegate to the canonical
guard shipped alongside (``frozen_tests`` + ``hercules_state``), so the frozen set, the block
message, and the user-granted ``frozen_override`` escape hatch are identical on every host.

Three named protocols, a closed set — a new host behavior is a new named protocol in THIS file, with
tests, never logic in the JSON. ``pre_tool`` is a real pre-write veto. ``event_guards`` covers the
shell / MCP (Model Context Protocol) / after-edit surfaces, selected via argv, where after-edit is
advisory in an interactive IDE (integrated development environment) and restores via ``git
checkout`` only under ``HERCULES_RUNTIME_MODE=headless``.

Invoked as ``python3 hercules_gate.py [<mode>]`` with the host event JSON on stdin. Fails OPEN on
any error, malformed input, or unreadable config, so a gate bug never bricks an unrelated edit
(disclosed per ecosystem in CAPABILITIES.md). Reads are never blocked: the doctrine locks frozen
tests against edits, not reads.
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

def _nested_paths(args: dict, path_keys, nested_keys) -> list:
    """Recurse into the batched edit lists under *nested_keys*, flattening every hunk's paths so a
    frozen file in any later hunk of a multi-edit is still seen."""
    found: list = []
    for key in nested_keys:
        seq = args.get(key)
        if isinstance(seq, list):
            for item in seq:
                found.extend(_extract_paths(item, path_keys, nested_keys))
    return found


def _extract_paths(args, path_keys, nested_keys):
    """Return EVERY target file path a host tool's arguments name, in order (deduped). Accepts a dict
    or an unparsed JSON string, and recurses into nested edit lists so a batched multi-edit is seen in
    FULL — a frozen file in any later hunk must still block. Never raises."""
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except Exception:
            return []
    if not isinstance(args, dict):
        return []
    found: list = []
    for key in path_keys:                       # direct path arguments on this dict
        value = args.get(key)
        if isinstance(value, str) and value:
            found.append(value)
    found.extend(_nested_paths(args, path_keys, nested_keys))  # batched multi-edit hunks
    # De-duplicate while preserving first-seen order (dict keeps insertion order since 3.7).
    return list(dict.fromkeys(found))


def _emit_pre_tool(cfg, reason) -> None:
    """Print the host's decision: the ``deny`` shape with the canonical *reason* under ``reason_key``,
    or the ``allow`` shape — omitted entirely for hosts whose silence means allow."""
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
    paths = _extract_paths(args, cfg["path_keys"], cfg.get("nested_keys") or [])
    cwd = evt.get("cwd") or os.getcwd()
    # Check EVERY named path — a batched edit whose first target is innocuous but a later one is a
    # frozen test must still be denied.
    for path in paths:
        payload = {"tool_name": mapped, "tool_input": {"file_path": path}, "cwd": cwd}
        code, reason = decide(payload, home=home)
        if code == 2:
            return reason
    return None


# ── protocol: codex_pre_tool (Codex PreToolUse — hookSpecificOutput decision envelope) ─────────

_CODEX_PATCH_FILE = re.compile(r"^\*\*\* (?:Update|Add|Delete) File:\s*(.+?)\s*$", re.M)


def _codex_patch_paths(command):
    """Extract file paths from Codex's apply_patch payload.

    Codex sends the patch itself in ``tool_input.command`` rather than a separate path argument.
    The patch markers are deliberately parsed instead of searching for basenames: a frozen filename
    mentioned in a hunk's prose must not be mistaken for a target file.
    """
    if not isinstance(command, str):
        return []
    return list(dict.fromkeys(m.group(1).strip() for m in _CODEX_PATCH_FILE.finditer(command)))


def _codex_pre_tool_reason(cfg, evt, home=None):
    """Return the canonical block reason for a Codex ``PreToolUse`` event, or ``None`` to allow."""
    if not isinstance(evt, dict):
        return None
    tool = evt.get("tool_name") or evt.get("toolName") or ""
    if tool not in cfg.get("tools", {}):
        return None
    cwd = evt.get("cwd") or os.getcwd()
    args = evt.get("tool_input") if evt.get("tool_input") is not None else evt.get("toolArgs")
    if tool == "Bash":
        command = args.get("command", "") if isinstance(args, dict) else args
        hit = _writes_frozen(command, frozen_map(cwd, home=home))
        if hit is not None:
            frozen = frozen_map(cwd, home=home)
            return _reason(hit, frozen[hit])
        return None
    command = args.get("command", "") if isinstance(args, dict) else args
    for path in _codex_patch_paths(command):
        payload = {"tool_name": "Edit", "tool_input": {"file_path": path}, "cwd": cwd}
        code, reason = decide(payload, home=home)
        if code == 2:
            return reason
    return None


def _emit_codex_pre_tool(cfg, reason) -> None:
    """Emit Codex's nested ``hookSpecificOutput`` envelope."""
    if reason is None:
        allow = cfg.get("allow")
        if allow is not None:
            print(json.dumps(allow))
        return
    denial = json.loads(json.dumps(cfg["deny"]))
    output = denial.setdefault("hookSpecificOutput", {})
    output[cfg.get("reason_key", "permissionDecisionReason")] = reason
    print(json.dumps(denial))


# ── protocol: event_guards (shell / mcp write-guards + runtime-aware after-edit) ────────────────

# Command wrappers that may precede the real verb — consumed so ``time git add …`` / ``xargs rm …`` /
# ``env X=1 sed -i …`` are still caught. Covers known wrappers, their flags, env assignments, numbers.
_WRAP = r"(?:(?:sudo|time|nice|env|stdbuf|xargs|nohup|command|\w+=\S+|-\S+|\d+)\s+)*"
# A write/delete/commit command at the START of a pipeline segment (after optional wrappers). Coarse
# by necessity — the hook sees only the raw command string, so ``python -c``, heredocs and
# cross-segment data flow still evade it. A guardrail, not a sandbox; disclosed in CAPABILITIES.md.
_SEG_WRITE = re.compile(
    r"^\s*" + _WRAP +
    r"(?:git\s+(?:add|commit|mv|rm)|sed\s+-i|rm|mv|cp|dd|tee|truncate|install|ln|patch)\b"
)
_FIND_DELETE = re.compile(r"\bfind\b.*\s-delete\b")  # `find … -delete` carries no `rm` token
_SEGMENT = re.compile(r"[\n;|&()]")                  # shell separators between pipeline segments
_REDIRECT = re.compile(r">>?[|&]?\s*(\S+)")           # output redirection (incl. >| clobber, >&) + target
# A quoted span in a shell command. Spans are UNWRAPPED to their inner text before the frozen-path
# scan, so ``rm "tests/test_frozen.py"`` is still caught — except a ``-m``/``--message`` span, which
# is dropped as prose so ``git commit -m "fix test_login.py"`` stays allowed.
_QUOTED = re.compile(r"'[^']*'|\"[^\"]*\"")
_MSG_FLAG = re.compile(r"(?:^|\s)(?:-m|--message)=?\s*$")


def _unquote(cmd: str) -> str:
    """Replace each quoted span with its INNER text so a quoted frozen path is still scanned; drop a
    span that directly follows ``-m``/``--message`` (a commit message, not a path)."""
    out: list = []
    # `last` is used ONLY as a slice-start bound below (`cmd[last:...]`), and Python's slice protocol
    # treats `None` identically to `0` for a start bound, for every string. Mutating this literal
    # therefore cannot change this function's output for ANY input: a provable equivalent mutant.
    last = 0  # pragma: no mutate (equivalent: only ever used as a slice-start bound; see comment above)
    for m in _QUOTED.finditer(cmd):
        gap = cmd[last:m.start()]           # the text between the previous quoted span and this one
        inner_text = m.group(0)[1:-1]       # this span with its surrounding quote characters removed
        is_commit_message = _MSG_FLAG.search(gap)  # this span directly follows -m / --message
        out.append(gap)
        out.append(" " if is_commit_message else inner_text)
        last = m.end()
    out.append(cmd[last:])
    return "".join(out)
# A *write-ish* MCP tool name (an MCP git/filesystem server) — lets a pure read of a frozen test
# through, as the doctrine allows, while catching write/commit MCP operations on frozen paths.
_MCP_WRITE_HINT = re.compile(
    r"(write|commit|edit|create|delete|remove|put|add|move|rename|patch|apply|stash|checkout|reset"
    r"|save|update|append|insert|push)", re.I)

# Git write/commit subcommands, plus git's own GLOBAL options that may sit between ``git`` and the
# subcommand. _SEG_WRITE anchors the verb immediately after ``git`` and so misses ordinary forms such
# as ``git -C . add``; _git_write_seg tokenises past the global options so those are caught too.
_GIT_WRITE_SUBCMDS = {"add", "commit", "mv", "rm"}
_GIT_OPT_TAKES_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env"}
_LEAD_WRAP = re.compile(r"^\s*" + _WRAP)  # strip time/env/sudo/… wrappers before the ``git`` token


def _git_write_seg(seg: str) -> bool:
    """True if *seg* is a ``git`` add/commit/mv/rm even when git GLOBAL OPTIONS precede the subcommand.
    Value-taking options (``-C <path>``, ``-c <k=v>``, ``--git-dir <p>``) consume their argument, so the
    first non-option token is classified as the subcommand."""
    toks = _LEAD_WRAP.sub("", seg).strip().split()
    if not toks or toks[0] != "git":
        return False
    idx = 1
    while idx < len(toks):
        tok = toks[idx]
        if not tok.startswith("-"):
            return tok in _GIT_WRITE_SUBCMDS  # first non-option token = the subcommand
        # A value-taking global option written as ``-C path`` (not ``-C=path``) keeps its value in the
        # NEXT token, so step over two tokens instead of one.
        consumes_next = "=" not in tok and tok in _GIT_OPT_TAKES_VALUE
        idx += 2 if consumes_next else 1
    return False


def _seg_names(seg: str, base: str) -> bool:
    """True if basename *base* appears in *seg* as a whole filename rather than a substring of a longer
    name — so a frozen ``test_login.py`` is not matched inside ``mytest_login.py.bak``."""
    return re.search(r"(?:^|[^\w.\-])" + re.escape(base) + r"(?![\w.\-])", seg) is not None


def _is_headless() -> bool:
    """Headless (autonomous, no human) iff Hercules declared it via env. An event payload cannot tell the
    two apart, so the mode is *declared* by whoever owns the invocation; the default is the interactive
    IDE — the safe, non-mutating direction."""
    return os.environ.get("HERCULES_RUNTIME_MODE") == "headless"


def _restore(cwd: str, fp: str) -> bool:
    """Restore *fp* to its committed content via ``git checkout`` — the one working-tree mutation any
    hook makes. Returns True ONLY if git actually restored it, so the caller never claims a revert that
    didn't happen (an untracked frozen test or a non-git tree fails here, honestly)."""
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


def _context_guards_frozen(session, project) -> bool:
    """True if this build context still enforces its freeze: it is in the build phase AND its project
    has not opted out via ``frozen_hook: off``. A non-build or opted-out context guards nothing."""
    return session.get("current_phase") == "build" and (project or {}).get("frozen_hook") != "off"


def _guarded_paths(session, roots):
    """Yield each canonical frozen path this session still guards — one covered by a live,
    user-granted ``frozen_override`` is dropped (the shared "change this test" escape hatch)."""
    for entry in session.get("frozen_test_files") or []:
        for cand in frozen_candidates(entry, roots):
            if not _override_allows(session, roots, cand):
                yield cand


def frozen_map(cwd: str, home=None) -> dict:
    """Map each canonical frozen-test path guarded for *cwd* right now → its owning session (empty when
    no build is active), so a block can quote that session's spec/round. A path covered by a live,
    user-granted ``frozen_override`` is omitted, via the shared ``frozen_tests._override_allows``."""
    frozen: dict = {}
    for session, roots, project in resolve_build_contexts(cwd, home=home):
        if not _context_guards_frozen(session, project):
            continue
        for cand in _guarded_paths(session, roots):
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
    design: a redirection counts only when its TARGET is the frozen file, and a write/delete verb only
    when a frozen filename shares its pipeline segment — so ``pytest test_x.py | tee log`` (read here,
    write there) is not a write."""
    unquoted = _unquote(cmd)
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
    """Return the frozen canon-path a *write-ish* MCP call targets, or None. Fires when the tool NAME
    looks mutating (``_MCP_WRITE_HINT``) AND a frozen test's basename appears in the serialized
    arguments, so a pure read/list/get call stays allowed. Name and argument field names vary by
    server, so several candidates are checked."""
    name = ""
    # The host's payload keys are not firmly specified, so accept the plausible snake_case AND
    # camelCase spellings; when none match, the tool name stays "" and the call fails OPEN — the
    # guardrail posture CAPABILITIES.md discloses.
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


def _decide_shell(cfg, evt: dict, frozen: dict) -> None:
    """Shell guard: deny with the canonical reason when the command writes/deletes a frozen file."""
    hit = _writes_frozen(evt.get("command", ""), frozen)
    if hit is not None:
        reason = _reason(hit, frozen[hit])  # the canonical block message every ecosystem emits
        _guards_deny(cfg, reason, reason)
    else:
        _guards_allow(cfg)


def _decide_mcp(cfg, evt: dict, frozen: dict) -> None:
    """MCP guard: deny with the canonical reason when a write-ish MCP call targets a frozen file."""
    hit = _mcp_hits_frozen(evt, frozen)
    if hit is not None:
        reason = _reason(hit, frozen[hit])
        _guards_deny(cfg, reason, reason)
    else:
        _guards_allow(cfg)


def _after_edit_note(cwd: str, fp: str, session) -> str:
    """The notification text for an after-edit hit on a frozen file: an advisory that never touches the
    tree in an interactive IDE, a git restore in headless — claimed ONLY when git actually did it."""
    if not _is_headless():
        return _ide_advisory(fp)  # interactive IDE — never mutate the user's tree
    if _restore(cwd, fp):
        return _reason(fp, session) + " (No human was present, so Hercules restored the file from git.)"
    return (_reason(fp, session)
            + " (Hercules could NOT auto-restore it — not a git repo, or the test is "
              "untracked. Revert it manually before continuing.)")


def _decide_after_edit(cfg, evt: dict, cwd: str, frozen: dict) -> None:
    """After-edit guard: afterFileEdit is notification-only (the edit already landed), so a frozen
    hit is announced — advisory or restore note — never vetoed here."""
    fp = evt.get("file_path")
    c = canon(fp) if fp else None
    if c is not None and c in frozen:
        _guards_notify(cfg, _after_edit_note(cwd, fp, frozen[c]))


def _event_guards_decide(cfg, mode: str, evt: dict, home=None) -> None:
    """Emit the host's decision for *mode* given event *evt*. Never raises for a resolvable state."""
    cwd = _cwd(evt)
    frozen = frozen_map(cwd, home=home)
    if not frozen:
        if mode in ("shell", "mcp"):
            _guards_allow(cfg)
        return
    if mode == "shell":
        _decide_shell(cfg, evt, frozen)
    elif mode == "mcp":
        _decide_mcp(cfg, evt, frozen)
    elif mode == "after_edit":
        _decide_after_edit(cfg, evt, cwd, frozen)


# ── entry point ─────────────────────────────────────────────────────────────────────────────────

def _dispatch(cfg, protocol, mode: str, evt, home=None) -> None:
    """Route a parsed event to its protocol handler (the happy path)."""
    if protocol == "pre_tool":
        _emit_pre_tool(cfg, _pre_tool_reason(cfg, evt, home=home))
    elif protocol == "codex_pre_tool":
        _emit_codex_pre_tool(cfg, _codex_pre_tool_reason(cfg, evt, home=home))
    elif protocol == "event_guards":
        _event_guards_decide(cfg, mode, evt if isinstance(evt, dict) else {}, home=home)


def _fail_open(cfg, protocol, mode: str) -> None:
    """The fail-OPEN response after any error: hosts that expect an explicit allow get one; silent
    hosts (Gemini) get silence — never a block, so a gate bug can't brick an unrelated edit."""
    if protocol == "pre_tool":
        _emit_pre_tool(cfg, None)
    elif protocol == "codex_pre_tool":
        _emit_codex_pre_tool(cfg, None)
    elif protocol == "event_guards" and mode in ("shell", "mcp"):
        _guards_allow(cfg)


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
        _dispatch(cfg, protocol, mode, evt, home=home)
    except Exception:
        _fail_open(cfg, protocol, mode)
    return 0


# The __main__ guard carries no behavioural mutant under test (a wrapped "__main__" never equals the
# real dunder), hence the pragma.
if __name__ == "__main__":  # pragma: no mutate
    sys.exit(main())
