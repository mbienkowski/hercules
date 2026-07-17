"""Stage 1 — Python 3.9 floor, README path fix, and branch-naming convention.

These are content/regression checks read as raw text (NOT via tomllib, which is
absent on Python 3.9 — the very floor this suite must run on).
"""

from __future__ import annotations

import re
