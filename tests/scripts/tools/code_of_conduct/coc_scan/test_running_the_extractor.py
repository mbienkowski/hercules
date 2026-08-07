"""`extract` runs a program an agent wrote minutes ago, against a repository nobody here has seen.
Everything pinned below was measured failing first.

A plain `subprocess.run(timeout=)` signals only the direct child: a grandchild the extractor spawned
was found still running under init, burning CPU, seconds after the supposedly bounded call returned.
And a cap that applies after capture is not a cap — a child printing 300MB filled the parent's memory
in 0.22s, nowhere near any deadline."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time

import pytest

from tests.scripts.tools.code_of_conduct.coc_scan.conftest import CONTRACT, build_repo
from tests.scripts.tools.tool_harness import invoke, load_tool

SLEEPER = "import time; time.sleep(600)"


@pytest.fixture
def extract(tmp_path):
    """Run one extractor against a real repository under a deliberately short deadline."""
    repo = build_repo(tmp_path / "target")
    main = load_tool("coc_scan")
    module = sys.modules["coc_scan"]
    module.EXTRACTOR_TIMEOUT_SECONDS = 3

    def run(source, argv=None):
        script = tmp_path / "extractor.py"
        script.write_text(source)
        return invoke(main, None, argv or ["extract", "--root", str(repo),
                                           "--extractor", str(script),
                                           "--contract", str(CONTRACT)])

    return run, repo, module


def emits(payload: str) -> str:
    return f"import json, sys\nprint(json.dumps({payload}))\n"


def test_a_well_behaved_extractor_has_its_facts_admitted(extract):
    run, _, _ = extract
    code, document = run(emits("{'areas': [{'path': 'src/core', 'role': 'the engine'}],"
                               " 'files_processed': 4, 'files_at_head': 4}"))
    assert code == 0
    assert document["findings"] == []
    assert "arch.areas" in {f["id"] for f in document["facts"]}


def test_a_hanging_extractor_is_stopped_at_the_deadline(extract):
    run, _, _ = extract
    started = time.time()
    code, document = run(f"{SLEEPER}\n")
    assert code == 1
    assert document["rule"] == "extractor_timed_out"
    assert time.time() - started < 30  # the deadline decided this, not the sleep


def test_a_grandchild_does_not_outlive_the_kill(extract):
    """The leak this suite exists for. Killing only the direct child leaves whatever it started
    running under init — a bounded call that returns while the work it spawned keeps burning CPU."""
    run, _, _ = extract
    marker = "hercules-orphan-probe"
    code, _ = run("import subprocess, sys, time\n"
                  f"subprocess.Popen([sys.executable, '-c', {SLEEPER!r}, {marker!r}])\n"
                  f"{SLEEPER}\n")
    assert code == 1
    time.sleep(1)
    survivors = subprocess.run(["pgrep", "-f", marker], capture_output=True, text=True).stdout.split()
    for pid in survivors:  # never leave the machine dirtier than we found it
        subprocess.run(["kill", "-9", pid], capture_output=True)
    assert survivors == []


def test_a_flooding_extractor_is_cut_off_rather_than_buffered(extract):
    """The writer never stops, which is what makes this test mean anything. A reader that collects
    first and measures after would follow it forever and die on the DEADLINE — so asserting the
    flood rule, and only the flood rule, is what proves the cap bit during capture rather than
    after it. A finite flood cannot tell those two apart: it is refused either way, having already
    filled the parent's memory in the second case."""
    run, _, _ = extract
    code, document = run("import sys\n"
                         "chunk = 'x' * 65536\n"
                         "while True:\n    sys.stdout.write(chunk)\n")
    assert code == 1
    assert document["rule"] == "extractor_flooded"


def test_the_interpreter_is_this_one_not_whatever_the_path_offers(extract, tmp_path, monkeypatch):
    """A repository's own `.venv/bin` sitting in an ambient dev shell must never decide what runs."""
    run, _, _ = extract
    decoy = tmp_path / "decoy"
    decoy.mkdir()
    (decoy / "python3").write_text("#!/bin/sh\necho '{\"areas\": \"hijacked\"}'\n")
    (decoy / "python3").chmod(0o755)
    monkeypatch.setenv("PATH", f"{decoy}:{os.environ['PATH']}")
    code, document = run(emits("{'files_processed': 1, 'files_at_head': 1}"))
    assert code == 0
    assert document["findings"] == []


def test_the_child_inherits_no_open_file(extract, tmp_path):
    """The extractor is handed a repository path, never a descriptor the parent happened to hold."""
    run, _, _ = extract
    secret = tmp_path / "secret.txt"
    secret.write_text("SHOULD-NOT-BE-READABLE")
    with open(secret) as handle:
        source = (f"import json, os\n"
                  f"try:\n    os.read({handle.fileno()}, 10); leaked = True\n"
                  f"except OSError:\n    leaked = False\n"
                  f"print(json.dumps({{'files_processed': 1, 'files_at_head': 1,"
                  f" 'conventions': [{{'concern': 'leak', 'sides': str(leaked)}}]}}))\n")
        code, document = run(source)
    assert code == 0
    reported = next(f for f in document["facts"] if f["id"] == "arch.conventions")
    assert reported["value"][0]["sides"] == "False"


def test_an_extractor_that_prints_nothing_is_refused_not_read_as_empty(extract):
    run, _, _ = extract
    code, document = run("pass\n")
    assert code == 1
    assert document["rule"] == "extractor_said_nothing"


def test_why_it_printed_nothing_is_relayed_rather_than_swallowed(extract):
    """An extractor that died on its first line refused identically to one that ran fine and said
    nothing, and the agent told to fix it had no way to tell which. Its error output carries that."""
    run, _, _ = extract
    code, document = run("raise SystemExit('the reason it died')\n")
    assert code == 1
    assert "the reason it died" in document["message"]


def test_a_relative_root_still_reaches_the_repository(extract, tmp_path, monkeypatch):
    """The child deliberately runs somewhere else, so a relative root handed through unchanged made
    every `git -C` inside the extractor ask about the temporary directory instead of the repository
    — measured on the first real end-to-end run, which died with nothing to show for it."""
    run, repo, _ = extract
    monkeypatch.chdir(repo.parent)
    script = tmp_path / "rel.py"
    script.write_text("import json, subprocess, sys\n"
                      "n = subprocess.run(['git', '-C', sys.argv[1], 'ls-files'],\n"
                      "                   capture_output=True, text=True).stdout.split()\n"
                      "print(json.dumps({'files_processed': len(n), 'files_at_head': len(n)}))\n")
    main = load_tool("coc_scan")
    code, document = invoke(main, None, ["extract", "--root", repo.name,
                                         "--extractor", str(script), "--contract", str(CONTRACT)])
    assert code == 0
    assert document["unknowns"] == []


def test_extract_without_a_script_says_so(extract):
    run, repo, _ = extract
    code, document = run("pass\n", argv=["extract", "--root", str(repo),
                                         "--contract", str(CONTRACT)])
    assert code == 4
    assert "--extractor" in document["message"]


# ── The completeness counters ─────────────────────────────────────────────────────────────────

def test_a_short_read_is_recorded_rather_than_passing_as_complete(extract):
    """An extractor that got through a fifth of the files reported almost nothing, and without the
    pair its artifact is shaped exactly like one that read everything."""
    run, _, _ = extract
    code, document = run(emits("{'files_processed': 1, 'files_at_head': 4}"))
    assert code == 0
    assert "arch.files_truncated" in document["unknowns"]


def test_a_complete_read_records_no_truncation(extract):
    run, _, _ = extract
    code, document = run(emits("{'files_processed': 4, 'files_at_head': 4}"))
    assert code == 0
    assert document["unknowns"] == []


def test_missing_counters_are_an_unknown_and_never_a_refusal(extract):
    """Advisory, because a hard gate here would refuse artifacts that are otherwise entirely sound."""
    run, _, _ = extract
    code, document = run(emits("{'areas': [{'path': 'src/core', 'role': 'the engine'}]}"))
    assert code == 0
    assert "arch.coverage_unstated" in document["unknowns"]


def test_reading_more_files_than_were_found_is_refused(extract):
    run, _, _ = extract
    code, document = run(emits("{'files_processed': 99, 'files_at_head': 4}"))
    assert code == 1
    assert [f for f in document["findings"] if f["rule"] == "counters_impossible"]


def test_finding_more_files_than_the_repository_has_is_refused(extract):
    run, _, _ = extract
    code, document = run(emits("{'files_processed': 5000, 'files_at_head': 5000}"))
    assert code == 1
    assert [f for f in document["findings"] if f["rule"] == "counters_impossible"]


def test_an_honestly_lower_count_is_not_refused(extract):
    """The blueprint declines to read symlinks, so an honest `files_at_head` is routinely BELOW the
    tracked total. An equality gate would refuse correct artifacts from ordinary repositories — a
    comparison that refuses honest work is worse than no comparison at all."""
    run, _, _ = extract
    code, document = run(emits("{'files_processed': 2, 'files_at_head': 2}"))
    assert code == 0
    assert not [f for f in document["findings"] if f["rule"] == "counters_impossible"]


def test_the_repository_root_is_a_place_a_file_can_belong_to(extract):
    """A flat repository keeps its entrypoint at the root, so `.` is the area those files are in.
    Refusing that spelling would push every extractor into inventing a directory for them."""
    run, _, _ = extract
    code, document = run(emits("{'files_processed': 4, 'files_at_head': 4,"
                               " 'edges': [{'from': '.', 'to': 'src/core'}]}"))
    assert code == 0
    assert "arch.edges" in {f["id"] for f in document["facts"]}
