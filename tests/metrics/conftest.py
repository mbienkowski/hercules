"""Shared helpers for the threshold-runner test files.

`_write_thresholds` materialises a thresholds.json; `_run_one_check` is the write→run pattern the
execution tests share (single threshold + optional target files → results). Kept here so the setup
lives in one place and each test body stays a Given/When/Then that fits on one screen.
"""

from __future__ import annotations

import json
from pathlib import Path

from tests.metrics.threshold_runner import load_thresholds, run_threshold_checks


def _write_thresholds(tmp_path: Path, checks: list[dict]) -> Path:
    f = tmp_path / "thresholds.json"
    f.write_text(json.dumps(checks))
    return f


def _run_one_check(tmp_path: Path, config: dict, files: dict | None = None):
    """Write a single-threshold config plus any named target files under tmp_path, run the checks,
    and return the results list. Behaviour-identical to writing the config inline then running."""
    threshold_file = _write_thresholds(tmp_path, [config])
    for name, text in (files or {}).items():
        (tmp_path / name).write_text(text)
    return run_threshold_checks(tmp_path, load_thresholds(threshold_file))
