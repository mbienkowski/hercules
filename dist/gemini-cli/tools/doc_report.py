"""Turn a reviewer's judgement of a delivery document into one decision a workflow can act on.

WHY THIS EXISTS: whether the flows are the right flows, or a name reveals its behaviour, is not
something a pattern match can answer — a reviewer has to read the document and form a view. What a
program CAN do is refuse to let that view be vague. So the reviewer fills in a report against a
fixed rubric, one verdict per category, and this tool checks the accounting and applies the policy.

The division of labour, stated once:
  - the reviewer forms the opinion       (this tool never does, and never scores quality itself)
  - this tool checks the opinion is COMPLETE — every rubric category answered, because silence is
    not a pass, the same rule the A2A protocol already puts on a Pass status
  - this tool turns severities into a DECISION — proceed, revise, or escalate — so "needs work"
    stops being a feeling and becomes a threshold someone agreed to in advance.

Mechanical findings from `doc_lint.py` fold into the same report, so an author reads one list
instead of two, sorted by what actually costs them.

READ-ONLY by declaration: it prints the merged report and the decision, and the caller persists
whatever it wants through `state_patch.py`. Every path prints one JSON object, refusals included.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_UNCONFIRMED = 2
EXIT_INTERNAL = 3
EXIT_NOT_FOUND = 4

_RULES_FILE = "doc_rules.json"
_RANK = {"blocker": 0, "major": 1, "minor": 2, "nit": 3, "pass": 4}


class Refused(Exception):
    """A precondition rejected the run. Carries the scripted message the caller relays verbatim —
    § Failure moments: a stop names the next action, never just the problem."""

    def __init__(self, message: str, detail=None):
        super().__init__(message)
        self.message = message
        self.detail = detail or []


def load_rules(script_dir: Path) -> dict:
    path = script_dir / _RULES_FILE
    if not path.exists():
        raise Refused("the standard is missing at %s — reinstall the plugin" % path)
    return json.loads(path.read_text(encoding="utf-8"))


def rubric_for(rules: dict, kind: str):
    rubrics = rules["review"]["rubrics"]
    if kind not in rubrics:
        raise Refused("no rubric for %r — expected one of %s"
                      % (kind, ", ".join(sorted(rubrics))))
    return rubrics[kind]


# ── validation ──────────────────────────────────────────────────────────────────────────────────


def validate_shape(report: dict, rules: dict) -> str:
    """The report has to be answerable before it can be judged. A missing field here means the
    reviewer skipped the question rather than answered it."""
    for field in ("document", "kind", "tier", "reviewer", "categories"):
        if field not in report:
            raise Refused("the report names no %r — a reviewer must say what it reviewed and how"
                          % field)
    if report["tier"] not in rules["tiers"]:
        raise Refused("unknown tier %r — expected one of %s"
                      % (report["tier"], ", ".join(rules["tiers"])))
    if not isinstance(report["categories"], list):
        raise Refused("'categories' must be a list, one entry per rubric category")
    return report["kind"]


def validate_completeness(report: dict, rubric, severities) -> list:
    """Every category answered, every non-pass carrying a real finding. This is the whole
    mechanical contribution: it cannot tell a good verdict from a bad one, but it can tell an
    ANSWERED question from a skipped one."""
    problems = []
    answered = {}
    for entry in report["categories"]:
        name = entry.get("category")
        if name is None:
            problems.append("a category entry names no category")
            continue
        if entry.get("verdict") not in severities:
            problems.append("%s: verdict %r is not one of %s"
                            % (name, entry.get("verdict"), ", ".join(severities)))
            continue
        answered[name] = entry

    expected = [item["category"] for item in rubric]
    for name in expected:
        if name not in answered:
            problems.append("%s: not assessed — silence on a category is never a pass" % name)

    for name in sorted(set(answered) - set(expected)):
        problems.append("%s: not a category in this rubric" % name)

    for name, entry in answered.items():
        verdict = entry.get("verdict")
        if verdict == "pass":
            # Mirrors the A2A rule: a Pass names what was checked, or it is a rubber stamp.
            if not str(entry.get("note", "")).strip():
                problems.append("%s: a pass must name what was checked" % name)
            continue
        if not entry.get("findings"):
            problems.append("%s: verdict %r with no finding — say what is wrong or mark it a pass"
                            % (name, verdict))
    return problems


def validate_findings(report: dict, required_fields) -> list:
    problems = []
    for entry in report["categories"]:
        for index, finding in enumerate(entry.get("findings") or []):
            for field in required_fields:
                if not str(finding.get(field, "")).strip():
                    problems.append("%s finding %d: no %r — a finding without one is not actionable"
                                    % (entry.get("category"), index + 1, field))
    return problems


# ── merge and decide ────────────────────────────────────────────────────────────────────────────


def fold_in_mechanical(report: dict, lint_payload: dict) -> list:
    """A lint finding is a fact, not an opinion, so it enters as its own category rather than
    colouring a reviewer's verdict. `block` maps to blocker; everything else is a minor by
    construction — the linter is advisory and does not get to outrank a human reviewer."""
    findings = []
    for item in lint_payload.get("findings", []):
        findings.append({
            "where": "%s:%s" % (item.get("section") or lint_payload.get("path", ""), item.get("line")),
            "observation": "%s — %s" % (item.get("rule"), item.get("message")),
            "impact": item.get("title", ""),
            "recommendation": item.get("fix", ""),
            "severity": "blocker" if item.get("severity") == "block" else "minor",
        })
    if not findings:
        return []
    worst = "blocker" if any(f["severity"] == "blocker" for f in findings) else "minor"
    return [{"category": "mechanical", "verdict": worst,
             "note": "folded in from doc_lint", "findings": findings}]


def tally(categories) -> dict:
    counts = {name: 0 for name in _RANK}
    for entry in categories:
        verdict = entry.get("verdict")
        if verdict in counts:
            counts[verdict] += 1
    return counts


def decide(counts: dict, rules: dict, tier: str, round_number: int) -> dict:
    """One threshold, agreed in advance, so the same report yields the same call every time."""
    policy = rules["review"]["policy"]
    limits = policy["tiers"][tier]
    max_rounds = policy["max_rounds"]

    reasons = []
    over_blocker = counts["blocker"] > limits["blocker_allowed"]
    over_major = counts["major"] > limits["major_allowed"]
    if over_blocker:
        reasons.append("%d blocker(s); tier %s allows %d"
                       % (counts["blocker"], tier, limits["blocker_allowed"]))
    if over_major:
        reasons.append("%d major(s); tier %s allows %d"
                       % (counts["major"], tier, limits["major_allowed"]))

    if not reasons:
        return {"decision": "proceed", "reasons": ["within the tier's tolerance"],
                "round": round_number, "max_rounds": max_rounds}
    if round_number >= max_rounds:
        reasons.append("round %d of %d — the loop stops here and a person decides"
                       % (round_number, max_rounds))
        return {"decision": "escalate", "reasons": reasons,
                "round": round_number, "max_rounds": max_rounds}
    return {"decision": "revise", "reasons": reasons,
            "round": round_number, "max_rounds": max_rounds}


def worklist(categories):
    """What to fix, worst first — the point of the whole exercise being that a reviewer's prose
    becomes an ordered list of work rather than an impression."""
    items = []
    for entry in categories:
        verdict = entry.get("verdict")
        if verdict == "pass":
            continue
        for finding in entry.get("findings") or []:
            items.append({
                "severity": finding.get("severity", verdict),
                "category": entry.get("category"),
                "where": finding.get("where", ""),
                "do": finding.get("recommendation", ""),
                "because": finding.get("impact", ""),
            })
    return sorted(items, key=lambda item: _RANK.get(item["severity"], 9))


# ── modes ───────────────────────────────────────────────────────────────────────────────────────


def read_json(path_text: str, what: str) -> dict:
    path = Path(path_text)
    if not path.exists():
        raise Refused("no %s at %s" % (what, path))
    return json.loads(path.read_text(encoding="utf-8"))


def run_judge(rules: dict, args) -> tuple:
    report = read_json(args.report, "report")
    kind = validate_shape(report, rules)
    rubric = rubric_for(rules, kind)
    severities = rules["review"]["severities"]

    problems = validate_completeness(report, rubric, severities)
    problems += validate_findings(report, rules["review"]["finding_fields"])
    if problems:
        raise Refused("the review is not answerable yet — %d gap(s) to close" % len(problems),
                      detail=problems)

    categories = list(report["categories"])
    if args.lint:
        categories += fold_in_mechanical(report, read_json(args.lint, "lint result"))

    counts = tally(categories)
    verdict = decide(counts, rules, report["tier"], int(args.round or report.get("round", 1)))
    payload = {
        "mode": "judge",
        "document": report["document"],
        "kind": kind,
        "tier": report["tier"],
        "reviewer": report["reviewer"],
        "rules_version": rules["rules_version"],
        "counts": counts,
        "worklist": worklist(categories),
    }
    payload.update(verdict)
    return payload, EXIT_OK if verdict["decision"] == "proceed" else EXIT_REFUSED


def run_template(rules: dict, args) -> tuple:
    """The shape a reviewer fills in. Emitted rather than described, so the reviewer and the
    checker cannot disagree about what a complete review looks like."""
    kind = args.kind
    rubric = rubric_for(rules, kind)
    skeleton = {
        "document": "YYYY-MM-DD-{slug}-%s.md" % ("business-requirements" if
                                                 kind == "business-requirements" else "spec-NN-{name}"),
        "kind": kind,
        "tier": args.tier or "medium",
        "reviewer": "{the agent or person who read it}",
        "round": 1,
        "categories": [
            {"category": item["category"],
             "asks": item["asks"],
             "verdict": "one of: " + ", ".join(rules["review"]["severities"]),
             "note": "what you checked (required when the verdict is a pass)",
             "findings": [{field: "..." for field in rules["review"]["finding_fields"]}]}
            for item in rubric
        ],
    }
    return {"mode": "template", "kind": kind, "rules_version": rules["rules_version"],
            "report_template": skeleton}, EXIT_OK


def run_rubric(rules: dict, args) -> tuple:
    return {"mode": "rubric", "rules_version": rules["rules_version"],
            "severities": rules["review"]["severities"],
            "severity_meaning": rules["review"]["severity_meaning"],
            "policy": rules["review"]["policy"],
            "rubrics": rules["review"]["rubrics"]}, EXIT_OK


def emit(payload: dict, code: int) -> int:
    sys.stdout.write(json.dumps(payload, indent=2, sort_keys=False) + "\n")
    return code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="doc_report",
        description="Judge a document review: check it is complete, then apply the tier's policy.")
    parser.add_argument("mode", choices=("judge", "template", "rubric"))
    parser.add_argument("--report", dest="report")
    parser.add_argument("--lint", dest="lint", help="a doc_lint check result to fold in")
    parser.add_argument("--kind", dest="kind", default="")
    parser.add_argument("--tier", dest="tier", default="")
    parser.add_argument("--round", dest="round", default="")
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        rules = load_rules(Path(__file__).resolve().parent)
        if args.mode == "judge":
            if not args.report:
                raise Refused("judge needs --report naming the review to read")
            payload, code = run_judge(rules, args)
        elif args.mode == "template":
            if not args.kind:
                raise Refused("template needs --kind naming the document reviewed")
            payload, code = run_template(rules, args)
        else:
            payload, code = run_rubric(rules, args)
        return emit(payload, code)
    except Refused as refusal:
        missing = refusal.message.startswith("no ")
        return emit({"mode": args.mode, "error": "refused", "message": refusal.message,
                     "detail": refusal.detail},
                    EXIT_NOT_FOUND if missing else EXIT_REFUSED)
    except json.JSONDecodeError as broken:
        return emit({"mode": args.mode, "error": "internal",
                     "message": "not valid JSON: %s" % broken}, EXIT_INTERNAL)
    except OSError as unreadable:
        return emit({"mode": args.mode, "error": "internal",
                     "message": "cannot read: %s" % unreadable}, EXIT_INTERNAL)


if __name__ == "__main__":
    sys.exit(main())
