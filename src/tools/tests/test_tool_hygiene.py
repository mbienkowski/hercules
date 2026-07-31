"""Hygiene scans for every shipped tool — the `src/tools/` tree.

Tools are executable Python the plugin ships and a command invokes deliberately, unlike the hooks
next door, which the host fires on an event. The two domains have opposite safe defaults: a hook
fails OPEN, because allowing an edit is harmless; a tool that deletes fails CLOSED, because doing
nothing is harmless. Keeping them apart is what lets `src/hooks/`'s blanket write-ban stay exactly
as strict as it is.

Each tool declares its own posture below and the scans are read against that declaration. A file in
the tree with no entry fails — nothing acquires a capability by being added quietly.
"""

from __future__ import annotations

import ast
import importlib.util
import re
import sys
from pathlib import Path

import pytest

_TOOLS_DIR = Path(__file__).resolve().parents[1]
_TOOL_SCRIPTS = sorted(_TOOLS_DIR.glob("*.py"))

# Modules that would open a network channel — banned in shipped tool code, as in shipped hook code.
_NETWORK_MODULES = {
    "requests", "urllib", "urllib2", "http", "httplib", "socket", "ssl",
    "ftplib", "telnetlib", "smtplib", "asyncio", "aiohttp", "websocket", "urllib3",
}

# The capability table. `writes` says the tool mutates the filesystem; `fails` says which way it
# resolves an error it cannot classify.
#
# `writes: True` is a DECLARATION, not a bounded permission. A syntax scan cannot know WHICH trees a
# program writes to, because this one computes its targets per invocation from a record it reads at
# run time. Containment is proven by test_refusals.py — one test per safety rule, each asserting the
# target survived — and by nothing in this file. Saying otherwise here would imply an enforcement
# that does not exist.
_TOOLS = {
    "project_reset.py": {"writes": True, "fails": "closed"},
}


def _imported_roots(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            yield node.module.split(".")[0]


def test_the_capability_table_covers_every_shipped_tool():
    """The guard's own precondition. A tool added to the tree without an entry here would be scanned
    against nothing and pass silently, which is worse than having no scan at all."""
    assert {p.name for p in _TOOL_SCRIPTS} == set(_TOOLS)


def test_at_least_one_tool_ships():
    """A glob that quietly matched nothing would make every parametrised scan below vacuous."""
    assert _TOOL_SCRIPTS


def _needs_installing(root: str) -> bool:
    """Whether importing `root` would pull in an installed package rather than the standard library.

    Answered by where the module actually lives, not by a name list. `sys.stdlib_module_names` exists
    only from Python 3.10, while this project supports 3.9 (`requires-python = ">=3.9"`) and CI runs
    that floor — so a name-list check silently becomes a no-op on exactly the version that matters.
    """
    if root in sys.builtin_module_names:
        return False
    try:
        spec = importlib.util.find_spec(root)
    except (ImportError, ValueError):
        return True
    if spec is None:
        return True
    origin = spec.origin or ""
    return "site-packages" in origin or "dist-packages" in origin


@pytest.mark.parametrize("script", _TOOL_SCRIPTS, ids=lambda p: p.name)
def test_a_shipped_tool_needs_no_installed_package(script: Path):
    """A consumer installs the plugin, not a dependency tree. Every import resolves against the
    standard library or a sibling in this same directory."""
    local = {p.stem for p in _TOOL_SCRIPTS}
    roots = set(_imported_roots(ast.parse(script.read_text())))
    outside = {r for r in roots if r not in local and _needs_installing(r)}
    assert not outside, f"{script.name} imports {sorted(outside)}, which a consumer would have to install"


def test_the_installed_package_check_can_actually_fail():
    """The guard's own precondition. On Python 3.9 the house pattern for this check
    (`getattr(sys, "stdlib_module_names", None)` and skip when absent) degrades to a no-op, so the
    version CI runs is the one where it proves nothing. This asserts the replacement still says no
    to something — `pytest` is installed, and is exactly what a consumer must not need."""
    assert _needs_installing("pytest") is True
    assert _needs_installing("json") is False


@pytest.mark.parametrize("script", _TOOL_SCRIPTS, ids=lambda p: p.name)
def test_a_shipped_tool_opens_no_network_channel(script: Path):
    """The plugin tells people it talks to nothing. A tool that reached the network would make that
    claim false wherever it is printed."""
    roots = set(_imported_roots(ast.parse(script.read_text())))
    assert not (roots & _NETWORK_MODULES), f"{script.name} imports a network module"


@pytest.mark.parametrize("script", _TOOL_SCRIPTS, ids=lambda p: p.name)
def test_a_tool_that_deletes_declares_that_it_fails_closed(script: Path):
    """The two properties travel together. A tool permitted to write must resolve every unclassified
    error by doing nothing, so the declaration pairs them rather than allowing one without the other."""
    declared = _TOOLS[script.name]
    if declared["writes"]:
        assert declared["fails"] == "closed"


@pytest.mark.parametrize("script", _TOOL_SCRIPTS, ids=lambda p: p.name)
def test_a_tool_declared_read_only_performs_no_write(script: Path):
    """Only the read-only declarations are scanned for writes — the write-capable ones are contained
    by their refusal rules instead. This keeps the scan honest about what it can prove."""
    if _TOOLS[script.name]["writes"]:
        pytest.skip(f"{script.name} declares writes; containment is proven by its refusal tests")
    source = script.read_text()
    assert "shutil" not in source
    assert not any(a in source for a in ("write_text", "write_bytes", "os.replace", "unlink"))


@pytest.mark.parametrize("script", _TOOL_SCRIPTS, ids=lambda p: p.name)
def test_a_shipped_tool_never_invokes_version_control(script: Path):
    """The record is the tool's business; a person's history is not. Shelling out to git is the one
    route by which a mistake here could rewrite work the tool was never asked to touch."""
    source = script.read_text()
    roots = set(_imported_roots(ast.parse(source)))
    assert "subprocess" not in roots, f"{script.name} imports subprocess"
    # Whole word only — "legitimate" and "digit" are not invocations of git.
    calls = [line for line in source.splitlines()
             if re.search(r"\bgit\b", line) and not line.lstrip().startswith(("#", '"', "'"))]
    assert not calls, f"{script.name} mentions git in executable code: {calls}"
