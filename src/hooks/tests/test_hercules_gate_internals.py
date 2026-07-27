"""Unit-level coverage for ``hercules_gate.py``'s internal helpers, which the ecosystem-level suites
drive only indirectly through a full ``main()`` decision.

``main``'s fail-open ``except`` clause re-derives the SAME safe output an internal exception would
have produced, so an end-to-end decision cannot observe some of these contracts at all — calling the
private functions directly is the only way to pin them. Each test file in this suite carries its own
small copy of the ``_load_gate`` / state-writing helpers rather than importing across files.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SHARED_HOOKS = REPO_ROOT / "src" / "hooks"


def _load_gate():
    if str(SHARED_HOOKS) not in sys.path:
        sys.path.insert(0, str(SHARED_HOOKS))
    spec = importlib.util.spec_from_file_location("hercules_gate_generic", SHARED_HOOKS / "hercules_gate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gate = _load_gate()


def _write_state(home: Path, proj: Path, session: dict):
    (home / ".hercules" / "state").mkdir(parents=True, exist_ok=True)
    (home / ".hercules" / "config.json").write_text(json.dumps({"projects": {
        "p": {"directory": str(proj), "state_file": "p.json"}}}), encoding="utf-8")
    (home / ".hercules" / "state" / "p.json").write_text(
        json.dumps({"active_session": "s1", "sessions": {"s1": session}}), encoding="utf-8")


@pytest.fixture
def active_build(tmp_path):
    home, proj = tmp_path / "home", tmp_path / "proj"
    (proj / "tests").mkdir(parents=True)
    frozen = proj / "tests" / "test_frozen.py"
    frozen.write_text("def test_x():\n    assert True\n", encoding="utf-8")
    _write_state(home, proj, {"current_phase": "build", "current_spec": "spec-1.md",
                              "current_spec_round": 1, "frozen_test_files": ["tests/test_frozen.py"]})
    return home, proj, frozen


# ── _read_config: loads gate.json beside the script's OWN file, fails open when absent ──────────

def test_read_config_loads_gate_json_from_the_scripts_own_directory(tmp_path, monkeypatch):
    fake_dir = tmp_path / "adapter"
    fake_dir.mkdir()
    (fake_dir / "gate.json").write_text(json.dumps({"protocol": "pre_tool"}), encoding="utf-8")
    monkeypatch.setattr(gate, "__file__", str(fake_dir / "hercules_gate.py"))
    assert gate._read_config() == {"protocol": "pre_tool"}


def test_read_config_returns_none_when_gate_json_is_absent(tmp_path, monkeypatch):
    fake_dir = tmp_path / "adapter"
    fake_dir.mkdir()
    monkeypatch.setattr(gate, "__file__", str(fake_dir / "hercules_gate.py"))
    assert gate._read_config() is None


def test_hercules_gate_prioritizes_its_own_directory_over_a_decoy_earlier_on_sys_path(tmp_path):
    """The module inserts its OWN directory at ``sys.path[0]`` (not merely somewhere on the path) so
    a same-named module elsewhere on ``sys.path`` can never shadow the canonical guard it imports."""
    decoy = tmp_path / "decoy"
    decoy.mkdir()
    (decoy / "frozen_tests.py").write_text(
        "def _override_allows(*a, **k):\n    return False\n"
        "def _reason(*a, **k):\n    return 'DECOY'\n"
        "def decide(payload, home=None):\n    return 0, ''\n", encoding="utf-8")
    (decoy / "hercules_state.py").write_text(
        "def canon(p):\n    return str(p)\n"
        "def frozen_candidates(entry, roots):\n    return set()\n"
        "def resolve_build_contexts(cwd, home=None):\n    return []\n", encoding="utf-8")
    saved_path = list(sys.path)
    saved_modules = {k: sys.modules.pop(k) for k in ("frozen_tests", "hercules_state") if k in sys.modules}
    sys.path.insert(0, str(decoy))
    try:
        spec = importlib.util.spec_from_file_location(
            "hercules_gate_decoy_check", SHARED_HOOKS / "hercules_gate.py")
        fresh = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fresh)
        reason = fresh._reason("tests/x.py", {"current_spec": "s", "current_spec_round": 1})
        assert reason.startswith("Hercules: tests/x.py is a frozen test"), \
            "must resolve the REAL frozen_tests, not the decoy shadowing it earlier on sys.path"
    finally:
        sys.path[:] = saved_path
        for name in ("frozen_tests", "hercules_state"):
            sys.modules.pop(name, None)
        sys.modules.update(saved_modules)


# ── _extract_paths: only a genuine string value counts; dedup keeps the FIRST occurrence ─────────

def test_extract_paths_ignores_a_non_string_truthy_value():
    assert gate._extract_paths({"file_path": 123}, ["file_path"], []) == []


def test_extract_paths_dedupes_a_repeated_path_across_nested_edits():
    args = {"edits": [{"file_path": "a.py"}, {"file_path": "a.py"}]}
    assert gate._extract_paths(args, ["file_path"], ["edits"]) == ["a.py"]


# ── _pre_tool_reason: the tool_name/toolName fallback default ────────────────────────────────────

def test_pre_tool_reason_looks_up_the_empty_string_when_no_tool_name_key_is_present(active_build):
    home, proj, frozen = active_build
    cfg = {"tools": {"": "Edit"}, "path_keys": ["file_path"], "nested_keys": []}
    evt = {"toolArgs": {"file_path": str(frozen)}, "cwd": str(proj)}
    reason = gate._pre_tool_reason(cfg, evt, home=str(home))
    assert reason is not None, "the fallback lookup key must be the empty string, not some other default"


# ── _unquote: the dropped `-m`/`--message` span becomes exactly one space; a kept span keeps ALL
# of its inner text (only the outer quote characters are stripped) ───────────────────────────────

def test_unquote_replaces_a_dropped_message_span_with_exactly_one_space():
    assert gate._unquote('git commit -m "fix flake in test_x.py"') == 'git commit -m  '


def test_unquote_preserves_the_full_inner_text_of_a_non_message_quote():
    assert gate._unquote('rm "test.py"') == 'rm test.py'


# NOTE: `_unquote`'s `last = 0` accumulator is pragma'd at its definition in hercules_gate.py — a
# provable equivalent mutant, since `last` is only ever a slice-start bound.


# ── _git_write_seg: git subcommand set, value-taking global options, wrapper stripping ───────────

def test_git_write_seg_recognizes_mv_as_a_write_subcommand():
    assert gate._git_write_seg("git mv a b") is True


def test_git_write_seg_recognizes_rm_as_a_write_subcommand():
    assert gate._git_write_seg("git rm a") is True


def test_git_write_seg_skips_the_value_after_git_dir():
    assert gate._git_write_seg("git --git-dir /repo/.git add x") is True


def test_git_write_seg_skips_the_value_after_work_tree():
    assert gate._git_write_seg("git --work-tree /repo add x") is True


def test_git_write_seg_skips_the_value_after_namespace():
    assert gate._git_write_seg("git --namespace ns add x") is True


def test_git_write_seg_skips_the_value_after_exec_path():
    assert gate._git_write_seg("git --exec-path /path add x") is True


def test_git_write_seg_skips_the_value_after_config_env():
    assert gate._git_write_seg("git --config-env FOO=bar add x") is True


def test_git_write_seg_strips_a_leading_wrapper_before_the_git_token():
    assert gate._git_write_seg("sudo git add x") is True


def test_git_write_seg_does_not_overrun_the_token_list_on_a_trailing_flag():
    """A value-taking-looking scan must not run past the end of the token list: a lone, unrecognized
    trailing flag with nothing after it must resolve to False, not index past the tokens."""
    assert gate._git_write_seg("git -x") is False


def test_git_write_seg_finds_the_subcommand_after_a_non_value_flag():
    assert gate._git_write_seg("git -x add") is True


def test_git_write_seg_returns_false_when_no_subcommand_follows_the_options():
    assert gate._git_write_seg("git -C /repo") is False


def test_git_write_seg_does_not_consume_a_value_token_for_an_equals_form_option(monkeypatch):
    """A value-taking option given in ``--opt=value`` form already carries its value inline — it
    must NOT ALSO consume the next token, or the real subcommand would be skipped past."""
    monkeypatch.setattr(gate, "_GIT_OPT_TAKES_VALUE", {"--foo=bar"})
    assert gate._git_write_seg("git --foo=bar add x") is True


# ── _restore: the exact subprocess.run contract, and honest failure on any exception ─────────────

def test_restore_calls_git_checkout_with_capture_output_true(monkeypatch, tmp_path):
    calls = {}

    class _Result:
        returncode = 0

    def fake_run(cmd, **kwargs):
        calls["kwargs"] = kwargs
        return _Result()

    monkeypatch.setattr(gate.subprocess, "run", fake_run)
    gate._restore(str(tmp_path), "f.py")
    assert calls["kwargs"]["capture_output"] is True


def test_restore_calls_git_checkout_with_a_ten_second_timeout(monkeypatch, tmp_path):
    calls = {}

    class _Result:
        returncode = 0

    def fake_run(cmd, **kwargs):
        calls["kwargs"] = kwargs
        return _Result()

    monkeypatch.setattr(gate.subprocess, "run", fake_run)
    gate._restore(str(tmp_path), "f.py")
    assert calls["kwargs"]["timeout"] == 10


def test_restore_returns_false_when_git_checkout_raises(monkeypatch, tmp_path):
    def fake_run(cmd, **kwargs):
        raise OSError("git not found")

    monkeypatch.setattr(gate.subprocess, "run", fake_run)
    assert gate._restore(str(tmp_path), "f.py") is False


# ── _ide_advisory: the exact pinned wording (a user reads this — content matters) ────────────────

def test_ide_advisory_carries_the_exact_pinned_message():
    expected = (
        "Hercules: x.py is a locked acceptance test for this Build. "
        "The goal is to write code that makes it pass — not to change the test, which would let the "
        "acceptance criteria drift to force a green. Your edit is still on disk and Hercules did NOT "
        "touch it. Undo it (Ctrl+Z) and implement against the test, OR grant an override by telling "
        'Hercules: "change test x.py — <reason>".'
    )
    assert gate._ide_advisory("some/dir/x.py") == expected


# ── frozen_map: a skipped session/project must not stop the scan of the REST ──────────────────────

def test_frozen_map_continues_past_a_non_build_session_to_a_later_build_session(monkeypatch):
    monkeypatch.setattr(gate, "_override_allows", lambda *a, **k: False)
    build = {"current_phase": "build", "frozen_test_files": ["tests/test_x.py"]}
    monkeypatch.setattr(gate, "resolve_build_contexts", lambda cwd, home=None: [
        ({"current_phase": "design"}, ["/r"], {}),
        (build, ["/r"], {}),
    ])
    assert gate.canon("/r/tests/test_x.py") in gate.frozen_map("/r", home=None)


def test_frozen_map_continues_past_a_frozen_hook_off_project_to_the_next(monkeypatch):
    monkeypatch.setattr(gate, "_override_allows", lambda *a, **k: False)
    off = {"current_phase": "build", "frozen_test_files": ["tests/test_off.py"]}
    on = {"current_phase": "build", "frozen_test_files": ["tests/test_on.py"]}
    monkeypatch.setattr(gate, "resolve_build_contexts", lambda cwd, home=None: [
        (off, ["/r"], {"frozen_hook": "off"}),
        (on, ["/r"], {}),
    ])
    result = gate.frozen_map("/r", home=None)
    assert gate.canon("/r/tests/test_on.py") in result
    assert gate.canon("/r/tests/test_off.py") not in result
