"""Decide whether a drafted code-of-conduct (CoC) may be written at all — the gate behind the
generator's draft step, and the only thing standing between a rule an agent liked and a rule the
repository can be held to. Every rule is tagged, names a mechanical check, and cites evidence this
draft carries; the whole draft is counted against the directive budget.

It judges STRUCTURE, before any markdown exists. What the resulting document reads like is
`coc_lint.py`'s question, asked after this one is settled.

Two properties are not negotiable. It is a PURE function of its input: no path is opened and no
subprocess runs, so a hostile repository has no surface here. And it fails CLOSED — an unclassified
error is a refusal, never a pass, because a gate that errs open is not a gate.
"""

from __future__ import annotations

import argparse
import json
import sys

# Bumped only when the envelope shape or the argument surface breaks; the skill passes the version it
# was written against, and a mismatch refuses rather than judging against a grammar nobody meant.
CONTRACT_VERSION = 1

EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_CONTRACT = 2
EXIT_INTERNAL = 4

# A submission larger than this is a defect or an attack, never a code-of-conduct draft.
MAX_INPUT_BYTES = 1024 * 1024

# MUST blocks in continuous integration, SHOULD is enforced by a reviewer. A rule outside this pair
# carries no enforcement meaning, so its tag would tell a reader nothing.
NORMATIVE_TAGS = ("MUST", "SHOULD")

# Where a draft sits against the budget. Only the ceiling refuses: a hard gate at the intended band
# would be answered by merging two rules into one longer bullet, buying a number and costing a reader.
BAND_INTENDED = 40
BAND_LARGE = 50
BAND_CEILING = 70

# The evidence kinds a citation may name: something the scan observed, or something the user said.
CITATION_KINDS = ("fact", "answer")


class Refused(Exception):
    """A rule of this gate rejected the submission. Carries the identifier and the message the skill
    relays verbatim."""

    def __init__(self, rule: str, message: str):
        super().__init__(message)
        self.rule = rule
        self.message = message


class Internal(Exception):
    """The submission could not be read or understood. Never a reason to retry unchanged."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


# ── Reading the submission ────────────────────────────────────────────────────────────────────

def read_envelope(stream) -> dict:
    """The submitted envelope, read whole and bounded. Reading one byte past the cap is enough to
    know the cap is breached, so a huge submission is refused rather than held in memory."""
    try:
        text = stream.read(MAX_INPUT_BYTES + 1)
    except Exception as exc:
        raise Internal(f"The draft could not be read. {exc}") from exc
    if text is None or not str(text).strip():
        raise Internal("No draft was submitted. Send the envelope on standard input.")
    if len(text) > MAX_INPUT_BYTES:
        raise Internal(f"The draft exceeds {MAX_INPUT_BYTES} bytes. Nothing was judged.")
    try:
        envelope = json.loads(text)
    except ValueError as exc:
        raise Internal(f"The draft is not valid JSON, so no rule could be read. {exc}") from exc
    if not isinstance(envelope, dict):
        raise Internal("The draft must be one JSON object carrying `rules`.")
    return envelope


def evidence_ids(envelope: dict, key: str) -> set:
    """Every id the envelope offers under `facts` or `answers`. An entry with no id offers nothing
    and is passed over rather than refused — the rule citing it fails, which names the real defect."""
    entries = envelope.get(key)
    if entries is None:
        return set()
    if not isinstance(entries, list):
        raise Internal(f"`{key}` must be a list of evidence entries.")
    found = set()
    for entry in entries:
        if isinstance(entry, dict) and isinstance(entry.get("id"), str) and entry["id"].strip():
            found.add(entry["id"].strip())
    return found


def rules_of(envelope: dict) -> list:
    """The drafted rules. A draft with none would otherwise clear every check below by having
    nothing to fail."""
    rules = envelope.get("rules")
    if not isinstance(rules, list):
        raise Internal("`rules` must be a list of drafted rules.")
    for rule in rules:
        if not isinstance(rule, dict):
            raise Internal("Every entry in `rules` must be an object.")
    return rules


# ── Judging one rule ──────────────────────────────────────────────────────────────────────────

def _text_of(rule: dict, key: str) -> str:
    value = rule.get(key)
    return value.strip() if isinstance(value, str) else ""


def finding(name: str, rule_id: str, message: str) -> dict:
    return {"rule": name, "rule_id": rule_id, "message": message}


def citation_findings(rule: dict, rule_id: str, known: dict) -> list:
    """Whether each citation names an evidence kind, and whether that evidence exists. An id the
    envelope never offered is the shape of a rule invented and justified afterwards."""
    citations = rule.get("citations")
    if not isinstance(citations, list) or not citations:
        return [finding("rule_uncited", rule_id,
                        f"Rule '{rule_id}' cites no evidence. A rule nobody can trace to a scan "
                        "observation or a user answer is a rule nobody agreed to.")]
    found = []
    for citation in citations:
        kind, _, identifier = str(citation).partition(":")
        if kind not in CITATION_KINDS or not identifier:
            found.append(finding(
                "citation_malformed", rule_id,
                f"Rule '{rule_id}' cites '{citation}', which names no evidence kind. "
                f"Write one of {', '.join(k + ':<id>' for k in CITATION_KINDS)}."))
        elif identifier not in known[kind]:
            found.append(finding(
                "citation_unknown", rule_id,
                f"Rule '{rule_id}' cites {kind} '{identifier}', which this draft does not carry."))
    return found


def rule_findings(rule: dict, known: dict, seen_ids: set) -> list:
    """Every way one rule fails the grammar the code-of-conduct promises of itself."""
    rule_id = _text_of(rule, "id")
    if not rule_id:
        return [finding("rule_unidentified", "",
                        "A rule carries no id, so nothing can cite it or re-verify it later.")]
    if rule_id in seen_ids:
        return [finding("rule_id_duplicated", rule_id,
                        f"Rule id '{rule_id}' is used more than once; an update run could not tell "
                        "the two apart.")]
    seen_ids.add(rule_id)

    found = []
    if _text_of(rule, "tag") not in NORMATIVE_TAGS:
        found.append(finding(
            "rule_untagged", rule_id,
            f"Rule '{rule_id}' is not tagged {' or '.join(NORMATIVE_TAGS)}, so a reader cannot tell "
            "what enforces it."))
    if not _text_of(rule, "check"):
        found.append(finding(
            "rule_uncheckable", rule_id,
            f"Rule '{rule_id}' names no mechanical check. Name the grep, lint rule, job or threshold "
            "that decides it, or drop the rule."))
    found.extend(citation_findings(rule, rule_id, known))
    return found


# ── Judging the draft ─────────────────────────────────────────────────────────────────────────

def band_of(directives: int) -> str:
    """Where the draft sits against the budget."""
    if directives > BAND_CEILING:
        return "ceiling"
    if directives > BAND_LARGE:
        return "over"
    if directives > BAND_INTENDED:
        return "large"
    return "intended"


def band_message(band: str, directives: int) -> str:
    if band == "ceiling":
        return (f"{directives} directives is past the hard ceiling of {BAND_CEILING}. Merge "
                "near-duplicates and cut what the code already makes obvious, then submit again.")
    if band == "over":
        return (f"{directives} directives buys coverage with adherence — past roughly "
                f"{BAND_LARGE} the delegate total crosses the line where instructions start being "
                "dropped. Say so when reporting the draft.")
    if band == "large":
        return (f"{directives} directives suits a large or polyglot repository; a smaller one reads "
                f"better nearer {BAND_INTENDED}.")
    return f"{directives} directives sits inside the intended band."


def judge(envelope: dict) -> dict:
    """The whole verdict: the findings that must clear, what the draft costs, and which evidence it
    left on the table — the last being where the next question comes from, never a failure."""
    known = {"fact": evidence_ids(envelope, "facts"),
             "answer": evidence_ids(envelope, "answers")}
    rules = rules_of(envelope)
    if not rules:
        raise Refused("draft_empty",
                      "The draft carries no rules. A code-of-conduct with nothing in it would pass "
                      "every check by having nothing to check.")

    seen_ids = set()
    findings = []
    cited = set()
    for rule in rules:
        findings.extend(rule_findings(rule, known, seen_ids))
        for citation in rule.get("citations") or []:
            kind, _, identifier = str(citation).partition(":")
            if kind in CITATION_KINDS:
                cited.add(identifier)

    directives = len(rules)
    band = band_of(directives)
    return {
        "findings": findings,
        "directives": directives,
        "band": band,
        "bands": {"intended": BAND_INTENDED, "large": BAND_LARGE, "ceiling": BAND_CEILING},
        "message": band_message(band, directives),
        "unused_evidence": sorted((known["fact"] | known["answer"]) - cited),
    }


# ── Command surface ───────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="coc_audit", add_help=False)
    parser.add_argument("mode", choices=["draft"])
    parser.add_argument("--contract", type=int, required=True)
    return parser


def emit(payload: dict, mode: str, code: int) -> int:
    """Print the verdict as one JSON object and return the exit code. Every path emits, including
    refusals, so the skill parses one shape and never has to guess."""
    print(json.dumps(dict({"contract": CONTRACT_VERSION, "mode": mode}, **payload), indent=2))
    return code


def main(argv=None, home=None, stdin=None) -> int:
    """Read, judge, and turn every failure into a scripted refusal — nothing escapes as a traceback.
    `home` is accepted for a uniform tool signature and unused: this gate keeps no record."""
    try:
        args = build_parser().parse_args(list(argv) if argv is not None else None)
    except SystemExit:
        return emit({"error": "usage",
                     "message": "The arguments were not understood. Expected: "
                                f"draft --contract {CONTRACT_VERSION}"},
                    "draft", EXIT_INTERNAL)
    if args.contract != CONTRACT_VERSION:
        return emit({"error": "contract",
                     "message": f"This tool speaks version {CONTRACT_VERSION}; the skill asked for "
                                f"{args.contract}. Update the plugin, then run this again."},
                    args.mode, EXIT_CONTRACT)
    try:
        report = judge(read_envelope(stdin if stdin is not None else sys.stdin))
    except Refused as exc:
        return emit({"error": "refused", "rule": exc.rule, "message": exc.message,
                     "findings": [finding(exc.rule, "", exc.message)]}, args.mode, EXIT_REFUSED)
    except Internal as exc:
        return emit({"error": "internal", "message": exc.message}, args.mode, EXIT_INTERNAL)
    except Exception as exc:  # fail closed: an unclassified error is never a pass
        return emit({"error": "internal", "message": f"Nothing was judged. {exc}"},
                    args.mode, EXIT_INTERNAL)
    if report["findings"] or report["band"] == "ceiling":
        return emit(report, args.mode, EXIT_REFUSED)
    return emit(report, args.mode, EXIT_OK)


if __name__ == "__main__":  # pragma: no cover - exercised via main() in tests
    sys.exit(main())
