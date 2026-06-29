"""Instruction and status-table row counting in markdown files."""

import re

_NUMBERED_RE = re.compile(r"^\s*\d+\.\s")
_BULLET_RE = re.compile(r"^\s*[-*]\s")


def count_instructions(text: str) -> int:
    """Count numbered and bulleted list items, excluding any inside fenced code blocks.

    Table rows start with ``|`` and never match a list-item pattern, so they are excluded
    automatically — no explicit table check is needed here.
    """
    n = 0
    in_fence = False  # pragma: no mutate — sole mutant (False→None) is equivalent: None is falsy like False
    for line in text.split("\n"):
        stripped = line.lstrip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if _NUMBERED_RE.match(line) or _BULLET_RE.match(line):
            n += 1
    return n


def count_status_table_rows(text: str) -> int:
    """Count data rows in the STATUS reference table (header: STATUS | Meaning | ACTION).

    Returns -1 when no matching header row is found.
    """
    lines = text.split("\n")
    header_index = -1
    for i, line in enumerate(lines):
        stripped = line.strip()
        if (
            stripped.startswith("|")
            and "STATUS" in stripped
            and "Meaning" in stripped
            and "ACTION" in stripped
        ):
            header_index = i
            break
    if header_index == -1:
        return -1

    n = 0
    for line in lines[header_index + 2:]:  # skip header row + separator row
        if not line.strip().startswith("|"):
            break
        n += 1
    return n
