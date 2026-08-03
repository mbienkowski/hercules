"""The ONE write-gate adapter every ecosystem ships — ``python3 hercules_gate.py [<mode>]``, host
event JSON on stdin — parameterized entirely by its sibling ``write_gate.json``: the tool-name
mapping, the keys a target path arrives under, and the allow/deny shapes. Verdicts delegate to
``frozen_tests``, so the frozen set, the block message and the user override behave identically
everywhere. Three protocols: a pre-write veto, the shell / MCP (Model Context Protocol) guards, and
an after-edit backstop. Fails OPEN on any error — a gate bug never bricks an edit, and reads never block.
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
    """This host's gate parameters, read from ``write_gate.json`` beside this script. None — fail
    OPEN — when absent or unreadable."""
    try:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "write_gate.json")
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


# ── answering BEFORE a write: a true veto, for hosts that ask first ─────────────────────────────

def _nested_paths(args: dict, path_keys, nested_keys) -> list:
    """Every path inside the batched edit lists under *nested_keys*, flattened."""
    found: list = []
    for key in nested_keys:
        seq = args.get(key)
        if isinstance(seq, list):
            for item in seq:
                found.extend(_extract_paths(item, path_keys, nested_keys))
    return found


def _extract_paths(args, path_keys, nested_keys):
    """EVERY file path a tool's arguments name, deduped and in order — a batched multi-edit is read
    in FULL, since a frozen file in any later hunk must still block. Never raises."""
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
    return list(dict.fromkeys(found))           # deduped, first-seen order preserved


def _put(obj, path, value) -> None:
    """Set ``value`` at ``path`` (a list of keys), creating intermediate objects as needed — how one
    emitter serves both hosts that put the refusal reason beside the decision and hosts that nest it."""
    for key in path[:-1]:
        nxt = obj.get(key)
        if not isinstance(nxt, dict):
            nxt = {}
            obj[key] = nxt
        obj = nxt
    obj[path[-1]] = value


def _emit(cfg, reason) -> None:
    """Print the host's decision: its ``allow`` shape, or its ``deny`` shape carrying the canonical
    reason at ``reason_at``. Hosts whose silence means allow declare no ``allow`` and get silence."""
    if reason is None:
        allow = cfg.get("allow")
        if allow is not None:
            print(json.dumps(allow))
        return
    denial = json.loads(json.dumps(cfg["deny"]))  # deep copy: never mutate the shared config
    _put(denial, cfg.get("reason_at") or ["reason"], reason)
    print(json.dumps(denial))


def _paths_from_args(strategy, args):
    """Paths named directly by the request's own arguments, batched hunks included."""
    return _extract_paths(args, strategy.get("keys") or [], strategy.get("nested") or [])


def _paths_from_patch(strategy, args):
    """Paths named inside a patch body carried in one argument. The patch's own markers are parsed,
    never the prose, so a frozen filename mentioned in a hunk is not mistaken for one being written."""
    body = args.get(strategy["arg"]) if isinstance(args, dict) else args
    if not isinstance(body, str):
        return []
    found = re.finditer(strategy["pattern"], body, re.M)
    return list(dict.fromkeys(m.group(1).strip() for m in found))


def _pre_write_reason(cfg, evt, home=None):
    """The canonical refusal for a request about to write, or None to allow. Both payload casings are
    accepted, and EVERY path found is checked — one innocuous target never excuses the next."""
    if not isinstance(evt, dict):
        return None
    tool = evt.get("tool_name") or evt.get("toolName") or ""
    mapped = cfg.get("tools", {}).get(tool)
    if mapped is None:
        return None
    args = evt.get("tool_input") if evt.get("tool_input") is not None else evt.get("toolArgs")
    cwd = evt.get("cwd") or os.getcwd()

    for strategy in cfg.get("paths") or []:
        kind = strategy.get("from")
        if kind == "shell_command":
            # A command line, not a path: the shared reader decides what it writes, on every host.
            command = args.get(strategy.get("arg", "command"), "") if isinstance(args, dict) else args
            frozen = frozen_map(cwd, home=home)
            hit = _writes_frozen(command, frozen)
            if hit is not None:
                return _reason(hit, frozen[hit])
            continue
        if kind == "arg_keys":
            paths = _paths_from_args(strategy, args)
        elif kind == "patch_body":
            paths = _paths_from_patch(strategy, args)
        else:
            continue  # a strategy nobody implements finds nothing — fail open, never block
        as_tool = strategy.get("as_tool") or mapped
        for path in paths:
            payload = {"tool_name": as_tool, "tool_input": {"file_path": path}, "cwd": cwd}
            code, reason = decide(payload, home=home)
            if code == 2:
                return reason
    return None


# ── protocol: event_guards (shell / mcp write-guards + runtime-aware after-edit) ────────────────

# Wrappers consumed before the real verb, so ``time git add …`` and ``env X=1 sed -i …`` are caught.
_WRAP = r"(?:(?:sudo|time|nice|env|stdbuf|xargs|nohup|command|\w+=\S+|-\S+|\d+)\s+)*"

# A write/delete/commit verb opening a pipeline segment. Coarse — only the raw command string is visible, so `python -c` and heredocs evade it.
_SEG_WRITE = re.compile(
    r"^\s*" + _WRAP +
    r"(?:git\s+(?:add|commit|mv|rm)|sed\s+-i|rm|mv|cp|dd|tee|truncate|install|ln|patch)\b"
)
_FIND_DELETE = re.compile(r"\bfind\b.*\s-delete\b")  # `find … -delete` carries no `rm` token
_SEGMENT = re.compile(r"[\n;|&()]")                  # shell separators between pipeline segments
_REDIRECT = re.compile(r">>?[|&]?\s*(\S+)")           # output redirection (incl. >| clobber, >&) + target
# A quoted span, unwrapped before the path scan so `rm "test_frozen.py"` is caught — except a commit message, which is prose, not a target.
_QUOTED = re.compile(r"'[^']*'|\"[^\"]*\"")
_MSG_FLAG = re.compile(r"(?:^|\s)(?:-m|--message)=?\s*$")


def _unquote(cmd: str) -> str:
    """Replace each quoted span with its INNER text so a quoted frozen path is still scanned; drop a
    span that directly follows ``-m``/``--message`` (a commit message, not a path)."""
    out: list = []
    last = 0  # pragma: no mutate (equivalent: only ever a slice-start bound, where Python reads 0 and None identically)
    for m in _QUOTED.finditer(cmd):
        gap = cmd[last:m.start()]           # the text between the previous quoted span and this one
        inner_text = m.group(0)[1:-1]
        is_commit_message = _MSG_FLAG.search(gap)  # this span directly follows -m / --message
        out.append(gap)
        out.append(" " if is_commit_message else inner_text)
        last = m.end()
    out.append(cmd[last:])
    return "".join(out)


# A write-ish MCP tool name: catches an MCP server's write/commit operations while letting a pure read through.
_MCP_WRITE_HINT = re.compile(
    r"(write|commit|edit|create|delete|remove|put|add|move|rename|patch|apply|stash|checkout|reset"
    r"|save|update|append|insert|push)", re.I)

# Git's write subcommands and the global options that may sit before one, which `_SEG_WRITE`'s anchored match alone would miss in `git -C . add`.
_GIT_WRITE_SUBCMDS = {"add", "commit", "mv", "rm"}
_GIT_OPT_TAKES_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env"}
_LEAD_WRAP = re.compile(r"^\s*" + _WRAP)  # strip time/env/sudo/… wrappers before the ``git`` token


def _git_write_seg(seg: str) -> bool:
    """True if *seg* is a ``git`` add/commit/mv/rm even behind global options. A value-taking option
    consumes its argument, so the first non-option token left is the subcommand."""
    toks = _LEAD_WRAP.sub("", seg).strip().split()
    if not toks or toks[0] != "git":
        return False
    idx = 1
    while idx < len(toks):
        tok = toks[idx]
        if not tok.startswith("-"):
            return tok in _GIT_WRITE_SUBCMDS  # first non-option token = the subcommand

        # `-C path` (not `-C=path`) keeps its value in the NEXT token, so step over two.
        consumes_next = "=" not in tok and tok in _GIT_OPT_TAKES_VALUE
        idx += 2 if consumes_next else 1
    return False


def _seg_names(seg: str, base: str) -> bool:
    """True if *base* appears in *seg* as a whole filename, so a frozen ``test_login.py`` is not
    matched inside ``mytest_login.py.bak``."""
    return re.search(r"(?:^|[^\w.\-])" + re.escape(base) + r"(?![\w.\-])", seg) is not None


def _is_headless() -> bool:
    """True when Hercules declares this run autonomous. No payload distinguishes the two, so whoever
    owns the invocation declares it; the default is the interactive IDE, which never mutates."""
    return os.environ.get("HERCULES_RUNTIME_MODE") == "headless"


def _restore(cwd: str, fp: str) -> bool:
    """Restore *fp* from git — the ONE working-tree mutation any hook makes. True only when git really
    did it, so an untracked test or a non-git tree is reported honestly rather than claimed as reverted."""
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
    """The directory this event belongs to: the host's first workspace root, else its cwd."""
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
    """Every frozen path guarded for *cwd* right now → its owning session, so a block can quote that
    session's spec and round. Empty when no build is active; overridden paths are omitted."""
    frozen: dict = {}
    for session, roots, project in resolve_build_contexts(cwd, home=home):
        if not _context_guards_frozen(session, project):
            continue
        for cand in _guarded_paths(session, roots):
            frozen.setdefault(cand, session)
    return frozen


def _guards_allow(cfg) -> None:
    """Let the request through, in this host's allow shape."""
    print(json.dumps(cfg["allow"]))


def _guards_deny(cfg, user: str, agent: str) -> None:
    """Refuse the request, carrying the reason to the person and to the agent separately."""
    decision = dict(cfg["deny"])
    decision[cfg["user_key"]] = user
    decision[cfg["agent_key"]] = agent
    print(json.dumps(decision))


def _guards_notify(cfg, note: str) -> None:
    """Announce something to both audiences without deciding anything — the after-edit shape."""
    print(json.dumps({cfg["user_key"]: note, cfg["agent_key"]: note}))


def _writes_frozen(cmd: str, frozen: dict):
    """The frozen path *cmd* writes to or deletes, or None. Basename-level: a redirection counts only
    when the frozen file is its TARGET, and a verb only when a frozen name shares its own segment."""
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
    """The frozen path a write-ish MCP call targets, or None — the tool NAME must look mutating AND a
    frozen basename must appear in its arguments, so a pure read/list/get call stays allowed."""
    name = ""

    # MCP servers spell these keys freely, so try every plausible one; none matching fails OPEN.
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
    """After-edit guard: the edit already landed, so a frozen hit is announced, never vetoed."""
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

def _dispatch(cfg, when: str, mode: str, evt, home=None) -> None:
    """Route a parsed event by WHEN the host asks — before a write, or after one."""
    if when == "before_write":
        _emit(cfg, _pre_write_reason(cfg, evt, home=home))
    elif when == "after_write":
        _event_guards_decide(cfg, mode, evt if isinstance(evt, dict) else {}, home=home)


def _fail_open(cfg, when: str, mode: str) -> None:
    """The fail-OPEN response after any error: hosts expecting an explicit allow get one, hosts
    whose silence means allow get silence — never a block, so a gate bug can't brick an edit."""
    if when == "before_write":
        _emit(cfg, None)
    elif when == "after_write" and mode in ("shell", "mcp"):
        _guards_allow(cfg)


def main(argv=None, stdin_text=None, home=None, config=None) -> int:
    """Entry point: load this host's config, read its event from stdin, and emit one decision. Every
    failure lands in `_fail_open`, so a gate that cannot do its job still lets work continue."""
    argv = argv if argv is not None else sys.argv
    mode = argv[1] if len(argv) > 1 else ""
    cfg = config if config is not None else _read_config()
    if not isinstance(cfg, dict):
        return 0  # no readable host config → fail OPEN (never brick an edit)
    when = cfg.get("when", "before_write")
    try:
        raw = stdin_text if stdin_text is not None else sys.stdin.read()
        evt = json.loads(raw) if raw and raw.strip() else {}
        _dispatch(cfg, when, mode, evt, home=home)
    except Exception:
        _fail_open(cfg, when, mode)
    return 0


# pragma: no mutate — a wrapped "__main__" never equals the real dunder, so this guard carries no behavioural mutant.
if __name__ == "__main__":  # pragma: no mutate
    sys.exit(main())
