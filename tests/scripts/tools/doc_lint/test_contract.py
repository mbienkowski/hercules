"""Pins the linter's output contract: one JSON object on stdout on every path, exit codes a caller
can branch on, and a template that grows with the tier.

A command invokes this tool and relays its reply, so the contract IS the interface. A refusal that
printed prose, or an exit code that did not distinguish "your document is wrong" from "I could not
read it", would make the calling command guess — and a guessing gate is not a gate.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from tests.scripts.tools.doc_lint.conftest import (
    CLEAN_REQUIREMENTS, CLEAN_SPEC, REQUIREMENTS_NAME, SPEC_NAME, fired, lint, run,
)

EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_INTERNAL = 3
EXIT_NOT_FOUND = 4


def test_a_clean_document_exits_zero_and_says_so(tmp_path):
    code, payload = lint(tmp_path, CLEAN_REQUIREMENTS, REQUIREMENTS_NAME)
    assert code == EXIT_OK
    assert payload["clean"] is True
    assert payload["counts"]["error"] == 0


def test_a_violating_document_exits_refused(tmp_path):
    """The caller branches on the code, never on the prose."""
    broken = CLEAN_REQUIREMENTS.replace("- **Change wanted**", "- **Change wanted** TBD", 1)
    code, payload = lint(tmp_path, broken, REQUIREMENTS_NAME)
    assert code == EXIT_REFUSED
    assert payload["clean"] is False
    assert "DOC103" in fired(payload)


def test_a_warning_alone_does_not_block(tmp_path):
    """Style rules are advisory by design; only --strict promotes them."""
    warned = CLEAN_REQUIREMENTS.replace(
        "## Constraints\n", "## Constraints\n- The bookingSlot stays bound to 1 stylist.\n", 1)
    code, payload = lint(tmp_path, warned, REQUIREMENTS_NAME)
    assert "DOC209" in fired(payload)
    assert payload["counts"]["error"] == 0
    assert code == EXIT_OK
    assert payload["clean"] is True

    strict_code, strict_payload = lint(tmp_path, warned, REQUIREMENTS_NAME, strict=True)
    assert strict_code == EXIT_REFUSED
    assert strict_payload["clean"] is False


def test_a_missing_document_is_not_found_rather_than_refused(tmp_path):
    """A caller distinguishes 'the path is wrong' from 'the document is wrong'."""
    code, payload = run(["check", "--path", str(tmp_path / "absent.md"),
                         "--kind", "spec"])
    assert code == EXIT_NOT_FOUND
    assert payload["error"] == "refused"
    assert "absent.md" in payload["message"]


def test_an_unresolvable_kind_names_the_flag_that_fixes_it(tmp_path):
    """§ Failure moments: a stop names the next action, never just the problem."""
    path = tmp_path / "some-notes.md"
    path.write_text(CLEAN_REQUIREMENTS, encoding="utf-8")
    code, payload = run(["check", "--path", str(path)])
    assert code == EXIT_REFUSED
    assert "--kind" in payload["message"]


@pytest.mark.parametrize("bad", ["enormous", "", "HIGH"])
def test_an_unknown_tier_is_refused_with_the_options(tmp_path, bad):
    path = tmp_path / REQUIREMENTS_NAME
    path.write_text(CLEAN_REQUIREMENTS, encoding="utf-8")
    argv = ["check", "--path", str(path), "--kind", "business-requirements"]
    if bad:
        argv += ["--tier", bad]
        code, payload = run(argv)
        assert code == EXIT_REFUSED
        assert "medium" in payload["message"]
    else:
        # An omitted tier is not an error: it defaults, so a caller with no session still gets a read.
        code, payload = run(argv)
        assert payload["tier"] == "medium"


def test_the_reply_carries_the_hash_the_caller_persists(tmp_path):
    """The phase-boundary backstop compares this against the file later, so it must be the hash of
    exactly what was checked."""
    _, payload = lint(tmp_path, CLEAN_SPEC, SPEC_NAME)
    assert payload["sha256"] == hashlib.sha256(CLEAN_SPEC.encode("utf-8")).hexdigest()
    assert payload["rules_version"] >= 1


def test_every_finding_names_a_fix(tmp_path):
    """A finding that states only the defect leaves the author guessing at the remedy."""
    broken = CLEAN_REQUIREMENTS.replace("### In scope", "#### In scope", 1)
    _, payload = lint(tmp_path, broken, REQUIREMENTS_NAME)
    assert payload["findings"]
    for finding in payload["findings"]:
        assert finding["fix"].strip(), finding
        assert finding["severity"] in ("error", "warn")
        assert finding["rule"].startswith("DOC")


def test_errors_are_reported_before_warnings(tmp_path):
    """The first line a person reads should be the one that blocks them."""
    broken = CLEAN_REQUIREMENTS.replace(
        "## Constraints\n",
        "## Constraints\n- The bookingSlot stays bound to 1 stylist.\n- Slots TBD.\n", 1)
    _, payload = lint(tmp_path, broken, REQUIREMENTS_NAME)
    severities = [finding["severity"] for finding in payload["findings"]]
    assert severities == sorted(severities, key=lambda value: value != "error")


@pytest.mark.parametrize("kind", ["business-requirements", "spec"])
def test_the_template_is_emitted_per_kind(kind):
    code, payload = run(["template", "--kind", kind, "--tier", "medium"])
    assert code == EXIT_OK
    assert payload["template"].startswith("## ")
    assert payload["kind"] == kind


def test_the_template_deepens_with_the_tier():
    """Depth scaling is the whole point of the tier: a higher tier asks for more of the document."""
    low = run(["template", "--kind", "spec", "--tier", "low"])[1]["template"]
    high = run(["template", "--kind", "spec", "--tier", "high"])[1]["template"]
    low_sections = {line for line in low.splitlines() if line.startswith("## ")}
    high_sections = {line for line in high.splitlines() if line.startswith("## ")}
    assert low_sections < high_sections, (sorted(low_sections), sorted(high_sections))


def test_a_generated_template_names_only_sections_the_rules_define():
    """The template and the checker read one catalogue, so a document written from the template
    cannot fail the 'unknown section' rule."""
    catalogue = run(["rules"])[1]
    assert catalogue["kinds"] == ["business-requirements", "spec"]
    for kind in catalogue["kinds"]:
        template = run(["template", "--kind", kind, "--tier", "critical"])[1]["template"]
        assert template.count("## ") >= 5


def test_an_unknown_kind_is_refused_by_template():
    code, payload = run(["template", "--kind", "slide-deck"])
    assert code == EXIT_REFUSED
    assert "business-requirements" in payload["message"]


def test_the_rules_mode_publishes_the_whole_catalogue():
    """The authoring skill summarises this list; a summary of a list nobody can read drifts."""
    code, payload = run(["rules"])
    assert code == EXIT_OK
    ids = [rule["id"] for rule in payload["rules"]]
    assert len(ids) == len(set(ids)), "duplicate rule identifiers"
    assert all(rule["fix"] for rule in payload["rules"])


def test_every_mode_prints_exactly_one_json_object(tmp_path):
    """The output contract in one assertion: parseable, on every path, including refusals."""
    path = tmp_path / REQUIREMENTS_NAME
    path.write_text(CLEAN_REQUIREMENTS, encoding="utf-8")
    for argv in (["rules"],
                 ["template", "--kind", "spec"],
                 ["template", "--kind", "nope"],
                 ["check", "--path", str(path), "--kind", "business-requirements"],
                 ["check", "--path", str(tmp_path / "gone.md"), "--kind", "spec"],
                 ["check"]):
        _, payload = run(argv)
        assert isinstance(payload, dict)
        assert "mode" in payload
        assert json.dumps(payload)
