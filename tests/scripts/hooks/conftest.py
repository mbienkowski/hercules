"""Shared helpers for the frozen-tests hook tests: the registry/state builders, the one canonical
frozen path and spec, and the two gate-configuration readers every write-gate suite shares.
`FROZEN_TEST`/`SPEC` bind three roles that must agree — the fixture default, the edit target, and the
assertions reading it back out of the block message — so one constant keeps writer and reader in sync.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

# Only an env var, never the process-local flag, stops a subprocess writing into committed dist/.
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

_HOOKS_DIR = Path(__file__).resolve().parents[3] / "src" / "scripts" / "hooks"
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))  # same dir the test module inserts — idempotent
from frozen_tests import main  # noqa: E402

FROZEN_TEST = "tests/test_login.py"   # the one canonical frozen path
SPEC = "spec-02-login.md"             # the one canonical spec

_REPO_ROOT = Path(__file__).resolve().parents[3]
_FIXTURES = Path(__file__).resolve().parent / "fixtures"
_RECIPES = _REPO_ROOT / "src" / "targets"
_GATE_DEST = "hooks/write_gate.json"


def gate_fixture(name: str) -> dict:
    """A hand-made gate configuration from ``fixtures/<name>.json``. Documentation keys (``_``-prefixed)
    are stripped, so a suite can compare a fixture with a real configuration for equality."""
    data = json.loads((_FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    return {key: value for key, value in data.items() if not key.startswith("_")}


def declared_gate_configs() -> dict:
    """Every gate configuration a target DECLARES, read from the source its recipe names; what ships
    is pinned to that source verbatim, so reading it here reads what installs."""
    found: dict = {}
    for recipe_path in sorted(_RECIPES.glob("*.json")):
        if ".schema." in recipe_path.name:
            continue
        recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
        entry = (recipe.get("targets") or {}).get(_GATE_DEST)
        sources = (entry or {}).get("sources") or []
        for source in sources:
            found[recipe_path.stem] = json.loads((_REPO_ROOT / source).read_text(encoding="utf-8"))
    return found


def _setup(home: Path, project: Path, *, phase="build", frozen=(FROZEN_TEST,),
           repositories=None, slug="proj", create=True, merge=False):
    """Write a registry + state tree under `home/.hercules` for one project/session. `merge=True`
    folds the entry into an existing `config.json` — the shape several mid-build projects share."""
    hh = home / ".hercules"
    (hh / "state").mkdir(parents=True, exist_ok=True)
    entry = {"directory": str(project), "docs_root": "docs", "state_file": f"{slug}.json"}
    if repositories:
        entry["repositories"] = {k: str(v) for k, v in repositories.items()}
    cfg_path = hh / "config.json"
    config = (json.loads(cfg_path.read_text()) if merge and cfg_path.exists()
              else {"schema_version": 1, "projects": {}})
    config["projects"][slug] = entry
    cfg_path.write_text(json.dumps(config))
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


def build_project(tmp_path: Path, *, phase="build", frozen=(FROZEN_TEST,), **kw) -> Path:
    """The project directory of a fresh mid-Build session with `FROZEN_TEST` frozen."""
    project = tmp_path / "proj"
    _setup(tmp_path, project, phase=phase, frozen=frozen, **kw)
    return project


def run_hook(project: Path, target, *, home: Path) -> int:
    """Feed a PreToolUse Edit payload for `target` to the hook; return its exit code."""
    return main(_payload(project, target), home=home)


@pytest.fixture
def monorepo(tmp_path: Path):
    """The ``(outer, inner)`` folder pair the nesting scenarios build their registry entries under."""
    outer = tmp_path / "mono"
    inner = outer / "svc"
    return outer, inner


@pytest.fixture
def fresh_hook_over_decoy_state(tmp_path: Path):
    """A FRESH frozen_tests imported while a decoy `hercules_state` sits ahead of it on sys.path;
    sys.path and sys.modules are restored on teardown."""
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
