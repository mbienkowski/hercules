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
# Recursive: tools are grouped into a directory per feature, so a flat glob would
# silently stop scanning the moment one moved into a group.
_TOOL_SCRIPTS = sorted(p for p in _TOOLS_DIR.rglob("*.py") if "__pycache__" not in p.parts)
_NAME = {p: p.relative_to(_TOOLS_DIR).as_posix() for p in _TOOL_SCRIPTS}

# DECLARATIONS, not permissions: a syntax scan cannot know which trees a program writes to.
# `git_subcommands` is per tool, never shared: the verbs a tool needs are part of what it is, and one
# pooled list would hand every future tool the most dangerous verb any existing one required.
_TOOLS = {
    "project_reset.py": {"writes": True, "fails": "closed", "shells_to_git": False},
    "state_patch.py": {"writes": True, "fails": "closed", "shells_to_git": False},
    "retire_spec.py": {"writes": True, "fails": "closed", "shells_to_git": True,
                       "git_subcommands": {"ls-files", "rm"}},
    "registry_sync.py": {"writes": True, "fails": "closed", "shells_to_git": False},
    "code_of_conduct/coc_gate.py": {"writes": False, "fails": "closed",
                                    "shells_to_git": False},
    "code_of_conduct/coc_lint.py": {"writes": False, "fails": "closed", "shells_to_git": True,
                                   "git_subcommands": {"ls-files", "ls-tree"}},
    "code_of_conduct/coc_scan.py": {"writes": False, "fails": "closed", "shells_to_git": True,
                                   "git_subcommands": {"ls-files", "ls-tree", "log", "tag",
                                                       "rev-parse"}},
}


def test_the_capability_table_covers_every_shipped_tool():
    """A tool with no entry would be scanned against nothing and pass silently."""
    assert set(_NAME.values()) == set(_TOOLS)


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


@pytest.mark.parametrize("script", _TOOL_SCRIPTS, ids=lambda p: p.relative_to(_TOOLS_DIR).as_posix())
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


@pytest.mark.parametrize("script", _TOOL_SCRIPTS, ids=lambda p: p.relative_to(_TOOLS_DIR).as_posix())
def test_a_shipped_tool_opens_no_network_channel(script: Path):
    """The plugin tells people it talks to nothing, wherever that claim is printed."""
    roots = set(_imported_roots(ast.parse(script.read_text())))
    assert not (roots & _NETWORK_MODULES), f"{script.name} imports a network module"


@pytest.mark.parametrize("script", _TOOL_SCRIPTS, ids=lambda p: p.relative_to(_TOOLS_DIR).as_posix())
def test_a_tool_that_deletes_declares_that_it_fails_closed(script: Path):
    """A tool permitted to write must resolve every unclassified error by doing nothing."""
    declared = _TOOLS[_NAME[script]]
    if declared["writes"]:
        assert declared["fails"] == "closed"


@pytest.mark.parametrize("script", _TOOL_SCRIPTS, ids=lambda p: p.relative_to(_TOOLS_DIR).as_posix())
def test_a_tool_declared_read_only_performs_no_write(script: Path):
    """Write-capable tools are contained by their refusal rules instead."""
    if _TOOLS[_NAME[script]]["writes"]:
        pytest.skip(f"{script.name} declares writes; containment is proven by its refusal tests")
    source = script.read_text()
    assert "shutil" not in source
    assert not any(a in source for a in ("write_text", "write_bytes", "os.replace", "unlink"))


@pytest.mark.parametrize("script", _TOOL_SCRIPTS, ids=lambda p: p.relative_to(_TOOLS_DIR).as_posix())
def test_a_shipped_tool_never_invokes_version_control(script: Path):
    """The record is the tool's business; a person's history is not, and git could rewrite work the
    tool was never asked to touch. The one declared exception is scoped by the test below."""
    if _TOOLS[_NAME[script]]["shells_to_git"]:
        pytest.skip(f"{script.name} declares shells_to_git; scope is proven by "
                    "test_a_git_capable_tool_never_runs_an_uncontained_git_subcommand")
    source = script.read_text()
    roots = set(_imported_roots(ast.parse(source)))
    assert "subprocess" not in roots, f"{script.name} imports subprocess"
    # Whole word only: "legitimate" and "digit" are not invocations of git.
    calls = [line for line in source.splitlines()
             if re.search(r"\bgit\b", line) and not line.lstrip().startswith(("#", '"', "'"))]
    assert not calls, f"{script.name} mentions git in executable code: {calls}"


def _starts_with_git(node) -> bool:
    return (isinstance(node, ast.List) and bool(node.elts)
            and isinstance(node.elts[0], ast.Constant) and node.elts[0].value == "git")


def _git_wrapper_names(tree) -> set:
    """Functions that assemble a `["git", …]` argv. Routing every invocation through one wrapper is
    the better shape — the hardening `-c` overrides are applied in a single place — so the scan
    understands it rather than pushing tools back to writing argv at each call site."""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if any(_starts_with_git(child) for child in ast.walk(node)):
                names.add(node.name)
    return names


def _git_argv_calls(source: str) -> list:
    """Every call that runs git: the argv written at the call site, or a call into the tool's own
    wrapper carrying the subcommand as a list."""
    tree = ast.parse(source)
    direct = [node for node in ast.walk(tree)
              if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
              and node.func.attr == "run" and node.args and _starts_with_git(node.args[0])]
    if direct:
        return direct
    wrappers = _git_wrapper_names(tree)
    return [node for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id in wrappers
            and any(isinstance(arg, ast.List) for arg in node.args)]


def _literal_subcommands(call) -> list:
    """The subcommand of one git argv: the FIRST non-flag literal, which is where git's own grammar
    puts the verb. Later literals are its arguments — `HEAD` to `ls-tree` names a ref, not a second
    command — and treating those as verbs would force refs into the allowlist, where a reader could
    no longer tell a granted capability from a positional argument."""
    argv = next((arg for arg in call.args if isinstance(arg, ast.List)), None)
    for element in (argv.elts if argv else []):
        if not (isinstance(element, ast.Constant) and isinstance(element.value, str)):
            continue  # a dynamic `-C <dir>` is no Constant, so it never masks the verb
        if element.value == "git" or element.value.startswith("-"):
            continue
        return [element.value]
    return []


@pytest.mark.parametrize("script", [p for p in _TOOL_SCRIPTS if _TOOLS[_NAME[p]]["shells_to_git"]],
                        ids=lambda p: p.relative_to(_TOOLS_DIR).as_posix())
def test_a_git_capable_tool_never_runs_an_uncontained_git_subcommand(script: Path):
    """Every git argv names only a subcommand THIS tool declared, and never `shell=True` — which
    would let an argument be reinterpreted by a shell."""
    allowed = _TOOLS[_NAME[script]].get("git_subcommands")
    assert allowed, f"{script.name} declares shells_to_git but no git_subcommands"
    source = script.read_text()
    argv_calls = _git_argv_calls(source)
    assert argv_calls, f"{script.name} declares shells_to_git but calls no git argv"
    # Checked over EVERY subprocess call in the file, not only the git ones: a tool that routes git
    # through a wrapper keeps its one `run(…)` somewhere else entirely, and a `shell=True` added
    # there would be invisible to a scan that only looked where the argv was written.
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr in ("run", "Popen", "call", "check_output"):
            assert not any(kw.arg == "shell" and getattr(kw.value, "value", False) is True
                           for kw in node.keywords), \
                f"{script.name} runs a subprocess with shell=True"
    for call in argv_calls:
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
