"""The scaffolding every shipped-tool suite shares, written once: importing a tool from the source
tree, the paths of a throwaway ``~/.hercules``, and a run that parses the JSON reply — four copies of
this is how one word quietly acquires four slightly different meanings. Fixture DATA stays per tool.
Not a conftest, deliberately: pytest would offer these names tree-wide and no tool could define an
``fx`` of its own shape.
"""

from __future__ import annotations

import contextlib
import importlib
import io
import json
import os
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[3] / "src" / "scripts" / "tools"


def tool_directories() -> list:
    """Every directory a shipped tool lives in. Tools are grouped by the feature they serve, and a
    host reaches one by path, so a test resolves them the same way rather than assuming one flat
    directory."""
    return [TOOLS_DIR] + sorted(p for p in TOOLS_DIR.rglob("*") if p.is_dir()
                                and p.name != "__pycache__")


def load_tool(module_name: str):
    """The shipped tool's ``main``, reached by putting its directory on the path — single-file
    programs with no package around them, the same way a host reaches one."""
    for directory in tool_directories():
        if str(directory) not in sys.path:
            sys.path.insert(0, str(directory))
    return importlib.import_module(module_name).main


class ToolHome:
    """The only route a test has to its tool. ``home`` is always explicit and never falls back, so no
    mutation of the resolution logic can reach a developer's own ``~/.hercules``."""

    def __init__(self, home: Path, project: Path, slug: str, docs: Path | None = None):
        self.home = home
        self.project = project
        self.slug = slug
        self.docs = docs

    @property
    def config_path(self) -> Path:
        return self.home / ".hercules" / "config.json"

    @property
    def state_dir(self) -> Path:
        return self.home / ".hercules" / "state"

    @property
    def state_path(self) -> Path:
        return self.state_dir / f"{self.slug}.json"

    def registry(self) -> dict:
        return json.loads(self.config_path.read_text())

    def state(self) -> dict:
        return json.loads(self.state_path.read_text())

    def entry(self, slug: str | None = None) -> dict:
        return self.registry()["projects"][slug or self.slug]

    def session(self, session_id: str) -> dict:
        return self.state()["sessions"][session_id]


def write_hercules_home(
    tmp_path: Path,
    *,
    slug: str,
    project: Path,
    sessions: dict,
    active_session: str | None,
    docs: Path | None = None,
    docs_root: Path | str | None = None,
    entry_extra: dict | None = None,
    repositories: dict | None = None,
    extra_projects: dict | None = None,
    write_config: bool = True,
) -> ToolHome:
    """Write the registry and state file under ``tmp_path/.hercules``. ``write_config=False`` leaves
    the registry absent on purpose: a tool without one must say so rather than invent it."""
    hercules = tmp_path / ".hercules"
    (hercules / "state").mkdir(parents=True, exist_ok=True)

    entry = {
        "directory": str(project),
        "docs_root": str(docs_root if docs_root is not None else docs),
        "state_file": f"{slug}.json",
        "repositories": dict(repositories or {}),
    }
    entry.update(entry_extra or {})

    projects = {slug: entry}
    projects.update(extra_projects or {})

    if write_config:
        (hercules / "config.json").write_text(
            json.dumps({"schema_version": 1, "projects": projects})
        )
    (hercules / "state" / f"{slug}.json").write_text(
        json.dumps({
            "schema_version": 1,
            "active_session": active_session,
            "sessions": {name: dict(body) for name, body in sessions.items()},
        })
    )
    return ToolHome(tmp_path, project, slug, docs)


def read_only_directories_are_enforced(tmp_path: Path) -> bool:
    """Whether stripping write permission from a directory actually stops a write here — measured,
    not inferred from the user id. A test that a failed write leaves the original intact needs the
    write to fail; run as root, or on a filesystem that ignores the mode, it never does, and the test
    would report a defect in the tool that is really a property of the machine."""
    probe = tmp_path / "permission-probe"
    probe.mkdir()
    (probe / "existing.txt").write_text("x")
    os.chmod(probe, 0o500)
    try:
        (probe / "new.txt").write_text("x")
        return False
    except OSError:
        return True
    finally:
        os.chmod(probe, 0o700)


def invoke(main, home: Path, argv, **extra):
    """Run the tool and return ``(exit_code, payload)``. The payload is PARSED, never matched as
    text: an unparseable reply is a real defect in a program whose output contract is one JSON object."""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = main(list(argv), home=home, **extra)
    return code, json.loads(buffer.getvalue())
