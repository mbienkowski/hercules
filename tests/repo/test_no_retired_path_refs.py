"""Guard: no test source names a retired build-output path. Artifacts live under `dist/`, so a
docstring or error message naming somewhere else sends whoever reads a failure to a dead path.
Only path-LIKE usages match, so the real file `plugin.json` and "this path must be gone" assertions
stay allowed.
"""
from __future__ import annotations

import re
from pathlib import Path

from tests.repo.collected_roots import collected_roots

TESTS_ROOT = Path(__file__).resolve().parent   # tests/repo
REPO_ROOT = TESTS_ROOT.parent.parent           # the repository root

# A path segment must follow the prefix, so the literal file `plugin.json` is never flagged.
_RETIRED = re.compile(r"(plugin/[a-z][a-z0-9-]*/|\.opencode/)")


def _test_files(request) -> list[Path]:
    # Every root pytest collects, so no island sits outside the sweep with nothing to report the gap.
    found = (p for root in collected_roots(request) for p in root.rglob("test_*.py"))

    # This guard names the retired paths in order to match them, so it exempts itself.
    return sorted(p for p in found if p.name != "test_no_retired_path_refs.py")


def test_old_project_folder_names_dont_linger_in_test_documentation(request):
    """A stray mention sends someone chasing a failure, or searching for a file, at a dead path."""
    offenders: list[tuple[str, int, str]] = []
    for path in _test_files(request):
        rel = path.relative_to(REPO_ROOT).as_posix()
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for m in _RETIRED.finditer(line):
                # A negation cue on the line marks an "old path is gone" assertion, which may name it.
                if any(cue in line for cue in ('"not in', "'not in", " not in ", "must not", "should not")):
                    continue
                offenders.append((rel, i, line.strip()))
    assert not offenders, (
        "test files reference retired `plugin/` or `.opencode/` paths (rename to "
        "`dist/claude-code/` or `dist/opencode/`):\n  "
        + "\n  ".join(f"{f}:{line}: {text}" for f, line, text in offenders)
    )
