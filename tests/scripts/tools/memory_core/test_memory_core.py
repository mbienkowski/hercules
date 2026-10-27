"""Behaviour tests for the shared memory core, mapped to the safeguards (M1–M9) and the three
invariants (I1–I3). These FAIL first:
the safeguards are the whole point, so each is a test, not a comment."""

from __future__ import annotations

import json

import pytest

from tests.scripts.tools.memory_core.conftest import SLUG, build_home, capture, run, select
from tests.scripts.tools.tool_harness import load_tool


# ── I1 isolation: auto-capture writes ONLY to auto-memory, never the committed store ─────────────

def test_i1_capture_never_touches_the_committed_store(fx, tmp_path):
    committed = tmp_path / "docs-repo" / "learnings.md"
    committed.write_text("# committed learnings\n")
    code, _ = capture(fx, "decision", "We use pnpm, not npm.", topic="package-manager")
    assert code == 0
    # The committed store is byte-for-byte unchanged.
    assert committed.read_text() == "# committed learnings\n"
    # The memory subtree is where the write actually landed.
    mem = fx.home / ".hercules" / "memory" / SLUG
    assert (mem / "entries.md").is_file()


def test_i1_only_promote_can_reach_the_committed_store(fx, tmp_path):
    committed = tmp_path / "docs-repo" / "learnings.md"
    committed.write_text("# committed learnings\n")
    code, _ = capture(fx, "decision", "Stand on pnpm.", topic="package-manager")
    assert code == 0
    before = committed.read_text()
    # Without --confirm, promote is refused and writes nothing (the only path to the committed store
    # is gated on an explicit decision).
    code2, payload = run(fx, "promote", "--cwd", str(fx.project), "--id", "M:0001",
                         "--target", str(committed))
    assert payload["status"] == "refused"
    assert committed.read_text() == before


# ── M1 relevance before popularity ──────────────────────────────────────────────────────────────

def test_m1_relevance_outranks_popularity(fx):
    capture(fx, "decision", "The database is PostgreSQL.", topic="db")
    # Give the irrelevant-but-popular entry a high hit-count; it must not surface on an unrelated query.
    capture(fx, "decision", "The build runs in Docker.", topic="build")
    (fx.home / ".hercules" / "memory" / SLUG / "stats.json").write_text(
        json.dumps({"hits": {"M:0001": 99, "M:0002": 0}}))
    code, payload = select(fx, query="postgresql schema")
    assert code == 0
    ids = [e["id"] for e in payload["entries"]]
    assert "M:0001" in ids            # relevant
    assert "M:0002" not in ids        # popular but irrelevant → never surfaced (M1)


# ── M2 an empty result is valid ────────────────────────────────────────────────────────────────

def test_m2_no_match_is_not_an_error(fx):
    code, payload = select(fx, query="nonexistent-unrelated-thing")
    assert code == 0                       # no-match is exit 0, not an error
    assert payload["status"] == "no-match"
    assert payload["entries"] == []


# ── M3 provenance + status; hypotheses are not governing ────────────────────────────────────────

def test_m3_every_entry_carries_provenance_and_hypotheses_are_excluded_by_default(fx):
    code, _ = capture(fx, "decision", "We choose pnpm.", topic="package-manager")
    code2, _ = capture(fx, "hypothesis", "Maybe the flake is a race.")
    assert code == code2 == 0
    # Read via select, the public path, and check provenance on every entry.
    c, all_payload = select(fx, query="")
    decided = [e for e in all_payload["entries"]]
    assert all("provenance" in e and "captured_at" in e["provenance"] for e in decided)
    # The hypothesis is excluded from a default select (not governing context).
    assert not any(e["kind"] == "hypothesis" for e in decided)
    # It is included when explicitly requested.
    c2, with_hyp = select(fx, query="", include_hypotheses=True)
    assert any(e["kind"] == "hypothesis" for e in with_hyp["entries"])


# ── M4 changed evidence needs re-verification ───────────────────────────────────────────────────

def test_m4_stale_code_version_flags_verification_required(fx):
    capture(fx, "verified-finding", "The lockstep test passes on this code.",
            code_version="abc123", topic="lockstep")
    code, payload = select(fx, query="lockstep test", code_version="def456")
    assert code == 0
    assert payload["status"] == "verification-required"
    assert any(e.get("related_code_version") == "abc123" for e in payload["entries"])


# ── M5 no silent conflict resolution ────────────────────────────────────────────────────────────

def test_m5_two_active_entries_on_a_topic_is_a_conflict(fx):
    capture(fx, "decision", "Auth is JWT in the header.", topic="auth")
    capture(fx, "decision", "Auth is a session cookie.", topic="auth")
    # Two active entries, one topic: the core surfaces both as a conflict, never picking a winner.
    code, payload = select(fx, query="auth")
    assert code == 0
    assert payload["status"] == "conflict"
    assert len(payload["conflicts"]) == 1
    assert set(payload["conflicts"][0]["entries"]) == {"M:0001", "M:0002"}


# ── M6 application with evidence ────────────────────────────────────────────────────────────────

def test_m6_report_use_rejects_unseen_revisions_and_dedups(fx):
    code, _ = capture(fx, "decision", "Use pnpm.", topic="package-manager")
    # A reference to a revision that is not in the store is rejected, not recorded.
    c, payload = run(fx, "report-use", "--cwd", str(fx.project), "--task", "t1",
                     "--entries", "M:9999:1,M:0001:1")
    assert c == 0
    assert "M:9999:1" in payload["rejected_unseen"]
    assert "M:0001:1" in payload["accepted"]
    # Re-reporting the same application dedupes.
    c2, payload2 = run(fx, "report-use", "--cwd", str(fx.project), "--task", "t1",
                       "--entries", "M:0001:1")
    assert payload2["accepted"] == []
    stats = json.loads((fx.home / ".hercules" / "memory" / SLUG / "stats.json").read_text())
    assert stats["hits"]["M:0001:1"] == 1


# ── M7 fixed budget, whole entries only ─────────────────────────────────────────────────────────

def test_m7_budget_omits_whole_entries_and_reports_truncation(fx):
    for i in range(5):
        capture(fx, "decision", f"Decision number {i} about the cache layer.")
    code, payload = select(fx, query="decision", budget=2)
    assert code == 0
    assert len(payload["entries"]) == 2
    assert payload["truncation"]["omitted"] == 3
    # No entry was cut mid-field: every returned entry is a complete object.
    for e in payload["entries"]:
        assert set(e) >= {"id", "statement", "kind"}


# ── I3 transparency: human-readable + machine-parseable + inspectable ───────────────────────────

def test_i3_entries_are_human_readable_and_round_trip(fx):
    code, _ = capture(fx, "decision", "We use pnpm, not npm.", topic="package-manager")
    text = (fx.home / ".hercules" / "memory" / SLUG / "entries.md").read_text()
    # Human-readable: a heading and a plain-language statement are present.
    assert "We use pnpm, not npm." in text
    assert "## [M:0001]" in text
    # Machine-parseable: the JSON block re-parses to the same id.
    c, payload = select(fx, query="pnpm")
    assert payload["entries"][0]["id"] == "M:0001"


def test_i3_inspect_lists_state(fx):
    capture(fx, "decision", "We use pnpm.", topic="package-manager")
    code, payload = run(fx, "inspect", "--cwd", str(fx.project))
    assert code == 0
    assert payload["slug"] == SLUG
    assert payload["entries"] == 1


# ── Determinism + no time decay ────────────────────────────────────────────────────────────────

def test_selection_is_deterministic(fx):
    capture(fx, "decision", "The database is PostgreSQL.", topic="db")
    capture(fx, "correction", "The cache key was missing a tenant id.")
    _, a = select(fx, query="database cache")
    _, b = select(fx, query="database cache")
    assert a == b                       # same inputs + state → same result


def test_no_time_decay_ranks_by_relevance_not_age(fx):
    # The older entry is highly relevant; the newer entry is irrelevant. Age must not demote the old.
    capture(fx, "decision", "The schema uses an index on the tenant column.", topic="schema")
    capture(fx, "decision", "The CI runs on macOS runners.", topic="ci")
    _, payload = select(fx, query="schema tenant index")
    ids = [e["id"] for e in payload["entries"]]
    assert "M:0001" in ids             # the old, relevant entry surfaces
    assert "M:0002" not in ids         # the new, irrelevant one does not


# ── Reconcile, don't append ─────────────────────────────────────────────────────────────────────

def test_auto_capture_adds_not_silently_reconciled(fx):
    """Auto-capture is a working log: a new same-topic entry does NOT quietly overwrite the old.
    Both stay active and the core surfaces the disagreement as a conflict (M5) for a human to
    resolve — reconcile-don't-append happens at the committed store, not in auto-memory."""
    capture(fx, "decision", "Package manager is npm.", topic="package-manager")
    code, _ = capture(fx, "decision", "Package manager is now pnpm.", topic="package-manager")
    assert code == 0
    _, payload = select(fx, query="package manager")
    assert payload["status"] == "conflict"
    assert set(payload["conflicts"][0]["entries"]) == {"M:0001", "M:0002"}


# ── Fail closed: an unclassified error changes nothing ─────────────────────────────────────────

def test_bad_kind_is_a_refused_not_a_crash(fx):
    code, payload = capture(fx, "bogus-kind", "Whatever.")
    assert code != 0
    assert payload["status"] == "refused"
    assert not (fx.home / ".hercules" / "memory" / SLUG / "entries.md").exists()


def test_invalid_evidence_json_is_internal_and_writes_nothing(fx):
    mem = fx.home / ".hercules" / "memory" / SLUG
    code, payload = run(fx, "capture", "--cwd", str(fx.project), "--kind", "decision",
                        "--statement", "x", "--evidence", "{not-json")
    assert code == 3                       # EXIT_INTERNAL
    assert payload["status"] == "error"
    assert not (mem / "entries.md").exists()    # nothing was written


# ── Slug resolution is from the registry / path, never a model-supplied string ───────────────────

def test_slug_resolved_from_registry_not_believed(fx):
    # A cwd inside the registered project resolves to its registered slug.
    code, payload = run(fx, "inspect", "--cwd", str(fx.project))
    assert payload["slug"] == SLUG


def test_unregistered_directory_derives_a_deterministic_slug(tmp_path, fx):
    stray = tmp_path / "some-unregistered-repo"
    stray.mkdir()
    code, payload = run(fx, "inspect", "--cwd", str(stray))
    # No crash; a slug derived from the directory name, so any repo works with no per-repo config.
    assert payload["slug"] == "some-unregistered-repo"


# ── The rebuildable index is a cache, not the source of truth ───────────────────────────────────

def test_index_is_rebuildable_and_select_works_without_it(fx):
    capture(fx, "decision", "The database is PostgreSQL.", topic="db")
    # select works with NO index (scans the canonical entries.md).
    c1, p1 = select(fx, query="postgresql")
    assert c1 == 0 and p1["entries"]
    # reindex builds the best-effort index.
    c2, p2 = run(fx, "reindex", "--cwd", str(fx.project))
    assert c2 == 0
    assert (fx.home / ".hercules" / "memory" / SLUG / "index.db").is_file()
    # The canonical file is unchanged by reindexing.
    c3, p3 = select(fx, query="postgresql")
    assert [e["id"] for e in p3["entries"]] == [e["id"] for e in p1["entries"]]


# ── Path escape is refused ──────────────────────────────────────────────────────────────────────

def test_path_escape_is_refused():
    """The one thing auto-capture must never do is reach outside the memory subtree. A slug that
    would escape (e.g. ``..`` or ``.``) is refused before any write."""
    import sys
    module = sys.modules["memory_core"]  # the conftest loaded it the way a host does
    for bad in ("..", ".", "proj/..", "..hidden", ".hidden"):
        with pytest.raises(module.Refused):
            module.memory_root(bad, home="/tmp/never-here-12345")
    # A plain slug name is NOT an escape — it lives inside the memory subtree and is allowed.
    module.memory_root("proj", home="/tmp/never-here-12345")


# ── The four gated lifecycle ops, locked in CI (promote/delete/checkpoint/reindex) ───────────────
# Each was previously proven only by a manual smoke; these lock the fail-closed refuse path AND the
# success path so a regression that, say, writes the committed store without --confirm, or deletes a
# live entry by accident, fails CI instead of a human noticing.

def test_promote_confirm_is_the_only_path_to_the_committed_store(fx, tmp_path):
    committed = tmp_path / "docs-repo" / "learnings.md"
    committed.write_text("# committed learnings\n")
    capture(fx, "decision", "We use pnpm, not npm.", topic="package-manager")
    # The gate: without --confirm, promote refuses and the committed store is byte-for-byte untouched.
    code, payload = run(fx, "promote", "--cwd", str(fx.project), "--id", "M:0001",
                        "--target", str(committed))
    assert code == 5                       # EXIT_REFUSED
    assert payload["status"] == "refused"
    assert committed.read_text() == "# committed learnings\n"
    # With --confirm (a deliberate human decision), the entry reaches the committed store.
    code2, payload2 = run(fx, "promote", "--cwd", str(fx.project), "--id", "M:0001",
                          "--target", str(committed), "--confirm")
    assert code2 == 0
    assert payload2["status"] == "ok"
    promoted = committed.read_text()
    assert "## [M:0001]" in promoted        # the entry's human-readable heading
    assert "We use pnpm, not npm." in promoted


def test_delete_refuses_without_confirm_then_removes_with_it(fx):
    capture(fx, "decision", "Auth is JWT in the header.", topic="auth")
    capture(fx, "decision", "The cache key was missing a tenant id.", topic="cache")
    # The gate: deletion is a corrective human action, never auto-capture — refused without --confirm.
    code, payload = run(fx, "delete", "--cwd", str(fx.project), "--id", "M:0001")
    assert code == 5                       # EXIT_REFUSED
    assert payload["status"] == "refused"
    code2, _ = run(fx, "inspect", "--cwd", str(fx.project))
    assert code2 == 0 and _["entries"] == 2          # nothing was removed
    # With --confirm, the entry is gone and the count drops.
    code3, payload3 = run(fx, "delete", "--cwd", str(fx.project), "--id", "M:0001", "--confirm")
    assert code3 == 0
    assert payload3["status"] == "ok"
    assert payload3["remaining"] == 1
    _, after = run(fx, "inspect", "--cwd", str(fx.project))
    assert after["entries"] == 1


def test_checkpoint_writes_a_restorable_snapshot(fx):
    state = {"progress": "50%", "next": "run the tests", "blockers": []}
    code, payload = run(fx, "checkpoint", "--cwd", str(fx.project),
                        "--task", "build-42", "--state", json.dumps(state))
    assert code == 0
    assert payload["status"] == "ok"
    snapshot = fx.home / ".hercules" / "memory" / SLUG / "checkpoints" / "build-42.json"
    assert snapshot.is_file()
    # The snapshot round-trips the recorded state (a future session resumes from it).
    assert json.loads(snapshot.read_text())["state"] == state
    # Idempotent per task: re-checkpointing the same task overwrites its own file, never another's.
    code2, _ = run(fx, "checkpoint", "--cwd", str(fx.project),
                   "--task", "build-42", "--state", json.dumps({**state, "progress": "100%"}))
    assert code2 == 0
    assert json.loads(snapshot.read_text())["state"]["progress"] == "100%"


def test_reindex_rebuilds_terms_from_the_canonical_file(fx):
    capture(fx, "decision", "The database is PostgreSQL.", topic="db")
    capture(fx, "correction", "The cache key was missing a tenant id.", topic="cache")
    code, payload = run(fx, "reindex", "--cwd", str(fx.project))
    assert code == 0
    assert payload["status"] == "ok"
    assert payload["terms"] > 0
    # The rebuilt index is a cache: select still works and returns the canonical entries.
    _, sel = select(fx, query="postgresql")
    assert [e["id"] for e in sel["entries"]] == ["M:0001"]
