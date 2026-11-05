"""The shared project-memory core: the one host-independent body every ecosystem drives to give an
agent standing context that grows across chats, in ANY repo, without per-repo config.

It is the canonical store for machine-local auto-memory, kept at
``~/.hercules/memory/<slug>/``:
  ``entries.md``    the human-readable, versioned, machine-parseable source of truth.
  ``index.db``      a REBUILDABLE search index over ``entries.md`` (best-effort; select works
                    without it, scanning the canonical file, so the canonical text is never the
                    index's hostage).
  ``stats.json``    hit-rate counters — authoritative and NON-rebuildable; the index is, these are
                    not, because a rebuild would silently erase what we learned about usefulness.
  ``checkpoints/``  task state (progress, verification, blockers, next step) per task.
  ``~/.hercules/memory/.deliveries.json`` one GLOBAL file of bounded per-slug+session delivery
                    fingerprints, suppressing unchanged context (no per-repo directory is created).

This is the NEW store. The committed ``docs/learnings.md`` + the phase-anchored ``learnings`` skill
are UNTOUCHED; an entry reaches them only through the explicit ``promote`` op, which is the ONE
path that may write the committed store, and only with ``--confirm`` (invariant I1).

Safeguards (M1–M9), each enforced here, not
in prose:
  M1 relevance before popularity        — an entry with zero relevance is never surfaced by its
                                          hit-count; only pinned decisions stand as context.
  M2 an empty result is valid          — no match returns status "no-match", never an error.
  M3 provenance + status               — every entry carries who/when/what-version captured it and a
                                          status; a "hypothesis" is labelled and never governing.
  M4 changed evidence needs re-verify   — an entry records the code version its evidence was checked
                                          against; a mismatch flags "verification-required", it does
                                          not silently pass.
  M5 no silent conflict resolution      — two active entries on one topic are surfaced as a conflict;
                                          the core never picks a winner.
  M6 usage references existing revisions — caller-reported use is deduped by task + entry+revision;
                                          this is not independent evidence of actual application.
  M7 a fixed response budget            — over budget we omit WHOLE entries, never cut mid-entry.
  M8 memory directs, it does not permit — selection returns context; it authorises no action.
  M9 we evaluate omissions             — a "no-match" and a truncated result name what they omitted.

Determinism: the PROCESS is repeatable (a host event starts it; idempotent; visible on start/fail/
complete). SELECTION is deterministic — same inputs + policy version + store state give the same
result; NO date or age enters ranking (we never forget the old, M-no-time-decay). EXTRACTION
(turning a chat into entries) is non-deterministic and lives at the caller; equivalent statements
are deduplicated conservatively, while different statements remain visible for review.

Stdlib-only, byte-copied like every tool in this tree: no shebang, no third-party import. Path
canonicalisation is LOADED from ``hooks/hercules_state.py`` by file path (never re-derived, so tools
and hooks stay independently copyable). A write is atomic (temp in the same directory, fsync, then
``os.replace``) and per-slug serialised by a lock file, so a hook-fired and a model-fired write
never race the model's own state — the memory subtree is disjoint from it. A missing ``python3``, an
unwritable directory, or an unregistered project is a VISIBLE, unrecorded limitation. The tool itself fails CLOSED like
every other write tool; the HOST-FIRED hook that invokes it is the fail-open layer, so a memory
failure never crashes the caller's session.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

EXIT_OK = 0
EXIT_NO_MATCH = 0          # a valid empty result is not an error (M2)
EXIT_NO_PROJECT = 1        # no slug could be resolved for the directory
EXIT_CONFLICT = 2         # the store holds a conflict the caller must resolve (M5)
EXIT_INTERNAL = 3
EXIT_UNCONFIRMED = 4
EXIT_REFUSED = 5

POLICY_VERSION = 2        # the selection policy; a change bumps it and the result records it
DEFAULT_STANDING_BUDGET = 8   # entries a no-query standing-context request returns, by default
DEFAULT_BYTE_BUDGET = 16_384  # conservative UTF-8 budget for complete serialized entries
FORMAT_VERSION = 1        # the on-disk entry format
KINDS = ("decision", "correction", "constraint", "verified-finding", "hypothesis")
STATUS = ("active", "superseded", "pending-verification")
# Confidence: higher ranks surface first WITHIN equal relevance. Popularity never outranks it (M1).
CONFIDENCE = {"verified-finding": 5, "decision": 4, "correction": 3, "constraint": 2, "hypothesis": 1}


class Refused(Exception):
    """A refusal the caller can read and act on — never a crash."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class Internal(Exception):
    """The store could not be read, written, or verified."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


# ── Identity, canonicalisation, the tree root — loaded, never re-derived ─────────────────────────

def hercules_home(home=None) -> Path:
    """The state tree root. ``home`` is a PARAMETER, not a flag, so no caller can redirect the tree
    at another ``~/.hercules``."""
    # The caller trusts HOME itself; only redirects below its canonical anchor are refused.
    return (Path(home) if home is not None else Path.home()).resolve() / ".hercules"


def is_within(child_c: str, root_c: str) -> bool:
    """True when ``child_c`` IS ``root_c`` or lives inside it, matching whole path components so
    ``/a/proj`` is not read as inside ``/a/project``."""
    return child_c == root_c or child_c.startswith(root_c + os.sep)


def _load_hercules_state():
    """Load the sibling ``hooks/hercules_state.py`` by file path — never a package import — so
    ``tools/`` and ``hooks/`` stay independently copyable. Raises ``Internal`` when it cannot load."""
    hooks_path = Path(__file__).resolve().parent.parent / "hooks" / "hercules_state.py"
    try:
        spec = importlib.util.spec_from_file_location("_memory_core_hercules_state", hooks_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception as exc:  # pragma: no cover - depends on tree layout, guarded by a test
        raise Internal(f"Could not load the path resolver ({hooks_path}). Nothing was changed. {exc}") \
            from exc


# ── The memory gate: a write may only ever land inside this project's memory subtree ────────────────

def memory_root(slug_c: str, home=None) -> Path:
    """``~/.hercules/memory/<slug>/`` — the ONLY subtree a memory write may touch. Every path the
    core writes is proven to live inside it (the memory-root containment invariant, I3)."""
    root = hercules_home(home) / "memory"
    slug = slug_c
    if not isinstance(slug, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", slug):
        raise Refused("bad_slug", f"Refusing to write under a slug that would escape the tree: '{slug}'.")
    path = root / slug
    _refuse_symlinks(path)
    return path


def _refuse_symlinks(path: Path) -> None:
    """Check lexical ancestors too: resolving first would trust a redirected boundary."""
    path = Path(os.path.abspath(path))
    for part in (path, *path.parents):
        if part.is_symlink():
            raise Refused("symlink", f"Refusing a symlink in the trusted path: {part}.")


def _assert_within_memory_root(path: Path, root: Path) -> None:
    """Refuse a path that would escape the memory subtree — the one thing auto-capture must never
    do (it can never reach the repo, docs/learnings.md, or code-of-conduct.md)."""
    _refuse_symlinks(root)
    _refuse_symlinks(path)
    try:
        pc = Path(path).resolve()
    except OSError as exc:
        raise Internal(f"Could not resolve the memory path {path}. Nothing was changed. {exc}") from exc
    rc = root.resolve()
    if not is_within(str(pc), str(rc)):
        raise Refused("path_escape",
                      f"Refusing to write {path}: it is outside the memory subtree {rc}.")


# ── Atomic, per-slug-serialised writes ────────────────────────────────────────────────────────────

def _atomic_write(path: Path, text: str, within_root: Path) -> None:
    """Write through a temp file in the SAME directory — flush, fsync, carry the original's mode,
    then ``os.replace`` (atomic on POSIX and Windows). The path is proven to live inside ``within_root``
    (the memory subtree this write was authorised for) before it is written."""
    _assert_within_memory_root(path, within_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = text if text.endswith("\n") else text + "\n"
    try:
        mode = os.stat(path).st_mode & 0o777 if path.exists() else 0o644
        handle, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".mem.")
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except OSError as exc:
        raise Internal(f"Could not write {path}. The original is unchanged. {exc.strerror or exc}") \
            from exc


def _acquire(attempt, busy, attempts) -> None:
    """Retry an exclusive lock every 10 ms for ``attempts`` tries, then refuse as busy. Host events pass
    a ~100 ms budget so a prompt never waits; model-fired writes wait up to ~5 s."""
    for _ in range(attempts):
        try:
            attempt()
            return
        except busy:
            time.sleep(0.01)
    raise Refused("busy", "Memory is busy with another write. Nothing was changed; try again.")


class _SlugLock:
    """Per-slug POSIX/Windows lock; inability to lock refuses every mutation. The global delivery
    lock reuses it with ``lock_name`` on ``memory/``, which holds no entries.md or stats.json."""

    def __init__(self, root: Path, lock_name: str = ".lock", attempts: int = 500):
        self.root = root
        self.lock_file = root / lock_name
        self.attempts = attempts
        self._fh = None

    def __enter__(self):
        _assert_within_memory_root(self.lock_file, self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            self._fh = open(self.lock_file, "a+b")
            if os.name == "nt":
                import msvcrt
                if self._fh.seek(0, os.SEEK_END) == 0:
                    self._fh.write(b"\0")
                    self._fh.flush()
                self._fh.seek(0)
                _acquire(lambda: msvcrt.locking(self._fh.fileno(), msvcrt.LK_NBLCK, 1), OSError, self.attempts)
            else:
                import fcntl
                _acquire(lambda: fcntl.flock(self._fh, fcntl.LOCK_EX | fcntl.LOCK_NB), BlockingIOError,
                         self.attempts)
            # Both files are authoritative. No operation may rewrite a partial recovery.
            load_entries(self.root)
            load_stats(self.root)
        except Exception as exc:
            if self._fh is not None:
                self._fh.close()
            if isinstance(exc, (Refused, Internal)):
                raise
            raise Internal(f"Could not lock memory. Nothing was changed. {exc}") from exc
        return self

    def __exit__(self, *exc):
        try:
            if os.name == "nt":
                import msvcrt
                self._fh.seek(0)
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._fh, fcntl.LOCK_UN)
        finally:
            self._fh.close()


# ── Slug resolution: the directory's project, never a model-supplied string ────────────────────────

def _registered_roots(entry):
    """Registry-relative paths belong to the registered directory, never process cwd."""
    directory = Path(entry.get("directory") or "").expanduser()
    if not directory.is_absolute():
        raise Refused("bad_registry", "Registered project directories must be absolute.")
    raw = [str(directory), entry.get("docs_root")] + list((entry.get("repositories") or {}).values())
    return [str((Path(value).expanduser() if Path(value).expanduser().is_absolute()
                 else directory / value).resolve()) for value in raw if value]


def _fallback_slug(canonical):
    repo_root = Path(canonical)
    for parent in (repo_root, *repo_root.parents):
        if (parent / ".git").exists():
            repo_root = parent
            break
    name = re.sub(r"[^A-Za-z0-9._-]", "-", repo_root.name).lstrip(".") or "project"
    return f"{name}-{hashlib.sha256(str(repo_root).encode('utf-8')).hexdigest()[:12]}"


def _registered_match(projects, cwd_c, hercules_state):
    matches = []
    for slug, entry in projects.items():
        if isinstance(entry, dict):
            depths = [len(r) for root in _registered_roots(entry)
                      if is_within(cwd_c, r := hercules_state.canon(root))]
            if depths:
                matches.append((max(depths), slug, entry))
    matches.sort(key=lambda row: (-row[0], row[1]))
    if len(matches) > 1 and matches[0][0] == matches[1][0]:
        raise Refused("ambiguous_project", "Equally specific projects match; fix the registry first.")
    return matches[0] if matches else None


def resolve_slug(cwd: str, home=None, hercules_state=None) -> str | None:
    """Resolve the deepest registered project, retaining memory created before registration."""
    hercules_state = hercules_state or _load_hercules_state()
    cwd_c = hercules_state.canon(cwd)
    config_path = hercules_home(home) / "config.json"
    _refuse_symlinks(config_path)
    try:
        projects = json.loads(config_path.read_text(encoding="utf-8")).get("projects") or {}
    except FileNotFoundError:
        projects = {}
    except (OSError, ValueError, AttributeError) as exc:
        raise Refused("bad_registry", "Project registry unreadable; memory identity unchanged.") from exc
    match = _registered_match(projects, cwd_c, hercules_state)
    if match is None:
        return _fallback_slug(cwd_c)
    _, slug, entry = match
    # Keep the existing store in place: registration must not strand ordinary-chat memories.
    identities = {slug}
    anchors = [entry["directory"]] + list((entry.get("repositories") or {}).values())
    for anchor in anchors:
        directory = Path(entry["directory"]).expanduser()
        path = Path(anchor).expanduser()
        identities.add(_fallback_slug(hercules_state.canon(str(path if path.is_absolute() else directory / path))))
    # A nested registration must not adopt its parent's pre-registration repository store.
    parent_identities = {_fallback_slug(hercules_state.canon(other["directory"]))
                         for other_slug, other in projects.items()
                         if other_slug != slug and isinstance(other, dict) and other.get("directory")
                         and is_within(hercules_state.canon(entry["directory"]),
                                       hercules_state.canon(other["directory"]))}
    identities = {identity for identity in identities if identity == slug or identity not in parent_identities}
    existing = [identity for identity in identities if (memory_root(identity, home) / "entries.md").exists()]
    if len(existing) > 1:
        raise Refused("ambiguous_memory", "Multiple pre-existing project stores; reconcile explicitly first.")
    return existing[0] if existing else slug


# ── The canonical store: entries.md ────────────────────────────────────────────────────────────────

_ENTRY_MARKER = "<!-- entry:%s -->"
_BLOCK_RE = re.compile(r"<!-- entry:(?P<id>[^>]+) -->\s*\n(?:(?!\n<!-- entry:).)*?```json\n"
                       r"(?P<body>.*?)\n```", re.DOTALL)


def _render_entry(entry: dict) -> str:
    """One entry: a human-readable heading (derived, non-authoritative) over the authoritative JSON
    block. A future backend reads the same block; a human reads the heading + statement."""
    heading = f"[{entry['id']}] {entry.get('kind', '?')} · {entry.get('status', 'active')}"
    statement = (entry.get("statement") or "").strip().split("\n", 1)[0]
    statement = statement.replace("<!--", "&lt;!--").replace("`", "&#96;")
    return f"{_ENTRY_MARKER % entry['id']}\n## {heading}\n{statement}\n\n" \
           f"```json\n{json.dumps(entry, indent=2, ensure_ascii=True, sort_keys=True)}\n```\n"


def _entries_header(root: Path) -> str:
    return (f"# Project memory for `{os.path.basename(root)}`\n\n"
              "Machine-local auto-memory, generated from chats. Human-readable and versioned; "
              "searchable. The committed `docs/learnings.md` is a separate, human-curated store; "
              "an entry reaches it only through `promote`. Pinned decisions are standing context.\n")


def load_entries(root: Path) -> list:
    """Fail closed on malformed canonical data rather than silently dropping it on rewrite."""
    path = root / "entries.md"
    _assert_within_memory_root(path, root)
    if not path.exists():
        return []
    try:
        text = path.read_text(encoding="utf-8")
        matches = list(_BLOCK_RE.finditer(text))
        entries = []
        seen = set()
        for match in matches:
            entry = json.loads(match.group("body"))
            if (not isinstance(entry, dict) or entry.get("id") != match.group("id")
                    or not re.fullmatch(r"M:[0-9]+", entry.get("id", ""))
                    or entry["id"] in seen
                    or type(entry.get("revision")) is not int or entry["revision"] < 1
                    or entry.get("kind") not in KINDS or entry.get("status") not in STATUS
                    or not isinstance(entry.get("statement"), str)
                    or not isinstance(entry.get("scope"), str)
                    or not isinstance(entry.get("provenance"), dict)
                    or not isinstance(entry.get("evidence"), dict)
                    or not isinstance(entry.get("rationale", ""), str)
                    or (entry.get("topic") is not None and not isinstance(entry["topic"], str))
                    or type(entry.get("repetitions", 1)) is not int
                    or entry.get("repetitions", 1) < 1):
                raise ValueError("invalid entry schema or duplicate id")
            seen.add(entry["id"])
            entries.append(entry)
        # Preserve nothing by guessing: even a truncated final block must refuse mutations.
        header = text.split("<!-- entry:", 1)[0]
        expected = "\n".join(_render_entry(e) for e in entries)
        if (header != _entries_header(root)
                or text[len(header):].strip() != expected.strip()
                or (not entries and "```" in header)):
            raise ValueError("unrecognized or incomplete entry blocks")
        return entries
    except (ValueError, OSError, TypeError) as exc:
        raise Refused("corrupt_entries", f"Cannot safely parse {path}; bytes preserved. {exc}") from exc


def save_entries(root: Path, entries: list) -> None:
    """Rewrite ``entries.md`` from ``entries`` in a stable order (by id, then revision), atomically."""
    ordered = sorted(entries, key=lambda e: (e.get("id", ""), e.get("revision", 0)))
    body = "\n".join(_render_entry(e) for e in ordered)
    header = _entries_header(root)
    _atomic_write(root / "entries.md", header + body, within_root=root)


def _next_id(entries: list, prefix: str) -> str:
    nums = [int(e["id"].split(":", 1)[1]) for e in entries
            if e.get("id", "").startswith(prefix + ":")
            and e["id"].split(":", 1)[1].isdigit()]
    return f"{prefix}:{max(nums) + 1 if nums else 1:04d}"


# ── Usage stats (authoritative, non-rebuildable) ──────────────────────────────────────────────────

def load_stats(root: Path) -> dict:
    path = root / "stats.json"
    _assert_within_memory_root(path, root)
    if not path.exists():
        return {"hits": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if (not isinstance(data, dict) or not isinstance(data.get("hits"), dict)
                or any(type(v) is not int or v < 0 for v in data["hits"].values())
                or type(data.get("last_id", 0)) is not int or data.get("last_id", 0) < 0
                or not isinstance(data.get("use_log", []), list)
                or any(not isinstance(u, dict) or not isinstance(u.get("task"), str)
                       or not isinstance(u.get("ref"), str) for u in data.get("use_log", []))):
            raise ValueError("invalid stats schema")
        return data
    except (ValueError, OSError, TypeError) as exc:
        raise Refused("corrupt_stats", f"Cannot safely parse {path}; bytes preserved. {exc}") from exc


def save_stats(root: Path, stats: dict) -> None:
    _atomic_write(root / "stats.json", json.dumps(stats, indent=2, sort_keys=True), within_root=root)


# ── Selection: deterministic, relevance→confidence→usefulness, NO time decay ───────────────────────

def _tokenize(text: str) -> set:
    return {t for t in re.split(r"\W+", text.lower()) if t}


def _relevance(query: str, entry: dict) -> int:
    """Deterministic relevance: word overlap between the query and the entry's surface. No model, no
    date. An empty query gives every active entry a baseline so standing context still loads."""
    if not query:
        return 1 if entry.get("pinned") else 0
    q = _tokenize(query)
    surface = _tokenize(f"{entry.get('statement', '')} {entry.get('rationale', '')} "
                        f"{entry.get('scope', '')} {entry.get('kind', '')}")
    return len(q & surface)


def _confidence(entry: dict) -> int:
    return CONFIDENCE.get(entry.get("kind", "hypothesis"), 0)


def _usefulness(entry: dict, stats: dict) -> int:
    """Hit-count popularity, used only as the LAST tie-breaker so it can never outrank relevance
    (M1)."""
    return int(stats.get("hits", {}).get(f"{entry.get('id')}:{entry.get('revision')}", 0))


def load_snapshot(cwd: str, home=None):
    """Read the directory's store once: ``(slug, entries, stats)``, or None when no project resolves.
    Read-only, and creates no per-slug directory. A caller issuing several selections passes the
    result to each ``select_context`` so the canonical file is parsed once."""
    slug = resolve_slug(cwd, home, _load_hercules_state())
    if slug is None:
        return None
    root = memory_root(slug, home)
    return slug, load_entries(root), load_stats(root)


def select_context(cwd: str, query: str = "", task: str = "", layers=None,
                   budget: int | None = None, include_hypotheses: bool = False,
                   current_code_version: str | None = None, home=None,
                   byte_budget: int = DEFAULT_BYTE_BUDGET, snapshot=None) -> dict:
    """The read path. Returns context for the directory, bounded and conflict-aware. Never writes.
    Honours M1–M9; an empty or partial result is a valid, fully-reasoned outcome, not an error."""
    if (budget is not None and budget < 0) or byte_budget < 2:
        raise Refused("bad_budget", "Entry budgets must be nonnegative; byte budgets must be at least 2.")
    layers = ["project", "task"] if layers is None else layers
    if snapshot is None:
        snapshot = load_snapshot(cwd, home)
    if snapshot is None:
        return {"status": "error", "command": "select", "reason": "no project resolved for the directory"}
    slug, entries, stats = snapshot

    active = [e for e in entries if e.get("status") == "active"]

    # M3: hypotheses are labelled context, not governing — excluded unless asked.
    if not include_hypotheses:
        active = [e for e in active if e.get("kind") != "hypothesis"]

    # Scope + layer relevance: an entry must touch a requested layer (or be project standing).
    def in_scope(e):
        scope = e.get("scope", "project")
        if scope == "project":
            return "project" in layers
        if scope.startswith("task:"):
            return "task" in layers and bool(task) and scope == f"task:{task}"
        return False

    candidates = [e for e in active if in_scope(e)]

    # Ranking. An empty query asks for STANDING context (what to know about this project): the
    # pinned decisions and project-scope active entries, bounded — a no-query request is not
    # "irrelevant", so M1's popularity guard does not apply to it. A real query ranks by relevance.
    if query:
        scored = []
        for e in candidates:
            rel = _relevance(query, e)
            if rel <= 0:
                continue                       # M1: zero relevance is never surfaced by popularity
            scored.append((rel, _confidence(e), _usefulness(e, stats), e))
        ranked = [row[3] for row in sorted(scored, key=lambda row: (
            -row[0], -row[1], -row[2], row[3]["id"], row[3]["revision"]))]
        effective_budget = DEFAULT_STANDING_BUDGET if budget is None else budget
    else:
        standing = candidates
        ranked = sorted(standing, key=lambda e: (
            -bool(e.get("pinned")), -e.get("repetitions", 1), -_confidence(e),
            -_usefulness(e, stats), e["id"], e["revision"]))
        effective_budget = DEFAULT_STANDING_BUDGET if budget is None else budget

    # M4: evidence checked against a code version that no longer matches → flag, do not pass.
    for e in ranked:
        checked = e.get("related_code_version")
        if checked and current_code_version and checked != current_code_version:
            e["_verification_required"] = True
            e["_note"] = f"evidence was checked against {checked}, not {current_code_version}"

    # M5: two active entries on one topic are a conflict the caller resolves; we surface both.
    conflicts = _find_conflicts(candidates)

    # shortcut: serialized UTF-8 bytes conservatively bound tokens; upgrade for a measured tokenizer.
    selected, used_bytes = [], 2  # serialized list delimiters
    for entry in ranked:
        size = len(json.dumps(entry, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        size += 1 if selected else 0
        if len(selected) < effective_budget and used_bytes + size <= byte_budget:
            selected.append(entry)
            used_bytes += size
    omitted = len(ranked) - len(selected)
    truncated = ({"omitted": omitted, "reason": "entry or UTF-8 byte budget exceeded"}
                 if omitted else None)
    ranked = selected
    status = "ok"
    if not ranked:
        status = "no-match"                      # M2
    if conflicts:
        status = "conflict"                      # M5: a conflict is a first-class status
    if any(e.get("_verification_required") for e in ranked):
        status = "verification-required" if status == "ok" else status

    return {
        "status": status,
        "command": "select",
        "policy_version": POLICY_VERSION,
        "slug": slug,
        "query": query,
        "task": task,
        "entries": ranked,
        "conflicts": conflicts,
        "truncation": truncated,
        "budget": {"entries": effective_budget, "bytes": byte_budget, "used_bytes": used_bytes},
        "sources": ["entries.md"],
        "notes": [e["_note"] for e in ranked if e.get("_verification_required")] or None,
        "counts": {"considered": len(candidates), "selected": len(ranked)},
    }


def _find_conflicts(entries: list) -> list:
    """M5: group active entries by declared topic; more than one active on a topic is a conflict we
    report rather than resolve. Entries without a topic never conflict (conservative: no false
    positives over the common case)."""
    by_topic = {}
    for e in entries:
        topic = e.get("topic")
        if topic:
            by_topic.setdefault((e.get("scope", "project"), _equivalent(topic)), []).append(e)
    conflicts = []
    for topic, group in by_topic.items():
        if len({_equivalent(e["statement"]) for e in group}) > 1:
            conflicts.append({"topic": group[0]["topic"], "scope": topic[0],
                              "entries": [e.get("id") for e in group],
                              "reason": "multiple active entries on one topic; resolve, do not pick"})
    return sorted(conflicts, key=lambda c: c["topic"])


# ── Writes: capture / supersede / report-use / checkpoint / promote / delete ───────────────────────

def _provenance(kind: str, captured_by: str, extraction_model: str | None,
                 extraction_version: str | None) -> dict:
    return {"captured_by": captured_by, "extraction_model": extraction_model,
            "extraction_version": extraction_version,
            "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


def _equivalent(text: str | None) -> str:
    return " ".join((text or "").casefold().split()).rstrip(".!? ")


# Recognizable credentials only; this is a safety net, not a general secret detector.
_SECRET_RE = re.compile(
    r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----|"
    r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b|"
    r"\b(?:gh[pousr]_|github_pat_|sk-(?:proj-)?)[A-Za-z0-9_-]{20,}|"
    r"\bBearer\s+[A-Za-z0-9._~+/-]{16,}=*|"
    r"\b(?:password|passwd|api[_-]?key|access[_-]?token|secret)[\"']?\s*[=:]\s*[\"']?[^\s\"']{8,}",
    re.IGNORECASE)


def _validate_capture(statement: str, rationale: str, evidence, metadata=None) -> None:
    if not isinstance(statement, str) or len(statement) > 1000:
        raise Refused("statement_limit", "Statements must be strings of at most 1000 characters.")
    surface = json.dumps([statement, rationale, evidence, metadata], ensure_ascii=False)
    if _SECRET_RE.search(surface):
        raise Refused("likely_secret", "Capture refused: input resembles a credential or private key.")


def capture_entry(cwd: str, kind: str, statement: str, rationale: str = "",
                  evidence: dict | None = None, scope: str = "project",
                  related_code_version: str | None = None, pinned: bool = False,
                  topic: str | None = None, captured_by: str = "capture",
                  extraction_model: str | None = None, extraction_version: str | None = None,
                  home=None, supersedes: str | None = None) -> dict:
    """Record provenance; count equivalent recaptures and preserve differing statements."""
    if kind not in KINDS:
        raise Refused("bad_kind", f"'{kind}' is not a known kind; one of {KINDS}.")
    _validate_capture(statement, rationale, evidence, [topic, scope, related_code_version, captured_by,
                                                      extraction_model, extraction_version])
    if not statement.strip() or not (scope == "project" or re.fullmatch(r"task:[A-Za-z0-9][A-Za-z0-9._-]*", scope)):
        raise Refused("bad_entry", "A nonempty statement and project or task:<name> scope are required.")
    if evidence is not None and not isinstance(evidence, dict):
        raise Refused("bad_evidence", "Evidence must be an object.")
    if kind != "hypothesis" and evidence and evidence.get("basis") == "hypothesis":
        raise Refused("hypothesis_evidence", "A hypothesis cannot justify governing context.")
    hercules_state = _load_hercules_state()
    slug = resolve_slug(cwd, home, hercules_state)
    if slug is None:
        raise Refused("no_project", f"No project could be resolved for {cwd}.")
    root = memory_root(slug, home)
    with _SlugLock(root):
        entries = load_entries(root)
        prior = None
        if supersedes:
            prior = next((e for e in entries if e["id"] == supersedes), None)
            if (prior is None or prior["status"] != "active" or prior["scope"] != scope
                    or _equivalent(prior.get("topic")) != _equivalent(topic)):
                raise Refused("bad_supersedes", "Supersession requires an active entry in the same scope and topic.")
        for existing in entries:
            if (not supersedes and existing["status"] == "active" and existing["kind"] == kind
                    and existing["scope"] == scope
                    and _equivalent(existing.get("topic")) == _equivalent(topic)
                    and _equivalent(existing["statement"]) == _equivalent(statement)
                    and existing.get("related_code_version") == related_code_version):
                existing["repetitions"] = existing.get("repetitions", 1) + 1
                save_entries(root, entries)
                return {"status": "ok", "command": "capture", "entry": existing, "deduplicated": True}
        stats = load_stats(root)
        number = max(stats.get("last_id", 0), int(_next_id(entries, "M").split(":")[1]) - 1) + 1
        entry_id = f"M:{number:04d}"
        # Reserve before saving: a crash may skip an ID, but can never recycle one.
        stats["last_id"] = number
        save_stats(root, stats)
        # Auto-capture ADDS and never decides one entry beats another: two active entries on a topic
        # become a conflict (M5) for a human to resolve. Reconcile-don't-append happens at the
        # committed store, by a human — auto-memory is the working log, allowed to hold a conflict.
        entry = {
            "format_version": FORMAT_VERSION,
            "id": entry_id,
            "revision": 1,
            "repetitions": 1,
            "slug": slug,
            "scope": scope,
            "kind": kind,
            "statement": statement,
            "rationale": rationale,
            "evidence": evidence or {"basis": "none"},
            "provenance": _provenance(kind, captured_by, extraction_model, extraction_version),
            "status": "active",
            "supersedes": supersedes,
            "superseded_by": None,
            "pinned": bool(pinned),
            "related_code_version": related_code_version,
            "topic": topic,
        }
        if prior is not None:
            prior["status"] = "superseded"
            prior["superseded_by"] = entry_id
        entries.append(entry)
        save_entries(root, entries)
        return {"status": "ok", "command": "capture", "entry": entry,
                "note": "recorded in auto-memory only; reach the committed store via promote"}


def statement_id(statement: str) -> str:
    """A deterministic id fragment from a statement, so re-capturing the same fact does not create a
    duplicate (extraction is non-deterministic; reconciliation is not)."""
    frag = hashlib.sha1(_equivalent(statement).encode("utf-8")).hexdigest()[:10]
    return f"stmt-{frag}"


def report_use(cwd: str, task: str, applied: list, home=None) -> dict:
    """M6: record which entries the agent APPLIED, with evidence — only for a revision actually
    present in the store, deduped by (task, id:revision). Never invents a hit for an unseen entry."""
    hercules_state = _load_hercules_state()
    slug = resolve_slug(cwd, home, hercules_state)
    root = memory_root(slug, home)
    with _SlugLock(root):
        stored = {(e["id"], e.get("revision")) for e in load_entries(root)}
        stats = load_stats(root)
        hits = stats.setdefault("hits", {})
        log = stats.setdefault("use_log", [])
        accepted, rejected = [], []
        for ref in applied:
            eid, _, rev = ref.rpartition(":")   # id contains a colon (M:0001); revision is last
            key = (eid, int(rev)) if rev.isdigit() else (eid, 0)
            if key not in stored and (eid, 0) not in stored:
                rejected.append(ref)           # M6: cannot apply a revision never in the store
                continue
            hit_key = f"{eid}:{rev}" if rev else eid
            if f"{task}:{hit_key}" in {f"{u.get('task')}:{u.get('ref')}" for u in log}:
                continue                       # dedupe
            hits[hit_key] = int(hits.get(hit_key, 0)) + 1
            log.append({"task": task, "ref": hit_key,
                        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
            accepted.append(ref)
        save_stats(root, stats)
        return {"status": "ok", "command": "report-use", "accepted": accepted,
                "rejected_unseen": rejected}


def save_checkpoint(cwd: str, task: str, state: dict, home=None) -> dict:
    """Record task state (progress, verification, blockers, next step) under checkpoints/<task>.json.
    Idempotent: the same task overwrites its own checkpoint, never another's."""
    hercules_state = _load_hercules_state()
    slug = resolve_slug(cwd, home, hercules_state)
    root = memory_root(slug, home)
    safe_task = task
    if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", task) or task.endswith(".")
            or task.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL",
                *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}):
        raise Refused("bad_task", f"Refusing an unsafe task name: '{task}'.")
    with _SlugLock(root):
        _atomic_write(root / "checkpoints" / f"{safe_task}.json",
                      json.dumps({"task": task, "state": state, "at":
                              time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
                             indent=2, sort_keys=True), within_root=root)
    return {"status": "ok", "command": "checkpoint", "task": task, "path": str(safe_task + ".json")}


def claim_delivery(cwd: str, session_id: str, fingerprint: str, home=None, reset=False) -> bool:
    """Claim changed context (or reset after compaction). One global ``.deliveries.json`` keyed by
    slug+session, at most 256 keys; the slug is only hashed, so no per-repo directory is created."""
    if not session_id or not fingerprint:
        raise Refused("bad_delivery", "A session id and context fingerprint are required.")
    slug = resolve_slug(cwd, home)
    root = hercules_home(home) / "memory"
    path = root / ".deliveries.json"
    session_key = hashlib.sha256(f"{slug}\0{session_id}".encode("utf-8")).hexdigest()
    digest = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()
    with _SlugLock(root, ".deliveries.lock", attempts=10):
        _assert_within_memory_root(path, root)
        sessions = {}
        if path.exists():
            try:
                sessions = json.loads(path.read_text(encoding="utf-8"))
                if (not isinstance(sessions, dict) or len(sessions) > 256
                        or any(not re.fullmatch(r"[0-9a-f]{64}", k)
                               or not isinstance(v, str) or not re.fullmatch(r"[0-9a-f]{64}", v)
                               for k, v in sessions.items())):
                    raise ValueError("invalid delivery state")
            except (ValueError, OSError) as exc:
                raise Refused("corrupt_delivery", "Delivery state is unreadable; bytes preserved.") from exc
        if not reset and sessions.get(session_key) == digest:
            return False
        sessions.pop(session_key, None)
        sessions[session_key] = digest
        while len(sessions) > 256:
            del sessions[next(iter(sessions))]
        _atomic_write(path, json.dumps(sessions), within_root=root)
        return True


def inspect_state(cwd: str, home=None) -> dict:
    """Transparency (I3): list entries, counts, and index health so a human can browse/verify."""
    hercules_state = _load_hercules_state()
    slug = resolve_slug(cwd, home, hercules_state)
    if slug is None:
        return {"status": "no-project", "command": "inspect", "reason": "no project resolved"}
    root = memory_root(slug, home)
    entries = load_entries(root)
    stats = load_stats(root)
    return {"status": "ok", "command": "inspect", "slug": slug, "root": str(root),
            "entries": len(entries),
            "by_kind": _count(entries, "kind"),
            "by_status": _count(entries, "status"),
            "pinned": sum(1 for e in entries if e.get("pinned")),
            "hits": stats.get("hits", {}),
            "index_current": _index_is_current(root)}


def _count(entries, key):
    out = {}
    for e in entries:
        out[e.get(key, "?")] = out.get(e.get(key, "?"), 0) + 1
    return out


def promote_entry(cwd: str, entry_id: str, target_md: str, confirmed: bool, home=None) -> dict:
    """The ONE path from auto-memory to the committed store (invariant I1). Appends the entry to
    ``docs/learnings.md`` ONLY when ``--confirm`` is given — a deliberate, human decision, never a
    silent auto-promotion. Writes to the committed store, which the auto-capture path never does."""
    if not confirmed:
        raise Refused("unconfirmed", "Promotion to the committed store needs --confirm.")
    hercules_state = _load_hercules_state()
    slug = resolve_slug(cwd, home, hercules_state)
    root = memory_root(slug, home)
    target = Path(target_md)
    target = target if target.is_absolute() else Path(cwd) / target
    _refuse_symlinks(target)
    target = target.resolve()
    if target.suffix != ".md":
        raise Refused("target_not_markdown", f"Promotion appends to a .md file only, not {target.name}.")
    if ".git" in target.parts:
        raise Refused("target_in_git", "Promotion cannot write inside a .git path.")
    config_path = hercules_home(home) / "config.json"
    _refuse_symlinks(config_path)
    projects = json.loads(config_path.read_text(encoding="utf-8")).get("projects", {}) if config_path.exists() else {}
    match = _registered_match(projects, hercules_state.canon(cwd), hercules_state)
    registered = match[2] if match else {}
    allowed = [Path(cwd).resolve()]
    for parent in (allowed[0], *allowed[0].parents):
        if (parent / ".git").exists():
            allowed = [parent]
            break
    if registered:
        allowed += [Path(value) for value in _registered_roots(registered)]
    if not any(is_within(str(target), str(base)) and target != base for base in allowed):
        raise Refused("target_escape", f"Refusing to promote outside registered project roots: {target_md}.")
    if is_within(str(target), str(hercules_home(home).resolve())):
        raise Refused("target_escape", "Promotion cannot write machine-local Hercules state.")
    with _SlugLock(root):
        entries = load_entries(root)
        entry = next((e for e in entries if e.get("id") == entry_id), None)
        if entry is None:
            raise Refused("not_found", f"No entry {entry_id}.")
        previous = target.read_text(encoding="utf-8") if target.exists() else ""
        _atomic_write(target, previous + _render_entry(entry), within_root=next(
            base for base in allowed if is_within(str(target), str(base)) and target != base))
    return {"status": "ok", "command": "promote", "entry_id": entry_id,
            "target": str(target), "note": "promoted by explicit decision; the committed store is now the source for this"}


def delete_entry(cwd: str, entry_id: str, confirmed: bool, home=None) -> dict:
    """Remove an entry from auto-memory. A human's corrective action, not auto-capture."""
    if not confirmed:
        raise Refused("unconfirmed", "Deletion needs --confirm.")
    hercules_state = _load_hercules_state()
    slug = resolve_slug(cwd, home, hercules_state)
    root = memory_root(slug, home)
    with _SlugLock(root):
        entries = load_entries(root)
        kept = [e for e in entries if e.get("id") != entry_id]
        if len(kept) == len(entries):
            raise Refused("not_found", f"No entry {entry_id}.")
        stats = load_stats(root)
        stats["last_id"] = max(stats.get("last_id", 0), int(_next_id(entries, "M").split(":")[1]) - 1)
        save_stats(root, stats)
        save_entries(root, kept)
    return {"status": "ok", "command": "delete", "entry_id": entry_id,
            "remaining": len(kept)}


# ── The rebuildable index (best-effort; select works without it) ──────────────────────────────────

def _index_is_current(root: Path) -> bool:
    idx = root / "index.db"
    _assert_within_memory_root(idx, root)
    src = root / "entries.md"
    if not idx.is_file() or not src.is_file():
        return False
    try:
        return idx.stat().st_mtime >= src.stat().st_mtime
    except OSError:
        return False


def reindex(cwd: str, home=None) -> dict:
    """Rebuild the search index (a plain SQLite token index, best-effort) FROM entries.md. The index
    is a cache: select falls back to scanning entries.md when it is absent or stale, so a rebuild is
    never required for correctness. No embedding model — a vector backend is a future, measured choice."""
    hercules_state = _load_hercules_state()
    slug = resolve_slug(cwd, home, hercules_state)
    root = memory_root(slug, home)
    with _SlugLock(root):
        entries = load_entries(root)
        db = root / "index.db"
        for name in ("index.db", "index.db-journal", "index.db-wal", "index.db-shm"):
            _assert_within_memory_root(root / name, root)
        conn = sqlite3.connect(str(db))
        try:
            conn.execute("CREATE TABLE IF NOT EXISTS terms (id TEXT, term TEXT, PRIMARY KEY(id, term))")
            conn.execute("DELETE FROM terms")
            for e in entries:
                for term in _tokenize(f"{e.get('statement','')} {e.get('rationale','')}"):
                    conn.execute("INSERT OR IGNORE INTO terms VALUES (?, ?)", (e["id"], term))
            conn.commit()
        finally:
            conn.close()
    return {"status": "ok", "command": "reindex", "terms": sum(
        len(_tokenize(f"{e.get('statement','')} {e.get('rationale','')}")) for e in entries)}


# ── Command line ──────────────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="memory_core", add_help=False)
    sub = p.add_subparsers(dest="command", required=True)
    p_add = sub.add_parser("select", add_help=False)
    p_add.add_argument("--cwd", required=True)
    p_add.add_argument("--query", default="")
    p_add.add_argument("--task", default="")
    p_add.add_argument("--layers", default="project,task")
    p_add.add_argument("--budget", type=int, default=None)
    p_add.add_argument("--byte-budget", type=int, default=DEFAULT_BYTE_BUDGET)
    p_add.add_argument("--include-hypotheses", action="store_true")
    p_add.add_argument("--code-version", default=None)
    p_cap = sub.add_parser("capture", add_help=False)
    p_cap.add_argument("--cwd", required=True)
    p_cap.add_argument("--kind", required=True)
    p_cap.add_argument("--statement", required=True)
    p_cap.add_argument("--rationale", default="")
    p_cap.add_argument("--evidence", default="")
    p_cap.add_argument("--scope", default="project")
    p_cap.add_argument("--code-version", default=None)
    p_cap.add_argument("--pinned", action="store_true")
    p_cap.add_argument("--topic", default=None)
    p_cap.add_argument("--supersedes", default=None)
    p_cap.add_argument("--compact", action="store_true")
    p_use = sub.add_parser("report-use", add_help=False)
    p_use.add_argument("--cwd", required=True)
    p_use.add_argument("--task", required=True)
    p_use.add_argument("--entries", required=True)
    p_cp = sub.add_parser("checkpoint", add_help=False)
    p_cp.add_argument("--cwd", required=True)
    p_cp.add_argument("--task", required=True)
    p_cp.add_argument("--state", required=True)
    p_ins = sub.add_parser("inspect", add_help=False)
    p_ins.add_argument("--cwd", required=True)
    p_prom = sub.add_parser("promote", add_help=False)
    p_prom.add_argument("--cwd", required=True)
    p_prom.add_argument("--id", required=True)
    p_prom.add_argument("--target", required=True)
    p_prom.add_argument("--confirm", action="store_true")
    p_del = sub.add_parser("delete", add_help=False)
    p_del.add_argument("--cwd", required=True)
    p_del.add_argument("--id", required=True)
    p_del.add_argument("--confirm", action="store_true")
    p_re = sub.add_parser("reindex", add_help=False)
    p_re.add_argument("--cwd", required=True)
    return p


def _run(args, home) -> tuple:
    if args.command == "select":
        # A conflict or no-match is a VALID, informative result, not a tool failure: the status
        # field carries it, and the exit is OK. Only refused/internal/no-project are non-zero.
        result = select_context(args.cwd, args.query, args.task,
                                [x for x in args.layers.split(",") if x],
                                args.budget, args.include_hypotheses,
                                args.code_version, home, args.byte_budget)
        return result, EXIT_OK
    if args.command == "capture":
        ev = json.loads(args.evidence) if args.evidence else None
        result = capture_entry(args.cwd, args.kind, args.statement, args.rationale, ev,
                               args.scope, args.code_version, args.pinned, args.topic,
                               home=home, supersedes=args.supersedes)
        if args.compact:
            entry = result["entry"]
            result = {"status": result["status"], "entry_id": entry["id"], "revision": entry["revision"]}
        return result, EXIT_OK
    if args.command == "report-use":
        return report_use(args.cwd, args.task,
                          [x for x in args.entries.split(",") if x], home), EXIT_OK
    if args.command == "checkpoint":
        return save_checkpoint(args.cwd, args.task, json.loads(args.state), home), EXIT_OK
    if args.command == "inspect":
        return inspect_state(args.cwd, home), EXIT_OK
    if args.command == "promote":
        return promote_entry(args.cwd, args.id, args.target, args.confirm, home), EXIT_OK
    if args.command == "delete":
        return delete_entry(args.cwd, args.id, args.confirm, home), EXIT_OK
    if args.command == "reindex":
        return reindex(args.cwd, home), EXIT_OK
    raise Refused("unknown_command", f"Unknown command '{args.command}'.")


def emit(payload: dict, command: str, code: int) -> int:
    """Every path emits one JSON shape — refusals included — so a caller parses one form."""
    print(json.dumps(payload, indent=2, default=str))
    return code


def main(argv=None, home=None) -> int:
    """Resolve, dispatch, and turn every failure into a scripted refusal or a visible limit — nothing
    escapes as a traceback, and no failure crashes the caller's session (fail-open on the caller)."""
    try:
        args = build_parser().parse_args(list(argv) if argv is not None else None)
    except SystemExit:
        return emit({"command": "unknown", "status": "error",
                     "message": "The arguments were not understood."}, "unknown", EXIT_INTERNAL)
    command = args.command
    try:
        payload, code = _run(args, home)
    except Refused as exc:
        return emit({"command": command, "status": "refused", "code": exc.code,
                     "message": exc.message}, command, EXIT_REFUSED)
    except Internal as exc:
        return emit({"command": command, "status": "error", "internal": exc.message},
                    command, EXIT_INTERNAL)
    except Exception as exc:  # fail closed: an unclassified error changes nothing (house pattern).
        # The HOST-FIRED hook that invokes this is the fail-open layer: on a non-zero exit it skips
        # memory and the caller's session continues.
        return emit({"command": command, "status": "error",
                     "message": f"Operation failed. {exc}"}, command, EXIT_INTERNAL)
    return emit(payload, command, code)


if __name__ == "__main__":  # pragma: no cover - exercised via main() in tests
    sys.exit(main())
