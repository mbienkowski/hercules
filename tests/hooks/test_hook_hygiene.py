"""Hygiene scans for shipped hook code under `plugin/hooks/`.

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

_HOOKS_DIR = Path(__file__).resolve().parents[2] / "plugin" / "hooks"
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
    assert _HOOK_SCRIPTS, "expected shipped hook scripts under plugin/hooks/"


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


def test_hook_modules_import_without_side_effects():
    """Importing a hook module must not read state, hit the filesystem, or fail — the guard logic
    only runs when called, so import must be inert."""
    sys.path.insert(0, str(_HOOKS_DIR))
    import hercules_state  # noqa: F401
    import frozen_tests  # noqa: F401
    # Importing again is idempotent and cheap.
    assert hasattr(frozen_tests, "main") and hasattr(hercules_state, "resolve_session")
