"""Guard: every path the pre-commit hook watches is a path this repository actually has. A pattern
matching nothing looks exactly like a pattern with nothing to match, so a stale path leaves ``dist/``
unbuilt and the commit sails through — silent by construction.
The patterns are therefore read out of the hook itself, each required to name something on disk, and
finding no patterns at all fails: an unparseable hook must not read as a hook with nothing wrong.
Whether the set is COMPLETE is deliberately not checked; nothing mechanical can know that."""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK = REPO_ROOT / ".githooks" / "pre-commit"

# `^src/content/` -> `src/content`; `^src/scripts/(hooks|tools)/…` -> both alternatives expanded.
_ANCHORED = re.compile(r"\^([A-Za-z0-9_./()|\\\[\]+$-]+)")


def _prefixes() -> list[str]:
    """Every anchored path prefix in the hook's grep pattern, alternations expanded."""
    match = re.search(r'grep -qE "([^"]+)"', HOOK.read_text())
    assert match, "the pre-commit hook no longer contains a grep -qE pattern to read"
    found: list[str] = []
    for raw in match.group(1).split("|^"):
        raw = raw.lstrip("^")
        # A literal dot, unescaped before splitting, or `^package\.json$` truncates to a fake directory.
        raw = raw.replace("\\.", ".")
        # Stop at the first WILDCARD, whichever spelling the hook uses. Splitting on `[` alone tied
        # this guard to one metacharacter: rewriting `[^/]+\.py` as `.*\.py` — the same intent, one
        # directory deeper — left `src/scripts/hooks/.*.py` looking like a path nobody has.
        head = re.split(r"[\[$\\*]", raw)[0]
        group = re.search(r"\(([^)]+)\)", head)
        if group:
            before, after = head.split(group.group(0), 1)
            found.extend(f"{before}{option}{after}" for option in group.group(1).split("|"))
        else:
            found.append(head)
    return [p for p in (f.rstrip("/.") for f in found) if p]


def test_every_path_the_hook_watches_is_a_path_that_exists():
    """A pattern naming a directory nobody has leaves dist/ stale and says nothing about it."""
    prefixes = _prefixes()
    assert len(prefixes) >= 3, f"found only {prefixes} — the hook's pattern is no longer being read"
    missing = [p for p in prefixes if not (REPO_ROOT / p).exists()]
    assert not missing, (
        "the pre-commit hook watches paths this repository does not have, so a change under the "
        f"REAL path never triggers a rebuild: {missing}"
    )
