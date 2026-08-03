"""Fixture tree for the project-reset tool tests: two features at different stages plus a documents
folder shaped like a real one. The shipped feature carries `build_progress` prose, so a test can
prove a reply names a feature without ever showing what is stored inside it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.scripts.tools.tool_harness import ToolHome, invoke, load_tool, write_hercules_home

main = load_tool("project_reset")

SLUG = "proj"
FEATURES = {"2026-01-02-alpha": "shipped", "2026-01-03-beta": "discover"}
ACTIVE = "2026-01-03-beta"


def _write_docs(docs: Path, features) -> None:
    """A documents folder shaped like a real one: a folder per feature, an index, a lessons file."""
    docs.mkdir(parents=True, exist_ok=True)
    for key in features:
        (docs / key).mkdir(exist_ok=True)
        (docs / key / f"{key}-business-requirements.md").write_text(f"# {key}\n")
    (docs / "INDEX.md").write_text("# Session index\n")
    (docs / "learnings.md").write_text("# Learnings\n")


def _session(stage: str) -> dict:
    """One feature record; only a shipped feature carries `build_progress` prose."""
    session = {"tier": "low", "current_phase": stage, "last_updated": "2026-01-02T00:00:00Z"}
    if stage == "shipped":
        session["build_progress"] = [{"spec": "spec-01.md", "decisions": "a private narrative"}]
        session["shipped_commit"] = "abc1234"
    return session


def build_home(tmp_path: Path, *, slug: str = SLUG, docs_inside: bool = False,
               features=None, docs_root=None, extra_projects=None) -> ToolHome:
    """A registry, state tree, project and documents. `docs_inside` puts documents inside the code
    repository — the arrangement that needs a warning."""
    features = FEATURES if features is None else features
    project = tmp_path / "code"
    project.mkdir(parents=True, exist_ok=True)
    docs = project / "docs" if docs_inside else tmp_path / "docs-repo"
    if docs_root is None:
        _write_docs(docs, features)

    return write_hercules_home(
        tmp_path, slug=slug, project=project, docs=docs, docs_root=docs_root,
        sessions={name: _session(stage) for name, stage in features.items()},
        active_session=ACTIVE, extra_projects=extra_projects,
    )


def run(fx: ToolHome, *argv: str, cwd=None):
    """`cwd` defaults to the project directory — where a real invocation runs from."""
    return invoke(main, fx.home, argv, cwd=str(cwd or fx.project))


def plan(fx: ToolHome, *argv: str, cwd=None):
    """`plan` with the contract version already supplied — the shape every real call takes."""
    return run(fx, "plan", "--contract", "1", *argv, cwd=cwd)


def apply(fx: ToolHome, *argv: str, cwd=None):
    """`apply` with the contract version and confirmation already supplied."""
    return run(fx, "apply", "--contract", "1", "--confirm", *argv, cwd=cwd)


@pytest.fixture
def fx(tmp_path: Path) -> ToolHome:
    """The default `build_home()`, so each test states only what makes it different."""
    return build_home(tmp_path)


def tree_paths(root: Path):
    """Every path under `root`, relative and sorted: the before/after a deletion test compares."""
    return sorted(str(p.relative_to(root)) for p in root.rglob("*"))
