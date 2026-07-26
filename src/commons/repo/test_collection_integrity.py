"""Guard: every test dir is actually collected by ``pytest`` (testpaths = src/commons/repo, src/hooks/tests).

pytest's default ``norecursedirs`` includes ``build`` and ``dist``, so a directory named, say,
``tests/build/`` would be silently skipped during recursion -- its tests only run when the path is
named explicitly. That once hid an entire suite of 152 tests from CI (back when the now-retired
Python compiler's tests lived at ``tests/build/`` -- ported to TypeScript and removed by the same
commit that deleted the compiler itself, so the directory that incident was named after no longer
exists). This meta-test fails if any reserved-name pattern would exclude a real test directory
under either pytest-collected root, so the regression cannot return unnoticed under a different
directory name.

Frozen for spec-05-ci-release-integration.
"""
import fnmatch
from pathlib import Path

TESTS_ROOT = Path(__file__).resolve().parent
REPO_ROOT = TESTS_ROOT.parent.parent
# The two roots pyproject.toml's [tool.pytest.ini_options] testpaths actually collects.
_COLLECTED_ROOTS = [TESTS_ROOT, REPO_ROOT / "hooks" / "tests"]


def _test_dirs() -> list[Path]:
    """Directories under a collected root that contain at least one test_*.py file."""
    return sorted({p.parent for root in _COLLECTED_ROOTS if root.is_dir() for p in root.rglob("test_*.py")})


def test_no_test_folder_is_silently_skipped_when_running_the_full_suite(request):
    """None of the folders under a pytest-collected root may share a name with a pattern the test
    runner excludes by default (such as "build" or "dist"). If one did, every test in that folder
    would quietly stop running -- as happened once before, when an entire suite of 152 tests
    went dark without anyone noticing."""
    patterns = request.config.getini("norecursedirs")
    hidden = [
        d.relative_to(REPO_ROOT).as_posix()
        for d in _test_dirs()
        if any(fnmatch.fnmatch(d.name, pat) for pat in patterns)
    ]
    assert hidden == [], (
        f"test directories match a norecursedirs pattern and will be skipped under "
        f"pytest's collected testpaths: {hidden} (patterns: {patterns})"
    )
