"""Repo-wide setup for the tools island: only an env var (never the process-local
`sys.dont_write_bytecode`) stops a subprocess that spawns a shipped script from dropping a
`__pycache__` into the committed `dist/` tree, so it is set once here rather than per test.
"""

from __future__ import annotations

import os

os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
