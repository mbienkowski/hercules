"""What a lint run needs: a repository whose files a citation can resolve against, and the two ways
a document arrives — already on disk, or as a draft that has not been written yet."""

from __future__ import annotations

import io
import json
import subprocess

import pytest

from tests.scripts.tools.tool_harness import invoke, load_tool

CONTRACT = 2


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "src" / "engine.py").write_text("x\n")
    (root / "Makefile").write_text("build:\n\techo hi\ntest:\n\techo hi\n")
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(root), "-c", "user.email=t@t.t", "-c", "user.name=t",
                    "commit", "-q", "-m", "init", "--no-gpg-sign"], check=True, capture_output=True)
    return root


@pytest.fixture
def lint():
    """A draft checked for shape alone, submitted on stdin before it exists on disk."""
    main = load_tool("coc_lint")

    def run(markdown, argv=None, paths=None):
        body = {"contract": CONTRACT, "markdown": markdown}
        if paths is not None:
            body["paths"] = paths
        return invoke(main, None, argv or ["--contract", str(CONTRACT)],
                      stdin=io.StringIO(json.dumps(body)))

    return run


@pytest.fixture
def review(repo, tmp_path):
    """A document on disk checked for shape AND citations, against a real repository."""
    main = load_tool("coc_lint")

    def run(markdown, name="code-of-conduct.md"):
        document = tmp_path / name
        document.write_text(markdown)
        return invoke(main, None, ["--contract", str(CONTRACT), "--file", str(document),
                                   "--root", str(repo)], stdin=io.StringIO(""))

    return run, repo


# The agreed document shape: orientation first, each section a summary then tagged rules, and the
# reasons in one Why section at the end — rules first because a reader wants the requirement, then
# the argument.
VALID_SHAPE = """A rule's prefix says what it is: MUST is gated, SHOULD is convention, AVOID names
a tempting path, NEVER_DO is a hard stop. The reasons sit at the end.

## Development

Standards drawn from the code are the ones people already follow.

- MUST: Never commit a credential — the scanner runs in CI.

## Why this is the way it is

- A credential that lands in history stays there for every future clone.
"""


def document(body: str) -> str:
    """`body` inside a document that is otherwise well-formed, so a citation test fails for its
    citation and never for its shape — the tool reports both, so the fixture has to isolate one."""
    return VALID_SHAPE + body


def findings(report, rule):
    return [f for f in report.get("findings", []) if f.get("rule") == rule]


def entries(report, state):
    return [e for e in report["entries"] if e["state"] == state]
