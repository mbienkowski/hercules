"""Hygiene scans for every shipped hook script, plus the wiring that fires them: stdlib-only, no
network modules, no state-corrupting filesystem writes, and every mutating tool really watched by a
hook command resolving to a script that really ships."""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

import pytest

from tests.repo.hygiene_rules import NETWORK_MODULES as _NETWORK_MODULES
from tests.repo.hygiene_rules import top_level_import_roots as _top_level_imports

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SHARED_HOOKS = _REPO_ROOT / "src" / "scripts" / "hooks"
# Globbed, not listed, so a new hook script is picked up rather than silently skipped.
_HOOK_SCRIPTS = sorted(_SHARED_HOOKS.glob("*.py"))

# Sibling hook modules that are allowed to be imported by other hook scripts.
_LOCAL_MODULES = {p.stem for p in _HOOK_SCRIPTS}

_PLUGIN_ROOT = _REPO_ROOT / "dist" / "claude-code"

def test_the_hook_checks_below_would_fail_loudly_if_no_hooks_shipped():
    """An empty script list would report success without checking anything."""
    assert _HOOK_SCRIPTS, "expected shipped hook scripts under hooks/"

def test_a_shipped_hook_never_requires_installing_a_separate_package():
    """Standard library and sibling hooks only, so a user runs it immediately with no install step."""
    stdlib = getattr(sys, "stdlib_module_names", None)
    violations = {}
    for script in _HOOK_SCRIPTS:
        tree = ast.parse(script.read_text())
        bad = [mod for mod in _top_level_imports(tree)
               if mod not in _LOCAL_MODULES and stdlib is not None and mod not in stdlib]
        if bad:
            violations[script.name] = bad
    assert not violations, f"non-stdlib imports {violations}; hooks must be dependency-free"

def test_a_shipped_hook_cannot_open_a_network_connection():
    """Nothing can phone home or leak data."""
    violations = {}
    for script in _HOOK_SCRIPTS:
        tree = ast.parse(script.read_text())
        offenders = sorted(m for m in _top_level_imports(tree) if m in _NETWORK_MODULES)
        if offenders:
            violations[script.name] = offenders
    assert not violations, f"network module imports {violations}"

_WRITE_ATTRS = {
    "replace", "rename", "remove", "unlink", "mkdir", "makedirs", "rmdir", "removedirs",
    "write_text", "write_bytes", "symlink", "chmod", "truncate", "touch",
}

def _open_modes(call: ast.Call):
    """Yield the mode string of an `open(...)` call, positional or keyword."""
    if len(call.args) >= 2 and isinstance(call.args[1], ast.Constant):
        yield str(call.args[1].value)
    for kw in call.keywords:
        if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
            yield str(kw.value.value)

def test_a_shipped_hook_never_writes_hercules_state():
    """A direct write could corrupt ``~/.hercules`` by racing the model's own atomic writes, so the
    one sanctioned mutation goes through ``subprocess``, bounded by the test below."""
    violations = {}
    for script in _HOOK_SCRIPTS:
        text = script.read_text()
        tree = ast.parse(text)
        offenders = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func
                if isinstance(fn, ast.Name) and fn.id == "open":
                    for mode in _open_modes(node):
                        if any(c in mode for c in ("w", "a", "x", "+")):
                            offenders.append(f"open(mode={mode!r})")
                elif isinstance(fn, ast.Attribute) and fn.attr in _WRITE_ATTRS:
                    offenders.append(f"{fn.attr}()")
        if "import shutil" in text:
            offenders.append("import shutil")
        if offenders:
            violations[script.name] = offenders
    assert not violations, f"direct filesystem writes {violations}; hooks stay read-only over state"

def test_the_after_edit_backstop_is_bounded_honest_and_headless_only():
    """The ONE working-tree mutation any hook performs: path-bounded, headless-only, and claimed as a
    success only when git's return code says the file was actually restored."""
    gate = _SHARED_HOOKS / "hercules_gate.py"
    if not gate.is_file():
        pytest.skip("no gate adapter shipped")
    src = gate.read_text()
    assert '"checkout", "--"' in src, "the backstop must restore via a path-bounded `git checkout -- <file>`"
    assert "HERCULES_RUNTIME_MODE" in src, "the mutation must be gated to headless mode (IDE is advisory)"
    assert "returncode == 0" in src, "success must be claimed only when git actually restored the file"
    assert '"stash"' not in src, "the after-edit backstop must not run git stash (no false-recovery path)"
    for forbidden in ("reset --hard", "clean -", "rm -"):
        assert forbidden not in src, f"the after-edit backstop must not use `{forbidden}`"

def test_test_coverage_exemptions_cannot_be_used_to_hide_untested_logic():
    """A ``pragma: no mutate`` belongs on fixed text, a type declaration, or a documented equivalence
    — never on a line making a real decision."""
    for path in _SHARED_HOOKS.glob("*.py"):
        if path.name.startswith("test_"):
            continue
        for i, line in enumerate(path.read_text().splitlines(), 1):
            if "pragma: no mutate" in line:
                assert ('"' in line or "'" in line or "Callable" in line or "equivalent" in line), (
                    f"{path.name}:{i} pragma on a non-string line without a documented-"
                    "equivalence justification — write a killing test instead"
                )

@pytest.fixture(scope="module")
def hooks_json():
    return json.loads((_PLUGIN_ROOT / "hooks" / "hooks.json").read_text())

def test_the_frozen_tests_guard_is_wired_up_before_every_editing_tool(hooks_json):
    """Omitting one mutating tool lets a frozen test be altered right through it; the exec form means
    a Python-less machine does nothing rather than blocking every edit."""
    assert "PreToolUse" in hooks_json.get("hooks", {}), "hooks.json must declare a PreToolUse hook"
    matchers = " ".join(entry.get("matcher", "") for entry in hooks_json["hooks"]["PreToolUse"])
    for tool in ("Edit", "MultiEdit", "Write", "NotebookEdit"):
        assert re.search(rf"\b{tool}\b", matchers), f"the frozen-tests guard must match {tool}"

    guard = next(
        (h for entry in hooks_json["hooks"]["PreToolUse"] for h in entry.get("hooks", [])
         if any("frozen_tests.py" in a for a in h.get("args", []))),
        None,
    )
    assert guard, "the frozen-tests guard must be wired via exec form with the script in `args`"
    assert guard["command"] == "python3", \
        f"exec form must spawn python3 directly, not a shell string: {guard['command']!r}"
    assert isinstance(guard.get("args"), list) and guard["args"], \
        "exec form must carry a non-empty `args` list (shell form has none)"

def test_every_hook_points_to_a_script_that_actually_exists(hooks_json):
    """A hook pointing at a missing script fails silently, disabling the safety check it stands for."""
    for event in hooks_json["hooks"].values():
        for entry in event:
            for hook in entry.get("hooks", []):
                invocation = " ".join([hook.get("command", "")] + list(hook.get("args", [])))
                m = re.search(r"\$\{CLAUDE_PLUGIN_ROOT\}/(\S+?\.py)", invocation)
                assert m, f"hook must invoke a ${{CLAUDE_PLUGIN_ROOT}} script: {hook!r}"
                assert (_PLUGIN_ROOT / m.group(1)).is_file(), f"hook references a missing script: {m.group(1)}"
