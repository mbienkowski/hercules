"""Shared pytest fixtures for the Hercules test suite."""

from __future__ import annotations

import os
import stat
import sys
import textwrap
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Walk up from this file until we find pyproject.toml (the repo root)."""
    here = Path(__file__).resolve().parent
    for candidate in [here, *here.parents]:
        if (candidate / "pyproject.toml").exists():
            return candidate
    raise RuntimeError("pyproject.toml not found above tests/ — is this the repo root?")


@pytest.fixture(scope="session")
def plugin_root(repo_root: Path) -> Path:
    """Path to the plugin/ subdirectory containing all Claude plugin content."""
    return repo_root / "plugin"


@pytest.fixture(scope="session")
def agent_files(plugin_root: Path) -> list[Path]:
    """Sorted list of all agent markdown files."""
    return sorted((plugin_root / "agents").glob("*.md"))


@pytest.fixture(scope="session")
def skill_files(plugin_root: Path) -> list[Path]:
    """Sorted list of all skill SKILL.md files."""
    return sorted((plugin_root / "skills").glob("*/SKILL.md"))


@pytest.fixture(scope="session")
def command_files(plugin_root: Path) -> list[Path]:
    """Sorted list of all command markdown files."""
    return sorted((plugin_root / "commands").glob("*.md"))


@pytest.fixture
def read_file(repo_root: Path):
    """Return a helper that reads a file relative to repo_root."""
    def _read(rel: str) -> str:
        return (repo_root / rel).read_text()
    return _read


@pytest.fixture
def fake_bin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Write executable stub scripts to a temp directory and prepend it to PATH.

    Usage: fake_bin("git", exit_code=0, stdout="")
    Returns a factory; call it once per binary you want to stub.
    """
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ.get("PATH", ""))

    def _make_stub(name: str, exit_code: int = 0, stdout: str = "", stderr: str = "") -> Path:
        script = bin_dir / name
        script.write_text(
            textwrap.dedent(f"""\
                #!/bin/sh
                printf '%s' {repr(stdout)} >&1
                printf '%s' {repr(stderr)} >&2
                exit {exit_code}
            """)
        )
        script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        return script

    return _make_stub
