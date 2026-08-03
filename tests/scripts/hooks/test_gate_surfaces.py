"""The three surfaces a host asks the gate through — a shell command, an MCP call, a report after an
edit — at their deep end: every shell write primitive, and an after-the-fact report in an editor
versus an unattended run.
Driven against ``src/scripts/hooks/hercules_gate.py`` and the ``fixtures/`` configurations, never
``dist/``: the gate is byte-copied into every distribution, so a shipped copy proves the copy rather
than the gate, and only a fixture states a shape nobody ships (one key for person and agent both)."""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.scripts.hooks.conftest import gate_fixture

REPO_ROOT = Path(__file__).resolve().parents[3]
SHARED_HOOKS = REPO_ROOT / "src" / "scripts" / "hooks"
_HAVE_GIT = shutil.which("git") is not None

GATE_CONFIG = gate_fixture("after_write_two_channel_gate")
# A host reading one key rather than two, carrying a field of its own in every decision.
ONE_CHANNEL_CONFIG = gate_fixture("after_write_one_channel_gate")


def _load_gate():
    """Import the shared adapter in-process; it imports its guard siblings off its own dir."""
    import sys
    if str(SHARED_HOOKS) not in sys.path:
        sys.path.insert(0, str(SHARED_HOOKS))
    spec = importlib.util.spec_from_file_location("hercules_gate_generic", SHARED_HOOKS / "hercules_gate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gate = _load_gate()


def _write_state(home: Path, proj: Path, session: dict, project_extra: dict | None = None):
    (home / ".hercules" / "state").mkdir(parents=True, exist_ok=True)
    (home / ".hercules" / "config.json").write_text(json.dumps({"projects": {
        "p": {"directory": str(proj), "state_file": "p.json", **(project_extra or {})}}}), encoding="utf-8")
    (home / ".hercules" / "state" / "p.json").write_text(
        json.dumps({"active_session": "s1", "sessions": {"s1": session}}), encoding="utf-8")


@pytest.fixture
def active_build(tmp_path):
    """A throwaway ~/.hercules with one active build freezing ``tests/test_frozen.py``; ``(home, proj)``."""
    home, proj = tmp_path / "home", tmp_path / "proj"
    (proj / "tests").mkdir(parents=True)
    _write_state(home, proj, {"current_phase": "build", "current_spec": "spec-1.md",
                              "current_spec_round": 1, "frozen_test_files": ["tests/test_frozen.py"]})
    return home, proj


def _decide(mode: str, evt: dict, home: Path, capsys, config=None) -> dict:
    """The parsed decision for *mode*/*evt*, or {} when the adapter says nothing."""
    gate.main(["hercules_gate.py", mode], stdin_text=json.dumps(evt), home=str(home),
              config=GATE_CONFIG if config is None else config)
    out = capsys.readouterr().out.strip()
    return json.loads(out) if out else {}


@pytest.fixture(autouse=True)
def _interactive_by_default(monkeypatch):
    """Interactive-IDE mode (advisory, non-mutating) unless a test opts into headless, so a stray
    ``HERCULES_RUNTIME_MODE`` in the runner environment cannot skew a verdict."""
    monkeypatch.delenv("HERCULES_RUNTIME_MODE", raising=False)


# One HARDCODED literal per guarded write primitive, so dropping one turns exactly one case red.
_DENY_COMMANDS = [
    "git add tests/test_frozen.py",
    "git commit -- tests/test_frozen.py",
    "git mv tests/test_frozen.py tests/renamed.py",
    "git rm tests/test_frozen.py",
    "sed -i s/a/b/ tests/test_frozen.py",
    "rm tests/test_frozen.py",
    "rm -f tests/test_frozen.py",
    "mv tests/test_frozen.py /tmp/x",
    "cp /tmp/x tests/test_frozen.py",
    "dd if=/dev/null of=tests/test_frozen.py",
    "tee tests/test_frozen.py",
    "truncate -s 0 tests/test_frozen.py",
    "install /dev/null tests/test_frozen.py",
    "ln -f /dev/null tests/test_frozen.py",
    "echo x > tests/test_frozen.py",             # redirection target is the frozen file
    "echo x >> tests/test_frozen.py",
    "cat src | tee tests/test_frozen.py",        # write verb after a pipe boundary, targeting frozen
    "find tests -name test_frozen.py -delete",   # find … -delete carries no rm token
    "time git add tests/test_frozen.py",         # wrapper prefix: time
    "env GIT_X=1 git commit -- tests/test_frozen.py",  # wrapper + env assignment
    "nice -n 10 git rm tests/test_frozen.py",    # wrapper + numeric-arg flag
    "stdbuf -oL sed -i s/a/b/ tests/test_frozen.py",   # wrapper + flag
    # git's own GLOBAL options between `git` and the subcommand must not evade the deny.
    "git -C . add tests/test_frozen.py",               # -C <path>, the form the gate itself uses
    "git -c core.editor=vi commit -- tests/test_frozen.py",  # -c <k=v>
    "git --git-dir=/r/.git add tests/test_frozen.py",  # --git-dir=… (=value form)
    "echo x >| tests/test_frozen.py",                  # >| clobber-override redirect to a frozen file
    "echo x >& tests/test_frozen.py",                  # >& redirect to a frozen file
    # A quoted path is the common way an agent writes one, and must not become a bypass.
    'rm "tests/test_frozen.py"',                        # double-quoted frozen path
    "git add 'tests/test_frozen.py'",                  # single-quoted frozen path
    'echo x > "tests/test_frozen.py"',                 # quoted redirect target
    'sed -i s/a/b/ "tests/test_frozen.py"',            # quoted arg to an in-place edit
]


@pytest.mark.parametrize("command", _DENY_COMMANDS, ids=lambda c: c.split()[0] + "…")
def test_shell_denies_each_write_command_on_a_frozen_test(command, active_build, capsys):
    home, proj = active_build
    d = _decide("shell", {"command": command, "workspace_roots": [str(proj)]}, home, capsys)
    assert d["permission"] == "deny", f"a write command must be denied: {command!r}"


# Commands that NAME a frozen test without writing to it — the over-blocking side of the same logic.
_ALLOW_COMMANDS = [
    "cat tests/test_frozen.py",                          # read, no write verb
    "grep -r mv tests/test_frozen.py",                   # a write *word* as a search term, not a command
    "pytest tests/test_frozen.py -v > /tmp/out.txt",     # run the frozen test, redirect elsewhere
    "pytest tests/test_frozen.py 2>&1 | tee /tmp/log",   # run it, tee OUTPUT to a non-frozen file
    "cat tests/test_frozen.py > /dev/null",              # read it, redirect elsewhere
    "diff tests/test_frozen.py b.py > d.txt",            # compare it, redirect elsewhere
    "git add src/feature.py",                            # write verb, unrelated file
    'git commit -m "rewrite test_frozen.py assertions"', # -m message NAMING the file is not an op on it
    "find . -name conftest.py -delete",                  # find -delete, but not a frozen file
    "git -C . diff tests/test_frozen.py > /tmp/d",       # read (diff) via a global option, output elsewhere
    "rm mytest_frozen.py.bak",                           # substring of a frozen basename, not the file
    # Global options and no subcommand: the tokenizer runs off the end with nothing to classify.
    "git -c core.pager=cat --no-pager | grep -n test_frozen.py",
]


@pytest.mark.parametrize("command", _ALLOW_COMMANDS, ids=lambda c: c.split()[0] + "…")
def test_shell_allows_legit_commands_that_only_name_a_frozen_test(command, active_build, capsys):
    home, proj = active_build
    d = _decide("shell", {"command": command, "workspace_roots": [str(proj)]}, home, capsys)
    assert d["permission"] == "allow", f"a non-writing command must be allowed: {command!r}"


def test_shell_deny_carries_the_canonical_reason_with_the_escape_hatch(active_build, capsys):
    """The deny reuses the one canonical reason, so the "change this test" unblock is identical
    across ecosystems and reaches both channels."""
    home, proj = active_build
    d = _decide("shell", {"command": "rm tests/test_frozen.py", "workspace_roots": [str(proj)]}, home, capsys)
    assert d["agentMessage"] == d["userMessage"], "both channels carry the one canonical reason"
    assert "is a frozen test for spec-1.md (build round 1/3)" in d["agentMessage"]
    assert 'saying "change this test' in d["agentMessage"], "the escape hatch must be named in the block"


# ── shell allow: quoted mention, no build, phase, opt-out ────────────────────────────────────
def test_shell_allows_a_commit_whose_message_merely_names_a_frozen_test(active_build, capsys):
    """A ``-m`` span is dropped before the frozen-path scan: naming a file is not operating on it."""
    home, proj = active_build
    evt = {"command": 'git commit -m "fix flake in test_frozen.py"', "workspace_roots": [str(proj)]}
    assert _decide("shell", evt, home, capsys)["permission"] == "allow"


def test_shell_ignores_a_frozen_file_when_the_phase_is_not_build(tmp_path, capsys):
    home, proj = tmp_path / "home", tmp_path / "proj"
    (proj / "tests").mkdir(parents=True)
    _write_state(home, proj, {"current_phase": "design", "frozen_test_files": ["tests/test_frozen.py"]})
    evt = {"command": "rm tests/test_frozen.py", "workspace_roots": [str(proj)]}
    assert _decide("shell", evt, home, capsys)["permission"] == "allow"


def test_shell_respects_the_frozen_hook_off_opt_out(tmp_path, capsys):
    """The opt-out holds even mid-build."""
    home, proj = tmp_path / "home", tmp_path / "proj"
    (proj / "tests").mkdir(parents=True)
    _write_state(home, proj, {"current_phase": "build", "frozen_test_files": ["tests/test_frozen.py"]},
                 project_extra={"frozen_hook": "off"})
    evt = {"command": "rm tests/test_frozen.py", "workspace_roots": [str(proj)]}
    assert _decide("shell", evt, home, capsys)["permission"] == "allow"


def test_shell_resolves_cwd_from_the_event_when_no_workspace_roots(active_build, capsys):
    home, proj = active_build
    evt = {"command": "rm tests/test_frozen.py", "cwd": str(proj)}
    assert _decide("shell", evt, home, capsys)["permission"] == "deny"


# ── frozen_override: the user-sanctioned escape hatch works identically to Claude/OpenCode ──────
def _override_session():
    return {"current_phase": "build", "current_spec": "spec-1.md", "current_spec_round": 1,
            "frozen_test_files": ["tests/test_frozen.py"],
            "frozen_override": {"files": ["tests/test_frozen.py"], "spec": "spec-1.md", "round": 1,
                                "reason": "user: 'the expected status is 201 not 200 — fix the test'"}}


def test_after_edit_does_not_revert_a_sanctioned_override_edit(tmp_path, capsys):
    """The after-edit backstop honours the same grant the shell and MCP surfaces do."""
    home, proj = tmp_path / "home", tmp_path / "proj"
    (proj / "tests").mkdir(parents=True)
    _write_state(home, proj, _override_session())
    evt = {"file_path": str(proj / "tests" / "test_frozen.py"), "workspace_roots": [str(proj)]}
    assert _decide("after_edit", evt, home, capsys) == {}


# ── after_edit (afterFileEdit) — advisory in the IDE, honest git-checkout restore only in headless ──
def test_after_edit_ide_advises_and_never_touches_the_tree(active_build, capsys):
    """Interactive IDE: a loud USER-visible advisory, and the tree left exactly as the human left it
    — the human owns their working tree, so nothing is silently mutated under them."""
    home, proj = active_build
    frozen = proj / "tests" / "test_frozen.py"
    frozen.write_text("tampered\n", encoding="utf-8")
    evt = {"file_path": str(frozen), "workspace_roots": [str(proj)]}
    d = _decide("after_edit", evt, home, capsys)
    assert d["userMessage"] == d["agentMessage"], "surfaced to the USER, not agent-only"
    assert "locked acceptance test" in d["userMessage"]
    assert "change test test_frozen.py" in d["userMessage"], "names the override escape hatch"
    assert frozen.read_text(encoding="utf-8") == "tampered\n", "the IDE path must NOT mutate the tree"


@pytest.mark.skipif(not _HAVE_GIT, reason="git required for the live restore check")
def test_after_edit_headless_restores_via_git_checkout(active_build, capsys, monkeypatch):
    """Headless, with no human to act on a notice: the edit is restored and the message says so."""
    monkeypatch.setenv("HERCULES_RUNTIME_MODE", "headless")
    home, proj = active_build
    frozen = proj / "tests" / "test_frozen.py"
    frozen.write_text("original\n", encoding="utf-8")
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    base = ["git", "-C", str(proj), "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null"]
    for cmd in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "init"]):
        subprocess.run(base + cmd, check=True, env=env, capture_output=True)
    frozen.write_text("tampered\n", encoding="utf-8")  # a Composer edit slips through
    evt = {"file_path": str(frozen), "workspace_roots": [str(proj)]}
    d = _decide("after_edit", evt, home, capsys)
    assert "restored the file from git" in d["userMessage"], "claims the restore that actually happened"
    assert frozen.read_text(encoding="utf-8") == "original\n", "headless restores the frozen content"


def test_after_edit_headless_is_honest_when_restore_cannot_happen(active_build, capsys, monkeypatch):
    """An untracked frozen test is the common case right after Design→Build: nothing can be restored,
    so the message must say so rather than claim a success that did not happen."""
    monkeypatch.setenv("HERCULES_RUNTIME_MODE", "headless")
    home, proj = active_build          # active_build's proj is NOT a git repo
    frozen = proj / "tests" / "test_frozen.py"
    frozen.write_text("tampered\n", encoding="utf-8")
    evt = {"file_path": str(frozen), "workspace_roots": [str(proj)]}
    d = _decide("after_edit", evt, home, capsys)
    assert "could NOT auto-restore" in d["userMessage"], "no false success when the restore failed"
    assert "restored the file from git" not in d["userMessage"]
    assert frozen.read_text(encoding="utf-8") == "tampered\n"


# ── mcp (beforeMCPExecution) — deny a WRITE-ish MCP call naming a frozen test; allow reads ────
def test_mcp_denies_a_writeish_call_targeting_a_frozen_test(active_build, capsys):
    """An MCP git or filesystem server bypasses the shell gate entirely; this closes that hole."""
    home, proj = active_build
    evt = {"tool_name": "git_commit", "arguments": {"files": ["tests/test_frozen.py"], "message": "x"},
           "workspace_roots": [str(proj)]}
    d = _decide("mcp", evt, home, capsys)
    assert d["permission"] == "deny"
    assert "is a frozen test for spec-1.md (build round 1/3)" in d["agentMessage"]


def test_mcp_allows_a_read_call_on_a_frozen_test(active_build, capsys):
    """The doctrine locks a frozen test against edits, never against reads."""
    home, proj = active_build
    evt = {"tool_name": "read_file", "arguments": {"path": "tests/test_frozen.py"},
           "workspace_roots": [str(proj)]}
    assert _decide("mcp", evt, home, capsys)["permission"] == "allow"


def test_mcp_allows_a_write_call_that_names_no_frozen_test(active_build, capsys):
    home, proj = active_build
    evt = {"tool_name": "write_file", "arguments": {"path": "src/feature.py", "content": "x"},
           "workspace_roots": [str(proj)]}
    assert _decide("mcp", evt, home, capsys)["permission"] == "allow"


# ── fail-open discipline: a resolvable-state error must never brick a command ────────────────
def test_shell_allows_everything_when_no_build_is_active(tmp_path, capsys):
    """No configuration or state at all leaves the frozen set empty, so nothing may be interfered with."""
    home = tmp_path / "empty-home"
    home.mkdir()
    evt = {"command": "rm tests/test_frozen.py", "workspace_roots": [str(tmp_path)]}
    assert _decide("shell", evt, home, capsys)["permission"] == "allow"


def test_shell_allows_a_write_the_user_sanctioned_via_frozen_override(tmp_path, capsys):
    """The documented "change test X" grant is one canonical policy, identical on every host."""
    home, proj = tmp_path / "home", tmp_path / "proj"
    (proj / "tests").mkdir(parents=True)
    _write_state(home, proj, _override_session())
    evt = {"command": "git add tests/test_frozen.py", "workspace_roots": [str(proj)]}
    assert _decide("shell", evt, home, capsys)["permission"] == "allow"


def test_shell_fails_open_on_malformed_event(tmp_path, capsys):
    """Garbage on stdin must still yield allow for shell — a gate bug never bricks a command."""
    home = tmp_path / "home"
    home.mkdir()
    gate.main(["hercules_gate.py", "shell"], stdin_text="{not json", home=str(home), config=GATE_CONFIG)
    assert json.loads(capsys.readouterr().out.strip())["permission"] == "allow"


def test_mcp_allows_everything_when_no_build_is_active(tmp_path, capsys):
    home = tmp_path / "empty"
    home.mkdir()
    evt = {"tool_name": "write_file", "arguments": {"path": "tests/test_frozen.py"},
           "workspace_roots": [str(tmp_path)]}
    assert _decide("mcp", evt, home, capsys)["permission"] == "allow"


def test_mcp_respects_the_frozen_override(tmp_path, capsys):
    """The same canonical grant, on the MCP surface."""
    home, proj = tmp_path / "home", tmp_path / "proj"
    (proj / "tests").mkdir(parents=True)
    _write_state(home, proj, _override_session())
    evt = {"tool_name": "git_commit", "arguments": {"files": ["tests/test_frozen.py"]},
           "workspace_roots": [str(proj)]}
    assert _decide("mcp", evt, home, capsys)["permission"] == "allow"


def test_mcp_fails_open_on_malformed_event(tmp_path, capsys):
    """Garbage on stdin must still yield allow for mcp — a gate bug never bricks an MCP call."""
    home = tmp_path / "home"
    home.mkdir()
    gate.main(["hercules_gate.py", "mcp"], stdin_text="{not json", home=str(home), config=GATE_CONFIG)
    assert json.loads(capsys.readouterr().out.strip())["permission"] == "allow"


def test_after_edit_is_silent_for_a_non_frozen_file(active_build, capsys):
    home, proj = active_build
    evt = {"file_path": str(proj / "src" / "feature.py"), "workspace_roots": [str(proj)]}
    assert _decide("after_edit", evt, home, capsys) == {}


def test_after_edit_is_silent_when_no_build_is_active(tmp_path, capsys):
    """No active build → empty frozen set → after_edit emits nothing (it neither allows nor reverts)."""
    home = tmp_path / "empty"
    home.mkdir()
    evt = {"file_path": str(tmp_path / "tests" / "test_frozen.py"), "workspace_roots": [str(tmp_path)]}
    assert _decide("after_edit", evt, home, capsys) == {}


# ── shapes only a hand-made configuration can ask for ────────────────────────────────────────
def test_a_refusal_is_the_hosts_own_decision_object_even_when_it_reads_one_channel(active_build, capsys):
    """The refusal is the host's own deny object, extra fields untouched, with ONE key filled in when
    person and agent read the same one — a shape every shipped host lacks, so only a fixture reaches it."""
    home, proj = active_build
    evt = {"command": "rm tests/test_frozen.py", "workspace_roots": [str(proj)]}
    d = _decide("shell", evt, home, capsys, config=ONE_CHANNEL_CONFIG)
    assert d["permission"] == "deny"
    assert d["source"] == "hercules", "the host's own fields must survive the refusal verbatim"
    assert "is a frozen test for spec-1.md (build round 1/3)" in d["message"]
    assert set(d) == {"permission", "source", "message"}, "one channel means exactly one message key"


def test_an_allowed_command_is_the_hosts_own_allow_object_verbatim(active_build, capsys):
    """The allow side of the same rule: the gate prints the declared object, never invents one."""
    home, proj = active_build
    evt = {"command": "cat tests/test_frozen.py", "workspace_roots": [str(proj)]}
    assert _decide("shell", evt, home, capsys, config=ONE_CHANNEL_CONFIG) == \
        {"permission": "allow", "source": "hercules"}


def test_mcp_reads_the_tool_name_from_whichever_key_the_server_uses(active_build, capsys):
    """MCP payload keys are not firmly specified, so an empty ``tool_name`` is not an answer: the gate
    keeps looking, and refuses the write-ish call it finds."""
    home, proj = active_build
    evt = {"tool_name": "", "method": "git_commit",
           "arguments": {"files": ["tests/test_frozen.py"]}, "workspace_roots": [str(proj)]}
    d = _decide("mcp", evt, home, capsys)
    assert d["permission"] == "deny"
    assert "is a frozen test for spec-1.md (build round 1/3)" in d["agentMessage"]


def test_mcp_allows_a_call_whose_tool_name_sits_under_a_key_the_gate_does_not_know(active_build, capsys):
    """With no name to judge write-ishness by, the call is allowed: never a block on a payload the
    gate could not read — the guardrail posture CAPABILITIES.md discloses."""
    home, proj = active_build
    evt = {"mcpToolIdentifier": "git_commit", "arguments": {"files": ["tests/test_frozen.py"]},
           "workspace_roots": [str(proj)]}
    assert _decide("mcp", evt, home, capsys)["permission"] == "allow"


def test_mcp_allows_a_write_ish_call_that_carries_no_arguments_at_all(active_build, capsys):
    """A call naming no file names no frozen file, and an unnamed target is never a reason to block."""
    home, proj = active_build
    evt = {"tool_name": "git_commit", "workspace_roots": [str(proj)]}
    assert _decide("mcp", evt, home, capsys)["permission"] == "allow"
