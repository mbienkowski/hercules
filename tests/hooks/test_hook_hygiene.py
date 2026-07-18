"""Hygiene scans for shipped hook code under `src/targets/claude-code/hooks/`.

The plugin claims "no external network channel" and "no credentials"; hooks are the only
executable Python it ships, so they must be scanned (the markdown-only network scan in
`test_plugin_integrity` does not cover `.py`). These tests enforce: stdlib-only (portability —
no third-party install step), no network modules, and no import-time side effects.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

_HOOKS_DIR = Path(__file__).resolve().parents[2] / "src" / "targets" / "claude-code" / "hooks"
_HOOK_SCRIPTS = sorted(_HOOKS_DIR.glob("*.py"))

# Modules that would open a network channel — banned in shipped hook code.
_NETWORK_MODULES = {
    "requests", "urllib", "urllib2", "http", "httplib", "socket", "ssl",
    "ftplib", "telnetlib", "smtplib", "asyncio", "aiohttp", "websocket", "urllib3",
}
# Sibling hook modules that are allowed to be imported by other hook scripts.
_LOCAL_MODULES = {p.stem for p in _HOOK_SCRIPTS}


def _top_level_imports(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                yield node.module.split(".")[0]


def test_the_hook_checks_below_would_fail_loudly_if_no_hooks_shipped():
    """If the plugin shipped zero hook scripts, every check further down this file would run
    against an empty list and silently report success without having checked anything. This
    guarantees there is at least one real hook script to scan, so the safety checks can't be
    quietly disabled just by deleting all the hooks."""
    assert _HOOK_SCRIPTS, "expected shipped hook scripts under src/targets/claude-code/hooks/"


@pytest.mark.parametrize("script", _HOOK_SCRIPTS, ids=lambda p: p.name)
def test_a_shipped_hook_never_requires_installing_a_separate_package(script: Path):
    """Every hook that ships with the plugin must run using only what already comes with Python,
    plus its own sibling hook files - it must never depend on a separately installed package.
    This guarantees a user can run a Hercules hook immediately with no install step; a hook that
    quietly gained an extra dependency would otherwise fail on machines that don't have it."""
    tree = ast.parse(script.read_text())
    stdlib = getattr(sys, "stdlib_module_names", None)
    violations = []
    for mod in _top_level_imports(tree):
        if mod in _LOCAL_MODULES:
            continue
        if stdlib is not None and mod not in stdlib:
            violations.append(mod)
    assert not violations, (
        f"{script.name} imports non-stdlib modules {violations}; hooks must be dependency-free"
    )


@pytest.mark.parametrize("script", _HOOK_SCRIPTS, ids=lambda p: p.name)
def test_a_shipped_hook_cannot_open_a_network_connection(script: Path):
    """The plugin promises it has no way to send or receive data over the network. This checks
    that none of the shipped hook scripts import any networking module, so that promise can't be
    silently broken by a hook that phones home or leaks data off the user's machine."""
    tree = ast.parse(script.read_text())
    offenders = sorted(m for m in _top_level_imports(tree) if m in _NETWORK_MODULES)
    assert not offenders, f"{script.name} imports network module(s) {offenders}"


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


@pytest.mark.parametrize("script", _HOOK_SCRIPTS, ids=lambda p: p.name)
def test_a_shipped_hook_cannot_create_edit_or_delete_any_file(script: Path):
    """A hook is only allowed to look at things, never change them. If a hook wrote to
    Hercules's saved state at the same moment the main process is saving it, that save could be
    corrupted, so this checks every shipped hook script for any file-writing operation and fails
    if one is found."""
    tree = ast.parse(script.read_text())
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
    if "import shutil" in script.read_text():
        offenders.append("import shutil")
    assert not offenders, f"{script.name} performs filesystem writes {offenders}; hooks are read-only"


def test_test_coverage_exemptions_cannot_be_used_to_hide_untested_logic(repo_root):
    """A line of hook or metrics code can be marked as exempt from the automated check that
    verifies tests actually catch bugs. That exemption is only legitimate on lines that are just
    fixed text, a type declaration, or a documented equivalent-behavior case - never on a line
    that makes a real decision. This guards against someone quietly turning off test coverage on
    code that genuinely needs it, letting a bug slip through unnoticed."""
    import itertools
    scoped = itertools.chain(
        (repo_root / "src" / "targets" / "claude-code" / "hooks").glob("*.py"),
        (repo_root / "tests" / "metrics").glob("*.py"),
    )
    for path in scoped:
        if path.name.startswith("test_"):
            continue
        for i, line in enumerate(path.read_text().splitlines(), 1):
            if "pragma: no mutate" in line:
                assert ('"' in line or "'" in line or "Callable" in line
                        or "equivalent" in line), (
                    f"{path.name}:{i} pragma on a non-string line without a documented-"
                    "equivalence justification — write a killing test instead"
                )
