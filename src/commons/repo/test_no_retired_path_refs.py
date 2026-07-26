"""Guard: test docstrings and messages must not reference the retired `plugin/` or `.opencode/` paths.

The src/→dist/ cutover renamed `plugin/`→`dist/claude-code/` and `.opencode/`→`dist/opencode/`.
Test logic resolved correctly, but docstrings and error messages were left pointing at the old
paths — misleading for anyone reading a failure or grepping for an artifact. This meta-test fails
if a retired path reference creeps back into a test module's source, so the cleanup cannot rot.

Allowed: the literal filename `plugin.json` (a real file), `marketplace.json` references, and
explicit "old path must be gone" assertions (which necessarily name the retired path to assert
against it). The guard matches path-like usages (`plugin/<segment>/`, `.opencode/`) only.
"""
from __future__ import annotations

import re
from pathlib import Path

TESTS_ROOT = Path(__file__).resolve().parent   # src/commons/repo
SRC_ROOT = TESTS_ROOT.parents[1]               # src/  (this file lives at src/commons/repo/)
REPO_ROOT = TESTS_ROOT.parents[2]              # the repository root

# Retired path prefixes that should never appear as live path references in test source.
# Matches `plugin/<word>/` or `.opencode/` — a path segment after the prefix — so the literal
# file `plugin.json` (no slash + segment) is not flagged.
_RETIRED = re.compile(r"(plugin/[a-z][a-z0-9-]*/|\.opencode/)")


def _test_files() -> list[Path]:
    # hooks/tests/ is the hooks island's own Python test tree (see CODE_OF_CONDUCT.md § Testing),
    # scanned here too so a retired-path reference can't creep in there unnoticed just because it
    # sits outside tests/ itself.
    roots = [TESTS_ROOT, SRC_ROOT / "hooks" / "tests"]
    # Fail LOUDLY if a future move breaks one of these paths, rather than silently scanning less of
    # the enforcement surface — a dropped root would quietly shrink coverage of exactly src/hooks/
    # with no red test to notice.
    missing = [str(r) for r in roots if not r.is_dir()]
    assert not missing, f"retired-path guard: scan root(s) no longer exist, fix the paths: {missing}"
    found = (p for root in roots for p in root.rglob("test_*.py"))
    # Skip this guard itself — it necessarily names the retired paths in its docstring/regex/error
    # message to document and match what it forbids.
    return sorted(p for p in found if p.name != "test_no_retired_path_refs.py")


def test_old_project_folder_names_dont_linger_in_test_documentation():
    """After `plugin/` and `.opencode/` were renamed to `dist/claude-code/` and `dist/opencode/`,
    no test file's explanatory text or error messages may still mention the old folder names.
    A leftover mention would send someone chasing a failure, or searching for a file, at a path
    that no longer exists."""
    offenders: list[tuple[str, int, str]] = []
    for path in _test_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for m in _RETIRED.finditer(line):
                # Allow explicit "old path is gone" assertions — they name the retired path to
                # assert it no longer exists. Detected by a negation cue on the same line.
                if any(cue in line for cue in ('"not in', "'not in", " not in ", "must not", "should not")):
                    continue
                offenders.append((rel, i, line.strip()))
    assert not offenders, (
        "test files reference retired `plugin/` or `.opencode/` paths (rename to "
        "`dist/claude-code/` or `dist/opencode/`):\n  "
        + "\n  ".join(f"{f}:{line}: {text}" for f, line, text in offenders)
    )
