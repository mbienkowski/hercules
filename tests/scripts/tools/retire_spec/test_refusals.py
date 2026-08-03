"""Every way a retire is rejected before anything is touched — usage mistakes, an unresolvable
project or session, a spec the record does not name — each proving nothing on disk moved."""

from __future__ import annotations

import json

from tests.scripts.tools.retire_spec.conftest import PENDING_SPEC, apply, plan


def test_a_blank_spec_file_is_refused(fx):
    code, payload = plan(fx, spec_file="")
    assert code == 1
    assert payload["rule"] == "spec_file_blank"


def test_a_spec_naming_neither_the_current_nor_a_pending_spec_is_refused(fx):
    code, payload = plan(fx, spec_file=str(fx.docs / "2026-06-22-user-auth" / "made-up-spec.md"))
    assert code == 1
    assert payload["rule"] == "unknown_spec"
    assert "made-up-spec.md" in payload["message"]


def test_a_pending_spec_is_a_legitimate_retire_target_even_off_disk(fx):
    """`resolve_spec` anchors on the session's own record, not on the file existing yet — the resume
    path retires a spec whose build finished but whose file delete was interrupted."""
    target = fx.docs / "2026-06-22-user-auth" / PENDING_SPEC
    code, payload = plan(fx, spec_file=str(target))
    assert code == 0
    assert payload["spec"]["name"] == PENDING_SPEC


def test_a_spec_path_outside_the_documents_root_is_refused(tmp_path, fx):
    outside = tmp_path / "elsewhere" / fx.spec_path().name
    outside.parent.mkdir(parents=True)
    outside.write_text("# not the real spec\n")
    code, payload = plan(fx, spec_file=str(outside))
    assert code == 1
    assert payload["rule"] == "spec_outside_docs_root"


def test_a_project_that_does_not_exist_is_refused_naming_the_registered_ones(fx):
    code, payload = apply(fx, "--project-slug", "no-such-project")
    assert code == 4
    assert payload["error"] == "ambiguous"
    assert [c["slug"] for c in payload["candidates"]] == [fx.slug]


def test_a_session_that_does_not_exist_is_refused_naming_the_recorded_ones(fx):
    code, payload = apply(fx, "--session-id", "no-such-session")
    assert code == 4
    assert payload["error"] == "ambiguous"


def test_an_unconfirmed_apply_changes_nothing(fx):
    before = fx.state_path.read_text()
    code, payload = apply(fx, confirm=False)
    assert code == 2
    assert payload["error"] == "unconfirmed"
    assert fx.state_path.read_text() == before
    assert fx.spec_path().exists()


def test_an_unreadable_state_file_is_refused(fx):
    fx.state_path.write_text("{ broken")
    code, payload = plan(fx)
    assert code == 3


def test_a_state_file_pointer_that_escapes_the_record_directory_is_refused(fx):
    config = fx.registry()
    config["projects"][fx.slug]["state_file"] = "../../etc/passwd"
    fx.config_path.write_text(json.dumps(config))
    code, payload = plan(fx)
    assert code == 3
    assert "escapes" in payload["message"]


def test_malformed_arguments_are_refused_without_a_traceback(fx):
    code, payload = apply(fx, "plan-extra-positional")
    assert code == 3
    assert payload["error"] == "usage"
