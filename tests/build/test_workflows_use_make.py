"""Invariant: GitHub Actions workflows contain NO inline logic — every ``run:`` step is a ``make``
target.

CI behaviour lives in the ``Makefile`` + ``scripts/ci/`` (one source of truth, testable and runnable
locally), never in YAML heredocs or multi-line shell scattered across workflow files. A step that
needs new logic adds a ``make`` target + a script under ``scripts/ci/`` — not an inline block.
"""
from __future__ import annotations

from pathlib import Path

import yaml

WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"


def _run_steps():
    """Yield ``(workflow, job, step_index, run_script)`` for every step that has a ``run:``."""
    for wf in sorted(WORKFLOWS.glob("*.yml")):
        doc = yaml.safe_load(wf.read_text(encoding="utf-8"))
        for job_name, job in (doc.get("jobs") or {}).items():
            for i, step in enumerate(job.get("steps") or []):
                if isinstance(step, dict) and "run" in step:
                    yield wf.name, job_name, i, step["run"]


def test_workflows_exist_and_have_run_steps():
    """Guard the guard: if the workflow dir moved or no run: steps parse, the make-only check below
    would vacuously pass. Anchor it to a non-empty, known surface."""
    steps = list(_run_steps())
    assert steps, "no workflow run: steps found — did the workflows move?"
    assert {wf for wf, *_ in steps} >= {"ci.yml", "release.yml", "smoke-nightly.yml"}


def test_every_workflow_run_step_calls_only_make():
    """Every ``run:`` step must be a single ``make <target>`` invocation (comments/blank lines
    allowed). Inline Python/bash logic belongs in ``scripts/ci/`` behind a make target."""
    offenders = []
    for wf, job, i, run in _run_steps():
        logic = [ln.strip() for ln in str(run).splitlines()
                 if ln.strip() and not ln.strip().startswith("#")]
        if not logic or not all(ln == "make" or ln.startswith("make ") for ln in logic):
            offenders.append(f"{wf} · job '{job}' · step {i}: {logic}")
    assert not offenders, (
        "GitHub Actions run: steps must call `make <target>` only — move inline logic into a "
        "Makefile target + a scripts/ci/ helper (CODE_OF_CONDUCT.md § Invariants):\n  "
        + "\n  ".join(offenders)
    )
