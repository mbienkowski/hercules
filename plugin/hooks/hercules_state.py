"""Read-only resolver for active Hercules build sessions.

Reads `~/.hercules/config.json` (the registry) and `~/.hercules/state/{slug}.json`
(the delivery state) to answer: for this working directory, which build sessions are
active, and what are their frozen test files? Never writes; never raises.

Used by the PreToolUse hook under `plugin/hooks/` and by its tests (which pass an
explicit `home` so they can point at a throwaway state tree).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def canon(p) -> str:
    """Canonicalise a path for comparison: expand ~, resolve symlinks/.., fold case.

    Folds case on macOS (default APFS is case-insensitive, so differently-cased paths
    are the same file — folding is the fail-closed direction) and on Windows (via
    normcase). Falls back to the raw string if filesystem resolution fails, so a
    comparison never throws.
    """
    try:
        resolved = os.path.realpath(os.path.expanduser(str(p)))
    except Exception:
        resolved = str(p)
    if sys.platform == "darwin":
        return resolved.lower()
    return os.path.normcase(resolved)


def _hercules_home(home=None) -> Path:
    return (Path(home) if home else Path.home()) / ".hercules"


def resolve_session(cwd, home=None):
    """Return `(session, roots, entry)` for the most authoritative matching context.

    Kept for attribution — block reasons name this session's spec — and for callers
    that want a single primary context. `resolve_build_contexts` is the guard's source
    of truth: EVERY matching build session, not just the winner. Returns
    `(None, [], None)` when nothing resolves — the fail-open direction.
    """
    contexts = resolve_build_contexts(cwd, home=home)
    if not contexts:
        return None, [], None
    return contexts[0]


def resolve_build_contexts(cwd, home=None):
    """Return `[(session, roots, entry), ...]` for every registry project containing `cwd`.

    Ordered most-authoritative first: build sessions before non-build, deeper (more
    specific) roots before shallower, a state file's active session before its paused
    ones. Registered roots can nest (a monorepo project plus an inner service project),
    several slugs can share one directory, and one state file can hold several build
    sessions — a single-winner resolution would silently drop the losers' frozen-test
    guards, so every build session rides along. When nothing is building, the deepest
    project's active session (if any) is returned alone so callers can see the phase.
    Never raises.
    """
    try:
        config = json.loads((_hercules_home(home) / "config.json").read_text())
        projects = config.get("projects", {}) or {}
    except Exception:
        return []

    cwd_c = canon(cwd)
    build_rows = []     # (depth, session, roots, entry); appended active-first per project
    fallback_rows = []  # non-build active sessions, kept for phase visibility
    for slug, entry in projects.items():
        try:
            raw_roots = [entry.get("directory")] + list((entry.get("repositories") or {}).values())
            roots = [canon(r) for r in raw_roots if r]
            matched = [r for r in roots if cwd_c == r or cwd_c.startswith(r + os.sep)]
            if not matched:
                continue  # unrelated repo → pure passthrough
            state_file = entry.get("state_file") or f"{slug}.json"
            if os.path.basename(state_file) != state_file:
                continue  # a pointer escaping ~/.hercules/state is never followed
            state = json.loads((_hercules_home(home) / "state" / state_file).read_text())
            sessions = state.get("sessions") or {}
            depth = max(len(r) for r in matched)
            active = sessions.get(state.get("active_session"))
            builds = [active] if isinstance(active, dict) and active.get("current_phase") == "build" else []
            builds += [s for s in sessions.values()
                       if s is not active and isinstance(s, dict) and s.get("current_phase") == "build"]
            if builds:
                build_rows += [(depth, s, roots, entry) for s in builds]
            elif isinstance(active, dict):
                fallback_rows.append((depth, active, roots, entry))
        except Exception:
            continue
    # Stable sort: deepest project first; within a project the insertion order stands
    # (active session first, then paused builds in file order).
    build_rows.sort(key=lambda r: r[0], reverse=True)
    if build_rows:
        return [(s, r, e) for _, s, r, e in build_rows]
    fallback_rows.sort(key=lambda r: r[0], reverse=True)
    return [(s, r, e) for _, s, r, e in fallback_rows[:1]]


def frozen_candidates(entry, roots) -> set:
    """Canonical paths a (usually repo-relative) frozen-test entry could denote.

    `frozen_test_files` are stored repo-relative (e.g. `tests/auth/test_login.py`); the tool
    sends an absolute `file_path`. Resolve the entry against every project root and keep every
    candidate that exists on disk (handles multi-service repos where the same relative path may
    live under a `repositories.*` root). If none exist, EVERY root stays guarded — matching
    under *any* root counts as frozen, the fail-closed direction for the flagship guard.
    Junk entries (non-string, empty) resolve to nothing rather than poisoning the caller's
    whole frozen set.
    """
    if not isinstance(entry, str) or not entry:
        return set()
    if os.path.isabs(entry):
        return {canon(entry)}
    existing = {canon(os.path.join(root, entry)) for root in roots if os.path.exists(os.path.join(root, entry))}
    if existing:
        return existing
    return {canon(os.path.join(root, entry)) for root in roots} or {canon(entry)}
