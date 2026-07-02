"""Data-driven threshold checks driven by thresholds.json."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from tests.metrics.a2a_grammar import (
    count_core_entries,
    extract_a2a_core,
    extract_used_statuses,
)
from tests.metrics.markdown_metrics import (
    count_instructions,
    count_status_table_rows,
)
from tests.metrics.token_counter import count_tokens

MetricFn = Callable[[str], int]  # pragma: no mutate

_VALID_SEVERITIES = {"gate", "warn"}
_VALID_OPS = {"==", "<=", ">=", "<", ">"}


def _core_token_count(text: str) -> int:
    core, ok = extract_a2a_core(text)
    if not ok:
        raise ValueError("no fenced Core block found")  # pragma: no mutate
    return count_tokens(core)


def _core_entry_count(text: str) -> int:
    return count_core_entries(extract_a2a_core(text)[0])


METRIC_REGISTRY: dict[str, MetricFn] = {
    "instruction_count": count_instructions,
    "token_count": count_tokens,
    "core_entry_count": _core_entry_count,
    "core_token_count": _core_token_count,
}


@dataclass
class ThresholdCheck:
    name: str
    target: str
    metric: str
    op: str
    limit: int
    severity: str
    warn_at: int | None = None
    per_file: bool = False


@dataclass
class CheckResult:
    name: str
    value: int
    passed: bool
    severity: str
    message: str
    near_warn: bool = False


def load_thresholds(path: Path) -> list[ThresholdCheck]:
    """Load and validate thresholds.json; raise ValueError on any invalid row."""
    raw: list[dict[str, Any]] = json.loads(path.read_text())
    checks: list[ThresholdCheck] = []
    for row in raw:
        name = row["name"]
        metric = row["metric"]
        if metric not in METRIC_REGISTRY:
            raise ValueError(
                f"thresholds.json row {name!r}: unknown metric {metric!r} "  # pragma: no mutate
                f"(known: {sorted(METRIC_REGISTRY)})"  # pragma: no mutate
            )
        severity = row.get("severity", "gate")
        if severity not in _VALID_SEVERITIES:
            raise ValueError(
                f"thresholds.json row {name!r}: unknown severity {severity!r} "  # pragma: no mutate
                f"(must be 'gate' or 'warn')"  # pragma: no mutate
            )
        op = row["op"]
        if op not in _VALID_OPS:
            raise ValueError(
                f"thresholds.json row {name!r}: unknown op {op!r} "  # pragma: no mutate
                f"(must be one of {sorted(_VALID_OPS)})"  # pragma: no mutate
            )
        warn_at = row.get("warn_at")
        limit = row["limit"]
        if warn_at is not None and warn_at > limit:
            raise ValueError(
                f"thresholds.json row {name!r}: warn_at ({warn_at}) > limit ({limit})"  # pragma: no mutate
            )
        checks.append(
            ThresholdCheck(
                name=name,
                target=row["target"],
                metric=metric,
                op=op,
                limit=limit,
                severity=severity,
                warn_at=warn_at,
                per_file=row.get("per_file", False),
            )
        )
    return checks


def run_threshold_checks(
    repo_root: Path, checks: list[ThresholdCheck]
) -> list[CheckResult]:
    """Run all data-driven threshold checks and return results.

    Gate failures are returned as results with passed=False; they do not raise.
    """
    results: list[CheckResult] = []

    for check in checks:
        targets = resolve_targets(repo_root, check.target)
        if not targets:
            results.append(
                CheckResult(
                    name=check.name,
                    value=0,
                    passed=False,
                    severity=check.severity,
                    message=f"target {check.target!r} matched no files",
                )
            )
            continue

        fn = METRIC_REGISTRY[check.metric]

        if check.per_file:
            # Apply the limit to each matched file individually (e.g. "every agent <= 800").
            offenders: list[str] = []
            worst = 0
            for path in targets:
                value = fn(path.read_text())
                worst = max(worst, value)
                ok, err = compare_value(value, check.op, check.limit)
                if err:
                    raise ValueError(f"check {check.name!r}: {err}")
                if not ok:
                    offenders.append(f"{path.relative_to(repo_root)}={value}")
            passed = not offenders
            reported = worst
            msg = (
                f"{check.name}: per-file {check.metric}({check.target}) "
                f"want {check.op} {check.limit}"
                + (f" — offenders: {', '.join(offenders)}" if offenders else "")
            )
        else:
            # Sum the metric across all matched files (a combined budget).
            total = 0
            for path in targets:
                total += fn(path.read_text())
            passed, err = compare_value(total, check.op, check.limit)
            if err:
                raise ValueError(f"check {check.name!r}: {err}")
            reported = total
            msg = (
                f"{check.name}: {check.metric}({check.target})={total}, "
                f"want {check.op} {check.limit}"
            )

        near_warn = (
            check.warn_at is not None and passed and reported >= check.warn_at
        )
        results.append(
            CheckResult(
                name=check.name,
                value=reported,
                passed=passed,
                severity=check.severity,
                message=msg,
                near_warn=near_warn,
            )
        )

    return results


def compare_value(value: int, op: str, limit: int) -> tuple[bool, str]:
    """Evaluate `value op limit`; return (result, error_message).

    Error message is non-empty only for unknown operators.
    """
    if op == "==":
        return value == limit, ""
    if op == "<=":
        return value <= limit, ""
    if op == ">=":
        return value >= limit, ""
    if op == "<":
        return value < limit, ""
    if op == ">":
        return value > limit, ""
    return False, f"unknown op {op!r}"


def resolve_targets(repo_root: Path, target: str) -> list[Path]:
    """Expand a comma-separated list of paths or globs relative to repo_root."""
    seen: set[Path] = set()
    out: list[Path] = []
    for pat in target.split(","):
        pat = pat.strip()
        if not pat:
            continue
        if any(c in pat for c in "*?["):
            for match in sorted(repo_root.glob(pat)):
                if match not in seen:
                    seen.add(match)
                    out.append(match)
        else:
            full = repo_root / pat
            if full not in seen:
                seen.add(full)
                out.append(full)
    return out
