"""Read-only resolver for active Hercules build sessions: which builds own a working directory, and
which test files each of them freezes. Reads `~/.hercules` only — never writes, never raises."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def canon(p) -> str:
    """Canonicalise a path for comparison: expand ~, resolve symlinks/.., fold case on macOS and
    Windows where two casings name one file. Falls back to the raw string, so it never throws."""
    try:
        resolved = os.path.realpath(os.path.expanduser(str(p)))
    except Exception:
        resolved = str(p)
    if sys.platform == "darwin":
        return resolved.lower()
    return os.path.normcase(resolved)


def _hercules_home(home=None) -> Path:
    """The machine-local record tree; `home` redirects it at a fixture tree in tests."""
    return (Path(home) if home else Path.home()) / ".hercules"


def resolve_session(cwd, home=None):
    """The single most authoritative context for `cwd` as `(session, roots, entry)` — the one a block
    message names — or `(None, [], None)`. Enforcement uses `resolve_build_contexts`, not this."""
    contexts = resolve_build_contexts(cwd, home=home)
    if not contexts:
        return None, [], None
    return contexts[0]


def _is_within_root(cwd_c, root):
    """True if `cwd_c` IS `root` or lives inside it, matching whole path components so `/a/proj` is
    not treated as inside `/a/project`."""
    return cwd_c == root or cwd_c.startswith(root + os.sep)


def _build_sessions(sessions, active):
    """Every build session, the active one first and then any paused builds in file order."""
    ordered = [active] if isinstance(active, dict) and active.get("current_phase") == "build" else []
    ordered += [s for s in sessions.values()
                if s is not active and isinstance(s, dict) and s.get("current_phase") == "build"]
    return ordered


def _project_rows(slug, entry, cwd_c, home):
    """One registry project's rows for `cwd_c` as `(build_rows, fallback_rows)` of `(depth, session,
    roots, entry)`: every build session, or the active one alone when nothing is building."""

    # The project's own directory plus every extra repository it registers, all canonicalised.
    raw_roots = [entry.get("directory")] + list((entry.get("repositories") or {}).values())
    roots = [canon(r) for r in raw_roots if r]
    matched = [r for r in roots if _is_within_root(cwd_c, r)]
    if not matched:
        return [], []  # unrelated repo → pure passthrough
    state_file = entry.get("state_file") or f"{slug}.json"
    if os.path.basename(state_file) != state_file:
        return [], []  # a pointer escaping ~/.hercules/state is never followed
    state = json.loads((_hercules_home(home) / "state" / state_file).read_text())
    sessions = state.get("sessions") or {}

    # Path length stands in for specificity: a longer matched root is a deeper, more specific match.
    depth = max(len(r) for r in matched)
    active = sessions.get(state.get("active_session"))
    builds = _build_sessions(sessions, active)
    if builds:
        return [(depth, s, roots, entry) for s in builds], []
    if isinstance(active, dict):
        return [], [(depth, active, roots, entry)]
    return [], []


def resolve_build_contexts(cwd, home=None):
    """Every build session guarding `cwd`, deepest root first, active before paused — ALL of them,
    since one winner would drop the losers' freezes. The active session alone when nothing builds."""
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
            builds, fallback = _project_rows(slug, entry, cwd_c, home)
        except Exception:
            continue  # this project's state is unreadable → skip it, guard the rest
        build_rows += builds
        fallback_rows += fallback

    # Stable sort: deepest project first, and within a project the insertion order stands.
    build_rows.sort(key=lambda r: r[0], reverse=True)
    if build_rows:
        return [(s, r, e) for _, s, r, e in build_rows]
    fallback_rows.sort(key=lambda r: r[0], reverse=True)
    return [(s, r, e) for _, s, r, e in fallback_rows[:1]]


def frozen_candidates(entry, roots) -> set:
    """Canonical paths a frozen-test entry could denote — joined to EVERY project root, existing or
    not, so a multi-repo project cannot dodge a freeze. A junk entry resolves to nothing."""
    if not isinstance(entry, str) or not entry:
        return set()
    if os.path.isabs(entry):
        return {canon(entry)}
    return {canon(os.path.join(root, entry)) for root in roots} or {canon(entry)}
