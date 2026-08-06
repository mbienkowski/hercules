"""Report what is wrong with a code-of-conduct (CoC) document, so it can be fixed. It answers one
question — *what would a reader trip over here?* — in two halves that a document fails independently:
its SHAPE (orientation first, every section summarised before it rules, every rule tagged from the
four-tier vocabulary, the reasons gathered last) and its CITATIONS (a path or make target it names
that the repository no longer has, including the paths the draft's observations were justified by).

It reports; it never edits. The fix belongs to whoever can weigh whether a rule is now wrong or its
path merely moved, and a best-effort parse of prose is not the ground to rewrite prose from. So this
runs twice in a normal flow: once over the draft before it is written, and again over the file on
disk afterwards, because the only document that matters is the one that landed.

Deliberately findings, never a score. A number invites being optimised toward, and the thing worth
optimising is the list.

Reading a document is all it does with the filesystem. A cited path resolves by membership in the
repository's file list — asked of git, never of the filesystem — so a document written by someone
else cannot probe for what exists outside the repository. It fails CLOSED: an unclassified error is
a refusal, never a clean bill of health.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

# Bumped only when the report shape or the argument surface breaks; the skill passes the version it
# was written against, and a mismatch refuses rather than being read against the wrong grammar.
# Version 2: the owner's document grammar — orientation, summaries, four plain-text tiers, Why last.
CONTRACT_VERSION = 2

EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_CONTRACT = 2
EXIT_INTERNAL = 4

# A document larger than this is a defect or an attack, never a code-of-conduct.
MAX_INPUT_BYTES = 1024 * 1024
GIT_TIMEOUT_SECONDS = 30


class Refused(Exception):
    """A rule of this tool rejected the target. Carries the identifier and the scripted message."""

    def __init__(self, rule: str, message: str):
        super().__init__(message)
        self.rule = rule
        self.message = message


class Internal(Exception):
    """The document could not be read or understood. Never a reason to report it as clean."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


# ── The emitted file's shape ──────────────────────────────────────────────────────────────────

SECTION = re.compile(r"^##\s+(.*\S)\s*$")
SUBSECTION = re.compile(r"^###\s+(.*\S)\s*$")
BULLET = re.compile(r"^[-*]\s+(.*)$")
# Four postures, each heading a numbered run of its own: MUST is gated, SHOULD is convention, AVOID
# names a tempting path with a better one, NEVER_DO is a hard stop. Grouping beats repeating the tag
# on every line — the reader maps the posture once and then reads requirements.
TIER_HEADER = re.compile(r"^(MUST|SHOULD|AVOID|NEVER_DO):\s*$")
TIER_SHAPED = re.compile(r"^([A-Z][A-Z0-9 _-]{1,24}):\s*$")
DIRECTIVE = re.compile(r"^(\d+)\.\s+(\S.*)$")
FENCE = re.compile(r"^\s*(?:```|~~~)")
BOLD = re.compile(r"\*\*")
# The reasons live together at the end, after every requirement: a reader wants the rule first and
# the argument only when they need to argue with one.
WHY_HEADING = re.compile(r"\bwhy\b", re.IGNORECASE)
INDENTED = re.compile(r"^(?:\t| {2,})")

# Orientation is a paragraph, not a chapter; a code block is read at a glance, not maintained as a
# program. The group cap is the real readability gate: past it a reader cannot tell what lives
# where, and the answer is a sub-heading that names the concern, never a longer list.
MAX_ORIENTATION_LINES = 15
MAX_CODE_LINES = 24
MAX_GROUP_DIRECTIVES = 8

# Literals that are true the day they are written and stale the day the repository moves. A measured
# tally justifies a rule in the ENVELOPE — the document names the mechanism and the directory, never
# today's count. Declared thresholds survive on purpose: "80%" and ">=3.9" are the rule's own
# content, so round percentages and two-part version floors pass; a dated count ("17 files today"),
# an exhaustive tally ("10 of 10"), a full x.y.z version, or a decimal percentage ("98.3%" — the
# shape of a measurement, where a declared threshold is round) are each the fossil of a scan.
SNAPSHOT_LITERALS = (
    ("dated count", re.compile(r"\b\d+\s+\w+\s+today\b", re.IGNORECASE)),
    ("tally", re.compile(r"\b\d+\s+of\s+\d+\b")),
    ("version literal", re.compile(r"\b\d+\.\d+\.\d+\b")),
    ("measured share", re.compile(r"\b\d+\.\d+\s*%")),
)

# Claims about the WHOLE repository, which one counterexample falsifies and which no path check can
# confirm. Measured on real output: every accuracy defect a blind review found took one of these
# shapes — "the only X anywhere", "on every host", "nowhere else", "all seven". The author saw a few
# files and generalised; the citation resolved, so the gate passed a sentence that was false.
# A rule's own imperative is not caught: "Never edit dist/ by hand" carries no scope quantifier.
# Exclusivity is dangerous wherever it appears: nothing in this tool can prove an absence, and the
# author who writes it has usually read a handful of files.
UNIVERSAL_EXCLUSIVITY = (
    ("an exclusivity claim",
     re.compile(r"\bthe only\b[^.]{0,100}?\b(?:anywhere|in the (?:repo|repository|codebase|"
                r"project|tree|suite))\b", re.IGNORECASE)),
    # Scoped to the repository-wide forms. Bare "and nothing else" is English for "only that",
    # usually about a closed list the document itself defines, and flagging it trains the reader
    # to ignore this rule — which costs more than the few real cases it would catch.
    ("an exclusivity claim",
     re.compile(r"\b(?:anywhere|nowhere)\s+else\b", re.IGNORECASE)),
)

# A sweep across every instance of something is a fine REQUIREMENT ("declare it in every recipe")
# and a claim nobody can verify when it appears as the EVIDENCE. So these bind only inside a
# `Check:` — where the sentence promises the reader a way to confirm the rule.
UNIVERSAL_AS_EVIDENCE = (
    ("a distributive claim",
     re.compile(r"\b(?:on|in|for|across|by)\s+every\s+\w+", re.IGNORECASE)),
    ("a distributive claim",
     re.compile(r"\bone\b[^.]{0,60}?\bper\s+\w+", re.IGNORECASE)),
    ("a spelled-out total",
     re.compile(r"\ball\s+(?:two|three|four|five|six|seven|eight|nine|ten)\s+\w+", re.IGNORECASE)),
)

# A `Check:` earns its name by naming something a reader can run or open — a path, a command, a job.
# Where nothing enforces the rule, saying so is the honest check; silence dressed as one is not.
CHECK_LINE = re.compile(r"^\s*Check:\s*(.+)$")
CHECK_RUNNABLE = re.compile(r"`[^`]+`")
# Inline code quotes the repository the way a fenced block does: `**kwargs` is Python, not bold
# markup, and a version inside backticks is the config's own content, not the document's claim.
INLINE_CODE = re.compile(r"`[^`\n]*`")


def _mask_inline_code(line: str) -> str:
    """The line with every inline-code span blanked, length preserved so finding lines stay
    right."""
    return INLINE_CODE.sub(lambda span: " " * len(span.group(0)), line)
CHECK_ADMITS_NOTHING = re.compile(
    r"\b(?:no\b[^.]{0,40}\b(?:tool|gate|test|check|scanner|hook|job)\b|not enforced|"
    r"nothing enforces|review is the enforcement|by convention only|unenforced)\b", re.IGNORECASE)


def _fenced_lines(markdown: str) -> set:
    """Every line inside a code fence, the fences themselves included. A code block is quoted
    material — its markup is syntax, its numbers are the file's, and its `##` is a comment, not a
    heading — so every prose rule below consults this set before firing."""
    inside, open_fence = set(), False
    for number, line in enumerate(markdown.splitlines(), 1):
        if FENCE.match(line):
            inside.add(number)
            open_fence = not open_fence
            continue
        if open_fence:
            inside.add(number)
    return inside


def _blocks(markdown: str, fenced: set) -> tuple:
    """The file as `(preamble, blocks)`, one block per heading of either level. A section carrying
    its own rules and a section carrying sub-headings are then the same shape to every check —
    which is what lets the group cap be counted per LEAF, where a reader actually reads."""
    preamble, blocks, current = [], [], None
    for number, line in enumerate(markdown.splitlines(), 1):
        if number not in fenced:
            match = SECTION.match(line) or SUBSECTION.match(line)
            if match:
                current = {"heading": match.group(1), "level": 2 if line.startswith("## ") else 3,
                           "start": number, "lines": []}
                blocks.append(current)
                continue
        (current["lines"] if current is not None else preamble).append((number, line))
    return preamble, blocks


def _orientation_findings(preamble_lines: list) -> list:
    """The document must open by orienting: what this repository is and what the loop is, in prose,
    before any heading. A file that opens cold with rules orients nobody; one that opens with an
    essay is a section wearing no heading."""
    prose = [(number, line) for number, line in preamble_lines if line.strip()]
    if not prose:
        return [{"rule": "orientation_missing", "line": 1,
                 "message": "The file opens with no orientation. Say in a few plain lines what this "
                            "repository is and what the edit-verify loop is, before any heading."}]
    if len(prose) > MAX_ORIENTATION_LINES:
        return [{"rule": "orientation_oversized", "line": prose[MAX_ORIENTATION_LINES][0],
                 "message": f"The orientation runs past {MAX_ORIENTATION_LINES} lines. Orientation "
                            "is a paragraph; anything longer is a section and needs its heading."}]
    return []


def _why_findings(blocks: list) -> list:
    """One Why section, last. Rules first and reasons last is the agreed reading order: a reader
    wants the requirement, then the argument — and every reason gathered in one place is what lets
    a directive stay about its own subject."""
    sections = [entry for entry in blocks if entry["level"] == 2]
    why = [index for index, entry in enumerate(sections)
           if WHY_HEADING.search(entry["heading"])]
    if not why:
        return [{"rule": "why_missing", "line": sections[-1]["start"] if sections else 1,
                 "message": "The document closes with no Why section. The reasons live together at "
                            "the end — without them every rule is obeyed literally."}]
    return [{"rule": "why_misplaced", "line": sections[index]["start"],
             "message": f"The Why section '{sections[index]['heading']}' is not the last section. "
                        "Rules first, reasons last — a Why in the middle splits both."}
            for index in why if index != len(sections) - 1]


def _code_findings(block: dict, fenced: set) -> list:
    """Code blocks are invited — a fragment of the real thing teaches a rule as prose cannot — and
    bounded, because past a screenful it is a program being maintained inside a document."""
    findings, run, opened = [], 0, None
    for number, line in block["lines"]:
        if number not in fenced:
            continue
        if FENCE.match(line):
            if opened is None:
                opened, run = number, 0
            else:
                opened = None
            continue
        run += 1
        if run == MAX_CODE_LINES + 1:
            findings.append({
                "rule": "code_block_too_long", "line": opened or number,
                "message": f"A code block in '{block['heading']}' runs past {MAX_CODE_LINES} "
                           "lines. Show the shape the rule turns on, not the whole file."})
    return findings


def _block_findings(block: dict, fenced: set, is_why: bool) -> tuple:
    """One leaf's findings and its directive count. The grammar: a summary in prose, then a tier
    header owning a numbered run beneath it. A directive may run as many lines as it needs — a rule
    worth stating is worth explaining — so only its FIRST line carries the number, and everything
    indented under it is that directive's body."""
    findings = list(_code_findings(block, fenced))
    tier, directives, numbering, summary_seen, first_rule = None, 0, 0, False, None
    for number, line in block["lines"]:
        if number in fenced or not line.strip():
            continue
        if BOLD.search(_mask_inline_code(line)):
            findings.append({
                "rule": "emphasis_used", "line": number,
                "message": f"A line in '{block['heading']}' uses bold markup. The format is plain "
                           "text: markup is spent from every agent's context on every task, and a "
                           "tiered directive already carries its own emphasis."})
        if is_why:
            continue  # rationale: numbered or bulleted, it is argument rather than requirement
        header = TIER_HEADER.match(line)
        if header:
            if tier is not None and numbering == 0:
                findings.append({
                    "rule": "tier_empty", "line": number,
                    "message": f"The {tier} run in '{block['heading']}' lists no directive. A tier "
                               "header with nothing under it says a posture and requires nothing."})
            tier, numbering = header.group(1), 0
            if first_rule is None:
                first_rule = number
            continue
        shaped = TIER_SHAPED.match(line)
        if shaped and not header:
            findings.append({
                "rule": "tier_unknown", "line": number,
                "message": f"'{shaped.group(1)}' is not a tier. The vocabulary is MUST, SHOULD, "
                           "AVOID and NEVER_DO — one of those four, or it is prose, not a header."})
            continue
        directive = DIRECTIVE.match(line)
        if directive:
            directives += 1
            numbering += 1
            if first_rule is None:
                first_rule = number
            if tier is None:
                findings.append({
                    "rule": "directive_untiered", "line": number,
                    "message": f"A directive in '{block['heading']}' sits under no tier header. "
                               "Open the run with MUST:, SHOULD:, AVOID: or NEVER_DO:."})
            elif int(directive.group(1)) != numbering:
                findings.append({
                    "rule": "directive_misnumbered", "line": number,
                    "message": f"Directive '{directive.group(1)}.' is number {numbering} of the "
                               f"{tier} run in '{block['heading']}'. A run counts from 1 without "
                               "gaps, or its numbers stop meaning anything."})
            continue
        if INDENTED.match(line):
            continue  # a directive's own body: explanation, a check, an example
        bullet = BULLET.match(line)
        if bullet:
            findings.append({
                "rule": "bullet_in_rules", "line": number,
                "message": f"A bullet in '{block['heading']}' states a rule. Directives are a "
                           "numbered run under their tier header, so a reader can cite one."})
            continue
        if first_rule is None:
            summary_seen = True  # prose arrived before any rule: the summary exists
    if tier is not None and numbering == 0:
        findings.append({
            "rule": "tier_empty", "line": first_rule or block["start"],
            "message": f"The {tier} run in '{block['heading']}' lists no directive."})
    if not summary_seen and not is_why:
        findings.append({
            "rule": "group_unsummarized", "line": block["start"],
            "message": f"'{block['heading']}' opens without a summary. One to three sentences of "
                       "intent are what a rule is generalised from; without them it is obeyed "
                       "literally and applied wrongly to the case the list never named."})
    return findings, directives


def _group_size_findings(blocks: list, counts: dict) -> list:
    """The readability gate. A leaf is where a reader reads, so a `##` that carries sub-headings is
    measured by each child and never by their sum. Past the cap the answer is a sub-heading naming
    the concern — never a longer list, which is how a document stops being navigable."""
    has_children, previous_section = set(), None
    for entry in blocks:
        if entry["level"] == 2:
            previous_section = id(entry)
        elif previous_section is not None:
            has_children.add(previous_section)
    findings = []
    for entry in blocks:
        if entry["level"] == 2 and id(entry) in has_children:
            continue
        count = counts.get(id(entry), 0)
        if count > MAX_GROUP_DIRECTIVES:
            findings.append({
                "rule": "group_oversized", "line": entry["start"],
                "message": f"'{entry['heading']}' carries {count} directives, past the "
                           f"{MAX_GROUP_DIRECTIVES} a reader can hold. Split it into sub-headings "
                           "that name the concerns — the boundaries are already in the list."})
    return findings


def _snapshot_findings(markdown: str, fenced: set) -> list:
    """Every literal in the document's PROSE that a normal week of work falsifies. The scan
    measures and the envelope records; a count that leaks into a rule reads as present truth long
    after it stopped being one. A code block is exempt: it quotes the file, and the file's own
    numbers are what makes the quotation worth showing."""
    found = []
    for number, line in enumerate(markdown.splitlines(), 1):
        if number in fenced:
            continue
        for kind, pattern in SNAPSHOT_LITERALS:
            match = pattern.search(_mask_inline_code(line))
            if match:
                found.append({
                    "rule": "snapshot_literal", "line": number,
                    "message": f"'{match.group(0)}' is a {kind} — true the day it was written, "
                               "stale the day the repository moves. Name the mechanism and the "
                               "directory; the number belongs in the envelope."})
    return found


def _universal_findings(markdown: str, fenced: set) -> list:
    """Sentences that claim something about the whole repository. A path check proves existence and
    can never prove an absence, so a universal is the one claim shape that clears every gate and is
    still wrong. Requirements may sweep — evidence may not."""
    found = []
    for number, line in enumerate(markdown.splitlines(), 1):
        if number in fenced:
            continue
        patterns = UNIVERSAL_EXCLUSIVITY
        check = CHECK_LINE.match(line)
        # A sweep is only unverifiable when it IS the evidence. Where the Check also names
        # something runnable, the universal describes that thing's scope and the reader can go
        # and look — so it binds only on a Check that offers nothing else to open.
        if check and not CHECK_RUNNABLE.search(check.group(1)):
            patterns = UNIVERSAL_EXCLUSIVITY + UNIVERSAL_AS_EVIDENCE
        for kind, pattern in patterns:
            match = pattern.search(line)
            if match:
                found.append({
                    "rule": "unhedged_universal", "line": number,
                    "message": f"'{match.group(0).strip()}' is {kind} offered as evidence. One "
                               "counterexample falsifies it and no citation can confirm it — name "
                               "what you actually verified, or drop the quantifier."})
                break
    return found


def _check_findings(markdown: str, fenced: set) -> list:
    """A `Check:` that names nothing runnable and does not admit that nothing enforces the rule.
    Prose in that position reads as verification and provides none."""
    found = []
    for number, line in enumerate(markdown.splitlines(), 1):
        if number in fenced:
            continue
        match = CHECK_LINE.match(line)
        if not match:
            continue
        body = match.group(1)
        if CHECK_RUNNABLE.search(body) or CHECK_ADMITS_NOTHING.search(body):
            continue
        found.append({
            "rule": "check_unfalsifiable", "line": number,
            "message": "This Check names nothing a reader can run or open. Name the file, command "
                       "or job in backticks — or say plainly that nothing enforces the rule."})
    return found


def _family_findings(markdown: str, families) -> list:
    """Every extension point the scan found is either taught or knowingly left out. A family the
    document never names is the shape of a whole way this repository grows going undocumented —
    the reader adds one more of that kind by guessing."""
    if families is None:
        return []
    if not isinstance(families, list) or not all(isinstance(f, str) for f in families):
        raise Internal("`families` must be a list of repository-relative directory strings.")
    return [{"rule": "family_uncovered", "line": 0,
             "message": f"`{family}` is a directory this repository grows by, and the document "
                        "never names it. Teach how one more is added, or record that it is "
                        "deliberately out of scope."}
            for family in sorted({f.strip() for f in families if f.strip()})
            if family not in markdown]


def lint_markdown(markdown, families=None) -> dict:
    if not isinstance(markdown, str) or not markdown.strip():
        raise Internal("`markdown` must be the emitted document as a string.")
    fenced = _fenced_lines(markdown)
    preamble, blocks = _blocks(markdown, fenced)

    findings = _orientation_findings(preamble)
    findings.extend(_why_findings(blocks))
    findings.extend(_snapshot_findings(markdown, fenced))
    findings.extend(_universal_findings(markdown, fenced))
    findings.extend(_check_findings(markdown, fenced))
    findings.extend(_family_findings(markdown, families))
    counts, rules = {}, 0
    for block in blocks:
        block_findings, block_rules = _block_findings(
            block, fenced, bool(WHY_HEADING.search(block["heading"])))
        findings.extend(block_findings)
        counts[id(block)] = block_rules
        rules += block_rules
    findings.extend(_group_size_findings(blocks, counts))
    findings.sort(key=lambda entry: (entry["line"], entry["rule"]))
    return {"findings": findings, "rules": rules,
            "sections": sum(1 for b in blocks if b["level"] == 2),
            "subsections": sum(1 for b in blocks if b["level"] == 3),
            "groups": [{"heading": b["heading"], "level": b["level"], "line": b["start"],
                        "directives": counts.get(id(b), 0)} for b in blocks]}


# ── Reading a code-of-conduct written elsewhere ───────────────────────────────────────────────

BACKTICKED = re.compile(r"`([^`\n]+)`")
PATH_SHAPED = re.compile(r"^[\w.@/-]+$")
PATH_SUFFIXES = (".md", ".py", ".json", ".ts", ".tsx", ".mts", ".js", ".yml", ".yaml", ".toml",
                 ".txt", ".cfg", ".ini", ".go", ".rs", ".java", ".rb", ".sh")

# Names that look like citations and are not. Measured on a real document, these classes were the
# false alarms: a dependency's entry point, a placeholder standing in for whatever the reader
# substitutes, and a name inside a contrastive example, which is CHOSEN to be wrong.
#
# That last one binds in update mode above all. This tool reads documents it did not write, in
# formats it does not set, and a `DON'T:` line naming a deliberately-bad path is not a rotted
# citation — reporting it teaches the reader to stop reading the findings. Worked examples in the
# emitted format are unaffected: they demonstrate inside a fenced block with real paths, and those
# stay checked.
PLACEHOLDER = re.compile(r"[<>{}]")
EXAMPLE_LINE = re.compile(r"^\s*(?:\*\*)?(?:DON'T|DO|BAD|GOOD)(?:\*\*)?:", re.IGNORECASE)


def read_document(path: str) -> str:
    try:
        with open(path, "rb") as handle:
            blob = handle.read(MAX_INPUT_BYTES + 1)
    except OSError as exc:
        raise Refused("unreadable_document",
                      f"That code-of-conduct could not be read: {exc}. Name the file to review, or "
                      "let the generator create one.") from exc
    if len(blob) > MAX_INPUT_BYTES:
        raise Refused("document_too_large",
                      f"That document exceeds {MAX_INPUT_BYTES} bytes; nothing was reviewed.")
    return blob.decode("utf-8", "replace")


def git(root: str, args: list) -> bytes:
    """Run one read-only git command against `root`, with the repository's own quoting and
    filesystem-monitor settings overridden — both are set by the thing being read."""
    argv = ["git", "-C", str(root), "-c", "core.quotePath=false", "-c", "core.fsmonitor=",
            "-c", "core.pager=cat", "-c", "log.showSignature=false"] + list(args)
    # Inherited GIT_* variables are dropped, not passed through: GIT_DIR alone overrides `-C`
    # discovery, silently checking citations against a different repository than `--root` names.
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith("GIT_")}
    environment.update(GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0")
    try:
        done = subprocess.run(argv, capture_output=True, timeout=GIT_TIMEOUT_SECONDS,
                              env=environment)
    except (OSError, subprocess.SubprocessError) as exc:
        raise Refused("not_a_repository",
                      f"Could not read that repository's file list. {exc}") from exc
    if done.returncode != 0:
        raise Refused("not_a_repository",
                      "That directory is not a readable git repository, so no citation in the "
                      "document can be checked against it.")
    return done.stdout


def head_paths(root: str) -> set:
    """Every path the repository has at HEAD. Membership is the ONLY way a cited path is resolved:
    asking the filesystem would let a document somebody else wrote probe for files outside the
    repository, and would answer for paths that exist but are not part of the project."""
    found = {chunk.decode("utf-8", "replace")
             for chunk in git(root, ["ls-files", "-z"]).split(b"\0") if chunk}
    if found:
        return found
    # A bare repository has no index for `ls-files` to read; without this it reports no files, and
    # then every citation in the document reads as dangling.
    return {chunk.decode("utf-8", "replace")
            for chunk in git(root, ["ls-tree", "-r", "-z", "--name-only", "HEAD"]).split(b"\0")
            if chunk}


def make_targets(root: str, paths: set) -> set:
    if "Makefile" not in paths:
        return set()
    try:
        with open(os.path.join(str(root), "Makefile"), "rb") as handle:
            text = handle.read(MAX_INPUT_BYTES).decode("utf-8", "replace")
    except OSError:
        return set()
    return {m.group(1) for m in re.finditer(r"^([A-Za-z0-9_.-]+):", text, flags=re.M)}


def classify_token(token: str, paths: set, targets: set) -> tuple:
    """One backticked token as `(kind, state, resolved)`. Anything not confidently a path or a make
    target is `unparsed` — about two thirds of a real document — because a scanner that guessed at
    prose would bury the few citations that had actually rotted."""
    text = token.strip()
    if not text or PLACEHOLDER.search(text):
        return "placeholder", "unparsed", text
    if text.startswith("make "):
        parts = text.split()
        target = parts[1] if len(parts) > 1 else ""
        return "make-target", ("verified" if target in targets else "dangling"), target
    bare = re.sub(r":\d+(-\d+)?$", "", text.split(" ")[0].rstrip(",.;:"))
    if not any(character.isalnum() for character in bare):
        # Prose quotes separators as themselves — "a `/` nests the ref" names a character, not a file.
        return "other", "unparsed", text
    looks_like_path = "/" in bare or bare.endswith(PATH_SUFFIXES)
    if not looks_like_path or not PATH_SHAPED.match(bare):
        return "other", "unparsed", text
    if bare.startswith("/") or ".." in bare.split("/"):
        # Absolute or climbing paths are dangling by construction: nothing outside the repository
        # is ever resolved, so the question of whether it exists is never asked.
        return "path", "dangling", bare
    candidate = re.sub(r"^\./", "", bare).rstrip("/")
    if candidate in paths:
        return "path", "verified", candidate
    if any(p.startswith(candidate + "/") for p in paths):
        return "path-prefix", "verified", candidate
    if not candidate.endswith(PATH_SUFFIXES):
        # A dependency's entry point (`js-tiktoken/lite`) has a slash and no file extension.
        return "package-specifier", "unparsed", candidate
    matches = [p for p in paths if p.endswith("/" + candidate)]
    if matches:
        return "path-suffix", "verified", sorted(matches)[0]
    return "path", "dangling", candidate


def review_citations(text: str, root: str) -> dict:
    """Which of the document's backticked references the repository still has. A dangling one is a
    finding for a person to weigh — the rule may be right and the path merely moved — so it is
    reported at its line rather than acted on."""
    paths = head_paths(root)
    targets = make_targets(root, paths)
    seen, entries = set(), []
    for number, line in enumerate(text.splitlines(), 1):
        in_example = bool(EXAMPLE_LINE.match(line))
        for match in BACKTICKED.finditer(line):
            token = match.group(1)
            # Deduplicated per shield, not per token: an example line's occurrence is unparsed by
            # design, and letting it claim the token would hide a genuine citation of the same
            # missing path later in the document.
            if (token, in_example) in seen:
                continue
            seen.add((token, in_example))
            kind, state, resolved = classify_token(token, paths, targets)
            if in_example and state == "dangling":
                kind, state = "example", "unparsed"
            entries.append({"token": token[:200], "kind": kind, "state": state,
                            "resolved": resolved[:200], "line": number})
    entries.sort(key=lambda entry: (entry["state"], entry["kind"], entry["token"]))
    tally = {}
    for entry in entries:
        tally[entry["state"]] = tally.get(entry["state"], 0) + 1
    resolvable = tally.get("verified", 0) + tally.get("dangling", 0)
    findings = [
        {"rule": "citation_dangling", "line": entry["line"],
         "message": f"`{entry['token']}` is cited but the repository has no such "
                    f"{'make target' if entry['kind'] == 'make-target' else 'path'}. Confirm whether "
                    "the rule is wrong or the target simply moved — this is a question, not an edit."}
        for entry in entries if entry["state"] == "dangling"
    ]
    return {
        "findings": findings,
        "entries": entries,
        "tally": {"verified": 0, "dangling": 0, "unparsed": 0, **tally},
        "tokens": len(entries),
        "citations_resolvable": resolvable,
        "citations_message":
            f"{resolvable} of {len(entries)} backticked references could be checked mechanically; "
            "the rest are concepts, commands or examples. Nothing was edited.",
    }


def verify_declared_paths(declared, paths: set) -> dict:
    """The observation paths the draft's evidence was justified by, held against the file list. The
    draft gate is pure and can only judge an observation's shape; this is where its path meets the
    repository — by membership, exactly as every other citation, so a rule justified by a file that
    is not there is caught before the document is written."""
    if not isinstance(declared, list) or not all(isinstance(p, str) for p in declared):
        raise Internal("`paths` must be a list of repository-relative path strings.")
    entries, findings = [], []
    for declared_path in sorted({p.strip().rstrip("/") for p in declared if p.strip()}):
        known = (declared_path in paths
                 or any(p.startswith(declared_path + "/") for p in paths))
        entries.append({"path": declared_path, "state": "verified" if known else "dangling"})
        if not known:
            findings.append({
                "rule": "observation_dangling", "line": 0,
                "message": f"An observation was justified by `{declared_path}`, which the "
                           "repository does not have. A rule standing on it stands on nothing — "
                           "re-read the code or drop the rule."})
    return {"declared_paths": entries, "findings": findings}


# ── Command surface ───────────────────────────────────────────────────────────────────────────

def read_stdin_envelope(stream) -> dict:
    """A draft submitted before it exists on disk, as `{"contract": 2, "markdown": "…"}`, with the
    optional `paths` its observations were justified by."""
    try:
        text = stream.read(MAX_INPUT_BYTES + 1)
    except Exception as exc:
        raise Internal(f"The draft could not be read. {exc}") from exc
    if text is None or not str(text).strip():
        raise Internal("No document was submitted. Send `--file <path>` or the draft on stdin.")
    if len(text) > MAX_INPUT_BYTES:
        raise Internal(f"The draft exceeds {MAX_INPUT_BYTES} bytes. Nothing was checked.")
    try:
        envelope = json.loads(text)
    except ValueError as exc:
        raise Internal(f"The draft is not valid JSON. {exc}") from exc
    if not isinstance(envelope, dict):
        raise Internal("The draft must be one JSON object carrying `markdown`.")
    return envelope


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="coc_lint", add_help=False)
    parser.add_argument("--contract", type=int, required=True)
    parser.add_argument("--file")
    parser.add_argument("--root")
    return parser


def emit(payload: dict, code: int) -> int:
    """Print the report as one JSON object and return the exit code. Every path emits, refusals
    included, so the skill parses one shape and never has to guess."""
    print(json.dumps(dict({"contract": CONTRACT_VERSION}, **payload), indent=2))
    return code


def review(markdown: str, file_path, root, declared=None, families=None) -> dict:
    """Both halves of the answer. Shape binds a draft and only informs about a document that already
    exists: an existing bullet is never retro-fitted with a tag or a reason, so listing its shape as
    something to fix would invite exactly the edit the additions-only rule forbids. A rotted citation
    is a finding either way — it is wrong no matter who wrote it. Declared observation paths are
    verified only when a repository is in reach; skipping them silently would read as verification."""
    if declared is not None and not root:
        raise Internal("`paths` were declared but no `--root` was given, so nothing could hold "
                       "them against the repository. Pass --root <repo>; skipping them silently "
                       "would read as verification.")
    report = lint_markdown(markdown, families)
    if file_path:
        report["shape_notes"] = report.pop("findings")
        report["findings"] = []
    if root:
        citations = review_citations(markdown, root)
        report["findings"] = report["findings"] + citations.pop("findings")
        report.update(citations)
        if declared is not None:
            observations = verify_declared_paths(declared, head_paths(root))
            report["findings"] = report["findings"] + observations.pop("findings")
            report.update(observations)
    report["checked"] = "shape+citations" if root else "shape"
    report["shape_binds"] = not file_path
    return report


def main(argv=None, home=None, stdin=None) -> int:
    """Read, report, and turn every failure into a scripted refusal — nothing escapes as a
    traceback. `home` is accepted for a uniform tool signature and unused: this tool keeps no
    record."""
    try:
        args = build_parser().parse_args(list(argv) if argv is not None else None)
    except SystemExit:
        return emit({"error": "usage",
                     "message": "The arguments were not understood. Expected: "
                                f"--contract {CONTRACT_VERSION} [--file <coc>] [--root <repo>]"},
                    EXIT_INTERNAL)
    if args.contract != CONTRACT_VERSION:
        return emit({"error": "contract",
                     "message": f"This tool speaks version {CONTRACT_VERSION}; the skill asked for "
                                f"{args.contract}. Update the plugin, then run this again."},
                    EXIT_CONTRACT)
    try:
        if args.file:
            markdown, declared, families = read_document(args.file), None, None
        else:
            envelope = read_stdin_envelope(stdin if stdin is not None else sys.stdin)
            markdown = envelope.get("markdown")
            declared, families = envelope.get("paths"), envelope.get("families")
        report = review(markdown, args.file, args.root, declared, families)
    except Refused as exc:
        return emit({"error": "refused", "rule": exc.rule, "message": exc.message}, EXIT_REFUSED)
    except Internal as exc:
        return emit({"error": "internal", "message": exc.message}, EXIT_INTERNAL)
    except Exception as exc:  # fail closed: an unread document is never a clean one
        return emit({"error": "internal", "message": f"Nothing was checked. {exc}"}, EXIT_INTERNAL)
    return emit(report, EXIT_REFUSED if report["findings"] else EXIT_OK)


if __name__ == "__main__":  # pragma: no cover - exercised via main() in tests
    sys.exit(main())
