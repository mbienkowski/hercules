"""Fixture tree for the retire-spec tool tests: a project carrying a frozen test, a docs directory
carrying the spec, and a session mid-build naming both. The spec sits in a real throwaway git
repository by default, so the deletion tests prove the `git rm` path rather than only the unlink one.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest

from tests.scripts.tools.tool_harness import ToolHome, invoke, load_tool, write_hercules_home

main = load_tool("retire_spec")

SLUG = "proj"
SESSION = "2026-06-22-user-auth"
SIBLING_SESSION = "2026-01-02-alpha"
FROZEN_TEST = "tests/test_login.py"
FROZEN_TEST_CONTENT = "def test_x():\n    assert real()\n"
SPEC = "2026-06-22-user-auth-spec-02-login.md"
PENDING_SPEC = "2026-06-22-user-auth-spec-03-refresh.md"
DELIVERED_SPEC = "2026-06-22-user-auth-spec-01-schema.md"


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class Fixture(ToolHome):
    """Adds the default session every retire test targets, and where its spec file lives."""

    def session(self, session_id: str = SESSION) -> dict:
        return super().session(session_id)

    def spec_path(self, session_id: str = SESSION, spec: str = SPEC) -> Path:
        return self.docs / session_id / spec


def _seed_git_repository(docs: Path, spec_file: Path) -> None:
    """A real repository with the spec committed, so `git rm` has something to remove."""
    subprocess.run(["git", "init", "-q", str(docs)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(docs), "config", "user.email", "test@example.com"],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(docs), "config", "user.name", "Test"],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(docs), "add", str(spec_file.relative_to(docs))],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(docs), "commit", "-q", "-m", "seed"],
                   check=True, capture_output=True)


def build_home(tmp_path: Path, *, slug: str = SLUG, session_id: str = SESSION,
               git_tracked: bool = True, frozen_content: str = FROZEN_TEST_CONTENT,
               baselined: bool = True, pending_specs=None, delivered_specs=None,
               keep_specs: bool = False, extra_sessions=None, with_override: bool = False) -> Fixture:
    """A registry, state tree, a project carrying the frozen test, and a docs directory carrying the
    spec — staged into a real git index when `git_tracked`."""
    project = tmp_path / "code"
    frozen_path = project / FROZEN_TEST
    frozen_path.parent.mkdir(parents=True, exist_ok=True)
    frozen_path.write_text(frozen_content, encoding="utf-8")

    docs = tmp_path / "docs-repo"
    spec_dir = docs / session_id
    spec_dir.mkdir(parents=True, exist_ok=True)
    spec_file = spec_dir / SPEC
    spec_file.write_text(f"# {SPEC}\n", encoding="utf-8")
    if git_tracked:
        _seed_git_repository(docs, spec_file)

    session = {
        "tier": "high",
        "current_phase": "build",
        "current_spec": SPEC,
        "current_spec_round": 1,
        "pending_specs": list(pending_specs) if pending_specs is not None else [PENDING_SPEC],
        "delivered_specs": list(delivered_specs) if delivered_specs is not None else [DELIVERED_SPEC],
        "frozen_test_files": [FROZEN_TEST],
    }
    if with_override:
        session["frozen_override"] = {"files": [FROZEN_TEST], "spec": SPEC, "round": 1,
                                      "reason": "user: 'a live grant, cleared once retired'"}
    if baselined:
        session["frozen_baseline"] = {FROZEN_TEST: sha(FROZEN_TEST_CONTENT)}

    sessions = {session_id: session,
                SIBLING_SESSION: {"tier": "low", "current_phase": "shipped",
                                  "handoff_note": "a private note"}}
    if extra_sessions:
        sessions.update(extra_sessions)

    built = write_hercules_home(
        tmp_path, slug=slug, project=project, docs=docs,
        sessions=sessions, active_session=session_id,
        entry_extra={"keep_specs": True} if keep_specs else None,
    )
    return Fixture(built.home, built.project, built.slug, built.docs)


def run(fx: Fixture, *argv: str):
    return invoke(main, fx.home, argv)


def plan(fx: Fixture, *argv: str, session: str = SESSION, spec_file=None):
    """`plan` against the default project/session/spec — the shape every real call takes."""
    spec_file = spec_file if spec_file is not None else str(fx.spec_path(session))
    return run(fx, "plan", "--project-slug", fx.slug, "--session-id", session,
               "--spec-file", spec_file, *argv)


def apply(fx: Fixture, *argv: str, session: str = SESSION, spec_file=None, confirm: bool = True):
    """`apply` against the default project/session/spec, confirmed unless a test wants the refusal."""
    spec_file = spec_file if spec_file is not None else str(fx.spec_path(session))
    extra = ("--confirm",) if confirm else ()
    return run(fx, "apply", "--project-slug", fx.slug, "--session-id", session,
               "--spec-file", spec_file, *extra, *argv)


@pytest.fixture
def fx(tmp_path: Path) -> Fixture:
    """The default `build_home()`, so each test states only what makes it different."""
    return build_home(tmp_path)
