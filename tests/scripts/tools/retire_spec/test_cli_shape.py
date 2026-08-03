"""The JSON envelope every call emits, and the module's own import/entry-point hygiene."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from tests.scripts.tools.retire_spec.conftest import apply, plan

_TOOL = Path(__file__).resolve().parents[4] / "src" / "scripts" / "tools" / "retire_spec.py"


def test_every_payload_carries_the_requested_mode(fx):
    code, payload = plan(fx)
    assert payload["mode"] == "plan"
    code, payload = apply(fx)
    assert payload["mode"] == "apply"


def test_importing_the_module_as_a_library_runs_nothing(fx):
    run = subprocess.run(
        [sys.executable, "-c", f"import sys; sys.path.insert(0, {str(_TOOL.parent)!r}); "
                                "import retire_spec; print('imported-ok')"],
        capture_output=True, text=True, timeout=10)
    assert run.returncode == 0
    assert "imported-ok" in run.stdout


def test_the_shipped_script_runs_standalone_with_a_real_argv(fx):
    """A fresh process with real argv and no fixture-only shortcuts, as a command invokes it."""
    run = subprocess.run(
        [sys.executable, str(_TOOL), "plan", "--project-slug", fx.slug, "--session-id",
         "2026-06-22-user-auth", "--spec-file", str(fx.spec_path())],
        capture_output=True, text=True, timeout=10,
        env={**os.environ, "HOME": str(fx.home)},
    )
    assert run.returncode == 0
    assert '"mode": "plan"' in run.stdout
