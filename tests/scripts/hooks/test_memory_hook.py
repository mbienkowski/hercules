"""Ordinary-chat memory contract, reached through the same stdin/stdout boundary as a host."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tests.scripts.tools.memory_core.conftest import build_home, capture

HOOK = Path(__file__).resolve().parents[3] / "src/scripts/hooks/memory_hook.py"
spec = importlib.util.spec_from_file_location("memory_hook", HOOK)
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)


@pytest.fixture
def fx(tmp_path):
    return build_home(tmp_path)


def submit(fx, capsys, *, session="new-chat", prompt="Continue the task", **extra):
    event = {"cwd": str(fx.project), "prompt": prompt, "session_id": session,
             "hook_event_name": "UserPromptSubmit", **extra}
    code = hook.main(json.dumps(event), home=fx.home, dialect="common")
    return code, json.loads(capsys.readouterr().out)


def test_an_ordinary_chat_receives_preferences_without_a_workflow_command(fx, capsys):
    capture(fx, "decision", "Keep responses concise.", topic="response-style", pinned=True)
    code, result = submit(fx, capsys)
    assert code == 0
    text = result["hookSpecificOutput"]["additionalContext"]
    assert "Keep responses concise." in text
    assert "captured_at" not in text


def test_an_unchanged_context_is_not_paid_for_on_every_turn(fx, capsys):
    submit(fx, capsys)
    _, result = submit(fx, capsys)
    assert result == {}


def test_a_new_session_or_compaction_restores_context(fx, capsys):
    submit(fx, capsys)
    _, next_chat = submit(fx, capsys, session="second-chat")
    _, compacted = submit(fx, capsys, source="compact")
    assert next_chat["hookSpecificOutput"]["additionalContext"]
    assert compacted["hookSpecificOutput"]["additionalContext"]


def test_a_preference_recorded_by_the_host_model_reaches_the_next_chat(fx, capsys):
    submit(fx, capsys)
    capture(fx, "decision", "Use pnpm for this project.", topic="package-manager", pinned=True)
    _, result = submit(fx, capsys, session="second-chat", prompt="Build the application")
    assert "Use pnpm for this project." in result["hookSpecificOutput"]["additionalContext"]


def test_a_conflicting_preference_is_not_injected_as_an_unqualified_rule(fx, capsys):
    capture(fx, "decision", "Use npm.", topic="package-manager", pinned=True)
    capture(fx, "decision", "Use pnpm.", topic="package-manager", pinned=True)
    _, result = submit(fx, capsys, prompt="pnpm")
    text = result["hookSpecificOutput"]["additionalContext"]
    assert "Conflicting memories omitted" in text
    assert '"statement":"Use pnpm."' not in text
    assert '"statement":"Use npm."' not in text


def test_unrelated_prompt_does_not_get_saved_as_a_preference(fx, capsys):
    submit(fx, capsys, prompt="Fix the failing test")
    assert not list((fx.home / ".hercules/memory").rglob("entries.md"))


def test_injected_context_has_a_hard_byte_cap(fx, capsys):
    for i in range(20):
        capture(fx, "decision", f"Preference {i}: " + "readable " * 60, pinned=True)
    _, result = submit(fx, capsys)
    text = result["hookSpecificOutput"]["additionalContext"]
    assert len(text.encode("utf-8")) <= hook.MAX_CONTEXT_BYTES


def test_a_repeated_preference_survives_a_crowded_standing_context(fx, capsys):
    for i in range(8):
        capture(fx, "decision", f"Earlier preference {i}.", topic=f"topic-{i}", pinned=True)
    for _ in range(2):
        capture(fx, "decision", "Keep responses concise.", topic="response-style", pinned=True)
    _, result = submit(fx, capsys, prompt="Continue")
    assert "Keep responses concise." in result["hookSpecificOutput"]["additionalContext"]


@pytest.mark.parametrize("raw", ["not-json", "[]", "{}", "x" * (hook.MAX_INPUT_BYTES + 1)])
def test_bad_events_never_block_the_conversation(raw, fx, capsys):
    # An empty object is harmless and has no explicit project identity; all other bad inputs fail open.
    if raw == "{}":
        raw = '{"cwd":null,"prompt":[]}'
    assert hook.main(raw, home=fx.home, dialect="common") == 0
    assert json.loads(capsys.readouterr().out) == {}


def test_failures_are_silent_per_prompt_and_actionable_at_session_start(fx, capsys, monkeypatch):
    def fail():
        raise OSError("secret from a damaged file")
    monkeypatch.setattr(hook, "load_core", fail)
    _, quiet = submit(fx, capsys)
    assert quiet == {}
    _, loud = submit(fx, capsys, hook_event_name="SessionStart")
    message = loud["systemMessage"]
    assert "memory unavailable" in message
    assert str(fx.home / ".hercules" / "memory") in message
    assert "Inspect with: python3" in message and "inspect --cwd" in message
    assert "secret" not in json.dumps(loud)
    hook.main(json.dumps({"hook_event_name": "SessionStart", "cwd": str(fx.project)}),
              home=fx.home, dialect="copilot")
    assert json.loads(capsys.readouterr().out) == {}  # Copilot ignores systemMessage: stay silent


@pytest.mark.parametrize("dialect,key", [("cursor", "additional_context"),
                                         ("common", "hookSpecificOutput")])
def test_context_uses_the_host_output_format(fx, capsys, dialect, key):
    hook.main(json.dumps({"cwd": str(fx.project)}), home=fx.home, dialect=dialect)
    assert key in json.loads(capsys.readouterr().out)


def test_copilot_receives_a_flat_additional_context(fx, capsys):
    hook.main(json.dumps({"cwd": str(fx.project)}), home=fx.home, dialect="copilot")
    result = json.loads(capsys.readouterr().out)
    assert set(result) == {"additionalContext"}
    assert "Hercules project memory" in result["additionalContext"]


def test_a_store_locked_by_another_process_never_blocks_a_prompt(fx, capsys):
    holder_script = ("import fcntl, sys, time\n"
                     "f = open(sys.argv[1], 'a+b')\n"
                     "fcntl.flock(f, fcntl.LOCK_EX)\n"
                     "print('locked', flush=True)\n"
                     "time.sleep(30)\n")
    lock = fx.home / ".hercules" / "memory" / ".deliveries.lock"
    lock.parent.mkdir(parents=True)
    holder = subprocess.Popen([sys.executable, "-c", holder_script, str(lock)], stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == "locked"
        started = time.monotonic()
        _, result = submit(fx, capsys)
        assert time.monotonic() - started < 1
        assert result == {}
    finally:
        holder.kill()
        holder.wait()


def test_an_empty_store_leaves_no_per_repo_footprint(fx, capsys):
    submit(fx, capsys)
    memory = fx.home / ".hercules" / "memory"
    assert {p.name for p in memory.iterdir()} <= {".deliveries.json", ".deliveries.lock"}
    assert (memory / ".deliveries.json").is_file()
    missing = fx.project.parent / "not-created"
    hook.main(json.dumps({"cwd": str(missing), "session_id": "s", "hook_event_name": "SessionStart"}),
              home=fx.home, dialect="common")
    assert json.loads(capsys.readouterr().out) == {}
    assert not missing.exists() and not (memory / "not-created").exists()


def test_the_capture_template_is_shell_inert(fx, capsys):
    _, result = submit(fx, capsys)
    text = result["hookSpecificOutput"]["additionalContext"]
    assert "--topic 'short-topic' --statement 'concise preference'" in text
    assert "'\\''" in text  # the apostrophe rule is stated once, in the instructions
    assert '"short-topic"' not in text


def test_host_payload_variants_resolve_the_same_project_and_skip_subagents(fx, capsys):
    capture(fx, "decision", "Keep responses concise.", topic="response-style", pinned=True)
    cursor = json.dumps({"workspace_roots": [str(fx.project)], "sessionId": "cursor-chat"})
    hook.main(cursor, home=fx.home, dialect="common")
    first = json.loads(capsys.readouterr().out)
    assert "Keep responses concise." in first["hookSpecificOutput"]["additionalContext"]
    hook.main(cursor, home=fx.home, dialect="common")
    assert json.loads(capsys.readouterr().out) == {}  # camelCase session id dedupes like snake_case
    hook.main(json.dumps({"cwd": str(fx.project), "subagentType": "explore"}), home=fx.home, dialect="common")
    assert json.loads(capsys.readouterr().out) == {}


def test_delegates_do_not_capture_a_second_copy_of_the_users_preferences(fx, capsys):
    _, result = submit(fx, capsys, agent_id="reviewer")
    assert result == {}


def test_versioned_code_findings_always_require_verification_in_host_context(fx, capsys):
    capture(fx, "verified-finding", "The parser accepts this input.", code_version="old-checkout", pinned=True)
    _, result = submit(fx, capsys)
    text = result["hookSpecificOutput"]["additionalContext"]
    assert '"verification_required":true' in text
    assert "verify flagged code findings" in text
