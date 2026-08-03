"""The JSON envelope every call emits, usage-error handling, and the module's own import/entry-point
hygiene."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from tests.scripts.tools.registry_sync.conftest import resolve, run

_TOOL = Path(__file__).resolve().parents[4] / "src" / "scripts" / "tools" / "registry_sync.py"


def test_every_payload_names_its_own_command(fx):
    code, payload = resolve(fx, fx.project)
    assert payload["command"] == "resolve"


def test_no_subcommand_is_a_usage_error_not_a_crash(fx):
    code, payload = run(fx)
    assert code == 3
    assert payload["error"] == "usage"


def test_importing_the_module_as_a_library_runs_nothing():
    result = subprocess.run(
        [sys.executable, "-c", f"import sys; sys.path.insert(0, {str(_TOOL.parent)!r}); "
                                "import registry_sync; print('imported-ok')"],
        capture_output=True, text=True, timeout=10)
    assert result.returncode == 0
    assert "imported-ok" in result.stdout


def test_the_shipped_script_runs_standalone_with_a_real_argv(fx):
    result = subprocess.run(
        [sys.executable, str(_TOOL), "resolve", "--cwd", str(fx.project)],
        capture_output=True, text=True, timeout=10,
        env={**os.environ, "HOME": str(fx.home)},
    )
    assert result.returncode == 0
    assert '"command": "resolve"' in result.stdout
