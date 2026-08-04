"""Retiring a spec must not leave its review behind.

A spec's `-report.json` proves ONE draft was reviewed. Once that draft is gone — deleted at retire,
or refreshed under `keep_specs` — the report is not merely stale, it is actively misleading: it
would keep saying `proceed` about a document nobody reviewed. This is the defect a prior pass through
this feature shipped without noticing, because every existing test fixture retires a spec with no
report sitting beside it — the gap was invisible until someone asked whether the report's lifecycle
was ever wired up. It wasn't, until now.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.scripts.tools.retire_spec.conftest import PENDING_SPEC, SPEC, apply, plan


def _report_path(fx, session=None, spec=SPEC) -> Path:
    return fx.spec_path(session or fx.__dict__.get("_default_session", "2026-06-22-user-auth"),
                        spec).with_name(Path(spec).stem + "-report.json")


def test_retiring_a_spec_deletes_its_report_too(fx):
    report = _report_path(fx)
    report.write_text('{"decision": "proceed"}', encoding="utf-8")
    assert report.exists()
    code, payload = apply(fx)
    assert code == 0
    assert not report.exists(), "the review outlived the spec it reviewed"
    assert payload["spec"]["report_deletion"] in ("git_rm", "unlink")


def test_a_report_is_git_rm_d_when_tracked(fx):
    """The same route the spec itself takes, so a committed review is removed the same way a
    committed spec is — staged, not just vanished from the working tree."""
    import subprocess
    report = _report_path(fx)
    report.write_text('{"decision": "proceed"}', encoding="utf-8")
    subprocess.run(["git", "-C", str(fx.docs), "add", "."], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(fx.docs), "commit", "-m", "reports"],
                   check=True, capture_output=True,
                   env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                        "GIT_COMMITTER_EMAIL": "t@t", "HOME": "/tmp"})
    _, payload = apply(fx)
    assert payload["spec"]["report_deletion"] == "git_rm"
    assert not report.exists()


def test_retiring_a_spec_with_no_report_is_not_an_error(fx):
    """A spec retired before review reports existed — or one nobody ever reviewed — must not fail
    retire on that account. Absent counts as done, the same contract the spec deletion already has."""
    report = _report_path(fx)
    assert not report.exists()
    code, payload = apply(fx)
    assert code == 0
    assert payload["spec"]["report_deletion"] == "already_absent"


def test_the_report_is_deleted_even_when_keep_specs_preserves_the_spec(fx):
    """The report review a PRE-refresh draft, and the spec is about to be refreshed to match what
    shipped. Keeping the report would make it look like the shipped version was reviewed, when only
    the draft was. Deleting it is not a keep_specs override — it never conditioned on keep_specs."""
    report = _report_path(fx)
    report.write_text('{"decision": "proceed"}', encoding="utf-8")
    spec_path = fx.spec_path()
    code, payload = apply(fx, "--keep-specs")
    assert code == 0
    assert payload["spec"]["deletion"] == "kept"
    assert spec_path.exists(), "keep_specs must still keep the spec itself"
    assert not report.exists(), "but never the stale review of the pre-refresh draft"


def test_the_plan_preview_names_the_report_it_will_delete(fx):
    """Plan mode writes nothing, so its promise is only as good as what it lists — a preview that
    omits the report cleanup would under-report what apply actually does."""
    _, payload = plan(fx)
    assert payload["would_retire"]["delete_report_file"] is True


def test_a_report_beside_a_different_pending_spec_is_left_alone(fx):
    """Retiring one spec must not touch another spec's review — the cleanup is scoped to the exact
    file stem being retired, not a directory-wide sweep."""
    other_report = fx.spec_path(spec=PENDING_SPEC).with_name(
        Path(PENDING_SPEC).stem + "-report.json")
    other_report.write_text('{"decision": "revise"}', encoding="utf-8")
    apply(fx)
    assert other_report.exists()
