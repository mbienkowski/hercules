"""Fixture tree for the registry-sync tool tests: one registered project with a code directory, a
separate docs directory, and a state file — the shape every resolve/repair test starts from.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.scripts.tools.tool_harness import ToolHome, invoke, load_tool, write_hercules_home

main = load_tool("registry_sync")

SLUG = "proj"


def build_home(tmp_path: Path, *, slug: str = SLUG, repositories=None,
               write_config: bool = True) -> ToolHome:
    """One registered project: a code directory, a separate docs directory, an optional cross-repo
    `repositories` entry, and its state file."""
    project = tmp_path / "code"
    project.mkdir(parents=True, exist_ok=True)
    docs = tmp_path / "docs-repo"
    docs.mkdir(parents=True, exist_ok=True)

    return write_hercules_home(
        tmp_path, slug=slug, project=project, docs=docs,
        sessions={}, active_session=None,
        repositories=repositories, write_config=write_config,
    )


def run(fx: ToolHome, *argv: str):
    return invoke(main, fx.home, argv)


def resolve(fx: ToolHome, cwd):
    return run(fx, "resolve", "--cwd", str(cwd))


def repair_plan(fx: ToolHome):
    return run(fx, "repair", "plan")


def repair_apply(fx: ToolHome, confirm: bool = True):
    extra = ("--confirm",) if confirm else ()
    return run(fx, "repair", "apply", *extra)


@pytest.fixture
def fx(tmp_path: Path) -> ToolHome:
    """The default `build_home()`, so each test states only what makes it different."""
    return build_home(tmp_path)
