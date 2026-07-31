"""Shared fixture tree for the project-reset tool tests.

**The isolation mechanism, stated plainly.** `project_reset` reaches its record through an explicit
`home` parameter and its working directory through an explicit `cwd` parameter. Neither is a command
-line flag and neither falls back to a real path inside these tests: every helper here passes
`tmp_path`. A test therefore cannot touch a real `~/.hercules`, a real repository, or anything
outside its own temporary tree — not by accident, and not when a mutation campaign corrupts the code
under test, because the corrupted code is still only ever handed fixture paths.

`test_the_fixture_tree_is_real_and_writable` guards that claim: an empty or unwritable fixture would
otherwise let every assertion below pass vacuously.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parents[2]
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))
from project_reset import main  # noqa: E402

SLUG = "proj"
# Two features with different stages: one carrying a delivery record, one that never built. Tests
# read these back, so writer and reader share the one definition.
FEATURES = {"2026-01-02-alpha": "shipped", "2026-01-03-beta": "discover"}
ACTIVE = "2026-01-03-beta"


class Fixture:
    """The paths one built tree exposes. Every test reaches the tool through these and nothing else."""

    def __init__(self, home: Path, project: Path, docs: Path, slug: str):
        self.home = home
        self.project = project
        self.docs = docs
        self.slug = slug

    @property
    def config_path(self) -> Path:
        return self.home / ".hercules" / "config.json"

    @property
    def state_path(self) -> Path:
        return self.home / ".hercules" / "state" / f"{self.slug}.json"

    def registry(self) -> dict:
        return json.loads(self.config_path.read_text())

    def state(self) -> dict:
        return json.loads(self.state_path.read_text())

    def entry(self) -> dict:
        return self.registry()["projects"][self.slug]


def _write_docs(docs: Path, features) -> None:
    """A documents folder shaped like a real one: a folder per feature, an index, a lessons file."""
    docs.mkdir(parents=True, exist_ok=True)
    for key in features:
        (docs / key).mkdir(exist_ok=True)
        (docs / key / f"{key}-business-requirements.md").write_text(f"# {key}\n")
    (docs / "INDEX.md").write_text("# Session index\n")
    (docs / "learnings.md").write_text("# Learnings\n")


def _session(stage: str) -> dict:
    """One feature record. `build_progress` carries prose only on a shipped feature — the shape the
    tool must name without ever showing."""
    session = {"tier": "low", "current_phase": stage, "last_updated": "2026-01-02T00:00:00Z"}
    if stage == "shipped":
        session["build_progress"] = [{"spec": "spec-01.md", "decisions": "a private narrative"}]
        session["shipped_commit"] = "abc1234"
    return session


def build_home(tmp_path: Path, *, slug: str = SLUG, docs_inside: bool = False,
               features=None, docs_root=None, extra_projects=None) -> Fixture:
    """Write a registry and state tree under `tmp_path/.hercules`, plus the project and its
    documents. `docs_inside` puts the documents folder inside the code repository — the default
    arrangement, and the one that needs a warning."""
    features = FEATURES if features is None else features
    project = tmp_path / "code"
    project.mkdir(parents=True, exist_ok=True)
    docs = project / "docs" if docs_inside else tmp_path / "docs-repo"
    if docs_root is None:
        _write_docs(docs, features)

    hh = tmp_path / ".hercules"
    (hh / "state").mkdir(parents=True, exist_ok=True)
    entry = {
        "directory": str(project),
        "docs_root": str(docs) if docs_root is None else str(docs_root),
        "state_file": f"{slug}.json",
        "repositories": {},
    }
    projects = {slug: entry}
    for other_slug, other_entry in (extra_projects or {}).items():
        projects[other_slug] = other_entry
    (hh / "config.json").write_text(json.dumps({"schema_version": 1, "projects": projects}))
    (hh / "state" / f"{slug}.json").write_text(json.dumps({
        "schema_version": 1,
        "active_session": ACTIVE,
        "sessions": {k: _session(v) for k, v in features.items()},
    }))
    return Fixture(tmp_path, project, docs, slug)


def run(fx: Fixture, *argv: str, cwd=None):
    """Invoke the tool and return `(exit_code, payload)`. `cwd` defaults to the project directory.

    The payload is parsed, not inspected as text: every path the tool takes must emit valid JSON on
    stdout, so a test that cannot parse it has found a real defect rather than a formatting quirk.
    """
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = main(list(argv), home=fx.home, cwd=str(cwd or fx.project))
    return code, json.loads(buffer.getvalue())


def plan(fx: Fixture, *argv: str, cwd=None):
    """`plan` with the contract version already supplied — the shape every real call takes."""
    return run(fx, "plan", "--contract", "1", *argv, cwd=cwd)


def apply(fx: Fixture, *argv: str, cwd=None):
    """`apply` with the contract version and confirmation already supplied."""
    return run(fx, "apply", "--contract", "1", "--confirm", *argv, cwd=cwd)


def tree_paths(root: Path):
    """Every path under `root`, relative and sorted — the before/after comparison a deletion test
    makes to prove nothing outside its target moved."""
    return sorted(str(p.relative_to(root)) for p in root.rglob("*"))
