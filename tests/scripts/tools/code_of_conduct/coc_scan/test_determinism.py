"""The promise the whole redesign rests on: at one commit, this scan says the same thing twice. Two
runs are compared as BYTES, because for a tool whose value is reproducibility the exact output is the
business fact — a looser assertion would pass while the property quietly rotted."""

from __future__ import annotations

import io
import json

from tests.scripts.tools.code_of_conduct.coc_scan.conftest import CONTRACT
from tests.scripts.tools.tool_harness import load_tool


def _emitted(root) -> str:
    """The scan's stdout verbatim, not the parsed reply — parsing would hide ordering changes."""
    import contextlib
    main = load_tool("coc_scan")
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        main(["all", "--root", str(root), "--contract", str(CONTRACT)], home=None)
    return buffer.getvalue()


def test_two_runs_at_one_commit_emit_the_same_bytes(repo):
    assert _emitted(repo) == _emitted(repo)


def test_the_document_carries_no_wall_clock_reading(repo):
    """A timestamp or an elapsed-time field would make every run differ and the promise unmeasurable,
    however carefully everything else were ordered."""
    body = json.loads(_emitted(repo))
    flat = json.dumps(body)
    assert "elapsed" not in flat
    assert "generated_at" not in flat
    assert "timestamp" not in flat


def test_the_commit_it_read_is_named_so_two_runs_can_be_compared_honestly(repo):
    """Determinism is per commit; without saying which, identical output would prove nothing."""
    assert len(json.loads(_emitted(repo))["head"]) == 40


def test_collections_are_ordered_by_content_rather_than_by_discovery(repo):
    body = json.loads(_emitted(repo))
    ids = [f["id"] for f in body["facts"]]
    assert ids == sorted(ids)


def test_object_keys_are_emitted_in_a_fixed_order(repo):
    """Insertion order happens to be stable in this runtime, so two runs would match anyway — which
    is precisely why ordering has to be asserted rather than observed."""
    top = json.loads(_emitted(repo), object_pairs_hook=lambda pairs: [k for k, _ in pairs])
    assert top == sorted(top)
