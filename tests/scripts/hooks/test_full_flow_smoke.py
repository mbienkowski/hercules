"""One session walked through the whole flow the gates are supposed to hold together, against the
SHIPPED copies, with real files on a real git repo.

The other smoke files each prove one mechanism in isolation. This one asks the question a single
mechanism can't answer: does the SEQUENCE survive contact with itself — two specs in one session,
one retired while the other is still pending, `keep_specs` changing what gets deleted, and the two
places an over-eager gate would do real damage: blocking an ordinary code edit during Build, and
blocking a spec write for a session the gate has never heard of.

Nothing here is about whether the generated CONTENT is good — that is what real usage will tell us.
This is only about whether the mechanical flow holds: gate fires when it should, stays out of the
way when it shouldn't, and the state on disk at the end matches what was actually done.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.scripts.tools.doc_lint.conftest import CLEAN_REQUIREMENTS, CLEAN_SPEC, REQUIREMENTS_NAME
from tests.scripts.tools.doc_report.conftest import full_review

_ALLOW, _DENY = 0, 2
_REPO_ROOT = Path(__file__).resolve().parents[3]
_DIST = _REPO_ROOT / "dist"
_SESSION = "2026-08-04-two-spec-session"
_SLUG = "fullflow"

_SHIPPED = sorted(p.name for p in _DIST.iterdir()
                  if (p / "hooks" / "document_gate.py").is_file()
                  and (p / "tools" / "probe_run.py").is_file()
                  and (p / "tools" / "retire_spec.py").is_file())


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})


class Session:
    """A live drive against one shipped ecosystem: real files, a real git repo, the gate and the
    tools invoked exactly as subprocesses, never imported."""

    def __init__(self, tmp_path: Path, ecosystem: str, tier: str = "medium"):
        self.eco = ecosystem
        self.home = tmp_path / "home"
        self.repo = tmp_path / "repo"
        self.folder = self.repo / "docs" / _SESSION
        self.folder.mkdir(parents=True)
        (self.home / ".hercules" / "state").mkdir(parents=True)
        # docs_root is absolute here deliberately: retire_spec.py's own containment check
        # (resolve_spec -> is_within(canon(spec_path), canon(docs_root))) resolves a RELATIVE
        # docs_root against the retire_spec PROCESS's cwd at invocation, not against `directory` —
        # confirmed separately and reported upstream. document_gate.py's own resolver (written this
        # session) does join a relative docs_root to `directory`; retire_spec.py's older one does
        # not. Using an absolute path here keeps this test testing the NEW flow, not that gap.
        (self.home / ".hercules" / "config.json").write_text(json.dumps({
            "schema_version": 1,
            "projects": {_SLUG: {"directory": str(self.repo), "docs_root": str(self.repo / "docs"),
                                "state_file": "%s.json" % _SLUG, "repositories": {}}}}))
        self.state_path = self.home / ".hercules" / "state" / ("%s.json" % _SLUG)
        self._write_state(tier=tier, phase="design")
        _git(self.repo, "init", "-q")

    def _write_state(self, tier: str, phase: str, pending_specs=None) -> None:
        session = {"tier": tier, "current_phase": phase}
        if pending_specs is not None:
            session["pending_specs"] = list(pending_specs)
        self.state_path.write_text(json.dumps({
            "schema_version": 1, "active_session": _SESSION,
            "sessions": {_SESSION: session}}))

    def _run(self, tool: str, *args: str, input_text: str = None):
        return subprocess.run([sys.executable, str(_DIST / self.eco / tool), *args],
                              input=input_text, capture_output=True, text=True,
                              env={**os.environ, "HOME": str(self.home)})

    def gate(self, mode: str, event: dict):
        result = self._run("hooks/document_gate.py", mode, input_text=json.dumps(event))
        return result.returncode, result.stderr

    def write_event(self, path: Path, relative: bool = False) -> dict:
        target = str(path.relative_to(self.repo)) if relative else str(path)
        return {"tool_name": "Write", "cwd": str(self.repo), "tool_input": {"file_path": target}}

    def probe(self, label: str, tier: str, *, ok: bool = True):
        record = self.folder / "probes" / ("probe-%s.json" % label)
        cmd = ["true"] if ok else ["false"]
        result = self._run("tools/probe_run.py", "run", "--label", label, "--tier", tier,
                           "--expect", "it runs clean", "--into", str(record), "--", *cmd)
        return json.loads(result.stdout)

    def retire(self, spec_name: str, *, keep_specs: bool = False):
        # retire_spec.py resolves the spec against the session's OWN record, never trusting a bare
        # name to already sit in the right place — so the argument must be the real on-disk path.
        args = ["apply", "--project-slug", _SLUG, "--session-id", _SESSION,
                "--spec-file", str(self.folder / spec_name), "--confirm"]
        if keep_specs:
            args.append("--keep-specs")
        result = self._run("tools/retire_spec.py", *args)
        return result.returncode, json.loads(result.stdout)


@pytest.mark.parametrize("ecosystem", _SHIPPED)
def test_two_specs_one_session_probes_once_retire_independently(tmp_path, ecosystem):
    session = Session(tmp_path, ecosystem, tier="medium")
    requirements = session.folder / REQUIREMENTS_NAME
    requirements.write_text(CLEAN_REQUIREMENTS, encoding="utf-8")
    requirements.with_name(requirements.stem + "-report.json").write_text(
        json.dumps(full_review(tier="medium")), encoding="utf-8")

    spec_a = session.folder / ("%s-spec-01-a.md" % _SESSION)
    spec_b = session.folder / ("%s-spec-02-b.md" % _SESSION)

    # 1. No probes yet — the FIRST spec of the session cannot be written.
    code, err = session.gate("probes", session.write_event(spec_a))
    assert code == _DENY, "%s: allowed spec-01 with zero probes" % ecosystem
    assert "cannot be written yet" in err

    # 2. Probes run and verify (this is the exact path that once failed on a missing directory).
    for label in ("dependency", "seam"):
        result = session.probe(label, "medium")
        assert result.get("verdict") == "PASS", "%s: probe %s: %s" % (ecosystem, label, result)

    # 3. Both specs of this session may now be written — probes are session-scoped, not per-spec.
    for spec in (spec_a, spec_b):
        spec.write_text(CLEAN_SPEC, encoding="utf-8")
        code, err = session.gate("probes", session.write_event(spec))
        assert code == _ALLOW, "%s: %s blocked after probes verified: %s" % (
            ecosystem, spec.name, err)

    # 4. A RELATIVE file_path (as some hosts pass) resolves the same as an absolute one.
    code, _ = session.gate("probes", session.write_event(spec_a, relative=True))
    assert code == _ALLOW, "%s: a relative path was not resolved against cwd" % ecosystem

    # 5. Each spec gets its own review, independently.
    for spec in (spec_a, spec_b):
        spec.with_name(spec.stem + "-report.json").write_text(
            json.dumps(full_review(kind="spec", tier="medium")), encoding="utf-8")

    # 6. Entering build is refused while EITHER spec's review is missing...
    (spec_b.with_name(spec_b.stem + "-report.json")).unlink()
    advance = {"tool_name": "Bash", "cwd": str(session.repo), "tool_input": {"command":
               "python3 tools/state_patch.py apply --project-slug %s --session-id %s "
               "--set current_phase=build --confirm" % (_SLUG, _SESSION)}}
    code, err = session.gate("advance", advance)
    assert code == _DENY, "%s: entered build while spec-02 had no review" % ecosystem

    # ...and allowed once both do.
    spec_b.with_name(spec_b.stem + "-report.json").write_text(
        json.dumps(full_review(kind="spec", tier="medium")), encoding="utf-8")
    code, err = session.gate("advance", advance)
    assert code == _ALLOW, "%s: still blocked with both specs reviewed: %s" % (ecosystem, err)

    # 7. Commit everything so retirement exercises the real `git rm` path, not the unlink fallback.
    _git(session.repo, "add", ".")
    _git(session.repo, "commit", "-q", "-m", "design output")
    session._write_state(tier="medium", phase="build", pending_specs=[spec_a.name, spec_b.name])

    # 8. Retiring spec-01 deletes IT and its report; spec-02 and ITS report are untouched.
    code, payload = session.retire(spec_a.name)
    assert code == 0, payload
    assert payload["spec"]["deletion"] == "git_rm"
    assert payload["spec"]["report_deletion"] == "git_rm"
    assert not spec_a.exists()
    assert not spec_a.with_name(spec_a.stem + "-report.json").exists()
    assert spec_b.exists(), "%s: retiring spec-01 deleted spec-02" % ecosystem
    assert spec_b.with_name(spec_b.stem + "-report.json").exists(), (
        "%s: retiring spec-01 deleted spec-02's report" % ecosystem)

    # 9. keep_specs preserves the spec but STILL drops its now-stale review.
    code, payload = session.retire(spec_b.name, keep_specs=True)
    assert code == 0, payload
    assert payload["spec"]["deletion"] == "kept"
    assert spec_b.exists(), "%s: keep_specs did not keep the spec" % ecosystem
    assert not spec_b.with_name(spec_b.stem + "-report.json").exists(), (
        "%s: keep_specs kept a review of the pre-refresh draft" % ecosystem)


@pytest.mark.parametrize("ecosystem", _SHIPPED)
def test_ordinary_code_edits_during_build_are_never_touched(tmp_path, ecosystem):
    """The gate that exists to stop a spec being written unreviewed must not so much as glance at
    the hundreds of ordinary source and test writes a Build TDD loop actually performs."""
    session = Session(tmp_path, ecosystem, tier="high")  # the tier with the largest probe budget
    (session.repo / "src").mkdir()
    for relative in ("src/app.py", "tests/test_app.py", "README.md",
                     "docs/%s/build-notes.md" % _SESSION):
        target = session.repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        code, err = session.gate("probes", session.write_event(target))
        assert (code, err) == (_ALLOW, ""), "%s: %s was gated: %s" % (ecosystem, relative, err)


@pytest.mark.parametrize("ecosystem", _SHIPPED)
def test_trivial_tier_never_blocks_a_spec_write(tmp_path, ecosystem):
    """Depth scales down too — a typo-sized change owes no feasibility pass."""
    session = Session(tmp_path, ecosystem, tier="trivial")
    spec = session.folder / ("%s-spec-01-a.md" % _SESSION)
    code, err = session.gate("probes", session.write_event(spec))
    assert (code, err) == (_ALLOW, "")
