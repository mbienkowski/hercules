"""Shared constants for the command-contract test files.

These regexes and section windows are used across the split test_*.py files in this package
(shared test infrastructure, not per-test data). The command *paths* and the `section()` helper
live in the root tests/conftest.py; import them from there.
"""

from __future__ import annotations

import re

# Section window reused by several build.md tests (start ↔ stop, lowercased).
_RETIRE_STEP = ("10. **retire the spec.**", "for a spec scoped")

_BAD_DATE_RE = re.compile(r"YYYY-DD-MM")
_ISO_DATE_RE = re.compile(r"YYYY-MM-DD")
# Letter-suffixed step labels (Step 4a, ## 1b, **4a —). Single letter + boundary so prose
# like "3am" (two letters, no boundary) is never flagged.
_LETTER_STEP_RE = re.compile(r"\bStep \d+[a-z]\b|^#+\s*\d+[a-z]\b|^\s*\*\*\d+[a-z]\b", re.MULTILINE)
