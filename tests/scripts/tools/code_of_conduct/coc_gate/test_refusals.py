"""Every way the gate declines before it judges a single rule. The tool runs while the draft exists
only in an agent's context, so a refusal must be legible enough to act on and must never be mistaken
for a pass."""

from __future__ import annotations

import io
import json

from tests.scripts.tools.code_of_conduct.coc_gate.conftest import CONTRACT, an_envelope
from tests.scripts.tools.tool_harness import invoke, load_tool


def test_a_contract_the_tool_does_not_speak_is_refused(gate):
    """Prose and tool ship per ecosystem and update on their own cadences; a mismatch says so
    instead of validating against a grammar the caller did not mean."""
    code, report = gate(an_envelope(), argv=["draft", "--contract", "99"])
    assert code == 2
    assert report["error"] == "contract"


def test_input_that_is_not_json_is_refused_rather_than_guessed(gate):
    code, report = gate(None, raw="this is prose, not an envelope")
    assert code == 4
    assert report["error"] == "internal"


def test_an_envelope_that_is_not_an_object_is_refused(gate):
    code, report = gate(None, raw=json.dumps(["a", "list"]))
    assert code == 4


def test_an_envelope_whose_rules_are_not_a_list_is_refused(gate):
    code, report = gate(an_envelope(rules="all of them"))
    assert code == 4


def test_a_rule_that_is_not_an_object_is_refused(gate):
    code, report = gate(an_envelope(rules=["just a string"]))
    assert code == 4


def test_an_oversized_submission_is_refused_before_it_is_parsed(gate):
    """A gate that reads whatever it is handed can be hung by the repository it is auditing. The
    submission is otherwise valid and would clear the gate at any smaller size, so only the cap can
    be what refuses it."""
    from tests.scripts.tools.code_of_conduct.coc_gate.conftest import a_rule

    bloated = an_envelope(rules=[a_rule(text="x" * (2 * 1024 * 1024))])
    code, report = gate(bloated)
    assert code == 4
    assert report["error"] == "internal"
    # Named explicitly: the bounded read also stops this, so without pinning the message a test
    # cannot tell the size refusal from a truncated-JSON parse error.
    assert "exceeds" in report["message"]


def test_an_unknown_mode_is_refused_as_usage(gate):
    code, report = gate(an_envelope(), argv=["polish", "--contract", str(CONTRACT)])
    assert code == 4
    assert report["error"] == "usage"


def test_the_reply_is_one_json_object_on_every_path(gate):
    """The caller parses one shape; a refusal that printed prose would be unreadable to it."""
    for envelope, raw in ((an_envelope(), None), (None, "{"), (an_envelope(rules=[]), None)):
        code, report = gate(envelope, raw=raw)
        assert isinstance(report, dict)
        assert report["contract"] == CONTRACT


def test_the_gate_never_reaches_the_filesystem_for_its_verdict(tmp_path):
    """This mode is a pure function of its envelope: no path is opened, so a hostile repository has
    no surface here at all. Verification against a repository arrives with the scan inventory."""
    main = load_tool("coc_gate")
    envelope = an_envelope()
    buffer = io.StringIO(json.dumps(envelope))
    code, report = invoke(main, None, ["draft", "--contract", str(CONTRACT)], stdin=buffer)
    assert code == 0
    assert list(tmp_path.iterdir()) == []
