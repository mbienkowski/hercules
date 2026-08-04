"""Runs the document standard on the host's schedule instead of the model's.

WHY THIS EXISTS: a command that TELLS an agent to run a checker is a request. It is followed most
of the time, which is the same as not being followed. These two modes move the same checks onto tool
calls the agent has to make anyway, so the standard is applied whether or not anyone remembered it.

  review   PostToolUse. A delivery document was just written; check it and hand the findings back.
           Never vetoes anything — the write already happened, and the point is to inform.

  advance  PreToolUse. The agent is about to move the session into the next phase. That is one
           specific shell command, so it is the chokepoint: the gate re-runs the checks HERE and
           refuses the call when the work has not actually been reviewed.

  probes   PreToolUse, on the spec file itself. Design's falsification step (probe the assumptions
           that would sink the plan) has no natural shell chokepoint of its own — presenting a draft
           is chat, not a tool call — so nothing stopped it being skipped outright. The one real
           chokepoint is earlier than a phase change: a spec cannot be WRITTEN until this session's
           tier-required probes exist and verify. This is what makes falsification non-skippable
           rather than a step an agent can quietly not do.

`advance` deliberately keeps NO state of its own. It re-derives the verdict at the moment of the
call rather than trusting a flag written earlier, so there is nothing to go stale and nothing for a
hook to write — the house rule that a hook never writes `~/.hercules` stays intact.

Fails OPEN throughout, like every hook here: an unresolvable project, a missing tool, a parse error
or an absent `python3` all allow the action. A gate bug must never brick someone's work. That makes
enforcement mediated, not tamper-proof, and it is a deliberate trade rather than an oversight.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
if os.path.isdir(_TOOLS):
    sys.path.insert(0, _TOOLS)

from frozen_tests import _target_paths  # noqa: E402  (one definition of "what did this tool touch")

ALLOW = 0
BLOCK = 2

_PHASE_TOOL = "state_patch"
_GATED_PHASES = {"design", "build"}


def _tools_dir() -> Path:
    """Where the checkers live: `tools/` beside `hooks/`, in the source tree and in every
    distribution alike."""
    return Path(_TOOLS)


def _load_checkers():
    """The two checkers, imported rather than shelled out to — no interpreter start-up per call, and
    a failure to import is just another reason to allow."""
    import doc_lint
    import doc_report
    return doc_lint, doc_report


def _rules(doc_lint):
    return doc_lint.load_rules(_tools_dir())


# ── review: hand the findings back after a document is written ──────────────────────────────────


def _is_delivery_document(doc_lint, rules, path: Path):
    """The document kind this path names, or None when it is an ordinary file the gate ignores."""
    try:
        return doc_lint.resolve_kind(rules, path, "")
    except Exception:
        return None


def _session_tier(path: Path, home) -> str:
    """The tier recorded for the session this document belongs to, defaulting to medium. Read-only,
    and a failure to resolve is not worth blocking anyone over."""
    try:
        from hercules_state import resolve_build_contexts  # noqa: F401  (presence check only)
    except Exception:
        pass
    try:
        home_dir = Path(home) if home else Path.home()
        config = json.loads((home_dir / ".hercules" / "config.json").read_text(encoding="utf-8"))
        for entry in (config.get("projects") or {}).values():
            state_file = entry.get("state_file")
            if not state_file or os.path.basename(state_file) != state_file:
                continue
            state = json.loads((home_dir / ".hercules" / "state" / state_file)
                               .read_text(encoding="utf-8"))
            sessions = state.get("sessions") or {}
            for session_id, session in sessions.items():
                if session_id and session_id in str(path):
                    return session.get("tier") or "medium"
    except Exception:
        pass
    return "medium"


def _describe(findings, path: Path) -> str:
    """What the agent reads. Ordered worst-first and capped, because a wall of advice is skimmed."""
    lines = ["Hercules checked %s against the document standard." % path.name]
    blocking = [f for f in findings if f.get("severity") == "block"]
    advice = [f for f in findings if f.get("severity") != "block"]
    if blocking:
        lines.append("")
        lines.append("Must fix:")
        for finding in blocking:
            lines.append("  - %s (line %s) — %s" % (finding["rule"], finding["line"],
                                                    finding["message"]))
            lines.append("    %s" % finding["fix"])
    if advice:
        lines.append("")
        lines.append("Worth a look (none of these block):")
        for finding in advice[:8]:
            lines.append("  - %s (line %s) — %s" % (finding["rule"], finding["line"],
                                                    finding["message"]))
            lines.append("    %s" % finding["fix"])
        if len(advice) > 8:
            lines.append("  ... and %d more; run the checker for the full list." % (len(advice) - 8))
    lines.append("")
    lines.append("These come from doc_rules.json, not from an opinion formed just now. Judgement "
                 "about whether the content is RIGHT is yours; this only reports what is checkable.")
    return "\n".join(lines)


def review(payload, home=None) -> tuple:
    """Check every delivery document this tool call wrote. `(exit_code, message)` — BLOCK is used
    only to route the message back into the conversation, never to undo the write."""
    try:
        doc_lint, _ = _load_checkers()
        rules = _rules(doc_lint)
    except Exception:
        return ALLOW, ""

    cwd = payload.get("cwd") or os.getcwd()
    reports = []
    for raw in _target_paths(payload.get("tool_input") or {}):
        try:
            path = Path(raw if os.path.isabs(str(raw)) else os.path.join(cwd, str(raw)))
            kind = _is_delivery_document(doc_lint, rules, path)
            if kind is None or not path.exists():
                continue
            findings = _check(doc_lint, rules, path, kind, _session_tier(path, home))
            if findings:
                reports.append(_describe(findings, path))
        except Exception:
            continue
    if not reports:
        return ALLOW, ""
    return BLOCK, "\n\n".join(reports)


def _check(doc_lint, rules, path: Path, kind: str, tier: str) -> list:
    """One document's findings, using the checker's own entry point so the hook and a manual run
    can never disagree."""
    class _Args:
        pass
    args = _Args()
    args.path = str(path)
    args.kind = kind
    args.tier = tier
    args.strict = False
    payload, _ = doc_lint.run_check(rules, args)
    return payload.get("findings") or []


# ── advance: the interlock in front of the phase change ─────────────────────────────────────────


def _phase_change(command: str):
    """The phase a `state_patch` command would move the session into, or None when the command is
    something else entirely. Matched on the tool name AND the assignment, so an unrelated mention of
    the word cannot trip the gate."""
    if not command or _PHASE_TOOL not in command:
        return None
    marker = "current_phase="
    if marker not in command:
        return None
    tail = command.split(marker, 1)[1]
    phase = ""
    for char in tail:
        if char.isalpha():
            phase += char
        else:
            break
    return phase or None


def _resolve_active_session(cwd, home):
    """The registered project matching `cwd`, and its active session. Returns
    `(directory, session_id, folder, session)` or `None` when nothing resolves — matched on the
    registry's `directory` field, never guessed from a filename or a loose substring of a path, so a
    coincidentally-named file in an unrelated repo is never mistaken for a Hercules session."""
    home_dir = Path(home) if home else Path.home()
    config = json.loads((home_dir / ".hercules" / "config.json").read_text(encoding="utf-8"))
    cwd = os.path.abspath(cwd)

    for entry in (config.get("projects") or {}).values():
        directory = entry.get("directory")
        if not directory or os.path.abspath(directory) != cwd:
            continue
        state_file = entry.get("state_file")
        if not state_file or os.path.basename(state_file) != state_file:
            return None
        state = json.loads((home_dir / ".hercules" / "state" / state_file)
                           .read_text(encoding="utf-8"))
        session_id = state.get("active_session")
        if not session_id:
            return None
        docs_root = entry.get("docs_root") or "docs"
        root = Path(docs_root)
        if not root.is_absolute():
            root = Path(directory) / docs_root
        session = (state.get("sessions") or {}).get(session_id) or {}
        return directory, session_id, root / session_id, session
    return None


def _session_documents(payload, phase, home):
    """The documents the phase being entered depends on: Design rests on the requirements, Build on
    the specs. Returns `(paths, session_id)`; an empty list means nothing to gate."""
    resolved = _resolve_active_session(payload.get("cwd") or os.getcwd(), home)
    if resolved is None:
        return [], None
    _directory, session_id, folder, _session = resolved
    if not folder.is_dir():
        return [], session_id
    pattern = "*-business-requirements.md" if phase == "design" else "*-spec-*.md"
    return sorted(folder.glob(pattern)), session_id


def _verdict(doc_lint, doc_report, rules, path: Path, tier: str):
    """One document's gate result: `(ok, reason)`. A missing or unjudged review is not a pass —
    that is the whole point of the interlock."""
    kind = _is_delivery_document(doc_lint, rules, path)
    if kind is None:
        return True, ""
    findings = _check(doc_lint, rules, path, kind, tier)
    blocking = [f for f in findings if f.get("severity") == "block"]
    if blocking:
        return False, "%s — %s (%s)" % (path.name, blocking[0]["message"], blocking[0]["rule"])

    report_path = path.with_name(path.stem + "-report.json")
    if not report_path.exists():
        return False, "%s has no review at %s" % (path.name, report_path.name)

    class _Args:
        pass
    args = _Args()
    args.report = str(report_path)
    args.lint = None
    args.round = ""
    try:
        result, _ = doc_report.run_judge(rules, args)
    except doc_report.Refused as refusal:
        # Name the gaps, not the count: "4 gaps to close" tells nobody which four.
        detail = "; ".join(refusal.detail[:4]) if refusal.detail else refusal.message
        return False, "%s: %s (%s)" % (report_path.name, refusal.message, detail)
    except Exception as exc:
        return False, "%s: the review could not be judged — %s" % (report_path.name, exc)
    if result.get("decision") != "proceed":
        return False, "%s: the review says %s — %s" % (
            report_path.name, result.get("decision"), "; ".join(result.get("reasons") or []))
    return True, ""


def _refusal(phase, problems) -> str:
    """The scripted stop: what is unfinished, and the one action that clears it."""
    lines = ["Hercules: this session is not ready to move into %s." % phase, ""]
    for problem in problems:
        lines.append("  - %s" % problem)
    lines += [
        "",
        "The phase gate re-checks the documents at the moment of the move, so there is nothing to "
        "mark done. Fix what is listed, write the review beside the document it reviews "
        "(<document>-report.json), and run the same command again.",
        "A review must answer every category in the rubric; `doc_report.py rubric` prints it.",
    ]
    return "\n".join(lines)


def advance(payload, home=None) -> tuple:
    """Veto a phase change whose documents have not survived the standard. Fails OPEN on anything
    it cannot resolve — an unregistered project is not evidence of a problem."""
    tool_input = payload.get("tool_input") or {}
    command = tool_input.get("command") or ""
    phase = _phase_change(str(command))
    if phase not in _GATED_PHASES:
        return ALLOW, ""

    try:
        doc_lint, doc_report = _load_checkers()
        rules = _rules(doc_lint)
        documents, session_id = _session_documents(payload, phase, home)
        resolved = _resolve_active_session(payload.get("cwd") or os.getcwd(), home)
    except Exception:
        return ALLOW, ""

    if not documents:
        return ALLOW, ""

    # The resolved session carries its own recorded tier — read that directly rather than
    # re-deriving it, so the gate and the session agree on the same fact by construction.
    tier = (resolved[3].get("tier") if resolved else None) or "medium"
    problems = []
    for path in documents:
        try:
            ok, reason = _verdict(doc_lint, doc_report, rules, path, tier)
        except Exception:
            continue
        if not ok:
            problems.append(reason)
    if not problems:
        return ALLOW, ""
    return BLOCK, _refusal(phase, problems)


# ── probes: a spec cannot be written until its session's probes have verified ───────────────────


def _load_prober():
    module = "probe_run"
    __import__(module)
    return sys.modules[module]


def _probes_refusal(spec_name, tier, why) -> str:
    lines = [
        "Hercules: %s cannot be written yet." % spec_name,
        "",
        "  - %s" % why,
        "",
        "This is Design's falsification step, not the phase gate: a spec is not written until the "
        "assumptions it rests on have been probed for tier %s (`probe_run.py budget` prints how "
        "many). Run the probes into docs/{session}/probes/, verify them, then write the spec again."
        % tier,
    ]
    return "\n".join(lines)


def probes(payload, home=None) -> tuple:
    """Refuse to write a spec file until this session's tier-required probes exist and verify.

    Fails OPEN whenever it cannot positively resolve a registered Hercules session for `cwd` — an
    unregistered project, or a coincidentally spec-shaped filename in an unrelated repo, is not
    evidence that anything was skipped."""
    try:
        doc_lint, _ = _load_checkers()
        rules = _rules(doc_lint)
        probe_run = _load_prober()
        resolved = _resolve_active_session(payload.get("cwd") or os.getcwd(), home)
    except Exception:
        return ALLOW, ""
    if resolved is None:
        return ALLOW, ""
    _directory, _session_id, folder, session = resolved

    cwd = payload.get("cwd") or os.getcwd()
    tier = session.get("tier") or "medium"
    budget = rules.get("probes", {}).get("tiers", {}).get(tier)
    if not budget or not budget.get("probes"):
        return ALLOW, ""  # this tier asks for no probes — nothing to gate

    for raw in _target_paths(payload.get("tool_input") or {}):
        try:
            path = Path(raw if os.path.isabs(str(raw)) else os.path.join(cwd, str(raw)))
            # Positively confirm the target is INSIDE this session's own folder — resolving the
            # project by cwd is not enough on its own if the write targets some other path entirely.
            if folder.resolve() not in path.resolve().parents:
                continue
            if _is_delivery_document(doc_lint, rules, path) != "spec":
                continue
        except Exception:
            continue

        probes_dir = folder / "probes"
        try:
            class _Args:
                pass
            args = _Args()
            args.into = str(probes_dir)
            args.tier = tier
            result, _ = probe_run.run_verify(rules, args)
        except probe_run.Refused:
            return BLOCK, _probes_refusal(
                path.name, tier, "no probes have been run for this session yet")
        except Exception:
            continue
        if result.get("decision") != "proceed":
            return BLOCK, _probes_refusal(path.name, tier, "; ".join(result.get("reasons") or []))
    return ALLOW, ""


# ── entry point ─────────────────────────────────────────────────────────────────────────────────


_MODES = {"review": review, "advance": advance, "probes": probes}


def main(argv=None, stdin_text=None, home=None) -> int:
    """Host event JSON on stdin, mode as the one argument. Prints any message on stderr and returns
    the exit code. Unreadable input allows — the fail-OPEN direction."""
    argv = list(sys.argv[1:] if argv is None else argv)
    mode = argv[0] if argv else "review"
    handler = _MODES.get(mode)
    if handler is None:
        return ALLOW
    try:
        raw = stdin_text if stdin_text is not None else \
            sys.stdin.buffer.read().decode("utf-8", "replace")  # pragma: no mutate
        payload = json.loads(raw) if raw and raw.strip() else {}
    except Exception:
        return ALLOW
    if not isinstance(payload, dict):
        return ALLOW
    try:
        code, message = handler(payload, home=home)
    except Exception:
        return ALLOW
    if code == BLOCK and message:
        print(message, file=sys.stderr)
    return code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
