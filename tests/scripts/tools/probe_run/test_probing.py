"""Proves a probe records what happened rather than what was hoped, and that the two controls that
make a verdict worth anything actually bite.

The failure this file exists to prevent is a feasibility check that always passes: a command that
runs, exits zero, asserts nothing, and buys false confidence in a plan nobody tested. Two rules stop
that, and both are tested here — an expectation must be stated BEFORE the run, and a probe may not
fake the very thing it exists to check.

The tool deliberately CANNOT prove a plan will work. Nothing below asserts that it does.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
from pathlib import Path

import pytest

from tests.scripts.tools.tool_harness import load_tool

main = load_tool("probe_run")

RULES = json.loads(
    (Path(__file__).resolve().parents[4] / "src" / "scripts" / "tools" / "doc_rules.json")
    .read_text(encoding="utf-8"))

EXIT_OK, EXIT_REFUSED, EXIT_NOT_FOUND = 0, 1, 4
PASS, FAIL, UNPROVEN = "PASS", "FAIL", "UNPROVEN"


def run(argv):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = main(list(argv))
    return code, json.loads(buffer.getvalue())


def probe(*, expect="the command succeeds", command=("true",), tier="medium", faked="", into=None,
          label="assumption"):
    argv = ["run", "--label", label, "--tier", tier]
    if expect:
        argv += ["--expect", expect]
    if faked:
        argv += ["--faked", faked]
    if into:
        argv += ["--into", str(into)]
    return run(argv + ["--"] + list(command))


# ── the two anti-theatre controls ───────────────────────────────────────────────────────────────


def test_a_probe_with_no_stated_expectation_is_never_a_pass():
    """The control that stops a green wall of nothing: a command asserting nothing can always be
    made to exit zero, so exiting zero is not evidence unless something was expected of it."""
    code, payload = probe(expect="", command=("true",))
    assert payload["verdict"] == UNPROVEN
    assert "expectation" in payload["why"]
    assert code == EXIT_REFUSED


def test_faking_the_thing_under_test_is_a_failure_not_a_pass():
    """A probe that stubs the dependency it exists to check is green precisely where production
    breaks. That is worse than no probe, so it fails rather than passes."""
    code, payload = probe(command=("true",), faked="database")
    assert payload["verdict"] == FAIL
    assert "meant to check" in payload["why"]
    assert code == EXIT_REFUSED


def test_standing_in_for_an_unwritten_internal_is_allowed():
    """The legitimate case, and the one that makes greenfield probing possible at all: the internals
    do not exist yet, so the probe fakes them and checks that the seams line up."""
    _, payload = probe(command=("true",), faked="BookingCalendar,SlotClaim")
    assert payload["verdict"] == PASS
    assert payload["faked"] == ["BookingCalendar", "SlotClaim"]


# ── verdicts ────────────────────────────────────────────────────────────────────────────────────


def test_a_clean_run_against_an_expectation_passes():
    code, payload = probe(command=("true",))
    assert (code, payload["verdict"]) == (EXIT_OK, PASS)
    assert payload["record"]["exit_code"] == 0


def test_a_contradicted_assumption_fails():
    """The verdict the whole gate exists to produce: the plan cannot work, found before anyone read
    the plan."""
    code, payload = probe(command=("false",))
    assert payload["verdict"] == FAIL
    assert "exited 1" in payload["why"]
    assert code == EXIT_REFUSED


def test_a_command_that_cannot_start_is_unproven_not_failed():
    """A missing tool says nothing about the plan, only about this machine."""
    _, payload = probe(command=("definitely-not-a-real-binary-9f2",))
    assert payload["verdict"] == UNPROVEN


def test_a_slow_probe_is_unproven_rather_than_failed():
    """Running out of time is a failure to check cheaply, not evidence the assumption is false —
    and the distinction is what stops a timeout being read as a broken plan."""
    _, payload = probe(command=("sleep", "5"), tier="low")
    argv = ["run", "--label", "slow", "--tier", "low", "--expect", "it finishes",
            "--timeout", "1", "--", "sleep", "5"]
    _, payload = run(argv)
    assert payload["verdict"] == UNPROVEN
    assert payload["record"]["timed_out"] is True


# ── the record ──────────────────────────────────────────────────────────────────────────────────


def test_the_record_carries_evidence_the_agent_could_not_have_invented():
    """'The probe ran' has to be checkable rather than claimed, so the record is derived from the
    execution: the argv, the exit code, the timing, and a hash of what came back."""
    _, payload = probe(command=("echo", "hello"))
    record = payload["record"]
    assert record["argv"] == ["echo", "hello"]
    assert record["exit_code"] == 0
    assert record["duration_ms"] >= 0
    assert len(record["stdout_sha256"]) == 64
    assert "hello" in record["output_head"]


def test_the_verdict_is_derived_not_declared():
    """There is no flag that sets the verdict. It comes from the exit code, every time."""
    parser_flags = set()
    for line in Path(main.__module__ and
                     (Path(__file__).resolve().parents[4] / "src" / "scripts" / "tools"
                      / "probe_run.py")).read_text(encoding="utf-8").splitlines():
        if "add_argument" in line and "--" in line:
            parser_flags.add(line.split('"')[1] if '"' in line else "")
    assert "--verdict" not in parser_flags
    assert "--pass" not in parser_flags


def test_a_probe_can_be_written_where_the_caller_asks(tmp_path):
    into = tmp_path / "probe-dependency.json"
    probe(command=("true",), into=into)
    saved = json.loads(into.read_text())
    assert saved["verdict"] == PASS
    assert saved["record"]["argv"] == ["true"]


def test_the_probes_directory_does_not_need_to_exist_first(tmp_path):
    """Design's own prose points a probe straight at `docs/{session}/probes/probe-{label}.json`
    with nothing that creates that directory first. The first probe of a session must not fail on
    that account — a missing directory is not a reason to call the plan unfalsifiable."""
    into = tmp_path / "docs" / "2026-08-04-x" / "probes" / "probe-dependency.json"
    assert not into.parent.exists()
    code, payload = probe(command=("true",), into=into)
    assert code == EXIT_OK, payload
    assert payload["verdict"] == PASS
    assert json.loads(into.read_text())["verdict"] == PASS


def test_a_write_failure_is_refused_with_its_own_message_not_mislabeled_as_unreadable(tmp_path):
    """A failed WRITE reported as 'cannot read' sends whoever debugs it looking in the wrong place.
    Point --into at a path a file already occupies as a directory component, so the write is
    guaranteed to fail regardless of platform, and check the message names the write."""
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("occupied", encoding="utf-8")
    into = blocker / "probe-dependency.json"
    code, payload = probe(command=("true",), into=into)
    assert code == EXIT_REFUSED
    assert payload["error"] == "refused"
    assert "write" in payload["message"].lower()
    assert "cannot read" not in payload["message"].lower()


# ── the budget, and UNPROVEN as an escape hatch ─────────────────────────────────────────────────


def test_trivial_runs_no_probes_at_all():
    """Depth scales: a typo does not earn a feasibility pass."""
    code, payload = probe(tier="trivial")
    assert code == EXIT_REFUSED
    assert "runs no probes" in payload["message"]


def _record(tmp_path, name, verdict):
    (tmp_path / ("probe-%s.json" % name)).write_text(json.dumps(
        {"label": name, "verdict": verdict, "record": {"argv": ["true"]}}))


def test_verify_wants_the_tier_s_probes_to_have_run(tmp_path):
    _record(tmp_path, "one", PASS)
    code, payload = run(["verify", "--tier", "high", "--into", str(tmp_path)])
    assert payload["decision"] == "not-ready"
    assert any("asks for" in reason for reason in payload["reasons"])
    assert code == EXIT_REFUSED


def test_verify_refuses_when_a_probe_contradicted_the_plan(tmp_path):
    _record(tmp_path, "one", PASS)
    _record(tmp_path, "two", FAIL)
    _, payload = run(["verify", "--tier", "medium", "--into", str(tmp_path)])
    assert payload["decision"] == "not-ready"
    assert any("contradicted" in reason for reason in payload["reasons"])


def test_unproven_cannot_become_the_universal_escape_hatch(tmp_path):
    """UNPROVEN is the frictionless verdict, so without a ceiling every probe becomes one and the
    gate quietly stops meaning anything."""
    for name in ("a", "b", "c"):
        _record(tmp_path, name, UNPROVEN)
    _record(tmp_path, "d", PASS)
    _, payload = run(["verify", "--tier", "medium", "--into", str(tmp_path)])
    assert payload["decision"] == "not-ready"
    assert any("UNPROVEN" in reason for reason in payload["reasons"])


def test_a_met_budget_with_no_contradiction_proceeds(tmp_path):
    _record(tmp_path, "one", PASS)
    _record(tmp_path, "two", PASS)
    code, payload = run(["verify", "--tier", "medium", "--into", str(tmp_path)])
    assert (code, payload["decision"]) == (EXIT_OK, "proceed")


def test_verify_says_so_when_there_is_nowhere_to_look(tmp_path):
    code, payload = run(["verify", "--tier", "medium", "--into", str(tmp_path / "absent")])
    assert code == EXIT_NOT_FOUND


def test_the_budget_is_published_rather_than_restated():
    """The numbers live in one file so a command cannot quietly disagree with the tool."""
    code, payload = run(["budget"])
    assert code == EXIT_OK
    assert set(payload["probes"]["tiers"]) == set(RULES["tiers"])
    assert payload["probes"]["verdicts"][UNPROVEN]


def test_the_tool_never_claims_a_probe_proves_a_plan_works():
    """The promise that was renegotiated, pinned in the shipped text so it cannot quietly return."""
    source = (Path(__file__).resolve().parents[4] / "src" / "scripts" / "tools" / "probe_run.py")
    text = source.read_text(encoding="utf-8").lower()
    assert "falsification" in text
    assert "never" in text and "will succeed" in text
