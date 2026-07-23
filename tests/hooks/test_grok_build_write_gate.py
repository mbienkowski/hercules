"""Grok Build write-gate: the SHIPPED plugin denies a frozen-test edit before it lands.

Grok Build reads Claude-format hooks, so its ``PreToolUse`` wiring invokes the byte-identical canonical
guard. This runs the guard exactly as Grok deploys it — the plugin's own shipped ``frozen_tests.py``
fed a real ``PreToolUse`` payload — and never skips (no live CLI needed), so the deny path always
carries coverage; the live smoke leg is an additional check, never the sole proof.
"""
from __future__ import annotations

import os
import subprocess
import sys

from scripts.build.cli import build_target
from tests.hooks.conftest import FROZEN_TEST, _payload, _setup

# Deny artifacts as hardcoded literals (never imported from the guard) so a mutated primitive is killed.
_DENY_EXIT = 2
_DENY_MARKER = "Hercules:"


def _shipped_guard(tmp_path):
    out = tmp_path / "grok"
    build_target("grok-build", out)
    return out / "hooks" / "frozen_tests.py"


def test_grok_shipped_gate_denies_a_frozen_edit_and_leaves_the_file_unchanged(tmp_path):
    guard = _shipped_guard(tmp_path)
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    frozen = project / FROZEN_TEST
    before = frozen.read_bytes()
    r = subprocess.run([sys.executable, str(guard)], input=_payload(project, FROZEN_TEST),
                       capture_output=True, text=True, env={**os.environ, "HOME": str(tmp_path)})
    assert r.returncode == _DENY_EXIT, "Grok's shipped gate must deny (exit 2) a frozen-test edit"
    assert _DENY_MARKER in r.stderr, "the deny must carry the Hercules block message"
    assert frozen.read_bytes() == before, "a denied edit must leave the frozen file's bytes unchanged"


def test_grok_shipped_gate_allows_a_non_frozen_edit(tmp_path):
    guard = _shipped_guard(tmp_path)
    project = tmp_path / "proj"
    _setup(tmp_path, project)
    r = subprocess.run([sys.executable, str(guard)], input=_payload(project, "src/login.py"),
                       capture_output=True, text=True, env={**os.environ, "HOME": str(tmp_path)})
    assert r.returncode == 0, "a non-frozen edit must be allowed (exit 0)"
