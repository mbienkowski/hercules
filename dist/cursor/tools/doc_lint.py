"""Check a Hercules delivery document against the standard, emit the template it should follow, and
publish the guidance a person applies with judgement.

WHY THIS EXISTS: the same instruction produces a careful document one day and a vague one the next.
Prompt rules are read and mostly followed, and "mostly" is the defect. So the standard lives in
`doc_rules.json` beside this file and has two halves. `rules` is the mechanical half — things that
are true or false with no opinion attached, which this program checks. `guidance` is the judgement
half — whether the flows are the right flows, whether a name reveals its behaviour — which this
program deliberately never scores. The skill and the command templates are written from the same
file, so what an author is told and what gets checked cannot drift apart.

WHAT IT IS NOT: an authority on whether a document is good. Almost every finding is `advice`, shown
next to the draft for a person to accept or wave away. Exactly one severity blocks — a reference
pointing at a section that does not exist — because a broken link is not a matter of taste.

This tool is READ-ONLY by declaration. The caller persists the verdict through `state_patch.py`,
which already owns atomic writes, so a failed check can never leave a torn state file. Every path
prints one JSON object on stdout, refusals included, so a caller never parses prose.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_UNCONFIRMED = 2
EXIT_INTERNAL = 3
EXIT_NOT_FOUND = 4

_RULES_FILE = "doc_rules.json"


class Refused(Exception):
    """A precondition rejected the run before any checking happened. Carries the scripted message
    the caller relays verbatim, per § Failure moments — a stop names the next action."""

    def __init__(self, message: str, candidates=None):
        super().__init__(message)
        self.message = message
        self.candidates = candidates or []


def load_rules(script_dir: Path) -> dict:
    """The standard, read from beside this script so the shipped copy is self-contained."""
    path = script_dir / _RULES_FILE
    if not path.exists():
        raise Refused("the standard is missing at %s — reinstall the plugin" % path)
    return json.loads(path.read_text(encoding="utf-8"))


# ── document model ──────────────────────────────────────────────────────────────────────────────


class Section:
    """One `##` section: its heading, the lines under it, and where it starts."""

    def __init__(self, name: str, line_no: int):
        self.name = name
        self.line_no = line_no
        self.lines = []

    def body(self):
        """Content lines, with blanks and sub-headings dropped."""
        return [line for line in self.lines if line.strip() and not line.lstrip().startswith("#")]

    def text(self) -> str:
        return "\n".join(self.lines)


class Document:
    """A parsed delivery document. Fenced blocks are tracked apart from prose because they are
    examples, and a rule that reads an example as prose reports the example rather than the work."""

    def __init__(self, path: Path, text: str):
        self.path = path
        self.raw = text
        self.lines = text.splitlines()
        self.sections = []
        self.headings = []
        self.preamble = []
        self._parse()

    def _parse(self) -> None:
        current = None
        in_fence = False
        for index, line in enumerate(self.lines, start=1):
            stripped = line.strip()
            if stripped.startswith("```"):
                in_fence = not in_fence
                if current is not None:
                    current.lines.append(line)
                continue
            if in_fence:
                if current is not None:
                    current.lines.append(line)
                continue
            if stripped.startswith("#"):
                depth = len(stripped) - len(stripped.lstrip("#"))
                self.headings.append((depth, stripped.lstrip("#").strip(), index))
                if depth == 2:
                    current = Section(stripped.lstrip("#").strip(), index)
                    self.sections.append(current)
                    continue
            if current is None:
                self.preamble.append((index, line))
            else:
                current.lines.append(line)

    def section(self, name: str):
        for section in self.sections:
            if section.name.lower() == name.lower():
                return section
        return None

    def heading_names(self):
        return {name.lower() for _, name, _ in self.headings}

    def prose_words(self, exempt_names) -> int:
        """Words a reader actually reads: fenced blocks, headings and exempt sections excluded."""
        total = 0
        exempt = {name.lower() for name in exempt_names}
        for section in self.sections:
            if section.name.lower() in exempt:
                continue
            in_fence = False
            for line in section.lines:
                if line.strip().startswith("```"):
                    in_fence = not in_fence
                    continue
                if in_fence or line.lstrip().startswith("#"):
                    continue
                total += len(line.split())
        return total


def fenced_ranges(section: Section):
    """Which of a section's lines sit inside a fence, so examples are not read as claims."""
    marks = []
    in_fence = False
    for line in section.lines:
        if line.strip().startswith("```"):
            in_fence = not in_fence
            marks.append(True)
            continue
        marks.append(in_fence)
    return marks


# ── findings ────────────────────────────────────────────────────────────────────────────────────


class Findings:
    """Collected observations, each carrying the fix its rule declares."""

    def __init__(self, catalogue):
        self.by_id = {rule["id"]: rule for rule in catalogue}
        self.items = []

    def add(self, rule_id: str, message: str, line: int = 0, section: str = "") -> None:
        rule = self.by_id.get(rule_id)
        if rule is None:
            raise Refused("rule %s is not in the standard" % rule_id)
        self.items.append({
            "rule": rule_id,
            "severity": rule["severity"],
            "title": rule["title"],
            "line": line,
            "section": section,
            "message": message,
            "fix": rule["fix"],
        })

    def counts(self):
        blocks = len([item for item in self.items if item["severity"] == "block"])
        return {"block": blocks, "advice": len(self.items) - blocks}


# ── checks ──────────────────────────────────────────────────────────────────────────────────────


def tier_index(rules: dict, tier: str) -> int:
    if tier not in rules["tiers"]:
        raise Refused("unknown tier %r — expected one of %s" % (tier, ", ".join(rules["tiers"])))
    return rules["tiers"].index(tier)


def required_sections(rules: dict, kind: dict, tier: str):
    """Sections the tier expects. `never` means allowed but never asked for."""
    at = tier_index(rules, tier)
    return [section for section in kind["sections"]
            if section["required_from"] != "never"
            and rules["tiers"].index(section["required_from"]) <= at]


def check_structure(doc: Document, rules: dict, kind: dict, tier: str, found: Findings) -> None:
    known = {section["name"].lower() for section in kind["sections"]}
    order = [section["name"].lower() for section in kind["sections"]]

    for section in required_sections(rules, kind, tier):
        if doc.section(section["name"]) is None:
            found.add("DOC101", "'%s' is usually present at tier %s — %s"
                      % (section["name"], tier, section["mandate"]))

    present = []
    for section in doc.sections:
        if section.name.lower() not in known:
            found.add("DOC106", "'%s' is not a section the standard names" % section.name,
                      section.line_no, section.name)
            continue
        present.append((order.index(section.name.lower()), section))

    ranks = [rank for rank, _ in present]
    if ranks != sorted(ranks):
        for position, (rank, section) in enumerate(present):
            if position and rank < present[position - 1][0]:
                found.add("DOC102", "'%s' appears after '%s'"
                          % (section.name, present[position - 1][1].name),
                          section.line_no, section.name)


def check_emptiness(doc: Document, rules: dict, kind: dict, tier: str, found: Findings) -> None:
    allowed_empty = {name.lower() for name in rules["meaningful_when_empty"]}
    required = {section["name"].lower(): section for section in required_sections(rules, kind, tier)}
    for section in doc.sections:
        spec = required.get(section.name.lower())
        if spec is None or section.name.lower() in allowed_empty:
            continue
        body = section.body()
        if not body:
            found.add("DOC104", "'%s' has no content" % section.name, section.line_no, section.name)
        elif len(body) < spec.get("min_items", 1):
            found.add("DOC104", "'%s' carries %d lines where this tier usually needs %d"
                      % (section.name, len(body), spec["min_items"]),
                      section.line_no, section.name)


def check_placeholders(doc: Document, rules: dict, found: Findings) -> None:
    allowed_empty = {name.lower() for name in rules["meaningful_when_empty"]}
    for section in doc.sections:
        if section.name.lower() in allowed_empty:
            continue
        marks = fenced_ranges(section)
        for offset, line in enumerate(section.lines):
            if marks[offset]:
                continue
            for token in rules["placeholders"]:
                if token.lower() in line.lower():
                    found.add("DOC103", "contains %r" % token,
                              section.line_no + offset + 1, section.name)
                    break


def check_business_containment(doc: Document, rules: dict, kind: dict, found: Findings) -> None:
    """Technical vocabulary belongs in one section of a business document, and only as an option.
    This is containment, not censorship: naming a system is fine, ordering a design is not."""
    allowed = {section["name"].lower() for section in kind["sections"]
               if section.get("allows_implementation_tokens")}
    patterns = [re.compile(pattern) for pattern in rules["implementation_token_patterns"]]
    mandates = [re.compile(pattern, re.IGNORECASE) for pattern in rules["mandate_patterns"]]

    for section in doc.sections:
        marks = fenced_ranges(section)
        for offset, line in enumerate(section.lines):
            if marks[offset] or not line.strip():
                continue
            line_no = section.line_no + offset + 1
            for mandate in mandates:
                if mandate.search(line):
                    found.add("DOC206", "reads as a technical instruction: %r" % line.strip()[:70],
                              line_no, section.name)
                    break
            if section.name.lower() in allowed:
                continue
            for pattern in patterns:
                match = pattern.search(line)
                if match:
                    found.add("DOC204", "names %r, which is implementation detail"
                              % match.group(0).strip()[:40], line_no, section.name)
                    break

    hedged = next((section for section in kind["sections"] if section.get("hedged")), None)
    if hedged is None:
        return
    suggestions = doc.section(hedged["name"])
    if suggestions is None:
        return
    hedges = [word.lower() for word in rules["hedge_words"]]
    for offset, line in enumerate(suggestions.lines):
        stripped = line.strip()
        if stripped.startswith(("- ", "* ")) and not any(h in stripped.lower() for h in hedges):
            found.add("DOC207", "stated as settled: %r" % stripped[:70],
                      suggestions.line_no + offset + 1, suggestions.name)
    if rules["suggestion_closing_sentence"] not in suggestions.text():
        found.add("DOC207", "the section does not close with its fixed sentence",
                  suggestions.line_no, suggestions.name)


def check_scenarios(doc: Document, rules: dict, kind: dict, tier: str, found: Findings) -> None:
    spec = next((s for s in kind["sections"] if s["style"] == "scenarios"), None)
    if spec is None:
        return
    section = doc.section(spec["name"])
    if section is None:
        return

    pattern = re.compile(rules["scenario_line"]["pattern"])
    claims = re.compile(rules["scenario_line"]["claim_pattern"])
    budget = kind["budgets"][tier]["scenarios"]
    seen = set()
    counts = {"M": 0, "N": 0, "C": 0}
    flow = None
    per_flow = {}
    marks = fenced_ranges(section)

    for offset, line in enumerate(section.lines):
        if marks[offset]:
            continue
        stripped = line.strip()
        line_no = section.line_no + offset + 1
        if stripped.startswith("### "):
            flow = stripped[4:].strip()
            per_flow[flow] = {"M": 0, "N": 0, "C": 0, "line": line_no, "waived": False}
            continue
        if flow is not None and "scenarios: n/a" in stripped.lower():
            per_flow[flow]["waived"] = True
            continue
        if not stripped.startswith(("- ", "* ")):
            continue
        normalised = stripped.replace("* ", "- ", 1)
        # A bullet not opening with an identifier is ordinary prose — a flow's story line lives
        # here too, and reading it as a broken scenario would refuse legitimate content.
        if claims.match(normalised) is None:
            continue
        match = pattern.match(normalised)
        if match is None:
            found.add("DOC302", "not a scenario line: %r" % stripped[:70], line_no, section.name)
            continue
        identifier = match.group(1) + match.group(2)
        if identifier in seen:
            found.add("DOC304", "identifier %s is used twice" % identifier, line_no, section.name)
        seen.add(identifier)
        counts[match.group(1)] += 1
        if flow is not None:
            per_flow[flow][match.group(1)] += 1

    for name, tally in per_flow.items():
        if tally["waived"] or tally["N"]:
            continue
        found.add("DOC301", "flow '%s' names no way it can fail" % name,
                  tally["line"], section.name)

    if counts["N"] < counts["M"]:
        found.add("DOC303", "%d happy paths against %d failure cases" % (counts["M"], counts["N"]),
                  section.line_no, section.name)
    for klass, allowed in budget.items():
        if counts[klass] > allowed:
            found.add("DOC305", "%d %s scenarios, where tier %s suggests %d"
                      % (counts[klass], rules["scenario_classes"][klass], tier, allowed),
                      section.line_no, section.name)


def check_budgets(doc: Document, rules: dict, kind: dict, tier: str, found: Findings) -> None:
    """Length is a signal, never a target: it says 'look at this', not 'this is wrong'."""
    exempt = [section["name"] for section in kind["sections"]
              if section.get("exempt_from_word_budget")]
    words = doc.prose_words(exempt)
    budget = kind["budgets"][tier]
    if words < budget["words_floor"]:
        found.add("DOC601", "%d words, where tier %s usually runs past %d"
                  % (words, tier, budget["words_floor"]))
    elif words > budget["words_hard"]:
        found.add("DOC602", "%d words, where tier %s usually stays under %d"
                  % (words, tier, budget["words_hard"]))


def check_tables(doc: Document, found: Findings) -> None:
    risks = doc.section("Risks & mitigations")
    if risks is None:
        return
    for offset, line in enumerate(risks.lines):
        stripped = line.strip()
        if not stripped.startswith("|") or set(stripped) <= set("|- :"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 2 or cells[0].lower() in ("risk", ""):
            continue
        if len(cells) < 3 or not cells[2]:
            found.add("DOC402", "risk %r carries no mitigation" % cells[0][:40],
                      risks.line_no + offset + 1, risks.name)


def check_references(doc: Document, rules: dict, found: Findings) -> None:
    """The one hard block. A spec pointing at a requirements section that does not exist has already
    lost its traceability, and no amount of judgement makes a dead link live."""
    config = rules["references"]
    header = re.compile(config["header_pattern"], re.IGNORECASE)
    covers = re.compile(config["covers_pattern"], re.IGNORECASE)
    marker = config["section_marker"]
    satisfied = None

    for line_no, line in doc.preamble:
        match = header.match(line.strip())
        if match is None:
            continue
        for reference in match.group(2).split(","):
            reference = reference.strip().strip("[]")
            if ".md" not in reference:
                continue
            filename, _, anchor = reference.partition(marker)
            filename = filename.strip()
            target = doc.path.parent / filename
            if not target.exists():
                found.add("DOC701", "%r names no file beside this document" % filename, line_no)
                continue
            satisfied = target
            anchor = anchor.strip()
            if not anchor:
                continue
            headings = {name.strip().lower()
                        for name in re.findall(r"^#{1,4}\s*(.+)$",
                                               target.read_text(encoding="utf-8"), re.MULTILINE)}
            if anchor.lower() not in headings:
                found.add("DOC701", "%r has no section %r" % (filename, anchor), line_no)

    # A `covers:` identifier is the other half of the same link: it names a scenario in the document
    # the spec satisfies, and that is what makes Build's traceability a grep rather than a paraphrase.
    if satisfied is None:
        return
    known = set(re.findall(r"^-\s*([MNC][0-9]+)\b", satisfied.read_text(encoding="utf-8"),
                           re.MULTILINE))
    for line_no, line in doc.preamble:
        match = covers.match(line.strip())
        if match is None:
            continue
        for identifier in match.group(1).split(","):
            identifier = identifier.strip().strip("[]")
            if ":" in identifier:
                identifier = identifier.split(":")[-1].strip()
            if identifier and identifier not in known:
                found.add("DOC702", "%s is not a scenario in %s" % (identifier, satisfied.name),
                          line_no)


# ── modes ───────────────────────────────────────────────────────────────────────────────────────


def resolve_kind(rules: dict, path: Path, named: str) -> str:
    if named:
        if named not in rules["kinds"]:
            raise Refused("unknown kind %r — expected one of %s"
                          % (named, ", ".join(sorted(rules["kinds"]))))
        return named
    for kind_name, kind in rules["kinds"].items():
        if re.match(kind["filename_pattern"], path.name):
            return kind_name
    raise Refused("cannot tell what kind of document %s is — pass --kind" % path.name)


def run_check(rules: dict, args) -> tuple:
    path = Path(args.path)
    if not path.exists():
        raise Refused("no document at %s" % path)
    kind_name = resolve_kind(rules, path, args.kind)
    kind = rules["kinds"][kind_name]
    tier = args.tier or "medium"
    tier_index(rules, tier)

    text = path.read_text(encoding="utf-8")
    doc = Document(path, text)
    found = Findings(rules["rules"])

    if not re.match(kind["filename_pattern"], path.name):
        found.add("DOC401", "%r does not match the naming pattern for a %s" % (path.name, kind_name))

    check_structure(doc, rules, kind, tier, found)
    check_emptiness(doc, rules, kind, tier, found)
    check_placeholders(doc, rules, found)
    check_scenarios(doc, rules, kind, tier, found)
    check_budgets(doc, rules, kind, tier, found)
    check_references(doc, rules, found)
    if kind_name == "business-requirements":
        check_business_containment(doc, rules, kind, found)
    else:
        check_tables(doc, found)

    counts = found.counts()
    blocking = counts["block"] or (args.strict and counts["advice"])
    payload = {
        "mode": "check",
        "path": str(path),
        "kind": kind_name,
        "tier": tier,
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "rules_version": rules["rules_version"],
        "clean": not blocking,
        "counts": counts,
        "findings": sorted(found.items,
                           key=lambda item: (item["severity"] != "block", item["line"])),
    }
    return payload, EXIT_REFUSED if blocking else EXIT_OK


def run_template(rules: dict, args) -> tuple:
    kind_name = args.kind
    if kind_name not in rules["kinds"]:
        raise Refused("unknown kind %r — expected one of %s"
                      % (kind_name, ", ".join(sorted(rules["kinds"]))))
    kind = rules["kinds"][kind_name]
    tier = args.tier or "medium"
    wanted = {section["name"] for section in required_sections(rules, kind, tier)}

    lines = []
    for section in kind["sections"]:
        if section["name"] in wanted:
            lines.append("## " + section["name"])
            lines.append("<!-- " + section["mandate"] + " -->")
            lines.append("")
    return {"mode": "template", "kind": kind_name, "tier": tier,
            "rules_version": rules["rules_version"],
            "template": "\n".join(lines).rstrip() + "\n"}, EXIT_OK


def run_rules(rules: dict, args) -> tuple:
    if args.kind:
        resolve_kind(rules, Path("x"), args.kind)
    return {"mode": "rules", "rules_version": rules["rules_version"],
            "kinds": sorted(rules["kinds"]), "rules": rules["rules"]}, EXIT_OK


def run_guidance(rules: dict, args) -> tuple:
    """The judgement half, published so the skill and the commands are written from this file too."""
    return {"mode": "guidance", "rules_version": rules["rules_version"],
            "guidance": rules["guidance"]}, EXIT_OK


def emit(payload: dict, code: int) -> int:
    sys.stdout.write(json.dumps(payload, indent=2, sort_keys=False) + "\n")
    return code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="doc_lint",
        description="Check a Hercules delivery document, emit its template, or publish the standard.")
    parser.add_argument("mode", choices=("check", "template", "rules", "guidance"))
    parser.add_argument("--path", dest="path")
    parser.add_argument("--kind", dest="kind", default="")
    parser.add_argument("--tier", dest="tier", default="")
    parser.add_argument("--strict", action="store_true",
                        help="treat advice as blocking (for an unattended run)")
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        rules = load_rules(Path(__file__).resolve().parent)
        if args.mode == "check":
            if not args.path:
                raise Refused("check needs --path naming the document to read")
            payload, code = run_check(rules, args)
        elif args.mode == "template":
            if not args.kind:
                raise Refused("template needs --kind naming the document to emit")
            payload, code = run_template(rules, args)
        elif args.mode == "guidance":
            payload, code = run_guidance(rules, args)
        else:
            payload, code = run_rules(rules, args)
        return emit(payload, code)
    except Refused as refusal:
        missing = refusal.message.startswith("no document at")
        return emit({"mode": args.mode, "error": "refused", "message": refusal.message,
                     "candidates": refusal.candidates},
                    EXIT_NOT_FOUND if missing else EXIT_REFUSED)
    except json.JSONDecodeError as broken:
        return emit({"mode": args.mode, "error": "internal",
                     "message": "the standard is not valid JSON: %s" % broken}, EXIT_INTERNAL)
    except OSError as unreadable:
        return emit({"mode": args.mode, "error": "internal",
                     "message": "cannot read the document: %s" % unreadable}, EXIT_INTERNAL)


if __name__ == "__main__":
    sys.exit(main())
