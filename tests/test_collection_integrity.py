"""Guard: every test directory is actually collected by ``pytest tests/``.

pytest's default ``norecursedirs`` includes ``build`` and ``dist``, so a directory named, say,
``tests/build/`` would be silently skipped during recursion -- its tests only run when the path is
named explicitly. That once hid an entire suite of 152 tests from CI (back when the now-retired
Python compiler's tests lived at ``tests/build/`` -- ported to TypeScript and removed by the same
commit that deleted the compiler itself, so the directory that incident was named after no longer
exists). This meta-test fails if any reserved-name pattern would exclude a real test directory
under ``tests/``, so the regression cannot return unnoticed under a different directory name.

Frozen for spec-05-ci-release-integration.
"""
import fnmatch
from pathlib import Path

TESTS_ROOT = Path(__file__).resolve().parent


def _test_dirs() -> list[Path]:
    """Directories under tests/ that contain at least one test_*.py file."""
    return sorted({p.parent for p in TESTS_ROOT.rglob("test_*.py")})


def test_no_test_folder_is_silently_skipped_when_running_the_full_suite(request):
    """None of the folders under tests/ may share a name with a pattern the test runner
    excludes by default (such as "build" or "dist"). If one did, every test in that folder
    would quietly stop running -- as happened once before, when an entire suite of 152 tests
    went dark without anyone noticing."""
    patterns = request.config.getini("norecursedirs")
    hidden = [
        d.relative_to(TESTS_ROOT.parent).as_posix()
        for d in _test_dirs()
        if any(fnmatch.fnmatch(d.name, pat) for pat in patterns)
    ]
    assert hidden == [], (
        f"test directories match a norecursedirs pattern and will be skipped under "
        f"`pytest tests/`: {hidden} (patterns: {patterns})"
    )
