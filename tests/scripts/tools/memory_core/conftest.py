"""Fixture tree for the memory-core tests: one registered project, like the registry-sync tree, plus
the auto-memory subtree under ``~/.hercules/memory/<slug>/`` that memory_core owns.

Each test starts from a registered project and reaches the tool exactly as a host would: by path,
with an explicit ``home`` (never the developer's own ``~/.hercules``).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.scripts.tools.tool_harness import ToolHome, invoke, load_tool, write_hercules_home

main = load_tool("memory_core")

SLUG = "proj"


def build_home(tmp_path: Path, *, slug: str = SLUG) -> ToolHome:
    project = tmp_path / "code"
    project.mkdir(parents=True, exist_ok=True)
    docs = tmp_path / "docs-repo"
    docs.mkdir(parents=True, exist_ok=True)
    return write_hercules_home(tmp_path, slug=slug, project=project, docs=docs,
                               sessions={}, active_session=None)


def run(fx: ToolHome, *argv: str):
    return invoke(main, fx.home, argv)


def capture(fx: ToolHome, kind: str, statement: str, **kw):
    argv = ["capture", "--cwd", str(fx.project), "--kind", kind, "--statement", statement]
    for key, value in kw.items():
        flag = "--" + key.replace("_", "-")
        argv += ([flag, str(value)] if not isinstance(value, bool) else ([flag] if value else []))
    return run(fx, *argv)


def select(fx: ToolHome, **kw):
    argv = ["select", "--cwd", str(fx.project)]
    for key, value in kw.items():
        flag = "--" + key.replace("_", "-")
        argv += ([flag, str(value)] if not isinstance(value, bool) else ([flag] if value else []))
    return run(fx, *argv)


@pytest.fixture
def fx(tmp_path: Path) -> ToolHome:
    return build_home(tmp_path)
