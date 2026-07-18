"""Shared helpers for the frozen-tests hook tests.

Hoists the registry/state builders and the one canonical frozen path/spec so a reword updates
one place, not sixty call-sites. `FROZEN_TEST`/`SPEC` bind three roles that must agree — the
fixture default that freezes the path, the edit target the tests block, and the assertion pins
that read it back out of the block message — so a single constant keeps writer and reader in sync
(the CoC "pin both ends of a cross-file contract" case, within one package).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_HOOKS_DIR = Path(__file__).resolve().parents[2] / "src" / "targets" / "claude-code" / "hooks"
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))  # same dir the test module inserts — idempotent
from frozen_tests import main  # noqa: E402

FROZEN_TEST = "tests/test_login.py"   # the one canonical frozen path (was inline ×61)
SPEC = "spec-02-login.md"             # the one canonical spec (was inline ×18)


def _setup(home: Path, project: Path, *, phase="build", frozen=(FROZEN_TEST,),
           repositories=None, slug="proj", create=True):
    """Write a registry + state tree under `home/.hercules` for one project/session."""
    hh = home / ".hercules"
    (hh / "state").mkdir(parents=True, exist_ok=True)
    entry = {"directory": str(project), "docs_root": "docs", "state_file": f"{slug}.json"}
    if repositories:
        entry["repositories"] = {k: str(v) for k, v in repositories.items()}
    (hh / "config.json").write_text(json.dumps({"schema_version": 1, "projects": {slug: entry}}))
    session = {
        "current_phase": phase,
        "current_spec": SPEC,
        "current_spec_round": 1,
        "frozen_test_files": list(frozen),
    }
    (hh / "state" / f"{slug}.json").write_text(
        json.dumps({"schema_version": 1, "active_session": "s1", "sessions": {"s1": session}})
    )
    if create:
        for f in frozen:
            p = project / f
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("def test_x():\n    assert True\n")


def _payload(project: Path, rel_or_abs, tool="Edit", cwd=None):
    fp = str(rel_or_abs if Path(str(rel_or_abs)).is_absolute() else project / rel_or_abs)
    return json.dumps({
        "hook_event_name": "PreToolUse",
        "tool_name": tool,
        "tool_input": {"file_path": fp},
        "cwd": str(cwd or project),
    })


def _grant(home: Path, *, files, round_=1, spec=SPEC, slug="proj", extra=None):
    """Record a frozen_override into the session, the way the orchestrator would."""
    state_path = home / ".hercules" / "state" / f"{slug}.json"
    state = json.loads(state_path.read_text())
    ov = {"files": files, "spec": spec, "round": round_,
          "reason": "user: 'the expected status is 201 not 200 — fix the test'"}
    if extra is not None:
        ov = extra
    state["sessions"]["s1"]["frozen_override"] = ov
    state_path.write_text(json.dumps(state))


def _add_project(home: Path, project: Path, slug: str, *, frozen, repositories=None,
                 create=True):
    """Merge one more single-build-session project into an existing registry tree."""
    hh = home / ".hercules"
    (hh / "state").mkdir(parents=True, exist_ok=True)
    cfg_path = hh / "config.json"
    config = (json.loads(cfg_path.read_text()) if cfg_path.exists()
              else {"schema_version": 1, "projects": {}})
    entry = {"directory": str(project), "docs_root": "docs", "state_file": f"{slug}.json"}
    if repositories:
        entry["repositories"] = {k: str(v) for k, v in repositories.items()}
    config["projects"][slug] = entry
    cfg_path.write_text(json.dumps(config))
    session = {"current_phase": "build", "current_spec": f"spec-{slug}.md",
               "current_spec_round": 1, "frozen_test_files": list(frozen)}
    (hh / "state" / f"{slug}.json").write_text(
        json.dumps({"schema_version": 1, "active_session": "s1", "sessions": {"s1": session}}))
    if create:
        for f in frozen:
            p = project / f
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("def test_x():\n    assert True\n")


def build_project(tmp_path: Path, *, phase="build", frozen=(FROZEN_TEST,), **kw) -> Path:
    """A registry + state tree for one build session; returns the project dir.

    The intention-named front door for the common case: `build_project(tmp_path)` gives a
    project mid-Build with `FROZEN_TEST` frozen. Pass `phase=` / `frozen=` to vary the scenario.
    """
    project = tmp_path / "proj"
    _setup(tmp_path, project, phase=phase, frozen=frozen, **kw)
    return project


def run_hook(project: Path, target, *, home: Path) -> int:
    """Feed a PreToolUse Edit payload for `target` to the hook; return its exit code."""
    return main(_payload(project, target), home=home)


@pytest.fixture
def fresh_hook_over_decoy_state(tmp_path: Path):
    """Import a FRESH frozen_tests while a same-named decoy `hercules_state` sits ahead of it on
    sys.path — the setup that proves the hook front-loads its OWN directory. Yields the fresh
    module and restores sys.path / sys.modules on teardown (encapsulated so the test body is tiny)."""
    decoy = tmp_path / "decoy"
    decoy.mkdir()
    (decoy / "hercules_state.py").write_text(
        "def canon(p):\n    return str(p)\n"
        "def resolve_session(cwd, home=None):\n    return None, [], None\n"
        "def frozen_candidates(entry, roots):\n    return set()\n"
    )
    saved_modules = {k: sys.modules.pop(k) for k in ("hercules_state",) if k in sys.modules}
    saved_path = list(sys.path)
    sys.path.insert(0, str(decoy))
    spec = importlib.util.spec_from_file_location("frozen_tests_fresh", _HOOKS_DIR / "frozen_tests.py")
    fresh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fresh)
    try:
        yield fresh
    finally:
        sys.path[:] = saved_path
        sys.modules.pop("hercules_state", None)
        sys.modules.update(saved_modules)
