"""Read-only resolver for the active Hercules build session.

Reads `~/.hercules/config.json` (the registry) and `~/.hercules/state/{slug}.json`
(the delivery state) to answer: for this working directory, is there an active build
session, and what are its frozen test files? Never writes; never raises.

Used by the PreToolUse hooks under `plugin/hooks/` and by their tests (which pass an
explicit `home` so they can point at a throwaway state tree).
"""

from __future__ import annotations

import json
import os
from pathlib import Path


def canon(p) -> str:
    """Canonicalise a path for comparison: expand ~, resolve symlinks/.., normcase.

    Falls back to a normcase of the raw string if the filesystem resolution fails, so a
    comparison never throws.
    """
    try:
        return os.path.normcase(os.path.realpath(os.path.expanduser(str(p))))
    except Exception:
        return os.path.normcase(str(p))


def _hercules_home(home=None) -> Path:
    return (Path(home) if home else Path.home()) / ".hercules"


def resolve_session(cwd, home=None):
    """Return `(session, roots)` for the active project whose tree contains `cwd`.

    `session` is the active session dict from the state file; `roots` is the list of
    canonical project roots (the project `directory` plus every `repositories.*` path,
    so multi-service builds resolve). Returns `(None, [])` when nothing active resolves
    — which the guards treat as fail-open. Never raises.
    """
    try:
        config = json.loads((_hercules_home(home) / "config.json").read_text())
        projects = config.get("projects", {}) or {}
    except Exception:
        return None, []

    cwd_c = canon(cwd)
    for slug, entry in projects.items():
        try:
            raw_roots = [entry.get("directory")] + list((entry.get("repositories") or {}).values())
            roots = [canon(r) for r in raw_roots if r]
            # cwd must sit inside one of this project's roots (exact or a subdirectory),
            # so a hook firing in an unrelated repo is a pure passthrough.
            if not any(cwd_c == r or cwd_c.startswith(r + os.sep) for r in roots):
                continue
            state_file = entry.get("state_file") or f"{slug}.json"
            state = json.loads((_hercules_home(home) / "state" / state_file).read_text())
            session = (state.get("sessions") or {}).get(state.get("active_session"))
            if session:
                return session, roots
        except Exception:
            continue
    return None, []


def frozen_candidates(entry, roots) -> set:
    """Canonical paths a (usually repo-relative) frozen-test entry could denote.

    `frozen_test_files` are stored repo-relative (e.g. `tests/auth/test_login.py`); the tool
    sends an absolute `file_path`. Resolve the entry against every project root and keep every
    candidate that exists on disk (handles multi-service repos where the same relative path may
    live under a `repositories.*` root). If none exist, fall back to the first root — matching
    under *any* root counts as frozen, the fail-closed direction for the flagship guard.
    """
    if os.path.isabs(entry):
        return {canon(entry)}
    existing = {canon(os.path.join(root, entry)) for root in roots if os.path.exists(os.path.join(root, entry))}
    if existing:
        return existing
    return {canon(os.path.join(roots[0], entry))} if roots else {canon(entry)}
