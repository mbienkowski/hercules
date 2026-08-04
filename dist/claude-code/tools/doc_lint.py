"""Check a Hercules delivery document against the standard, and emit the template it should follow.

The rules live in `doc_rules.json` beside this file, never in prose: a rule an agent is merely told
to follow is a suggestion it may paraphrase, while the same rule here is a finding with a line
number and an exit code. That is the § Executable over wishful principle applied to documents.

This tool is READ-ONLY by declaration. It writes nothing, so a failed check can never leave a
half-written document or a torn state file; the caller persists the verdict through
`state_patch.py`, which already owns atomic writes. Every path prints one JSON object on stdout,
including refusals, so the caller never parses prose. Unclassified errors resolve to EXIT_INTERNAL
and change nothing — it fails closed.

Severity governs blocking, not detection: structural rules are errors because a missing section is
unambiguous, while style rules are warnings because a banned-phrase list is routed around by
synonyms and would otherwise train authors to write past the checker rather than write better.
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
_PRONOUNS = ("it ", "this ", "they ", "these ", "those ", "there ")


class Refused(Exception):
    """A precondition rejected the run before any checking happened. Carries the scripted message
    the caller relays verbatim, per § Failure moments — a stop names the next action."""

    def __init__(self, message: str, candidates=None):
        super().__init__(message)
        self.message = message
        self.candidates = candidates or []


def load_rules(script_dir: Path) -> dict:
    """The catalogue, read from beside this script so the shipped copy is always self-contained."""
    path = script_dir / _RULES_FILE
    if not path.exists():
        raise Refused("the rule catalogue is missing at %s — reinstall the plugin" % path)
    return json.loads(path.read_text(encoding="utf-8"))


# ── document model ──────────────────────────────────────────────────────────────────────────────


class Section:
    """One `##` section: its heading, the lines under it, and where it starts."""

    def __init__(self, name: str, line_no: int):
        self.name = name
        self.line_no = line_no
        self.lines = []

    def body(self):
        """Content lines, with blank lines and sub-headings dropped."""
        return [ln for ln in self.lines if ln.strip() and not ln.lstrip().startswith("#")]

    def text(self) -> str:
        return "\n".join(self.lines)


class Document:
    """A parsed delivery document. Fenced blocks are tracked separately because they are examples,
    and a rule that reads an example as prose reports the example rather than the document."""

    def __init__(self, path: Path, text: str):
        self.path = path
        self.raw = text
        self.lines = text.splitlines()
        self.sections = []
        self.headings = []
        self.fenced_line_count = 0
        self.header_fields = {}
        self._parse()

    def _parse(self) -> None:
        current = None
        in_fence = False
        seen_heading = False
        for index, line in enumerate(self.lines, start=1):
            stripped = line.strip()
            if stripped.startswith("```"):
                in_fence = not in_fence
                if current is not None:
                    current.lines.append(line)
                continue
            if in_fence:
                self.fenced_line_count += 1
                if current is not None:
                    current.lines.append(line)
                continue
            if stripped.startswith("#"):
                depth = len(stripped) - len(stripped.lstrip("#"))
                self.headings.append((depth, stripped.lstrip("#").strip(), index))
                seen_heading = True
                if depth == 2:
                    current = Section(stripped.lstrip("#").strip(), index)
                    self.sections.append(current)
                    continue
            if not seen_heading and ":" in stripped and not stripped.startswith("-"):
                key, _, value = stripped.partition(":")
                if key and " " not in key.strip():
                    self.header_fields[key.strip().lower()] = value.strip()
            if current is not None:
                current.lines.append(line)

    def section(self, name: str):
        for section in self.sections:
            if section.name.lower() == name.lower():
                return section
        return None

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


# ── findings ────────────────────────────────────────────────────────────────────────────────────


class Findings:
    """Collected violations, each carrying the fix its rule declares."""

    def __init__(self, catalogue):
        self.by_id = {rule["id"]: rule for rule in catalogue}
        self.items = []

    def add(self, rule_id: str, message: str, line: int = 0, section: str = "") -> None:
        rule = self.by_id.get(rule_id)
        if rule is None:
            raise Refused("rule %s is not in the catalogue" % rule_id)
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
        errors = len([item for item in self.items if item["severity"] == "error"])
        return {"error": errors, "warn": len(self.items) - errors}


# ── checks ──────────────────────────────────────────────────────────────────────────────────────


def tier_index(rules: dict, tier: str) -> int:
    if tier not in rules["tiers"]:
        raise Refused("unknown tier %r — expected one of %s" % (tier, ", ".join(rules["tiers"])))
    return rules["tiers"].index(tier)


def required_sections(rules: dict, kind: dict, tier: str):
    """Sections the tier obliges. `never` means the section is allowed but never demanded."""
    at = tier_index(rules, tier)
    out = []
    for section in kind["sections"]:
        needed = section["required_from"]
        if needed != "never" and rules["tiers"].index(needed) <= at:
            out.append(section)
    return out


def check_structure(doc: Document, rules: dict, kind: dict, tier: str, found: Findings) -> None:
    known = {section["name"].lower(): section for section in kind["sections"]}
    order = [section["name"].lower() for section in kind["sections"]]

    for section in required_sections(rules, kind, tier):
        if doc.section(section["name"]) is None:
            found.add("DOC101", "'%s' is required at tier %s — %s"
                      % (section["name"], tier, section["mandate"]))

    present = []
    for section in doc.sections:
        if section.name.lower() not in known:
            found.add("DOC106", "'%s' is not a section this standard defines" % section.name,
                      section.line_no, section.name)
            continue
        present.append((order.index(section.name.lower()), section))

    ranks = [rank for rank, _ in present]
    if ranks != sorted(ranks):
        for position, (rank, section) in enumerate(present):
            if position and rank < present[position - 1][0]:
                found.add("DOC102", "'%s' appears after '%s'" % (section.name, present[position - 1][1].name),
                          section.line_no, section.name)

    for depth, heading, line_no in doc.headings:
        if depth > rules["style_limits"]["max_heading_depth"]:
            found.add("DOC105", "heading '%s' is at depth %d" % (heading, depth), line_no)


def check_emptiness(doc: Document, rules: dict, kind: dict, tier: str, found: Findings) -> None:
    allowed_empty = {name.lower() for name in rules["meaningful_when_empty"]}
    required = {section["name"].lower(): section for section in required_sections(rules, kind, tier)}
    for section in doc.sections:
        spec = required.get(section.name.lower())
        if spec is None:
            continue
        body = section.body()
        if not body and section.name.lower() not in allowed_empty:
            found.add("DOC104", "'%s' has no content" % section.name, section.line_no, section.name)
            continue
        if len(body) < spec.get("min_items", 1) and section.name.lower() not in allowed_empty:
            found.add("DOC104", "'%s' carries %d lines, below the %d this tier expects"
                      % (section.name, len(body), spec["min_items"]), section.line_no, section.name)

    for section in doc.sections:
        if section.name.lower() in allowed_empty:
            continue
        body = section.body()
        if not body:
            continue
        if not _has_referent(" ".join(body)) and len(" ".join(body).split()) < 15:
            found.add("DOC604", "'%s' says nothing checkable" % section.name,
                      section.line_no, section.name)
        first = body[0].lstrip("-*# ").strip().lower()
        heading_words = set(re.findall(r"[a-z]+", section.name.lower()))
        first_words = set(re.findall(r"[a-z]+", first))
        if first_words and first_words <= heading_words | _FILLER_WORDS:
            found.add("DOC605", "'%s' opens by restating its own heading" % section.name,
                      section.line_no, section.name)


_FILLER_WORDS = {"this", "the", "a", "an", "section", "describes", "of", "is", "are", "for",
                 "that", "which", "and", "it", "in", "to", "we", "here", "lists", "covers"}


def _has_referent(text: str) -> bool:
    """A bullet earns its place by naming something: an identifier, a path, a number, a proper noun."""
    if re.search(r"\d", text):
        return True
    if re.search(r"`[^`]+`", text):
        return True
    if re.search(r"[A-Za-z0-9_-]+/[A-Za-z0-9_./-]+", text):
        return True
    return bool(re.search(r"\b[A-Z][A-Za-z0-9]{2,}\b", text))


def _fenced_ranges(section: Section):
    ranges = []
    in_fence = False
    for offset, line in enumerate(section.lines):
        if line.strip().startswith("```"):
            in_fence = not in_fence
        ranges.append(in_fence or line.strip().startswith("```"))
    return ranges


def check_style(doc: Document, rules: dict, kind: dict, found: Findings) -> None:
    limits = rules["style_limits"]
    by_name = {section["name"].lower(): section for section in kind["sections"]}
    banned = [phrase.lower() for phrase in rules["banned_phrases"]]

    for section in doc.sections:
        spec = by_name.get(section.name.lower())
        if spec is None:
            continue
        fenced = _fenced_ranges(section)
        for offset, line in enumerate(section.lines):
            if fenced[offset] or not line.strip():
                continue
            line_no = section.line_no + offset + 1
            stripped = line.strip()
            is_bullet = stripped.startswith(("- ", "* "))
            is_table = stripped.startswith("|")
            is_heading = stripped.startswith("#")

            if spec["style"] in ("bullets", "scenarios") and not (is_bullet or is_table or is_heading):
                found.add("DOC201", "'%s' takes bullets, not prose" % section.name, line_no, section.name)
            if spec["style"] == "table" and not (is_table or is_heading or is_bullet):
                found.add("DOC201", "'%s' takes a table" % section.name, line_no, section.name)

            if is_bullet:
                words = len(stripped.split())
                if words > limits["max_bullet_words"]:
                    found.add("DOC203", "bullet runs to %d words" % words, line_no, section.name)
                body = stripped[2:].lstrip("*_ ").lower()
                if body.startswith(_PRONOUNS):
                    found.add("DOC205", "bullet opens with a pronoun", line_no, section.name)

            lowered = stripped.lower()
            for phrase in banned:
                if re.search(r"(?<![a-z])" + re.escape(phrase) + r"(?![a-z])", lowered):
                    found.add("DOC202", "uses %r" % phrase, line_no, section.name)
                    break

    if doc.fenced_line_count > limits["max_fenced_lines"]:
        found.add("DOC203", "fenced examples run to %d lines, over the %d limit"
                  % (doc.fenced_line_count, limits["max_fenced_lines"]))


def check_modality(doc: Document, rules: dict, found: Findings) -> None:
    """Bullets drop the subject and the modal a sentence carries, so a bullet-only style can raise
    ambiguity while every shape rule reports green. In the sections that state obligations, the
    modal is put back."""
    modals = [re.compile(pattern) for pattern in rules["modal_patterns"]]
    for name in rules["normative_sections"]:
        section = doc.section(name)
        if section is None:
            continue
        fenced = _fenced_ranges(section)
        for offset, line in enumerate(section.lines):
            if fenced[offset]:
                continue
            stripped = line.strip()
            if not stripped.startswith(("- ", "* ")):
                continue
            if not any(modal.search(stripped) for modal in modals):
                found.add("DOC208", "states no obligation: %r" % stripped[:70],
                          section.line_no + offset + 1, section.name)


def check_placeholders(doc: Document, rules: dict, found: Findings) -> None:
    allowed_empty = {name.lower() for name in rules["meaningful_when_empty"]}
    for section in doc.sections:
        if section.name.lower() in allowed_empty:
            continue
        fenced = _fenced_ranges(section)
        for offset, line in enumerate(section.lines):
            if fenced[offset]:
                continue
            for token in rules["placeholders"]:
                if token.lower() in line.lower():
                    found.add("DOC103", "contains %r" % token,
                              section.line_no + offset + 1, section.name)
                    break


def check_business_containment(doc: Document, rules: dict, kind: dict, found: Findings) -> None:
    """Technical vocabulary is legal in exactly one section, and only as a suggestion."""
    allowed = {section["name"].lower() for section in kind["sections"]
               if section.get("allows_implementation_tokens")}
    patterns = [re.compile(pattern) for pattern in rules["implementation_token_patterns"]]
    shapes = [re.compile(pattern) for pattern in rules["identifier_shape_patterns"]]
    mandates = [re.compile(pattern, re.IGNORECASE) for pattern in rules["mandate_patterns"]]

    for section in doc.sections:
        fenced = _fenced_ranges(section)
        for offset, line in enumerate(section.lines):
            if fenced[offset] or not line.strip():
                continue
            line_no = section.line_no + offset + 1
            for mandate in mandates:
                if mandate.search(line):
                    found.add("DOC206", "reads as a technical mandate: %r" % line.strip()[:70],
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
            for shape in shapes:
                match = shape.search(line)
                if match:
                    found.add("DOC209", "%r is shaped like an identifier" % match.group(0)[:40],
                              line_no, section.name)
                    break

    suggestions = None
    for section in kind["sections"]:
        if section.get("hedged"):
            suggestions = doc.section(section["name"])
            break
    if suggestions is None:
        return
    hedges = [word.lower() for word in rules["hedge_words"]]
    for offset, line in enumerate(suggestions.lines):
        stripped = line.strip()
        if not stripped.startswith(("- ", "* ")):
            continue
        if not any(hedge in stripped.lower() for hedge in hedges):
            found.add("DOC207", "suggestion states no alternative: %r" % stripped[:70],
                      suggestions.line_no + offset + 1, suggestions.name)
    if rules["suggestion_closing_sentence"] not in suggestions.text():
        found.add("DOC207", "the section does not close with its fixed sentence",
                  suggestions.line_no, suggestions.name)


def check_scenarios(doc: Document, rules: dict, kind: dict, tier: str, found: Findings) -> None:
    section_spec = None
    for section in kind["sections"]:
        if section["style"] == "scenarios":
            section_spec = section
            break
    if section_spec is None:
        return
    section = doc.section(section_spec["name"])
    if section is None:
        return

    pattern = re.compile(rules["scenario_line"]["pattern"])
    claims = re.compile(rules["scenario_line"]["claim_pattern"])
    max_words = rules["scenario_line"]["max_words"]
    budget = kind["budgets"][tier]["scenarios"]
    seen = set()
    counts = {"M": 0, "N": 0, "C": 0}
    flow = None
    per_flow = {}
    fenced = _fenced_ranges(section)

    for offset, line in enumerate(section.lines):
        if fenced[offset]:
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
        # A bullet that does not open with an identifier is ordinary prose — a flow's story line
        # lives here too, and reading it as a broken scenario would refuse legitimate content.
        if claims.match(normalised) is None:
            continue
        match = pattern.match(normalised)
        if match is None:
            found.add("DOC302", "not a scenario line: %r" % stripped[:70], line_no, section.name)
            continue
        klass, number, _, _ = match.groups()
        identifier = klass + number
        if identifier in seen:
            found.add("DOC304", "identifier %s is used twice" % identifier, line_no, section.name)
        seen.add(identifier)
        counts[klass] += 1
        if flow is not None:
            per_flow[flow][klass] += 1
        if len(stripped.split()) > max_words + 4:
            found.add("DOC203", "scenario %s runs to %d words" % (identifier, len(stripped.split())),
                      line_no, section.name)

    for name, tally in per_flow.items():
        if tally["waived"]:
            continue
        missing = [label for label in ("M", "N") if tally[label] == 0]
        if missing:
            found.add("DOC301", "flow '%s' has no %s scenario"
                      % (name, "/".join("main" if m == "M" else "negative" for m in missing)),
                      tally["line"], section.name)

    if counts["N"] < counts["M"]:
        found.add("DOC303", "%d main scenarios against %d negative" % (counts["M"], counts["N"]),
                  section.line_no, section.name)
    for klass, allowed in budget.items():
        if counts[klass] > allowed:
            found.add("DOC305", "%d %s scenarios, over the %d this tier allows"
                      % (counts[klass], rules["scenario_classes"][klass], allowed),
                      section.line_no, section.name)


def check_budgets(doc: Document, rules: dict, kind: dict, tier: str, found: Findings) -> None:
    exempt = [section["name"] for section in kind["sections"]
              if section.get("exempt_from_word_budget")]
    words = doc.prose_words(exempt)
    budget = kind["budgets"][tier]
    if words < budget["words_floor"]:
        found.add("DOC601", "%d words, under the %d floor for tier %s"
                  % (words, budget["words_floor"], tier))
    elif words > budget["words_hard"]:
        found.add("DOC602", "%d words, over the %d hard cap for tier %s"
                  % (words, budget["words_hard"], tier))
    elif words > budget["words_soft"]:
        found.add("DOC603", "%d words, over the %d target for tier %s"
                  % (words, budget["words_soft"], tier))


def check_tables(doc: Document, rules: dict, found: Findings) -> None:
    risks = doc.section("Risks & mitigations")
    if risks is not None:
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

    decisions = doc.section("Decision record")
    if decisions is None:
        return
    for offset, line in enumerate(decisions.lines):
        stripped = line.strip()
        if not stripped.startswith("|") or set(stripped) <= set("|- :"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 6 or cells[0].lower() in ("decision", ""):
            continue
        revisit = cells[5]
        if revisit and not re.search(r"\d", revisit) and not re.search(
                r"\b(?:when|after|once|exceeds|drops|reaches)\b", revisit, re.IGNORECASE):
            found.add("DOC403", "revisit-when %r names no observable condition" % revisit[:40],
                      decisions.line_no + offset + 1, decisions.name)


def check_naming(doc: Document, rules: dict, found: Findings) -> None:
    """The swap test: a port named after its vendor is a design that cannot change its vendor."""
    vendors = rules["lexicons"]["vendor"]
    markers = rules["lexicons"]["port_markers"]
    adapters = rules["lexicons"]["adapter_paths"]
    weak = rules["lexicons"]["weak_noun"]

    for section in doc.sections:
        fenced = _fenced_ranges(section)
        for offset, line in enumerate(section.lines):
            if fenced[offset]:
                continue
            line_no = section.line_no + offset + 1
            lowered = line.lower()
            if any(path in lowered for path in adapters):
                continue
            for identifier in re.findall(r"`([A-Za-z_][A-Za-z0-9_.]*)`", line):
                lowered_id = identifier.lower()
                if any(vendor in lowered_id for vendor in vendors) and \
                        any(marker.lower() in lowered_id for marker in markers):
                    found.add("DOC501", "%r names its vendor" % identifier, line_no, section.name)
                    continue
                for word in weak:
                    if lowered_id.endswith(word) and len(lowered_id) > len(word):
                        found.add("DOC502", "%r ends in %r" % (identifier, word), line_no, section.name)
                        break


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
        raise Refused("no document at %s" % path, candidates=[])
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
    check_style(doc, rules, kind, found)
    check_modality(doc, rules, found)
    check_scenarios(doc, rules, kind, tier, found)
    check_budgets(doc, rules, kind, tier, found)
    if kind_name == "business-requirements":
        check_business_containment(doc, rules, kind, found)
    else:
        check_tables(doc, rules, found)
        check_naming(doc, rules, found)

    counts = found.counts()
    blocking = counts["error"] or (args.strict and counts["warn"])
    payload = {
        "mode": "check",
        "path": str(path),
        "kind": kind_name,
        "tier": tier,
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "rules_version": rules["rules_version"],
        "clean": not blocking,
        "counts": counts,
        "findings": sorted(found.items, key=lambda item: (item["severity"] != "error", item["line"])),
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
        if section["name"] not in wanted:
            continue
        lines.append("## " + section["name"])
        lines.append("<!-- " + section["mandate"] + " -->")
        lines.append("")
    body = "\n".join(lines).rstrip() + "\n"
    return {"mode": "template", "kind": kind_name, "tier": tier,
            "rules_version": rules["rules_version"], "template": body}, EXIT_OK


def run_rules(rules: dict, args) -> tuple:
    catalogue = rules["rules"]
    if args.kind:
        resolve_kind(rules, Path("x"), args.kind)
    return {"mode": "rules", "rules_version": rules["rules_version"],
            "kinds": sorted(rules["kinds"]), "rules": catalogue}, EXIT_OK


def emit(payload: dict, code: int) -> int:
    sys.stdout.write(json.dumps(payload, indent=2, sort_keys=False) + "\n")
    return code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="doc_lint",
        description="Check a Hercules delivery document, or emit the template it should follow.")
    parser.add_argument("mode", choices=("check", "template", "rules"))
    parser.add_argument("--path", dest="path")
    parser.add_argument("--kind", dest="kind", default="")
    parser.add_argument("--tier", dest="tier", default="")
    parser.add_argument("--strict", action="store_true",
                        help="treat warnings as blocking")
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
                     "message": "the rule catalogue is not valid JSON: %s" % broken}, EXIT_INTERNAL)
    except OSError as unreadable:
        return emit({"mode": args.mode, "error": "internal",
                     "message": "cannot read the document: %s" % unreadable}, EXIT_INTERNAL)


if __name__ == "__main__":
    sys.exit(main())
