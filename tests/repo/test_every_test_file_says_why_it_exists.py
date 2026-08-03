"""Guard: every test file opens by saying why it exists — the cheapest guard here, protecting the
most expensive thing. Almost every header in this tree records a real failure, and those sentences
are the only way a later reader tells a redundant test from a load-bearing one before deleting it.
A header is any comment before the first test or ``describe``. Its accuracy is deliberately NOT
checked: nothing mechanical can know that, and a guard pretending otherwise is worse than none.
"""
from __future__ import annotations

import re
from pathlib import Path

from tests.repo.collected_roots import collected_roots

REPO_ROOT = Path(__file__).resolve().parents[2]

# Named rather than derived, since pytest does not collect them; the sweep assertion catches a miss.
_TYPESCRIPT_TESTS = REPO_ROOT / "tests"

_PY_TEST = re.compile(r"^\s*def test_|^\s*class Test", re.MULTILINE)
_TS_TEST = re.compile(r"^\s*(?:describe|it|test)\s*[.(]", re.MULTILINE)
_COMMENT_START = ("#", "//", "/*", '"""', "'''", "*")


def _first_comment_line(text: str) -> int | None:
    """The 1-based line of the first comment, or None when the file carries none."""
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith(_COMMENT_START):
            return number
    return None


def _first_test_line(text: str, pattern: re.Pattern[str]) -> int | None:
    match = pattern.search(text)
    return text[: match.start()].count("\n") + 1 if match else None


def _files_to_check(request) -> list[tuple[Path, re.Pattern[str]]]:
    """Every test module in both runtimes, paired with how a test declaration looks in it."""
    found: list[tuple[Path, re.Pattern[str]]] = []
    for root in collected_roots(request):
        found.extend((path, _PY_TEST) for path in root.rglob("test_*.py"))
    found.extend((path, _TS_TEST) for path in _TYPESCRIPT_TESTS.rglob("*.spec.ts"))
    return sorted(found)


def test_no_test_file_leaves_a_reader_guessing_why_it_is_there(request):
    """A comment BEFORE the first test is what a later reader weighs the file by."""
    checked = _files_to_check(request)
    # Guards the guard: an empty sweep would report success while checking nothing.
    assert len(checked) > 40, f"only {len(checked)} test files found — the sweep is not reaching them"

    offenders: list[str] = []
    for path, test_pattern in checked:
        if path.name == Path(__file__).name:
            continue
        text = path.read_text(encoding="utf-8")
        first_test = _first_test_line(text, test_pattern)
        if first_test is None:
            continue  # a support module that declares no tests; nothing to introduce
        comment = _first_comment_line(text)
        rel = path.relative_to(REPO_ROOT).as_posix()
        if comment is None:
            offenders.append(f"{rel}: no comment anywhere")
        elif comment > first_test:
            offenders.append(f"{rel}: first comment is at line {comment}, after the first test at {first_test}")

    assert not offenders, (
        "these test files start testing before they say why they exist — add a header stating what "
        "the file protects, and the failure it exists to prevent if it had one:\n  "
        + "\n  ".join(offenders)
    )
