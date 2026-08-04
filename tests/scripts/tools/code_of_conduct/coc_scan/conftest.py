"""A repository built to have every property the scanner claims to detect, and to have them at KNOWN
ages — a module worked on recently, one worked on inside the year but not lately, one untouched since
before the window, a path renamed away, and a generated tree. Commit dates are set explicitly rather
than taken from the clock, so a window boundary is a fact of the fixture and not of the day the suite
runs.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tests.scripts.tools.tool_harness import invoke, load_tool

CONTRACT = 1

# Ages in days before the fixture's final commit, which becomes the scan's anchor.
AGE_PREHISTORY = 800     # before a 12-month window: its files are present but dormant
AGE_OLD = 300            # inside the year, outside the recent window
AGE_MIDDLE = 150         # inside the year, outside the recent window
AGE_RECENT = 40          # inside the recent window
AGE_RENAME = 20
AGE_HEAD = 10

ALIVE_DIR = "src/core"
COOLING_DIR = "src/api"
DORMANT_DIR = "legacy/reporting"
GENERATED_DIR = "dist/bundle"


def _git(root: Path, *args, when: int | None = None):
    env = None
    if when is not None:
        stamp = f"{when} +0000"
        env = {"GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp,
               "GIT_AUTHOR_NAME": "Fixture", "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
               "GIT_COMMITTER_NAME": "Fixture", "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
               "PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(root)}
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, env=env)


def _write(root: Path, relative: str, text: str = "x\n"):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _commit(root: Path, subject: str, age_days: int, base_epoch: int):
    _git(root, "add", "-A")
    _git(root, "commit", "-m", subject, "--no-gpg-sign",
         when=base_epoch - age_days * 86400)


def build_repo(root: Path, base_epoch: int = 1_900_000_000) -> Path:
    """A repository whose every scannable property is placed deliberately."""
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "fixture@example.invalid")
    _git(root, "config", "user.name", "Fixture")
    _git(root, "config", "commit.gpgsign", "false")

    # Prehistory: files that still exist at HEAD but are never touched again.
    _write(root, f"{DORMANT_DIR}/report.py", "def report():\n    return 1\n")
    _write(root, f"{DORMANT_DIR}/legacy_export.py", "# TODO: retire this\n")
    _write(root, "src/old_name.py", "value = 1\n")
    _write(root, "README.md", "# fixture\n")
    _commit(root, "chore: initial import", AGE_PREHISTORY, base_epoch)

    # Configuration, so the probes have something true to find.
    _write(root, "package.json", json.dumps({
        "name": "fixture", "engines": {"node": ">=20"},
        "devDependencies": {"eslint": "9.0.0", "vitest": "2.0.0"}}))
    _write(root, "pyproject.toml",
           "[project]\nname = 'fixture'\n\n[tool.ruff]\nline-length = 100\n\n"
           "[tool.pytest.ini_options]\ntestpaths = ['tests']\n")
    _write(root, ".eslintrc.yml", "rules: {}\n")
    _write(root, ".github/workflows/ci.yml", "name: CI\n")
    _write(root, f"{COOLING_DIR}/handler.py", "def handle():\n    return 2\n")
    _commit(root, "feat: add the api surface", AGE_OLD, base_epoch)

    _write(root, f"{COOLING_DIR}/handler.py", "def handle():\n    return 3\n")
    _commit(root, "fix: correct the handler", AGE_MIDDLE, base_epoch)

    # Recent work: this is what "alive" must mean.
    _write(root, f"{ALIVE_DIR}/engine.py", "def run():\n    return 4\n")
    _commit(root, "feat(core): add the engine", AGE_RECENT, base_epoch)

    # A rename, so a path with history no longer exists at HEAD.
    _git(root, "mv", "src/old_name.py", "src/new_name.py")
    _commit(root, "rename the old module", AGE_RENAME, base_epoch)

    _write(root, f"{GENERATED_DIR}/out.js", "// generated\n")
    _commit(root, "chore: rebuild the bundle", AGE_HEAD, base_epoch)
    return root


@pytest.fixture
def repo(tmp_path) -> Path:
    return build_repo(tmp_path / "fixture")


@pytest.fixture
def scan():
    """Run the scanner, returning `(exit_code, document)`."""
    main = load_tool("coc_scan")

    def run(root, *extra, argv=None):
        return invoke(main, None, argv or ["all", "--root", str(root),
                                           "--contract", str(CONTRACT), *extra])

    return run


def fact_ids(document: dict) -> set:
    return {f["id"] for f in document.get("facts", [])}


def fact(document: dict, fact_id: str) -> dict:
    return next(f for f in document["facts"] if f["id"] == fact_id)


def directory(document: dict, path: str) -> dict:
    return next(d for d in document["liveness"]["directories"] if d["path"] == path)


def build_split_repo(root: Path, base_epoch: int = 1_900_000_000) -> Path:
    """A repository doing one thing two ways: a large legacy suite in the older convention that
    nobody touches, and a smaller new one that is where all the recent work happens. The two
    majorities disagree — by file count the old way wins, by recent work the new way does — which is
    the whole reason this is a question rather than a count."""
    build_repo(root, base_epoch)
    for index in range(6):
        _write(root, f"tests/legacy/test_report_{index}.py",
               "import unittest\n\n\nclass ReportTest(unittest.TestCase):\n"
               "    def test_it(self):\n        self.assertTrue(True)\n")
    _commit(root, "chore: import the legacy suite", AGE_PREHISTORY, base_epoch)

    for index in range(2):
        _write(root, f"tests/api/test_engine_{index}.py",
               "def test_it():\n    assert True\n")
    _commit(root, "feat(api): add the new suite", AGE_RECENT, base_epoch)
    _write(root, "tests/api/test_engine_0.py", "def test_it():\n    assert True  # revised\n")
    _commit(root, "fix(api): revise the new suite", AGE_HEAD, base_epoch)
    return root


@pytest.fixture
def split_repo(tmp_path) -> Path:
    return build_split_repo(tmp_path / "split")


def build_consistent_repo(root: Path, base_epoch: int = 1_900_000_000) -> Path:
    """A repository that does each thing exactly one way, and one non-test module that merely NAMES
    another way. Both are how a conflict gets invented where none exists: a lone convention counted
    as a split, and a mention read as a use."""
    build_repo(root, base_epoch)
    for index in range(3):
        _write(root, f"tests/api/test_engine_{index}.py", "def test_it():\n    assert True\n")
    _write(root, "src/core/style_notes.py",
           '"""The suite moved off unittest.TestCase years ago; self.assertTrue is gone too."""\n'
           "SUPPORTED = ('pytest',)\n")
    _commit(root, "feat(api): one way of testing", AGE_RECENT, base_epoch)
    return root


@pytest.fixture
def consistent_repo(tmp_path) -> Path:
    return build_consistent_repo(tmp_path / "consistent")
