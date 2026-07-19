"""The Cursor write-gate adapter (G1) — ``src/targets/cursor/hooks/hercules_gate.py``.

Cursor has no pre-file-edit veto, so the adapter enforces what Cursor's hooks CAN, all keyed off the
SAME frozen-test state AND the SAME ``frozen_override`` policy Claude Code and OpenCode read
(``hercules_state`` + ``frozen_tests._override_allows``):

- ``shell`` (``beforeShellExecution``): DENY a command that writes/commits a frozen test during a build.
- ``after_edit`` (``afterFileEdit``): notification-only — REVERT a frozen edit after the fact.

Reads are NOT blocked (the doctrine locks edits, not reads). A user-sanctioned ``frozen_override`` lifts
the gate for its files this round.

These drive the real adapter in-process against a throwaway ``~/.hercules`` state tree, asserting the
emitted Cursor decision JSON. Deny commands are HARDCODED literals (never read from the gate's own tuple)
so a mutated primitive is actually caught; the exact deny/revert message text is pinned for the same reason.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.build.cli import build_target

REPO_ROOT = Path(__file__).resolve().parents[2]
CURSOR_HOOKS = REPO_ROOT / "src" / "targets" / "cursor" / "hooks"
CLAUDE_HOOKS = REPO_ROOT / "src" / "targets" / "claude-code" / "hooks"
_HAVE_GIT = shutil.which("git") is not None


def _load_gate():
    """Import the adapter in-process. It does ``from frozen_tests/hercules_state import …`` off its own
    dir, so both shared modules (which live in the claude-code tree in source) must be on sys.path."""
    import sys
    for d in (str(CLAUDE_HOOKS), str(CURSOR_HOOKS)):
        if d not in sys.path:
            sys.path.insert(0, d)
    spec = importlib.util.spec_from_file_location("hercules_gate", CURSOR_HOOKS / "hercules_gate.py")
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
    """A throwaway ~/.hercules with one active build session freezing ``tests/test_frozen.py`` under a
    project rooted at *proj*. Returns ``(home, proj)``."""
    home, proj = tmp_path / "home", tmp_path / "proj"
    (proj / "tests").mkdir(parents=True)
    _write_state(home, proj, {"current_phase": "build", "current_spec": "spec-1.md",
                              "current_spec_round": 1, "frozen_test_files": ["tests/test_frozen.py"]})
    return home, proj


def _decide(mode: str, evt: dict, home: Path, capsys) -> dict:
    """Run the adapter's ``main`` for *mode*/*evt* and return the parsed Cursor decision (or {} when the
    adapter emitted nothing — the after_edit-on-clean case)."""
    gate.main(["hercules_gate.py", mode], stdin_text=json.dumps(evt), home=str(home))
    out = capsys.readouterr().out.strip()
    return json.loads(out) if out else {}


# ── shell deny: every write/commit primitive, as HARDCODED commands (not read from the tuple) ──
# One literal per guarded primitive so a mutant that drops/mistypes a primitive makes exactly one of
# these go green→red. Includes bare `rm`/`rm -f` (the historically-missed destructive primitive).
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
]


@pytest.mark.parametrize("command", _DENY_COMMANDS, ids=lambda c: c.split()[0] + "…")
def test_shell_denies_each_write_command_on_a_frozen_test(command, active_build, capsys):
    home, proj = active_build
    d = _decide("shell", {"command": command, "workspace_roots": [str(proj)]}, home, capsys)
    assert d["permission"] == "deny", f"a write command must be denied: {command!r}"


# Legit build commands that NAME a frozen test but do not write to it — must be allowed. Guards the
# redirect-target and same-pipeline-segment logic against over-blocking a routine test run.
_ALLOW_COMMANDS = [
    "cat tests/test_frozen.py",                          # read, no write verb
    "grep -r mv tests/test_frozen.py",                   # a write *word* as a search term, not a command
    "pytest tests/test_frozen.py -v > /tmp/out.txt",     # run the frozen test, redirect elsewhere
    "pytest tests/test_frozen.py 2>&1 | tee /tmp/log",   # run it, tee OUTPUT to a non-frozen file
    "cat tests/test_frozen.py > /dev/null",              # read it, redirect elsewhere
    "diff tests/test_frozen.py b.py > d.txt",            # compare it, redirect elsewhere
    "git add src/feature.py",                            # write verb, unrelated file
    "find . -name conftest.py -delete",                  # find -delete, but not a frozen file
]


@pytest.mark.parametrize("command", _ALLOW_COMMANDS, ids=lambda c: c.split()[0] + "…")
def test_shell_allows_legit_commands_that_only_name_a_frozen_test(command, active_build, capsys):
    home, proj = active_build
    d = _decide("shell", {"command": command, "workspace_roots": [str(proj)]}, home, capsys)
    assert d["permission"] == "allow", f"a non-writing command must be allowed: {command!r}"


def test_shell_deny_carries_the_canonical_reason_with_the_escape_hatch(active_build, capsys):
    """The deny message reuses ``frozen_tests._reason`` — the SAME wording Claude/OpenCode emit — so the
    'change this test' unblock is present and identical across ecosystems (and both channels carry it)."""
    home, proj = active_build
    d = _decide("shell", {"command": "rm tests/test_frozen.py", "workspace_roots": [str(proj)]}, home, capsys)
    assert d["agentMessage"] == d["userMessage"], "both channels carry the one canonical reason"
    assert "is a frozen test for spec-1.md (build round 1/3)" in d["agentMessage"]
    assert 'saying "change this test' in d["agentMessage"], "the escape hatch must be named in the block"


# ── shell allow: quoted mention, no build, phase, opt-out ────────────────────────────────────
def test_shell_allows_a_commit_whose_message_merely_names_a_frozen_test(active_build, capsys):
    """``git commit -m "fix test_frozen.py"`` names the file only inside the quoted message — not an
    operation on it. Quoted spans are stripped before the frozen-path scan, so this is allowed."""
    home, proj = active_build
    evt = {"command": 'git commit -m "fix flake in test_frozen.py"', "workspace_roots": [str(proj)]}
    assert _decide("shell", evt, home, capsys)["permission"] == "allow"


def test_shell_allows_everything_when_no_build_is_active(tmp_path, capsys):
    """No config/state at all → the frozen set is empty → the gate must never interfere."""
    home = tmp_path / "empty-home"
    home.mkdir()
    evt = {"command": "rm tests/test_frozen.py", "workspace_roots": [str(tmp_path)]}
    assert _decide("shell", evt, home, capsys)["permission"] == "allow"


def test_shell_ignores_a_frozen_file_when_the_phase_is_not_build(tmp_path, capsys):
    """The freeze only bites during ``build`` — the same file in ``design`` is fair game."""
    home, proj = tmp_path / "home", tmp_path / "proj"
    (proj / "tests").mkdir(parents=True)
    _write_state(home, proj, {"current_phase": "design", "frozen_test_files": ["tests/test_frozen.py"]})
    evt = {"command": "rm tests/test_frozen.py", "workspace_roots": [str(proj)]}
    assert _decide("shell", evt, home, capsys)["permission"] == "allow"


def test_shell_respects_the_frozen_hook_off_opt_out(tmp_path, capsys):
    """A project that sets ``frozen_hook: off`` disables the guard even mid-build."""
    home, proj = tmp_path / "home", tmp_path / "proj"
    (proj / "tests").mkdir(parents=True)
    _write_state(home, proj, {"current_phase": "build", "frozen_test_files": ["tests/test_frozen.py"]},
                 project_extra={"frozen_hook": "off"})
    evt = {"command": "rm tests/test_frozen.py", "workspace_roots": [str(proj)]}
    assert _decide("shell", evt, home, capsys)["permission"] == "allow"


def test_shell_resolves_cwd_from_the_event_when_no_workspace_roots(active_build, capsys):
    """With no ``workspace_roots`` the gate falls back to the event ``cwd`` — the freeze must still bite."""
    home, proj = active_build
    evt = {"command": "rm tests/test_frozen.py", "cwd": str(proj)}
    assert _decide("shell", evt, home, capsys)["permission"] == "deny"


# ── frozen_override: the user-sanctioned escape hatch works identically to Claude/OpenCode ──────
def _override_session():
    return {"current_phase": "build", "current_spec": "spec-1.md", "current_spec_round": 1,
            "frozen_test_files": ["tests/test_frozen.py"],
            "frozen_override": {"files": ["tests/test_frozen.py"], "spec": "spec-1.md", "round": 1,
                                "reason": "user: 'the expected status is 201 not 200 — fix the test'"}}


def test_shell_allows_a_write_the_user_sanctioned_via_frozen_override(tmp_path, capsys):
    """A live ``frozen_override`` covering the file lifts the shell gate — the documented "change test X"
    grant works on Cursor exactly as on Claude Code / OpenCode (same canonical override policy)."""
    home, proj = tmp_path / "home", tmp_path / "proj"
    (proj / "tests").mkdir(parents=True)
    _write_state(home, proj, _override_session())
    evt = {"command": "git add tests/test_frozen.py", "workspace_roots": [str(proj)]}
    assert _decide("shell", evt, home, capsys)["permission"] == "allow"


def test_after_edit_does_not_revert_a_sanctioned_override_edit(tmp_path, capsys):
    """An override-covered edit must not be reverted — the after-edit backstop respects the same grant."""
    home, proj = tmp_path / "home", tmp_path / "proj"
    (proj / "tests").mkdir(parents=True)
    _write_state(home, proj, _override_session())
    evt = {"file_path": str(proj / "tests" / "test_frozen.py"), "workspace_roots": [str(proj)]}
    assert _decide("after_edit", evt, home, capsys) == {}


# ── after_edit (afterFileEdit) — notification-only, so revert as a backstop ──────────────────
@pytest.mark.skipif(not _HAVE_GIT, reason="git required for the live revert check")
def test_after_edit_stashes_a_frozen_edit_recoverably(active_build, capsys):
    """afterFileEdit can't veto, so the adapter reverts a frozen edit by ``git stash`` — RECOVERABLE,
    never a destructive checkout that discards the user's work — and warns with the canonical reason plus
    how to get the change back."""
    home, proj = active_build
    frozen = proj / "tests" / "test_frozen.py"
    frozen.write_text("original\n", encoding="utf-8")
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    # -c guards keep the commit from tripping over a dev/CI box's global gpg-signing or pre-commit hook.
    base = ["git", "-C", str(proj), "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null"]
    for cmd in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "init"]):
        subprocess.run(base + cmd, check=True, env=env, capture_output=True)
    frozen.write_text("tampered\n", encoding="utf-8")  # a Composer edit slips through

    evt = {"file_path": str(frozen), "workspace_roots": [str(proj)]}
    d = _decide("after_edit", evt, home, capsys)
    assert "is a frozen test for spec-1.md" in d["agentMessage"], "carries the canonical reason"
    assert "git stash pop" in d["agentMessage"], "names the recovery path"
    assert frozen.read_text(encoding="utf-8") == "original\n", "the working tree is reverted"
    # ...and the user's work is RECOVERABLE, not discarded:
    subprocess.run(base + ["stash", "pop"], check=True, env=env, capture_output=True)
    assert frozen.read_text(encoding="utf-8") == "tampered\n", "git stash pop restores the user's edit"


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


# ── fail-open discipline: a resolvable-state error must never brick a command ────────────────
def test_shell_fails_open_on_malformed_event(tmp_path, capsys):
    """Garbage on stdin must still yield allow for shell — a gate bug never bricks a command."""
    home = tmp_path / "home"
    home.mkdir()
    gate.main(["hercules_gate.py", "shell"], stdin_text="{not json", home=str(home))
    assert json.loads(capsys.readouterr().out.strip())["permission"] == "allow"


# ── the shipped gate carries the canonical guard files ───────────────────────────────────────
def test_cursor_ships_the_gate_and_the_canonical_guard_files(tmp_path):
    """dist/cursor/hooks/ must ship the adapter + hooks.json + the canonical guard files
    (hercules_state.py reader AND frozen_tests.py, from which the adapter reuses the override policy),
    with hercules_state.py + frozen_tests.py byte-identical to the copies Claude Code uses."""
    out = tmp_path / "cursor"
    build_target("cursor", out)
    for name in ("hercules_gate.py", "hooks.json", "hercules_state.py", "frozen_tests.py"):
        assert (out / "hooks" / name).is_file(), f"dist/cursor/hooks/{name} must ship"
    for name in ("hercules_state.py", "frozen_tests.py"):
        assert (out / "hooks" / name).read_bytes() == (CLAUDE_HOOKS / name).read_bytes(), \
            f"{name} must not diverge across dists"
