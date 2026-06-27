"""A2A protocol entry structure validation and vocabulary checks."""

import re

ALLOWED_STATUSES: frozenset[str] = frozenset(
    {"Blocker", "High", "Medium", "Nitpick", "Pass", "Info"}
)

_CORE_ENTRY_RE = re.compile(r"^\d+\.")
_ENTRY_RE = re.compile(
    r"\[[A-Z][A-Z0-9_-]*\] (Blocker|High|Medium|Nitpick|Pass|Info) \|"
)


def extract_a2a_core(md: str) -> tuple[str, bool]:
    """Extract the content of the first fenced ``` block — the injected A2A Core."""
    lines = md.split("\n")
    start = -1
    for i, line in enumerate(lines):
        if lines[i].lstrip().startswith("```"):
            if start == -1:
                start = i + 1
            else:
                return "\n".join(lines[start:i]), True
    return "", False


def count_core_entries(text: str) -> int:
    """Count top-level numbered entries (^\\d+\\.) inside a Core block.

    Continuation lines are indented and do not match.
    """
    return sum(1 for line in text.split("\n") if _CORE_ENTRY_RE.match(line))


def find_core_entry_lines(text: str) -> list[str]:
    """Return all [ROLE] STATUS | CONTENT | ACTION lines found in text."""
    out = []
    for line in text.split("\n"):
        m = _ENTRY_RE.search(line)
        if m:
            out.append(line[m.start():])
    return out


def matches_a2a_entry_format(line: str) -> bool:
    """Return True if a line matches the [ROLE] STATUS | CONTENT | ACTION structure.

    The entry must contain exactly two ' | ' field separators (three fields total).
    A bare '|' inside the CONTENT field is permitted — only ' | ' with spaces counts.
    """
    return line.count(" | ") == 2


def extract_used_statuses(text: str) -> list[str]:
    """Return the STATUS value from each A2A entry line found in text."""
    return [m.group(1) for m in _ENTRY_RE.finditer(text)]
