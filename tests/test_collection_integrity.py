"""Guard: every test directory is actually collected by ``pytest tests/``.

pytest's default ``norecursedirs`` includes ``build`` and ``dist``, so a directory named
``tests/build/`` is silently skipped during recursion — its tests only run when the path is named
explicitly. That once hid the entire compiler suite (152 tests) from CI. This meta-test fails if any
reserved-name pattern would exclude a real test directory, so the regression cannot return unnoticed.

Frozen for spec-05-ci-release-integration.
"""
import fnmatch
from pathlib import Path

TESTS_ROOT = Path(__file__).resolve().parent


def _test_dirs() -> list[Path]:
    """Directories under tests/ that contain at least one test_*.py file."""
    return sorted({p.parent for p in TESTS_ROOT.rglob("test_*.py")})


def test_no_test_directory_is_hidden_by_norecursedirs(request):
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


def test_build_suite_is_present_and_recursable(request):
    # Positive companion: the compiler suite exists and is not excluded.
    build_dir = TESTS_ROOT / "build"
    assert build_dir.is_dir(), "tests/build/ (the compiler suite) is missing"
    assert list(build_dir.glob("test_*.py")), "tests/build/ has no test files"
    patterns = request.config.getini("norecursedirs")
    assert not any(fnmatch.fnmatch("build", pat) for pat in patterns), \
        "norecursedirs excludes 'build' — tests/build/ would be skipped during recursion"
