"""Each shipped edition's memory hook, run as its host runs it: the argv is read from that edition's dist
hooks.json, the event is JSON on stdin, and HOME is a throwaway directory. Wiring and output shape are
tested together, so a wiring change that breaks parsing fails here."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
DIST = REPO / "dist"
# A command's argv is the words after `memory_hook.py`, before any shell or PowerShell tail.
ARGV = re.compile(r'memory_hook\.py"?((?:\s+[A-Za-z]+)*)')


def wired_argvs(edition: str) -> list[list[str]]:
    config = json.loads((DIST / edition / "hooks/hooks.json").read_text(encoding="utf-8"))
    found = []
    for entries in config["hooks"].values():
        for entry in entries:
            for handler in entry.get("hooks", [entry]):
                command = handler.get("bash") or handler.get("command") or ""
                match = ARGV.search(command)
                if match:
                    found.append(match.group(1).split())
    return found


CASES = sorted({(edition, tuple(argv)) for edition in ("claude-code", "codex", "gemini-cli", "cursor",
                                                       "copilot-cli", "grok-build")
                for argv in wired_argvs(edition)} | {("opencode", ("text",))})


def run_hook(edition: str, argv, home: Path, project: Path, payload: dict) -> str:
    env = {"HOME": str(home), "PATH": "/usr/bin:/bin:/usr/local/bin"}
    script = DIST / edition / "hooks/memory_hook.py"
    done = subprocess.run([sys.executable, str(script), *argv], input=json.dumps({"cwd": str(project), **payload}),
                          capture_output=True, text=True, env=env, timeout=30)
    assert done.returncode == 0, done.stderr
    assert "Traceback" not in done.stderr
    return done.stdout


@pytest.mark.parametrize("edition,argv", CASES, ids=lambda v: " ".join(v) if isinstance(v, tuple) else v)
def test_the_wired_command_emits_the_dialect_its_host_parses(edition, argv, tmp_path):
    project = tmp_path / "code"
    project.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    stdout = run_hook(edition, list(argv), home, project,
                      {"sessionId": "e2e", "timestamp": 1, "source": "new", "prompt": "hi"})
    dialect = argv[0] if argv else "common"
    if dialect == "text":
        assert stdout.strip() and not stdout.lstrip().startswith("{")
    elif dialect == "cursor":
        assert set(json.loads(stdout)) <= {"additional_context"}  # {} is a compaction or an already-delivered event
    elif dialect == "copilot":
        assert set(json.loads(stdout)) <= {"additionalContext"}
    else:
        assert set(json.loads(stdout)) <= {"hookSpecificOutput"}
