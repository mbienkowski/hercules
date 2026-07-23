"""The universal smoke driver — live CLI checks steered by each descriptor's ``smoke.expect``.

The commands to run and what to expect are per-ecosystem CONFIG (the descriptor's ``smoke.expect``,
closed vocabulary), so a new ecosystem gets its basic live check by declaring data — no new test
file. Deep host-specific install flows (marketplace add/install/list, extension installs) stay as
named tests in each ecosystem's own smoke file, pointed at by ``smoke.test``.
"""
from __future__ import annotations

import shutil
import subprocess

import pytest

from scripts.build.descriptor import discover

_TIMEOUT = 120


def test_every_ecosystem_declares_its_smoke_expectations():
    """Fail-closed: every descriptor must declare smoke.expect.version_cmd — a target cannot ship
    without at least the basic live-CLI check being configured."""
    for name, d in sorted(discover().items()):
        cmd = (d.smoke.get("expect") or {}).get("version_cmd")
        assert cmd, f"{name}: smoke.expect.version_cmd missing from the descriptor"
        assert cmd[0] == d.smoke["cli"], f"{name}: version_cmd must invoke the declared cli"


@pytest.mark.parametrize("name", sorted(discover()))
def test_the_declared_version_command_succeeds_when_the_cli_is_present(name):
    """With the real CLI installed (CI smoke legs; skipped locally when absent), the descriptor's
    declared version command must exit 0 — a stub-on-PATH would not."""
    smoke = discover()[name].smoke
    if shutil.which(smoke["cli"]) is None:
        pytest.skip(f"{smoke['cli']} not installed")
    cmd = smoke["expect"]["version_cmd"]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=_TIMEOUT)
    assert res.returncode == 0, f"{name}: {' '.join(cmd)} failed: {res.stdout}\n{res.stderr}"
