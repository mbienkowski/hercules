"""The properties this tool's own header states, pinned. A gate that errs open is not a gate, so the
claim that it fails closed is the one worth a test of its own.
"""

from __future__ import annotations

import io
import json

from tests.scripts.tools.code_of_conduct.coc_gate.conftest import CONTRACT, an_envelope
from tests.scripts.tools.tool_harness import invoke, load_tool


def test_an_unclassified_failure_refuses_rather_than_passing_the_draft(monkeypatch):
    """The dangerous direction is only one: a gate that errors and returns zero waves through a
    draft nobody judged, and reads exactly like a draft that passed."""
    # `load_tool` is what puts the tools directory on the path, so it comes first:
    # importing the module directly would depend on another test having run.
    load_tool("coc_gate")
    import coc_gate

    def explode(*_args, **_kwargs):
        raise RuntimeError("something nobody anticipated")

    monkeypatch.setattr(coc_gate, "judge", explode)
    code, report = invoke(coc_gate.main, None, ["draft", "--contract", str(CONTRACT)],
                          stdin=io.StringIO(json.dumps(an_envelope())))
    assert code == 4
    assert report["error"] == "internal"
