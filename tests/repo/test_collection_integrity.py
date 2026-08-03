"""Guard: every test directory is actually collected by ``pytest``. Its default ``norecursedirs``
includes ``build`` and ``dist``, so a directory with either name is skipped during recursion and an
entire suite goes dark with no red check to show for it.
"""
import fnmatch
from pathlib import Path

from tests.repo.collected_roots import collected_roots

TESTS_ROOT = Path(__file__).resolve().parent
REPO_ROOT = TESTS_ROOT.parent.parent


def _test_dirs(request) -> list[Path]:
    """Directories under a collected root that contain at least one test_*.py file."""
    return sorted({p.parent for root in collected_roots(request) for p in root.rglob("test_*.py")})


def test_no_test_folder_is_silently_skipped_when_running_the_full_suite(request):
    """No folder under a pytest-collected root may share a name with a pattern the test runner excludes
    by default, such as "build" or "dist" -- every test in such a folder quietly stops running."""
    patterns = request.config.getini("norecursedirs")
    hidden = [
        d.relative_to(REPO_ROOT).as_posix()
        for d in _test_dirs(request)
        if any(fnmatch.fnmatch(d.name, pat) for pat in patterns)
    ]
    assert hidden == [], (
        f"test directories match a norecursedirs pattern and will be skipped under "
        f"pytest's collected testpaths: {hidden} (patterns: {patterns})"
    )
