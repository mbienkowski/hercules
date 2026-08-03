"""Fixture tree for the state-patch tool tests: two sessions, one the target of every patch and one
that must never move. The sibling carries a private-looking field, so a test can prove a reply never
echoes a session it was not asked about.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.scripts.tools.tool_harness import ToolHome, invoke, load_tool, write_hercules_home

main = load_tool("state_patch")

SLUG = "proj"
TARGET_SESSION = "2026-01-03-beta"
SIBLING_SESSION = "2026-01-02-alpha"
SESSIONS = {
    SIBLING_SESSION: {"tier": "low", "current_phase": "shipped", "handoff_note": "a private note"},
    TARGET_SESSION: {"tier": "low", "current_phase": "build", "current_spec_round": 1},
}


class Fixture(ToolHome):
    """Adds the default session every state-patch test targets."""

    def session(self, session_id: str = TARGET_SESSION) -> dict:
        return super().session(session_id)


def build_home(tmp_path: Path, *, slug: str = SLUG, sessions=None, extra_projects=None,
               repositories=None) -> Fixture:
    """Write a registry and state tree under `tmp_path/.hercules`, plus the project directory."""
    project = tmp_path / "code"
    project.mkdir(parents=True, exist_ok=True)

    built = write_hercules_home(
        tmp_path, slug=slug, project=project, docs=tmp_path / "docs",
        sessions=SESSIONS if sessions is None else sessions,
        active_session=TARGET_SESSION,
        repositories=repositories, extra_projects=extra_projects,
    )
    return Fixture(built.home, built.project, built.slug, built.docs)


def run(fx: Fixture, *argv: str):
    return invoke(main, fx.home, argv)


def plan(fx: Fixture, *argv: str, session=TARGET_SESSION):
    """`plan` against the default project and session — the shape every real call takes."""
    return run(fx, "plan", "--project-slug", fx.slug, "--session-id", session, *argv)


def apply(fx: Fixture, *argv: str, session=TARGET_SESSION, confirm=True):
    """`apply` against the default project and session, confirmed unless a test wants the refusal."""
    extra = ("--confirm",) if confirm else ()
    return run(fx, "apply", "--project-slug", fx.slug, "--session-id", session, *extra, *argv)


@pytest.fixture
def fx(tmp_path: Path) -> Fixture:
    """The default `build_home()`, so each test states only what makes it different."""
    return build_home(tmp_path)
