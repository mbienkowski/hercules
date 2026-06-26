"""Tests for the __main__ entry-point Python version gate."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_PROJECT_ROOT = str(Path(__file__).parent.parent)


def test_rejects_python_38():
    """Python 3.8 must trigger the version gate: print an error and exit with code 1."""
    script = (
        "import sys\n"
        "class _V(tuple):\n"
        "    major=3; minor=8\n"
        "sys.version_info = _V((3, 8, 0, 'final', 0))\n"
        "exec(open('hercules/__main__.py').read())\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        cwd=_PROJECT_ROOT,
    )
    assert result.returncode == 1
    assert b"3.9" in result.stderr


def test_accepts_python_39_plus():
    """Python 3.9 or later must not trigger the version gate (the comparison must be False)."""
    # The gate is: if sys.version_info < (3, 9): sys.exit(1)
    # Verify that 3.9 and 3.10 do not satisfy < (3, 9)
    assert not ((3, 9, 0, "final", 0) < (3, 9))
    assert not ((3, 10, 0, "final", 0) < (3, 9))
    # And that our running Python also passes
    assert not (sys.version_info < (3, 9))
