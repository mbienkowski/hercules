"""Regression reproductions through public operations, with throwaway homes only."""
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.scripts.tools.memory_core.conftest import SLUG, capture, run, select

core = sys.modules["memory_core"]


def memory(fx):
    return fx.home / ".hercules" / "memory" / SLUG


@pytest.mark.parametrize("component", [".hercules", "memory", SLUG])
def test_redirected_trusted_boundary_never_writes_external_directory(fx, tmp_path, component):
    boundary = fx.home / ".hercules"
    if component != ".hercules":
        boundary /= "memory"
    if component == SLUG:
        boundary /= SLUG
    boundary.parent.mkdir(parents=True, exist_ok=True)
    outside = tmp_path / "external"
    if boundary.exists():
        boundary.rename(outside)
    else:
        outside.mkdir()
    boundary.symlink_to(outside, target_is_directory=True)
    before = {p.relative_to(outside): p.read_bytes() for p in outside.rglob("*") if p.is_file()}
    code, result = capture(fx, "decision", "Use PostgreSQL.")
    assert code != 0 and result["status"] == "refused"
    assert {p.relative_to(outside): p.read_bytes() for p in outside.rglob("*") if p.is_file()} == before


@pytest.mark.parametrize("filename,command", [
    ("entries.md", "capture"), ("stats.json", "capture"), (".lock", "capture"),
    ("index.db", "reindex"), ("index.db-journal", "reindex"),
    ("index.db-wal", "reindex"), ("index.db-shm", "reindex"),
    ("checkpoints", "checkpoint"), (".deliveries.json", "delivery"),
])
def test_symlinked_storage_files_and_sqlite_sidecars_are_refused(fx, tmp_path, filename, command):
    capture(fx, "decision", "Existing fact.")
    outside = tmp_path / "outside"
    if filename == "checkpoints":
        outside.mkdir()
    else:
        outside.write_bytes(b"external bytes must survive")
    target = (memory(fx).parent if command == "delivery" else memory(fx)) / filename
    if target.exists():
        target.unlink()
    target.symlink_to(outside, target_is_directory=outside.is_dir())
    if command == "capture":
        code, _ = capture(fx, "decision", "Another fact.")
    elif command == "delivery":
        with pytest.raises(core.Refused):
            core.claim_delivery(str(fx.project), "s", "v", home=fx.home)
        code = 5
    else:
        args = [command, "--cwd", str(fx.project)]
        if command == "checkpoint":
            args += ["--task", "build", "--state", "{}"]
        code, _ = run(fx, *args)
    assert code != 0
    assert (not list(outside.iterdir())) if outside.is_dir() else outside.read_bytes() == b"external bytes must survive"


@pytest.mark.parametrize("which", ["entries.md", "stats.json"])
@pytest.mark.parametrize("command", ["capture", "delete", "report-use", "checkpoint", "reindex", "promote"])
def test_corruption_refuses_every_mutation_and_preserves_both_authoritative_files(fx, which, command):
    capture(fx, "decision", "Use PostgreSQL.")
    path = memory(fx) / which
    path.write_bytes(path.read_bytes() + b'\n<!-- entry:M:9999 -->\n```json\n{"broken":')
    before = {name: (memory(fx) / name).read_bytes() for name in ("entries.md", "stats.json")}
    args = {
        "capture": ["--kind", "decision", "--statement", "New fact."],
        "delete": ["--id", "M:0001", "--confirm"],
        "report-use": ["--task", "t", "--entries", "M:0001:1"],
        "checkpoint": ["--task", "t", "--state", "{}"],
        "reindex": [],
        "promote": ["--id", "M:0001", "--confirm", "--target", str(fx.project / "learnings.md")],
    }
    code, payload = run(fx, command, "--cwd", str(fx.project), *args[command])
    assert code != 0 and payload["status"] == "refused"
    assert {name: (memory(fx) / name).read_bytes() for name in before} == before
    assert not (fx.project / "learnings.md").exists()


@pytest.mark.parametrize("bad", [b"[]", b'{"hits": []}', b'{"hits": {"x": "bad"}}',
                                  b'{"hits": {}, "use_log": [null]}'])
def test_structurally_invalid_stats_are_not_reset(fx, bad):
    capture(fx, "decision", "Existing fact.")
    (memory(fx) / "stats.json").write_bytes(bad)
    assert capture(fx, "decision", "New fact.")[0] != 0
    assert (memory(fx) / "stats.json").read_bytes() == bad


def test_failed_posix_lock_writes_no_memory(fx, monkeypatch):
    import fcntl

    def unavailable(*args):
        raise OSError("lock unavailable")

    monkeypatch.setattr(fcntl, "flock", unavailable)
    assert capture(fx, "decision", "Must not be stored.")[0] != 0
    assert not (memory(fx) / "entries.md").exists()
    assert not (memory(fx) / "stats.json").exists()


@pytest.mark.parametrize("fail", [False, True])
def test_windows_locks_the_first_byte_and_refuses_lock_failure(fx, monkeypatch, fail):
    calls = []
    monkeypatch.setattr(core.time, "sleep", lambda _: None)  # 500 retries x 10 ms would dominate the suite

    def locking(fd, mode, size):
        calls.append((mode, size, os.lseek(fd, 0, os.SEEK_CUR), os.fstat(fd).st_size))
        if fail:
            raise OSError("Windows lock unavailable")

    monkeypatch.setitem(sys.modules, "msvcrt", SimpleNamespace(locking=locking, LK_NBLCK=2, LK_UNLCK=0))
    monkeypatch.setattr(core, "os", SimpleNamespace(**{**vars(os), "name": "nt"}))
    code, _ = capture(fx, "decision", "Windows fact.")
    assert calls[0] == (2, 1, 0, 1)
    assert code != 0 if fail else code == 0
    assert (memory(fx) / "entries.md").exists() is (not fail)
    if fail:
        assert len(calls) == 500 and not any(c[0] == 0 for c in calls)  # retried, then refused
    else:
        assert calls[-1][:3] == (0, 1, 0)


def test_delete_waits_out_a_brief_transaction_lock(fx):
    import threading

    capture(fx, "decision", "Delete this.")
    lock = core._SlugLock(memory(fx))
    lock.__enter__()
    release = threading.Timer(0.2, lock.__exit__, (None, None, None))  # another writer holds it ~200 ms
    release.start()
    try:
        assert core.delete_entry(str(fx.project), "M:0001", True, home=fx.home)["remaining"] == 0
    finally:
        release.join()


@pytest.mark.parametrize("name,code", [("notes.py", "target_not_markdown"), (".git/hooks.md", "target_in_git")])
def test_promote_writes_only_markdown_outside_git_metadata(fx, name, code):
    capture(fx, "decision", "Use PostgreSQL.")
    target = fx.project / name
    target.parent.mkdir(parents=True, exist_ok=True)
    result_code, payload = run(fx, "promote", "--cwd", str(fx.project), "--id", "M:0001",
                               "--target", str(target), "--confirm")
    assert result_code != 0 and payload["code"] == code
    assert not target.exists()


def test_parallel_captures_keep_every_distinct_fact(fx):
    with ThreadPoolExecutor(6) as pool:
        results = list(pool.map(lambda i: core.capture_entry(
            str(fx.project), "decision", f"Distinct fact {i}.", home=fx.home), range(18)))
    assert len({r["entry"]["id"] for r in results}) == 18
    assert run(fx, "inspect", "--cwd", str(fx.project))[1]["entries"] == 18


def test_deleting_highest_and_all_ids_never_reuses_usage_references(fx):
    capture(fx, "decision", "First.")
    capture(fx, "decision", "Second.")
    run(fx, "report-use", "--cwd", str(fx.project), "--task", "t", "--entries", "M:0002:1")
    for eid in ("M:0002", "M:0001"):
        assert run(fx, "delete", "--cwd", str(fx.project), "--id", eid, "--confirm")[0] == 0
    assert capture(fx, "decision", "Third.")[1]["entry"]["id"] == "M:0003"
    payload = run(fx, "report-use", "--cwd", str(fx.project), "--task", "t2", "--entries", "M:0002:1")[1]
    assert payload["accepted"] == []


def test_unregistered_nested_git_paths_share_identity_but_same_named_repos_do_not(fx, tmp_path):
    repos = [tmp_path / "a" / "repo", tmp_path / "b" / "repo"]
    for repo in repos:
        (repo / ".git").mkdir(parents=True)
        (repo / "src" / "nested").mkdir(parents=True)
    slug = core.resolve_slug(str(repos[0]), home=fx.home)
    assert slug == core.resolve_slug(str(repos[0] / "src" / "nested"), home=fx.home)
    assert slug != core.resolve_slug(str(repos[1]), home=fx.home)
    alias = tmp_path / "alias"
    alias.symlink_to(repos[0], target_is_directory=True)
    assert slug == core.resolve_slug(str(alias / "src"), home=fx.home)


def test_equivalent_capture_counts_repetition_without_hiding_contradictions(fx):
    a = capture(fx, "decision", "Use  PostgreSQL.", topic="Database")[1]["entry"]
    b = capture(fx, "decision", " use postgresql! ", topic=" database ")[1]["entry"]
    assert a["id"] == b["id"] and b["repetitions"] == 2
    capture(fx, "decision", "Use SQLite.", topic="database")
    payload = select(fx, query="postgresql", budget=1)[1]
    assert payload["status"] == "conflict"
    assert set(payload["conflicts"][0]["entries"]) == {"M:0001", "M:0002"}
    assert select(fx, query="unrelated")[1]["status"] == "conflict"


def test_query_sorts_relevance_then_confidence_then_usefulness(fx):
    capture(fx, "decision", "Cache.")
    capture(fx, "correction", "Cache tenant.")
    capture(fx, "decision", "Cache tenant index.")
    capture(fx, "verified-finding", "Cache.")
    capture(fx, "decision", "Cache tenant index extra.")
    run(fx, "report-use", "--cwd", str(fx.project), "--task", "t", "--entries", "M:0005:1")
    ids = [e["id"] for e in select(fx, query="cache tenant index")[1]["entries"]]
    assert ids == ["M:0005", "M:0003", "M:0002", "M:0004", "M:0001"]


@pytest.mark.parametrize("query", ["", "secret"])
def test_pinned_task_entries_never_leak_to_other_task_or_layer(fx, query):
    capture(fx, "decision", "Project secret.", topic="access")
    capture(fx, "decision", "Alpha secret.", scope="task:alpha", pinned=True, topic="access")
    capture(fx, "decision", "Beta secret.", scope="task:beta", pinned=True, topic="access")
    for options, expected in [({}, ["M:0001"]), ({"task": "alpha"}, ["M:0001", "M:0002"]),
                              ({"task": "alpha", "layers": "task"}, ["M:0002"]),
                              ({"task": "alpha", "layers": "project"}, ["M:0001"])]:
        payload = select(fx, query=query, **options)[1]
        assert {e["id"] for e in payload["entries"]} == set(expected)
        assert payload["conflicts"] == []


def test_default_query_is_bounded_in_entries_and_serialized_bytes(fx):
    for i in range(12):
        capture(fx, "decision", f"Cache {i}.")
    payload = select(fx, query="cache")[1]
    assert len(payload["entries"]) == payload["budget"]["entries"] == 8
    assert payload["truncation"]["omitted"] == 4
    capture(fx, "decision", "Cache giant.", rationale="界" * 20_000)
    payload = select(fx, query="cache giant", budget=100)[1]
    size = len(json.dumps(payload["entries"], ensure_ascii=False, separators=(",", ":")).encode())
    assert size == payload["budget"]["used_bytes"] <= payload["budget"]["bytes"]
    assert not any(e["statement"] == "Cache giant." for e in payload["entries"])
    assert payload["truncation"]["omitted"] == 1


def test_promote_resolves_relative_target_against_requested_cwd(fx, tmp_path, monkeypatch):
    capture(fx, "decision", "Use PostgreSQL.")
    monkeypatch.chdir(tmp_path)
    code, result = run(fx, "promote", "--cwd", str(fx.project), "--id", "M:0001",
                       "--target", "learnings.md", "--confirm")
    assert code == 0 and Path(result["target"]) == fx.project / "learnings.md"
    assert not (tmp_path / "learnings.md").exists()
    assert "Use PostgreSQL." in (fx.project / "learnings.md").read_text()


def test_promote_rejects_absolute_escape_and_symlink_target(fx, tmp_path):
    capture(fx, "decision", "Use PostgreSQL.")
    outside = tmp_path / "unregistered.md"
    outside.write_bytes(b"preserve")
    link = fx.project / "learnings.md"
    link.symlink_to(outside)
    for target in (outside, link):
        assert run(fx, "promote", "--cwd", str(fx.project), "--id", "M:0001",
                   "--target", str(target), "--confirm")[0] != 0
    assert outside.read_bytes() == b"preserve"


@pytest.mark.parametrize("task", ["../escape", "a/b", "a\\b", ".hidden", "", "two words", "CON", "NUL.json", "foo."])
def test_checkpoint_rejects_unsafe_names_instead_of_colliding(fx, task):
    assert run(fx, "checkpoint", "--cwd", str(fx.project), "--task", task, "--state", "{}")[0] != 0
    assert not (memory(fx) / "checkpoints").exists()


@pytest.mark.parametrize("secret", ["-----BEGIN RSA PRIVATE KEY-----", "AKIA" + "A" * 16,
                                    "ghp_" + "a" * 36, "sk-proj-" + "b" * 48,
                                    "Bearer " + "c" * 30, "password=supersecretvalue"])
def test_capture_refuses_recognizable_credentials_without_persisting_them(fx, secret):
    for kwargs in ({}, {"rationale": secret}, {"evidence": json.dumps({"source": secret})}):
        assert capture(fx, "decision", secret if not kwargs else "A safe fact.", **kwargs)[0] != 0
    assert not (memory(fx) / "entries.md").exists()


def test_capture_statement_limit_and_markup_roundtrip(fx):
    assert capture(fx, "decision", "x" * 1001)[0] != 0
    assert capture(fx, "decision", "x" * 1000)[0] == 0
    statement = "<!-- entry:fake --> ```json"
    assert capture(fx, "decision", statement)[0] == 0
    assert any(e["statement"] == statement for e in select(fx)[1]["entries"])


def test_delivery_deduplicates_per_session_and_retains_bounded_private_state(fx):
    claim = lambda session, fingerprint: core.claim_delivery(str(fx.project), session, fingerprint, home=fx.home)
    assert claim("first/private/session", "v1") is True
    assert claim("first/private/session", "v1") is False
    assert claim("second", "v1") is True
    assert claim("first/private/session", "v2") is True
    for i in range(260):
        assert claim(f"session {i}", "v1") is True
    raw = (fx.home / ".hercules" / "memory" / ".deliveries.json").read_text()
    assert len(json.loads(raw)) == 256
    assert "first/private/session" not in raw
    assert claim("session 139", "v1") is False


def test_concurrent_delivery_claims_have_one_winner(fx):
    def claim(_):
        try:
            return core.claim_delivery(str(fx.project), "session", "same-context", home=fx.home)
        except core.Refused as busy:  # a claim that finds the lock held is refused, never queued
            assert busy.code == "busy"
            return None
    with ThreadPoolExecutor(6) as pool:
        results = list(pool.map(claim, range(12)))
    assert results.count(True) == 1


def test_delivery_refuses_corruption_without_overwriting_it(fx):
    path = fx.home / ".hercules" / "memory" / ".deliveries.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"not JSON")
    with pytest.raises(core.Refused):
        core.claim_delivery(str(fx.project), "s", "f", home=fx.home)
    assert path.read_bytes() == b"not JSON"


def test_delivery_reset_reclaims_same_context_after_compaction(fx):
    args = (str(fx.project), "session", "same-context")
    assert core.claim_delivery(*args, home=fx.home)
    assert not core.claim_delivery(*args, home=fx.home)
    assert core.claim_delivery(*args, home=fx.home, reset=True)
    assert not core.claim_delivery(*args, home=fx.home)


def test_explicit_supersession_keeps_history_and_clears_only_named_conflict(fx):
    capture(fx, "decision", "Use npm.", topic="package-manager")
    code, result = capture(fx, "decision", "Use pnpm.", topic="package-manager", supersedes="M:0001")
    assert code == 0 and result["entry"]["supersedes"] == "M:0001"
    entries = core.load_entries(memory(fx))
    assert len(entries) == 2
    assert entries[0]["statement"] == "Use npm."
    assert entries[0]["status"] == "superseded"
    assert entries[0]["superseded_by"] == "M:0002"
    payload = select(fx)[1]
    assert payload["status"] == "ok" and [e["id"] for e in payload["entries"]] == ["M:0002"]
    # Omission of the explicit ID retains the original disagreement behavior.
    capture(fx, "decision", "Use yarn.", topic="package-manager")
    assert select(fx)[1]["status"] == "conflict"


@pytest.mark.parametrize("scope,topic,eid", [("task:other", "db", "M:0001"),
                                            ("project", "other", "M:0001"),
                                            ("project", "db", "M:9999")])
def test_supersession_refuses_unrelated_or_missing_prior_entry(fx, scope, topic, eid):
    capture(fx, "decision", "Use PostgreSQL.", topic="db")
    before = (memory(fx) / "entries.md").read_bytes()
    assert capture(fx, "decision", "Use SQLite.", topic=topic, scope=scope, supersedes=eid)[0] != 0
    assert (memory(fx) / "entries.md").read_bytes() == before


def test_secret_evidence_json_keys_are_checked_and_errors_do_not_echo_credentials(fx):
    credential = "supersecretvalue"
    code, payload = capture(fx, "decision", "Safe fact.", evidence=json.dumps({"api_key": credential}))
    assert code != 0 and credential not in json.dumps(payload)
    assert not (memory(fx) / "entries.md").exists()


@pytest.mark.parametrize("options", [{"budget": -1}, {"byte_budget": 0}, {"byte_budget": -1}])
def test_invalid_selection_budgets_are_refused(fx, options):
    assert select(fx, **options)[0] != 0


def test_compact_capture_only_changes_cli_success_output(fx):
    code, full = capture(fx, "decision", "First fact.", topic="first")
    assert code == 0 and full["command"] == "capture"
    assert full["entry"]["statement"] == "First fact." and "provenance" in full["entry"]
    code, compact = capture(fx, "decision", "Second fact.", topic="second", compact=True)
    assert code == 0 and compact == {"status": "ok", "entry_id": "M:0002", "revision": 1}
    # A deduplicated capture uses the same compact contract.
    assert capture(fx, "decision", "Second fact.", topic="second", compact=True)[1] == compact
    direct = core.capture_entry(str(fx.project), "decision", "Third fact.", home=fx.home)
    assert direct["entry"]["statement"] == "Third fact." and "provenance" in direct["entry"]
    code, refused = capture(fx, "decision", "password=supersecretvalue", compact=True)
    assert code != 0 and refused["code"] == "likely_secret"


def test_legitimate_home_alias_is_canonicalized_before_enforcing_memory_boundary(fx, tmp_path):
    alias = tmp_path / "home-alias"
    alias.symlink_to(fx.home, target_is_directory=True)
    result = core.capture_entry(str(fx.project), "decision", "A durable preference.", home=alias)
    assert result["entry"]["id"] == "M:0001"
    assert core.select_context(str(fx.project), home=alias)["entries"][0]["statement"] == "A durable preference."
    # Canonicalizing HOME must not canonicalize away an unsafe link inside .hercules.
    outside = tmp_path / "external-store"
    (memory(fx) / "entries.md").rename(outside)
    (memory(fx) / "entries.md").symlink_to(outside)
    with pytest.raises(core.Refused):
        core.capture_entry(str(fx.project), "decision", "Must not write.", home=alias)


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS system /var alias")
def test_macos_tmpdir_home_accepts_system_var_alias(fx):
    canonical = str(fx.home.resolve())
    if not canonical.startswith("/private/var/"):
        pytest.skip("temporary home is outside macOS /var")
    home_alias = Path(canonical.removeprefix("/private"))
    result = core.capture_entry(str(fx.project), "decision", "Mac preference.", home=home_alias)
    assert result["entry"]["id"] == "M:0001"
    assert core.select_context(str(fx.project), home=home_alias)["entries"]


@pytest.mark.parametrize("field", ["topic", "related_code_version", "captured_by",
                                  "extraction_model", "extraction_version"])
def test_capture_screens_metadata_before_persisting_or_injecting_it(fx, field):
    secret = "ghp_" + "a" * 36
    with pytest.raises(core.Refused) as error:
        core.capture_entry(str(fx.project), "decision", "A safe preference.", home=fx.home, **{field: secret})
    assert error.value.code == "likely_secret"
    assert not (memory(fx) / "entries.md").exists()
