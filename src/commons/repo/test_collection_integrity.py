"""Guard: every test directory is actually collected by ``pytest`` (testpaths = src/commons/repo,
src/hooks/tests, src/tools/tests).

pytest's default ``norecursedirs`` includes ``build`` and ``dist``, so a directory with either name
is skipped during recursion and its tests run only when the path is named explicitly -- an entire
suite can go dark with no red check. This meta-test fails if any reserved-name pattern would exclude
a real test directory under either collected root.

Frozen for spec-05-ci-release-integration.
"""
import fnmatch
from pathlib import Path

TESTS_ROOT = Path(__file__).resolve().parent
REPO_ROOT = TESTS_ROOT.parent.parent
# The roots pyproject.toml's [tool.pytest.ini_options] testpaths actually collects — one per Python
# island plus this meta-guard's own tree. A new island that lands without being added here is a whole
# suite this guard silently stops covering.
_COLLECTED_ROOTS = [TESTS_ROOT, REPO_ROOT / "hooks" / "tests", REPO_ROOT / "tools" / "tests"]


def _test_dirs() -> list[Path]:
    """Directories under a collected root that contain at least one test_*.py file."""
    return sorted({p.parent for root in _COLLECTED_ROOTS if root.is_dir() for p in root.rglob("test_*.py")})


def test_no_test_folder_is_silently_skipped_when_running_the_full_suite(request):
    """No folder under a pytest-collected root may share a name with a pattern the test runner excludes
    by default, such as "build" or "dist" -- every test in such a folder quietly stops running."""
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
