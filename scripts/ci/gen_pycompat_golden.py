"""Regenerate the pyCompat golden dump from CPython.

scripts-ts/build/pyCompat.mts reproduces Python's ``str.isspace()``, ``str.splitlines()`` and
``str.isprintable()``. This dumps those classifications so the TypeScript tests assert against
CPython itself rather than against a hand-maintained copy of it — otherwise a typo in the table
would be pinned by a test that shares the typo.

**Run it with the interpreter CI pins**, not whatever is on your PATH. Character classification is
Unicode-version dependent: CPython 3.9 ships Unicode 13.0 and 3.12 ships Unicode 15.0, which
disagree on 93 code points below U+3101. The parity harness compares the TypeScript port against
whichever Python is executing, so the port must match CI's. The recorded ``unidataVersion`` is what
``make pycompat-golden-check`` verifies.

Usage:
    python scripts/ci/gen_pycompat_golden.py [output-path]

With no argument it rewrites the tracked golden file; with one it writes elsewhere, which is how the
CI freshness check compares without mutating the repository.
"""

from __future__ import annotations

import json
import sys
import unicodedata
from pathlib import Path

DEFAULT_OUT = Path(__file__).resolve().parents[2] / "tests" / "testdata" / "pycompat-golden.json"

# pyRepr's documented ceiling. Above this, characters are emitted literally.
PRINTABLE_CEILING = 0x3101
# str.isspace() and str.splitlines() are surveyed over the whole BMP plus SMP boundary.
SURVEY_CEILING = 0x11000


def build() -> dict[str, object]:
    return {
        "_comment": [
            "Generated from CPython by scripts/ci/gen_pycompat_golden.py. The TypeScript pyCompat",
            "tables are asserted against this, so a hand-edited table cannot silently drift from the",
            "semantics it claims to reproduce.",
            "",
            "unidataVersion records WHICH Unicode database produced it. Character classification is",
            "version dependent (3.9 ships Unicode 13.0, 3.12 ships 15.0, disagreeing on 93 code",
            "points below U+3101), so this must be generated with the interpreter CI pins.",
            "`make pycompat-golden-check` fails if the committed file does not match a regeneration.",
        ],
        "pythonVersion": ".".join(str(part) for part in sys.version_info[:2]),
        "unidataVersion": unicodedata.unidata_version,
        "whitespace": [cp for cp in range(SURVEY_CEILING) if chr(cp).isspace()],
        "lineBoundaries": [
            cp for cp in range(SURVEY_CEILING) if (chr(cp) + "x").splitlines() != [chr(cp) + "x"]
        ],
        "nonPrintableBelow0x3101": [
            cp for cp in range(PRINTABLE_CEILING) if not chr(cp).isprintable() and cp != 0x20
        ],
    }


def main(argv: list[str]) -> int:
    out = Path(argv[1]) if len(argv) > 1 else DEFAULT_OUT
    payload = build()
    out.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    print(
        f"wrote {out} (python {payload['pythonVersion']}, unicode {payload['unidataVersion']})",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
