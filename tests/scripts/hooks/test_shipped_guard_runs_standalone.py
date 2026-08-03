"""The guard run directly as a program by a host that spawns Python itself and reads only an exit
status — the copy in a built distribution, invoked exactly as such a host invokes it.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.scripts.hooks.conftest import FROZEN_TEST, _payload, _setup

# Hardcoded, never imported from the guard, so a mutated primitive is killed rather than mirrored.
_DENY_EXIT = 2
_DENY_MARKER = "Hercules:"

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SHIPPED_GUARD = _REPO_ROOT / "dist" / "grok-build" / "hooks" / "frozen_tests.py"


@pytest.mark.parametrize("target,denied", [
    (FROZEN_TEST, True),
    ("src/login.py", False),
], ids=["frozen_edit_is_denied", "non_frozen_edit_is_allowed"])
def test_grok_shipped_gate_decides_correctly_as_a_standalone_program(tmp_path, target, denied):
    guard = _SHIPPED_GUARD
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    frozen = project / FROZEN_TEST
    before = frozen.read_bytes()
    r = subprocess.run([sys.executable, str(guard)], input=_payload(project, target),
                       capture_output=True, text=True, env={**os.environ, "HOME": str(tmp_path)})
    if denied:
        assert r.returncode == _DENY_EXIT, "Grok's shipped gate must deny (exit 2) a frozen-test edit"
        assert _DENY_MARKER in r.stderr, "the deny must carry the Hercules block message"
        assert frozen.read_bytes() == before, "a denied edit must leave the frozen file's bytes unchanged"
    else:
        assert r.returncode == 0, "a non-frozen edit must be allowed (exit 0)"
