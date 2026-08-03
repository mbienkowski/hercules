"""`frozen_tests.py check` — the retire-time backstop, invoked deliberately rather than fired on a
live edit: its exit codes and JSON over a real tmp `~/.hercules` tree, and the live hook's own
stdin-JSON contract standing beside it untouched."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys

from tests.scripts.hooks.conftest import _HOOKS_DIR

import frozen_tests as ft

SLUG = "proj"
SESSION = "s1"
FROZEN_TEST = "tests/test_login.py"
SPEC = "spec-02-login.md"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _build(tmp_path, *, content="def test_x():\n    assert real()\n", baselined=True,
           session_id=SESSION, active=SESSION):
    """One project/session with its frozen test on disk, baselined at that content by default."""
    project = tmp_path / "proj"
    test_path = project / FROZEN_TEST
    test_path.parent.mkdir(parents=True, exist_ok=True)
    test_path.write_text(content, encoding="utf-8")

    hh = tmp_path / ".hercules"
    (hh / "state").mkdir(parents=True, exist_ok=True)
    (hh / "config.json").write_text(json.dumps(
        {"schema_version": 1, "projects": {SLUG: {"directory": str(project),
                                                   "state_file": f"{SLUG}.json"}}}))
    session = {"current_phase": "build", "current_spec": SPEC, "current_spec_round": 1,
              "frozen_test_files": [FROZEN_TEST]}
    if baselined:
        session["frozen_baseline"] = {FROZEN_TEST: _sha(content)}
    (hh / "state" / f"{SLUG}.json").write_text(json.dumps(
        {"schema_version": 1, "active_session": active, "sessions": {session_id: session}}))
    return project


def test_check_exits_zero_and_reports_no_drift_on_a_matching_tree(tmp_path):
    _build(tmp_path)
    code, payload = ft.check_command(SLUG, SESSION, home=tmp_path)
    assert code == 0
    assert payload["drifted_files"] == []
    assert payload["error"] is None
    assert payload["project"] == SLUG and payload["session"] == SESSION


def test_check_exits_two_and_names_the_drifted_file_on_a_tampered_tree(tmp_path):
    project = _build(tmp_path)
    (project / FROZEN_TEST).write_text("def test_x():\n    assert True\n", encoding="utf-8")
    code, payload = ft.check_command(SLUG, SESSION, home=tmp_path)
    assert code == 2
    assert payload["drifted_files"] == [FROZEN_TEST]


def test_check_reports_clean_when_no_baseline_was_ever_recorded(tmp_path):
    """A session that never froze a test has nothing to verify."""
    _build(tmp_path, baselined=False)
    code, payload = ft.check_command(SLUG, SESSION, home=tmp_path)
    assert code == 0
    assert payload["drifted_files"] == []


def test_check_defaults_to_the_active_session_when_none_is_named(tmp_path):
    _build(tmp_path)
    code, payload = ft.check_command(SLUG, None, home=tmp_path)
    assert code == 0
    assert payload["session"] == SESSION


def test_check_fails_closed_when_the_project_is_not_registered(tmp_path):
    """The last check before a spec retires, so it fails CLOSED — the opposite of the live hook."""
    _build(tmp_path)
    code, payload = ft.check_command("no-such-project", SESSION, home=tmp_path)
    assert code == 2
    assert payload["drifted_files"] == []
    assert payload["error"]


def test_check_fails_closed_when_the_named_session_does_not_exist(tmp_path):
    _build(tmp_path)
    code, payload = ft.check_command(SLUG, "no-such-session", home=tmp_path)
    assert code == 2
    assert payload["error"]


def test_check_fails_closed_when_the_state_file_cannot_be_read(tmp_path):
    _build(tmp_path)
    (tmp_path / ".hercules" / "state" / f"{SLUG}.json").write_text("{ not json")
    code, payload = ft.check_command(SLUG, SESSION, home=tmp_path)
    assert code == 2
    assert payload["error"]


def test_check_fails_closed_when_the_registry_cannot_be_read(tmp_path):
    _build(tmp_path)
    (tmp_path / ".hercules" / "config.json").write_text("{ not json")
    code, payload = ft.check_command(SLUG, SESSION, home=tmp_path)
    assert code == 2
    assert payload["error"]


def test_check_fails_closed_when_the_state_pointer_escapes_the_record_directory(tmp_path):
    project = _build(tmp_path)
    config_path = tmp_path / ".hercules" / "config.json"
    config = json.loads(config_path.read_text())
    config["projects"][SLUG]["state_file"] = "../../etc/passwd"
    config_path.write_text(json.dumps(config))
    code, payload = ft.check_command(SLUG, SESSION, home=tmp_path)
    assert code == 2
    assert "escapes" in payload["error"]
    assert project.exists()  # the guard is read-only, so nothing it touches is a write


def test_the_check_subcommand_is_parsed_and_prints_its_json_payload(tmp_path, capsys):
    _build(tmp_path)
    code = ft.cli_main(["--project-slug", SLUG, "--session-id", SESSION], home=tmp_path)
    assert code == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["drifted_files"] == []


def test_the_guard_works_as_the_real_deployed_check_command(tmp_path):
    """A standalone program given real argv, exactly as a maintenance command invokes it."""
    project = _build(tmp_path)
    script = _HOOKS_DIR / "frozen_tests.py"
    env = {**os.environ, "HOME": str(tmp_path)}
    clean = subprocess.run(
        [sys.executable, str(script), "check", "--project-slug", SLUG, "--session-id", SESSION],
        capture_output=True, text=True, env=env)
    assert clean.returncode == 0
    assert json.loads(clean.stdout)["drifted_files"] == []

    (project / FROZEN_TEST).write_text("def test_x():\n    assert True\n", encoding="utf-8")
    tampered = subprocess.run(
        [sys.executable, str(script), "check", "--project-slug", SLUG, "--session-id", SESSION],
        capture_output=True, text=True, env=env)
    assert tampered.returncode == 2
    assert json.loads(tampered.stdout)["drifted_files"] == [FROZEN_TEST]


def test_adding_the_check_subcommand_left_the_live_hooks_stdin_json_contract_unchanged(tmp_path):
    """The live hook is invoked with no argv and the payload on stdin; the CLI dispatches from
    `sys.argv` beside it, never displacing that contract."""
    project = _build(tmp_path)
    script = _HOOKS_DIR / "frozen_tests.py"
    env = {**os.environ, "HOME": str(tmp_path)}
    payload = json.dumps({
        "tool_name": "Edit",
        "tool_input": {"file_path": str(project / FROZEN_TEST)},
        "cwd": str(project),
    })
    run = subprocess.run([sys.executable, str(script)], input=payload, capture_output=True,
                         text=True, env=env)
    assert run.returncode == 2 and "Hercules:" in run.stderr


def test_importing_the_module_as_a_library_runs_neither_entry_point():
    """Both entry points sit under `__main__`, so importing for the functions never parses argv or
    blocks on stdin."""
    run = subprocess.run(
        [sys.executable, "-c", f"import sys; sys.path.insert(0, {str(_HOOKS_DIR)!r}); "
                                "import frozen_tests; print('imported-ok')"],
        capture_output=True, text=True, input="", timeout=5)
    assert run.returncode == 0
    assert "imported-ok" in run.stdout
