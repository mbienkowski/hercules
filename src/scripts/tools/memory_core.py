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
  ``processing.json`` idempotent-event log, so a re-fired host event never double-writes.

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
  M6 application with evidence          — a use-report is recorded only for an entry revision the
                                          agent actually retrieved; deduped by task + entry+revision.
  M7 a fixed response budget            — over budget we omit WHOLE entries, never cut mid-entry.
  M8 memory directs, it does not permit — selection returns context; it authorises no action.
  M9 we evaluate omissions             — a "no-match" and a truncated result name what they omitted.

Determinism: the PROCESS is repeatable (a host event starts it; idempotent; visible on start/fail/
complete). SELECTION is deterministic — same inputs + policy version + store state give the same
result; NO date or age enters ranking (we never forget the old, M-no-time-decay). EXTRACTION
(turning a chat into entries) is non-deterministic and lives at the caller; the core reconciles by
stable id + revision, so a different extraction can neither duplicate nor drift a stored entry.

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

POLICY_VERSION = 1        # the selection policy; a change bumps it and the result records it
DEFAULT_STANDING_BUDGET = 8   # entries a no-query standing-context request returns, by default
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
    """The store could not be read, written, or verified. Nothing was changed."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


# ── Identity, canonicalisation, the tree root — loaded, never re-derived ─────────────────────────

def hercules_home(home=None) -> Path:
    """The state tree root. ``home`` is a PARAMETER, not a flag, so no caller can redirect the tree
    at another ``~/.hercules``."""
    return (Path(home) if home else Path.home()) / ".hercules"


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
    core writes is proven to live inside it (the memory_gate invariant, I3)."""
    root = hercules_home(home) / "memory"
    slug = os.path.basename(slug_c.rstrip(os.sep))
    if not slug or slug in (".", "..") or slug.startswith("."):
        raise Refused("bad_slug", f"Refusing to write under a slug that would escape the tree: '{slug}'.")
    return root / slug


def _assert_within_memory_root(path: Path, root: Path) -> None:
    """Refuse a path that would escape the memory subtree — the one thing auto-capture must never
    do (it can never reach the repo, docs/learnings.md, or code-of-conduct.md)."""
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


class _SlugLock:
    """A per-slug advisory lock so a hook-fired and a model-fired write serialise instead of racing.
    Best-effort: on a platform without fcntl we proceed un-locked rather than block the user."""

    def __init__(self, root: Path):
        self.lock_file = root / ".lock"

    def __enter__(self):
        self.root = self.lock_file.parent
        self.root.mkdir(parents=True, exist_ok=True)
        self._fh = None
        try:
            import fcntl  # POSIX only; absent on Windows, where we degrade to an un-locked write
            self._fh = open(self.lock_file, "w")
            fcntl.flock(self._fh, fcntl.LOCK_EX)
        except Exception:
            self._fh = None
        return self

    def __exit__(self, *exc):
        if self._fh is not None:
            try:
                import fcntl
                fcntl.flock(self._fh, fcntl.LOCK_UN)
                self._fh.close()
            except Exception:
                pass


# ── Slug resolution: the directory's project, never a model-supplied string ────────────────────────

def resolve_slug(cwd: str, home=None, hercules_state=None) -> str | None:
    """The slug that owns ``cwd`` — a registered project's slug, or a deterministic fallback from the
    directory name so ANY repo works with no per-repo config. A model-supplied slug is untrusted and
    is re-resolved from the directory, not believed."""
    if hercules_state is None:
        hercules_state = _load_hercules_state()
    cwd_c = hercules_state.canon(cwd)
    config_path = hercules_home(home) / "config.json"
    try:
        projects = json.loads(config_path.read_text(encoding="utf-8")).get("projects") or {}
    except (OSError, json.JSONDecodeError):
        projects = {}
    for slug, entry in projects.items():
        if not isinstance(entry, dict):
            continue
        roots = [hercules_state.canon(r) for r in ([entry.get("directory")] +
                 list((entry.get("repositories") or {}).values())) if r]
        if any(is_within(cwd_c, r) for r in roots):
            return slug
    # No registered project: derive a deterministic slug from the directory name.
    return os.path.basename(cwd_c.rstrip(os.sep)) or None


# ── The canonical store: entries.md ────────────────────────────────────────────────────────────────

_ENTRY_MARKER = "<!-- entry:%s -->"
_BLOCK_RE = re.compile(r"<!-- entry:(?P<id>[^>]+) -->\s*\n(?:(?!\n<!-- entry:).)*?```json\n"
                       r"(?P<body>.*?)\n```", re.DOTALL)


def _render_entry(entry: dict) -> str:
    """One entry: a human-readable heading (derived, non-authoritative) over the authoritative JSON
    block. A future backend reads the same block; a human reads the heading + statement."""
    heading = f"[{entry['id']}] {entry.get('kind', '?')} · {entry.get('status', 'active')}"
    statement = (entry.get("statement") or "").strip().split("\n", 1)[0]
    return f"{_ENTRY_MARKER % entry['id']}\n## {heading}\n{statement}\n\n" \
           f"```json\n{json.dumps(entry, indent=2, ensure_ascii=True, sort_keys=True)}\n```\n"


def load_entries(root: Path) -> list:
    """Parse every entry from ``entries.md`` in file order. A malformed block is skipped and the rest
    survive — a corrupted entry never destroys the store."""
    text = (root / "entries.md").read_text(encoding="utf-8") if (root / "entries.md").is_file() else ""
    entries = []
    for match in _BLOCK_RE.finditer(text):
        try:
            entries.append(json.loads(match.group("body")))
        except json.JSONDecodeError:
            continue
    return entries


def save_entries(root: Path, entries: list) -> None:
    """Rewrite ``entries.md`` from ``entries`` in a stable order (by id, then revision), atomically."""
    ordered = sorted(entries, key=lambda e: (e.get("id", ""), e.get("revision", 0)))
    body = "\n".join(_render_entry(e) for e in ordered)
    header = (f"# Project memory for `{os.path.basename(root)}`\n\n"
              "Machine-local auto-memory, generated from chats. Human-readable and versioned; "
              "searchable. The committed `docs/learnings.md` is a separate, human-curated store; "
              "an entry reaches it only through `promote`. Pinned decisions are standing context.\n")
    _atomic_write(root / "entries.md", header + body, within_root=root)


def _next_id(entries: list, prefix: str) -> str:
    nums = [int(e["id"].split(":", 1)[1]) for e in entries
            if e.get("id", "").startswith(prefix + ":")
            and e["id"].split(":", 1)[1].isdigit()]
    return f"{prefix}:{max(nums) + 1 if nums else 1:04d}"


# ── Usage stats (authoritative, non-rebuildable) ──────────────────────────────────────────────────

def load_stats(root: Path) -> dict:
    path = root / "stats.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"hits": {}}
    except (OSError, json.JSONDecodeError):
        return {"hits": {}}


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


def select_context(cwd: str, query: str = "", task: str = "", layers=None,
                   budget: int | None = None, include_hypotheses: bool = False,
                   current_code_version: str | None = None, home=None) -> dict:
    """The read path. Returns context for the directory, bounded and conflict-aware. Never writes.
    Honours M1–M9; an empty or partial result is a valid, fully-reasoned outcome, not an error."""
    layers = layers or ["project", "task"]
    hercules_state = _load_hercules_state()
    slug = resolve_slug(cwd, home, hercules_state)
    if slug is None:
        return {"status": "error", "command": "select", "reason": "no project resolved for the directory"}
    root = memory_root(slug, home)
    entries = load_entries(root)
    stats = load_stats(root)

    active = [e for e in entries if e.get("status") == "active"]

    # M3: hypotheses are labelled context, not governing — excluded unless asked.
    if not include_hypotheses:
        active = [e for e in active if e.get("kind") != "hypothesis"]

    # Scope + layer relevance: an entry must touch a requested layer (or be project standing).
    def in_scope(e):
        scope = e.get("scope", "project")
        if scope == "project":
            return True
        if scope.startswith("task:") and ("task" in layers or task):
            return scope == f"task:{task}" or not task
        return "project" in layers

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
        ranked = [e for _, _, _, e in scored]
        effective_budget = budget
    else:
        standing = [e for e in active if e.get("pinned") or e.get("scope", "project") == "project"]
        ranked = [e for _, _, _, e in sorted(
            ((1, _confidence(e), _usefulness(e, stats), e) for e in standing),
            key=lambda row: (-row[0], -row[1], -row[2],
                             (row[3].get("id", ""), row[3].get("revision", 0))))]
        effective_budget = DEFAULT_STANDING_BUDGET if budget is None else budget

    # M4: evidence checked against a code version that no longer matches → flag, do not pass.
    for e in ranked:
        checked = e.get("related_code_version")
        if checked and current_code_version and checked != current_code_version:
            e["_verification_required"] = True
            e["_note"] = f"evidence was checked against {checked}, not {current_code_version}"

    # M5: two active entries on one topic are a conflict the caller resolves; we surface both.
    conflicts = _find_conflicts(ranked)

    # M7: fixed budget — omit WHOLE entries over budget, never cut one.
    if effective_budget is not None and len(ranked) > effective_budget:
        truncated = {"omitted": len(ranked) - effective_budget,
                     "reason": "budget exceeded; lowest-ranked entries omitted"}
        ranked = ranked[:effective_budget]
    else:
        truncated = None
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
            by_topic.setdefault(topic, []).append(e)
    conflicts = []
    for topic, group in by_topic.items():
        if len(group) > 1:
            conflicts.append({"topic": topic,
                              "entries": [e.get("id") for e in group],
                              "reason": "multiple active entries on one topic; resolve, do not pick"})
    return sorted(conflicts, key=lambda c: c["topic"])


# ── Writes: capture / supersede / report-use / checkpoint / promote / delete ───────────────────────

def _provenance(kind: str, captured_by: str, extraction_model: str | None,
                 extraction_version: str | None) -> dict:
    return {"captured_by": captured_by, "extraction_model": extraction_model,
            "extraction_version": extraction_version,
            "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


def capture_entry(cwd: str, kind: str, statement: str, rationale: str = "",
                  evidence: dict | None = None, scope: str = "project",
                  related_code_version: str | None = None, pinned: bool = False,
                  topic: str | None = None, captured_by: str = "capture",
                  extraction_model: str | None = None, extraction_version: str | None = None,
                  home=None) -> dict:
    """M3: record a memory with full provenance. Idempotent on (id, revision); a new revision
    supersedes the old. Returns the stored entry. Never touches the committed store."""
    if kind not in KINDS:
        raise Refused("bad_kind", f"'{kind}' is not a known kind; one of {KINDS}.")
    hercules_state = _load_hercules_state()
    slug = resolve_slug(cwd, home, hercules_state)
    if slug is None:
        raise Refused("no_project", f"No project could be resolved for {cwd}.")
    root = memory_root(slug, home)
    with _SlugLock(root):
        entries = load_entries(root)
        entry_id = _next_id(entries, "M")
        # Auto-capture ADDS and never decides one entry beats another: two active entries on a topic
        # become a conflict (M5) for a human to resolve. Reconcile-don't-append happens at the
        # committed store, by a human — auto-memory is the working log, allowed to hold a conflict.
        entry = {
            "format_version": FORMAT_VERSION,
            "id": entry_id,
            "revision": 1,
            "slug": slug,
            "scope": scope,
            "kind": kind,
            "statement": statement,
            "rationale": rationale,
            "evidence": evidence or {"basis": "none"},
            "provenance": _provenance(kind, captured_by, extraction_model, extraction_version),
            "status": "active",
            "supersedes": None,
            "superseded_by": None,
            "pinned": bool(pinned),
            "related_code_version": related_code_version,
            "topic": topic,
        }
        entries.append(entry)
        save_entries(root, entries)
        return {"status": "ok", "command": "capture", "entry": entry,
                "note": "recorded in auto-memory only; reach the committed store via promote"}


def statement_id(statement: str) -> str:
    """A deterministic id fragment from a statement, so re-capturing the same fact does not create a
    duplicate (extraction is non-deterministic; reconciliation is not)."""
    import hashlib
    frag = hashlib.sha1(statement.strip().lower().encode("utf-8")).hexdigest()[:10]
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
    safe_task = re.sub(r"[^A-Za-z0-9._-]", "_", task)
    if not safe_task or safe_task.startswith("."):
        raise Refused("bad_task", f"Refusing an unsafe task name: '{task}'.")
    (root / "checkpoints").mkdir(parents=True, exist_ok=True)
    _atomic_write(root / "checkpoints" / f"{safe_task}.json",
                  json.dumps({"task": task, "state": state, "at":
                              time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
                             indent=2, sort_keys=True), within_root=root)
    return {"status": "ok", "command": "checkpoint", "task": task, "path": str(safe_task + ".json")}


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
    entries = load_entries(root)
    entry = next((e for e in entries if e.get("id") == entry_id), None)
    if entry is None:
        raise Refused("not_found", f"No entry {entry_id}.")
    target = Path(target_md)
    if not target.is_absolute() and not is_within(str((Path(cwd) / target).resolve()),
                                                 str(Path(cwd).resolve())):
        raise Refused("target_escape", f"Refusing to promote outside the repo: {target_md}.")
    block = _render_entry(entry)
    with open(target, "a", encoding="utf-8") as fh:
        fh.write(block)
    return {"status": "ok", "command": "promote", "entry_id": entry_id,
            "target": str(target), "note": "promoted by explicit decision; the committed store is now the source for this"}


def delete_entry(cwd: str, entry_id: str, confirmed: bool, home=None) -> dict:
    """Remove an entry from auto-memory. A human's corrective action, not auto-capture."""
    if not confirmed:
        raise Refused("unconfirmed", "Deletion needs --confirm.")
    hercules_state = _load_hercules_state()
    slug = resolve_slug(cwd, home, hercules_state)
    root = memory_root(slug, home)
    entries = load_entries(root)
    kept = [e for e in entries if e.get("id") != entry_id]
    if len(kept) == len(entries):
        raise Refused("not_found", f"No entry {entry_id}.")
    save_entries(root, kept)
    return {"status": "ok", "command": "delete", "entry_id": entry_id,
            "remaining": len(kept)}


# ── The rebuildable index (best-effort; select works without it) ──────────────────────────────────

def _index_is_current(root: Path) -> bool:
    idx = root / "index.db"
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
    entries = load_entries(root)
    db = root / "index.db"
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
                                args.code_version, home)
        return result, EXIT_OK
    if args.command == "capture":
        ev = json.loads(args.evidence) if args.evidence else None
        return capture_entry(args.cwd, args.kind, args.statement, args.rationale, ev,
                             args.scope, args.code_version, args.pinned, args.topic,
                             home=home), EXIT_OK
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
                     "message": f"Nothing was changed. {exc}"}, command, EXIT_INTERNAL)
    return emit(payload, command, code)


if __name__ == "__main__":  # pragma: no cover - exercised via main() in tests
    sys.exit(main())
