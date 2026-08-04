"""Hygiene scans for every shipped tool — the `src/scripts/tools/` tree. Unlike the host-fired, fail-OPEN
hooks next door, a tool a command invokes deliberately fails CLOSED. Each tool declares its own
posture below, scanned against it — a file with no entry fails, no capability by being added quietly."""

from __future__ import annotations

import ast
import importlib.util
import re
import sys
from pathlib import Path

import pytest

from tests.repo.hygiene_rules import NETWORK_MODULES as _NETWORK_MODULES
from tests.repo.hygiene_rules import top_level_import_roots as _imported_roots

_TOOLS_DIR = Path(__file__).resolve().parents[3] / "src" / "scripts" / "tools"
_TOOL_SCRIPTS = sorted(_TOOLS_DIR.glob("*.py"))

# DECLARATIONS, not permissions: a syntax scan cannot know which trees a program writes to.
# `git_subcommands` is per tool, never shared: the verbs a tool needs are part of what it is, and one
# pooled list would hand every future tool the most dangerous verb any existing one required.
_TOOLS = {
    "project_reset.py": {"writes": True, "fails": "closed", "shells_to_git": False},
    "state_patch.py": {"writes": True, "fails": "closed", "shells_to_git": False},
    "retire_spec.py": {"writes": True, "fails": "closed", "shells_to_git": True,
                       "git_subcommands": {"ls-files", "rm"}},
    "registry_sync.py": {"writes": True, "fails": "closed", "shells_to_git": False},
    "coc_audit.py": {"writes": False, "fails": "closed", "shells_to_git": False},
}


def test_the_capability_table_covers_every_shipped_tool():
    """A tool with no entry would be scanned against nothing and pass silently."""
    assert {p.name for p in _TOOL_SCRIPTS} == set(_TOOLS)


def test_at_least_one_tool_ships():
    """A glob that quietly matched nothing would make every parametrised scan below vacuous."""
    assert _TOOL_SCRIPTS


def _needs_installing(root: str) -> bool:
    """Whether importing `root` pulls in an installed package, answered by where the module lives:
    `sys.stdlib_module_names` starts at 3.10, and CI runs this project's 3.9 floor."""
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
    """A consumer installs the plugin, not a dependency tree."""
    local = {p.stem for p in _TOOL_SCRIPTS}
    roots = set(_imported_roots(ast.parse(script.read_text())))
    outside = {r for r in roots if r not in local and _needs_installing(r)}
    assert not outside, f"{script.name} imports {sorted(outside)}, which a consumer would have to install"


def test_the_installed_package_check_can_actually_fail():
    """The house pattern degrades to a no-op on the 3.9 floor, so the replacement must still say no
    to `pytest` — exactly what a consumer must not need."""
    assert _needs_installing("pytest") is True
    assert _needs_installing("json") is False


@pytest.mark.parametrize("script", _TOOL_SCRIPTS, ids=lambda p: p.name)
def test_a_shipped_tool_opens_no_network_channel(script: Path):
    """The plugin tells people it talks to nothing, wherever that claim is printed."""
    roots = set(_imported_roots(ast.parse(script.read_text())))
    assert not (roots & _NETWORK_MODULES), f"{script.name} imports a network module"


@pytest.mark.parametrize("script", _TOOL_SCRIPTS, ids=lambda p: p.name)
def test_a_tool_that_deletes_declares_that_it_fails_closed(script: Path):
    """A tool permitted to write must resolve every unclassified error by doing nothing."""
    declared = _TOOLS[script.name]
    if declared["writes"]:
        assert declared["fails"] == "closed"


@pytest.mark.parametrize("script", _TOOL_SCRIPTS, ids=lambda p: p.name)
def test_a_tool_declared_read_only_performs_no_write(script: Path):
    """Write-capable tools are contained by their refusal rules instead."""
    if _TOOLS[script.name]["writes"]:
        pytest.skip(f"{script.name} declares writes; containment is proven by its refusal tests")
    source = script.read_text()
    assert "shutil" not in source
    assert not any(a in source for a in ("write_text", "write_bytes", "os.replace", "unlink"))


@pytest.mark.parametrize("script", _TOOL_SCRIPTS, ids=lambda p: p.name)
def test_a_shipped_tool_never_invokes_version_control(script: Path):
    """The record is the tool's business; a person's history is not, and git could rewrite work the
    tool was never asked to touch. The one declared exception is scoped by the test below."""
    if _TOOLS[script.name]["shells_to_git"]:
        pytest.skip(f"{script.name} declares shells_to_git; scope is proven by "
                    "test_a_git_capable_tool_never_runs_an_uncontained_git_subcommand")
    source = script.read_text()
    roots = set(_imported_roots(ast.parse(source)))
    assert "subprocess" not in roots, f"{script.name} imports subprocess"
    # Whole word only: "legitimate" and "digit" are not invocations of git.
    calls = [line for line in source.splitlines()
             if re.search(r"\bgit\b", line) and not line.lstrip().startswith(("#", '"', "'"))]
    assert not calls, f"{script.name} mentions git in executable code: {calls}"


def _git_argv_calls(source: str) -> list:
    """Every `…run(["git", …])` in the source, as AST call nodes."""
    return [
        node for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and node.func.attr == "run" and node.args and isinstance(node.args[0], ast.List)
        and node.args[0].elts and isinstance(node.args[0].elts[0], ast.Constant)
        and node.args[0].elts[0].value == "git"
    ]


def _literal_subcommands(call) -> list:
    """The non-flag string literals of one git argv; a dynamic `-C <dir>` is no Constant."""
    return [elt.value for elt in call.args[0].elts[1:]
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
            and not elt.value.startswith("-")]


@pytest.mark.parametrize("script", [p for p in _TOOL_SCRIPTS if _TOOLS[p.name]["shells_to_git"]],
                        ids=lambda p: p.name)
def test_a_git_capable_tool_never_runs_an_uncontained_git_subcommand(script: Path):
    """Every git argv names only a subcommand THIS tool declared, and never `shell=True` — which
    would let an argument be reinterpreted by a shell."""
    allowed = _TOOLS[script.name].get("git_subcommands")
    assert allowed, f"{script.name} declares shells_to_git but no git_subcommands"
    argv_calls = _git_argv_calls(script.read_text())
    assert argv_calls, f"{script.name} declares shells_to_git but calls no git argv"
    for call in argv_calls:
        assert not any(kw.arg == "shell" for kw in call.keywords), \
            f"{script.name} runs git with shell=True"
        subcommands = _literal_subcommands(call)
        assert set(subcommands) <= allowed, \
            f"{script.name} runs a git argv with an unreviewed literal: {subcommands}"
        assert [s for s in subcommands if s in allowed], \
            f"{script.name} runs a git argv naming no allowed subcommand: {subcommands}"


def test_no_tool_is_granted_a_verb_another_tool_needed():
    """Guard the guard. The allowlist was once one shared set containing `rm`; any tool added later
    inherited a delete verb it never asked for. Declarations must stay disjointly owned."""
    declared = {name: entry.get("git_subcommands") or set()
                for name, entry in _TOOLS.items() if entry["shells_to_git"]}
    assert declared, "no git-capable tool ships; this guard would be vacuous"
    for name, allowed in declared.items():
        source = (_TOOLS_DIR / name).read_text()
        used = {s for call in _git_argv_calls(source) for s in _literal_subcommands(call)}
        assert allowed <= used, \
            f"{name} declares {sorted(allowed - used)}, which it never runs — a verb granted in advance"


def test_the_git_subcommand_scan_actually_refuses_an_undeclared_verb():
    """The scan above passes trivially if its comparison is inverted or its argv finder matches
    nothing, so it is run here against a source that must fail it."""
    hostile = 'subprocess.run(["git", "-C", root, "push", "--force"])'
    subcommands = {s for call in _git_argv_calls(hostile) for s in _literal_subcommands(call)}
    assert "push" in subcommands
    assert not subcommands <= {"ls-files", "rm"}
