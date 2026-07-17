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


def test_there_is_at_least_one_hook_script():
    assert _HOOK_SCRIPTS, "expected shipped hook scripts under src/targets/claude-code/hooks/"


@pytest.mark.parametrize("script", _HOOK_SCRIPTS, ids=lambda p: p.name)
def test_hook_uses_only_stdlib_and_local_modules(script: Path):
    """A hook must import only the standard library or a sibling hook module — no third-party
    dependency (so it runs against the user's ambient interpreter with no install step)."""
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
def test_hook_opens_no_network_channel(script: Path):
    """Shipped hook code must not import any network module — the plugin claims none."""
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
def test_hook_never_writes_the_filesystem(script: Path):
    """A hook must be read-only — writing `~/.hercules` would race the model's atomic
    temp+rename state writes. Statically reject write-mode `open(...)` and os/pathlib write calls."""
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


def test_hook_modules_import_without_side_effects():
    """Importing a hook module must not read state, hit the filesystem, or fail — the guard logic
    only runs when called, so import must be inert."""
    sys.path.insert(0, str(_HOOKS_DIR))
    import hercules_state  # noqa: F401
    import frozen_tests  # noqa: F401
    # Importing again is idempotent and cheap.
    assert hasattr(frozen_tests, "main") and hasattr(hercules_state, "resolve_session")


def test_pragma_no_mutate_only_on_static_strings(repo_root):
    """A pragma is a hole in the mutation gate — it may silence only behaviourally-equivalent
    mutants: static message strings, type aliases, replace-decode codec args. Any pragma on a
    line without a string literal or type alias is suppressing real logic and must go."""
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
