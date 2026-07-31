"""Hygiene scans for every shipped hook script — the shared `hooks/*.py` tree.

Hooks are the only executable Python the plugin ships, and it claims "no external network channel"
and "no credentials". All enforcement code is authored ONCE in `hooks/` and byte-copied to every
ecosystem, so scanning that tree covers every shipped hook. Enforced here: stdlib-only (so a
consumer carries no install step), no network modules, and no state-corrupting filesystem writes.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

_SHARED_HOOKS = Path(__file__).resolve().parents[1]
# ALL shipped hook code lives in the one shared tree — a new hook script added there is picked up
# automatically, so the scans below can never silently skip one.
_HOOK_SCRIPTS = sorted(_SHARED_HOOKS.glob("*.py"))

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
    """Every check below scans a list of hook scripts, so an empty list would report success without
    checking anything. At least one real hook script must exist for those checks to mean something."""
    assert _HOOK_SCRIPTS, "expected shipped hook scripts under hooks/"


@pytest.mark.parametrize("script", _HOOK_SCRIPTS, ids=lambda p: p.name)
def test_a_shipped_hook_never_requires_installing_a_separate_package(script: Path):
    """A shipped hook may import only the Python standard library and its own sibling hook files, so
    a user can run it immediately with no install step and on any machine with Python."""
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
    """The plugin promises it cannot send or receive data over the network: no shipped hook script
    imports a networking module, so nothing can phone home or leak data off the user's machine."""
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
def test_a_shipped_hook_never_writes_hercules_state(script: Path):
    """No hook performs a DIRECT filesystem write — ``open`` for write/append, an ``os``/``Path`` write
    attribute, or ``shutil`` — because such a write could corrupt Hercules's saved state under
    ``~/.hercules`` by racing the model's atomic writes. The one sanctioned working-tree mutation, the
    ``git checkout`` restore backstop, goes through ``subprocess`` and is bounded by
    ``test_the_after_edit_backstop_is_bounded_honest_and_headless_only``."""
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
    assert not offenders, f"{script.name} performs a direct filesystem write {offenders}; hooks stay read-only over state"


def test_the_after_edit_backstop_is_bounded_honest_and_headless_only():
    """The after-edit hook is notification-only, and its restore backstop is the ONE working-tree
    mutation any hook performs. It stays bounded three ways: a path-bounded ``git checkout -- <file>``
    and never a broad or destructive form; headless mode only, so an interactive IDE (integrated
    development environment) advises rather than mutates the user's tree; and success claimed only when
    git's return code says the file was actually restored. Vacuous if no such hook ships."""
    gate = _SHARED_HOOKS / "hercules_gate.py"
    if not gate.is_file():
        pytest.skip("no gate adapter shipped")
    src = gate.read_text()
    assert '"checkout", "--"' in src, "the backstop must restore via a path-bounded `git checkout -- <file>`"
    assert "HERCULES_RUNTIME_MODE" in src, "the mutation must be gated to headless mode (IDE is advisory)"
    assert "returncode == 0" in src, "success must be claimed only when git actually restored the file"
    # No destructive or broad working-tree operations, and no git-stash command — the backstop leaves
    # the stash stack alone. `'"stash"'` targets the subprocess argument token, not the write-hint regex
    # word of the same spelling.
    assert '"stash"' not in src, "the after-edit backstop must not run git stash (no false-recovery path)"
    for forbidden in ("reset --hard", "clean -", "rm -"):
        assert forbidden not in src, f"the after-edit backstop must not use `{forbidden}`"


def test_test_coverage_exemptions_cannot_be_used_to_hide_untested_logic():
    """A line of hook code can be marked exempt from the mutation check that verifies tests actually
    catch bugs. That exemption is legitimate only on a line that is fixed text, a type declaration, or a
    documented equivalent-behavior case — never on a line that makes a real decision. Scoped to
    `hooks/`, the shipped enforcement code a mutation campaign reads hardest."""
    for path in _SHARED_HOOKS.glob("*.py"):
        if path.name.startswith("test_"):
            continue
        for i, line in enumerate(path.read_text().splitlines(), 1):
            if "pragma: no mutate" in line:
                assert ('"' in line or "'" in line or "Callable" in line
                        or "equivalent" in line), (
                    f"{path.name}:{i} pragma on a non-string line without a documented-"
                    "equivalence justification — write a killing test instead"
                )
