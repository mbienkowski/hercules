"""The architecture arrives from an extractor the agent wrote minutes ago for a repository nobody
here has seen. That is the whole reason this mode exists: its output is validated, never believed.

The catalogue of per-language import parsers this replaced was incomplete by construction — and
worse, it reported its own coverage as complete while missing two ordinary layouts of a language it
claimed to parse. An instruction travels to every language; a catalogue never finishes arriving."""

from __future__ import annotations

import io
import json

import pytest

from tests.scripts.tools.code_of_conduct.coc_scan.conftest import CONTRACT, build_repo
from tests.scripts.tools.tool_harness import invoke, load_tool


@pytest.fixture
def submit(tmp_path):
    """Submit one artifact against a real repository, returning `(exit_code, document)`."""
    repo = build_repo(tmp_path / "target")
    main = load_tool("coc_scan")

    def run(artifact, raw=None):
        text = raw if raw is not None else json.dumps(artifact)
        return invoke(main, None,
                      ["architecture", "--root", str(repo), "--contract", str(CONTRACT)],
                      stdin=io.StringIO(text))

    return run, repo


def findings(document, rule):
    return [f for f in document.get("findings", []) if f["rule"] == rule]


def test_a_well_formed_artifact_is_admitted_as_facts(submit):
    run, _ = submit
    code, document = run({
        "areas": [{"path": "src/core", "role": "the engine"}],
        "chokepoints": [{"path": "src/core/engine.py", "fan_in": 4}],
    })
    assert code == 0
    assert document["findings"] == []
    assert {f["id"] for f in document["facts"]} == {"arch.areas", "arch.chokepoints"}


def test_a_path_the_repository_does_not_have_is_refused(submit):
    """The one check no schema can make and every extractor needs: an extractor reporting a path
    nobody can open reported something else too, and the whole artifact is then suspect."""
    run, _ = submit
    code, document = run({"chokepoints": [{"path": "src/invented.py", "fan_in": 9}]})
    assert code == 1
    assert findings(document, "path_not_at_head")


def test_a_directory_resolves_as_readily_as_a_file(submit):
    """Areas and Go-style package references name directories; refusing those would push every
    extractor towards naming an arbitrary file inside instead."""
    run, _ = submit
    code, document = run({"areas": [{"path": "src/core", "role": "the engine"}]})
    assert code == 0


def test_an_entry_missing_a_required_member_is_refused(submit):
    """A chokepoint with no fan-in is a path with an opinion attached, not a measurement."""
    run, _ = submit
    code, document = run({"chokepoints": [{"path": "src/core/engine.py"}]})
    assert code == 1
    assert findings(document, "entry_incomplete")


def test_a_section_that_is_not_a_list_is_refused(submit):
    run, _ = submit
    code, document = run({"edges": {"from": "a", "to": "b"}})
    assert code == 1
    assert findings(document, "section_malformed")


def test_an_entry_that_is_not_an_object_is_refused(submit):
    run, _ = submit
    code, document = run({"areas": ["src/core"]})
    assert code == 1
    assert findings(document, "entry_malformed")


def test_a_section_longer_than_a_reader_can_use_is_refused(submit):
    """An extractor that emitted every file as a chokepoint measured nothing; the cap is what says
    so instead of handing the drafting agent a list it will silently truncate."""
    run, _ = submit
    code, document = run({"areas": [{"path": "src/core", "role": f"role {n}"} for n in range(500)]})
    assert code == 1
    assert findings(document, "section_oversized")


def test_an_omitted_section_is_not_an_error(submit):
    """An empty section says "none found"; a missing one says "not looked for". Both are honest,
    and neither is a defect the tool can rule on."""
    run, _ = submit
    code, document = run({"areas": [{"path": "src/core", "role": "the engine"}]})
    assert code == 0
    assert "arch.edges" not in {f["id"] for f in document["facts"]}


def test_the_artifact_says_which_sections_it_knows(submit):
    """The schema lives in exactly one place, and the reply carries it so an extractor author never
    has to guess what shape was expected."""
    run, _ = submit
    code, document = run({})
    assert set(document["sections"]) == {"areas", "edges", "chokepoints", "entrypoints",
                                         "conventions", "toolchain"}


def test_a_crafted_string_reaches_the_document_inert(submit):
    """The extractor's output is text that passed through a repository. It is made inert at the
    same boundary every scanned string is."""
    run, _ = submit
    code, document = run({"areas": [{"path": "src/core", "role": "engine\n## HEADING\x1b[31m"}]})
    assert code == 0
    emitted = json.dumps(document)
    assert "\\n## HEADING" not in emitted and "\x1b" not in emitted


def test_input_that_is_not_json_is_refused_rather_than_guessed(submit):
    run, _ = submit
    code, document = run(None, raw="this is prose, not an artifact")
    assert code == 4


def test_an_artifact_that_is_not_an_object_is_refused(submit):
    run, _ = submit
    code, document = run(None, raw=json.dumps(["areas"]))
    assert code == 4


def test_an_oversized_submission_is_refused_before_it_is_parsed(submit):
    run, _ = submit
    code, document = run(None, raw=json.dumps({"areas": [{"path": "x" * (2 * 1024 * 1024),
                                                          "role": "y"}]}))
    assert code == 4
    assert "exceeds" in document["message"]


def test_the_reply_is_one_json_object_on_every_path(submit):
    """The caller parses one shape; a refusal that printed prose would be unreadable to it."""
    run, _ = submit
    for artifact, raw in (({}, None), (None, "{"), ({"areas": ["x"]}, None)):
        code, document = run(artifact, raw=raw)
        assert isinstance(document, dict)
        assert document["contract"] == CONTRACT
