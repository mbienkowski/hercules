"""Judge a drafted code-of-conduct (CoC) before anyone reads it — the gate behind the generator's
draft step. It takes the drafting agent's envelope on stdin and answers whether every rule is tagged,
names a check, and cites evidence the envelope actually contains, plus what the draft costs against
the directive budget. It also reviews a code-of-conduct written elsewhere, reporting which of its
citations have rotted. Three properties are not negotiable. Gating a draft is a PURE function of its
input — no path is opened and no subprocess runs, so a hostile repository has no surface where it
matters most. Reviewing an existing document reads that file and asks git for the repository's file
list, and NOTHING ELSE: a cited path is resolved by membership in that list, never against the
filesystem, so a document written by someone else can never probe for what exists outside the
repository. And it fails CLOSED — an unclassified error is a refusal, never a pass.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
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
GIT_TIMEOUT_SECONDS = 30

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


# ── The emitted file's shape ──────────────────────────────────────────────────────────────────

# The lead block: the rules never violated, first, because that is where a long context is read best.
LEAD_HEADING = "Non-negotiables"

SECTION = re.compile(r"^##\s+(.*\S)\s*$")
BULLET = re.compile(r"^\s*[-*]\s+(.*)$")
TAGGED = re.compile(r"\*\*(MUST|SHOULD)\*\*")
ANNOTATION = re.compile(r"^\s*\*\*(WHY|DON'T|DO):\*\*")

# A fragment pins a rule to the local idiom at a glance; past this it is a program to be read.
MAX_FRAGMENT_LINES = 3


def _sections(markdown: str) -> list:
    """The file as `(heading, first_line_number, lines)`, with anything before the first heading
    kept as a preamble so a rule stranded above one is still seen."""
    found, heading, start, body = [], None, 1, []
    for number, line in enumerate(markdown.splitlines(), 1):
        match = SECTION.match(line)
        if not match:
            body.append((number, line))
            continue
        if heading is not None or body:
            found.append((heading, start, body))
        heading, start, body = match.group(1), number, []
    found.append((heading, start, body))
    return [entry for entry in found if entry[0] is not None or entry[2]]


def _fragment_lines(text: str) -> int:
    """How many lines a DO/DON'T fragment stands for, counting the escape a single-line example
    uses to show a multi-line shape."""
    return text.count("\\n") + text.count("\n") + 1


def lint_markdown(markdown) -> dict:
    if not isinstance(markdown, str) or not markdown.strip():
        raise Internal("`markdown` must be the emitted document as a string.")
    sections = _sections(markdown)
    headed = [entry for entry in sections if entry[0]]
    findings, rules = [], 0

    if not headed or LEAD_HEADING.lower() not in headed[0][0].lower():
        findings.append({
            "rule": "lead_missing", "line": headed[0][1] if headed else 1,
            "message": f"The file must open with a `## {LEAD_HEADING} (MUST)` block. The rules never "
                       "violated go first, where a long document is read most reliably."})

    for index, (heading, start, body) in enumerate(headed):
        is_lead = index == 0 and heading and LEAD_HEADING.lower() in heading.lower()
        tagged_here, whys, donts, dos = 0, [], [], []
        for number, line in body:
            annotation = ANNOTATION.match(line)
            if annotation:
                kind = annotation.group(1)
                (whys if kind == "WHY" else donts if kind == "DON'T" else dos).append((number, line))
                if kind in ("DON'T", "DO") and _fragment_lines(line) > MAX_FRAGMENT_LINES:
                    findings.append({
                        "rule": "example_too_long", "line": number,
                        "message": f"The {kind} fragment in '{heading}' runs past "
                                   f"{MAX_FRAGMENT_LINES} lines. Cut it to the shape it is "
                                   "demonstrating."})
                continue
            bullet = BULLET.match(line)
            if not bullet:
                continue
            rules += 1
            if TAGGED.search(bullet.group(1)):
                tagged_here += 1
            else:
                findings.append({
                    "rule": "bullet_untagged", "line": number,
                    "message": f"A rule in '{heading}' is tagged neither MUST nor SHOULD, so a "
                               "reader cannot tell what enforces it."})
        if tagged_here and not whys and not is_lead:
            findings.append({
                "rule": "group_unexplained", "line": start,
                "message": f"The group '{heading}' states rules with no WHY line. Without one a rule "
                           "is obeyed literally and generalised wrongly."})
        if len(whys) > 1:
            findings.append({
                "rule": "why_repeated", "line": whys[1][0],
                "message": f"The group '{heading}' carries {len(whys)} WHY lines; annotations are "
                           "capped at one of each per group."})
        if len(donts) != len(dos):
            findings.append({
                "rule": "example_unpaired", "line": (donts or dos)[0][0],
                "message": f"The group '{heading}' has {len(donts)} DON'T and {len(dos)} DO lines. "
                           "An example shows both sides or neither."})
        if len(donts) > 1 or len(dos) > 1:
            findings.append({
                "rule": "example_repeated", "line": (donts + dos)[1][0],
                "message": f"The group '{heading}' carries more than one example pair; annotations "
                           "are capped at one of each per group."})

    return {"findings": findings, "sections": len(headed), "rules": rules}


# ── Reading a code-of-conduct written elsewhere ───────────────────────────────────────────────

BACKTICKED = re.compile(r"`([^`\n]+)`")
PATH_SHAPED = re.compile(r"^[\w.@/-]+$")
PATH_SUFFIXES = (".md", ".py", ".json", ".ts", ".tsx", ".mts", ".js", ".yml", ".yaml", ".toml",
                 ".txt", ".cfg", ".ini", ".go", ".rs", ".java", ".rb", ".sh")

# Names that look like citations and are not. Measured on a real document, these three classes were
# every single false alarm: a deliberately-wrong name in an example, a dependency's entry point, and
# a placeholder standing in for whatever the reader substitutes.
EXAMPLE_LINE = re.compile(r"^\s*\*\*(DON'T|DO):\*\*")
PLACEHOLDER = re.compile(r"[<>{}]")


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
            "-c", "core.pager=cat"] + list(args)
    environment = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0")
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


def review_existing(path: str, root: str) -> dict:
    text = read_document(path)
    paths = head_paths(root)
    targets = make_targets(root, paths)
    seen, entries = set(), []
    for number, line in enumerate(text.splitlines(), 1):
        # A name inside an example pair is chosen to be wrong; treating it as a citation was the
        # largest source of false alarms when this was measured against a real document.
        in_example = bool(EXAMPLE_LINE.match(line))
        for match in BACKTICKED.finditer(line):
            token = match.group(1)
            if token in seen:
                continue
            seen.add(token)
            kind, state, resolved = classify_token(token, paths, targets)
            if in_example and state == "dangling":
                kind, state = "example", "unparsed"
            entries.append({"token": token[:200], "kind": kind, "state": state,
                            "resolved": resolved[:200], "line": number})
    entries.sort(key=lambda entry: (entry["state"], entry["kind"], entry["token"]))
    tally = {}
    for entry in entries:
        tally[entry["state"]] = tally.get(entry["state"], 0) + 1
    checked = tally.get("verified", 0) + tally.get("dangling", 0)
    return {
        "findings": [],  # advice, never a refusal: this document is not ours to reject
        "entries": entries,
        "tally": {"verified": 0, "dangling": 0, "unparsed": 0, **tally},
        "tokens": len(entries),
        "checked": checked,
        "message": f"{checked} of {len(entries)} backticked references could be checked mechanically; "
                   "the rest are concepts, commands or examples. Nothing was edited.",
    }


# ── Command surface ───────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="coc_audit", add_help=False)
    parser.add_argument("mode", choices=["draft", "lint", "existing"])
    parser.add_argument("--contract", type=int, required=True)
    parser.add_argument("--file")
    parser.add_argument("--root")
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
                                f"draft|lint --contract {CONTRACT_VERSION}"},
                    "draft", EXIT_INTERNAL)
    if args.contract != CONTRACT_VERSION:
        return emit({"error": "contract",
                     "message": f"This tool speaks version {CONTRACT_VERSION}; the skill asked for "
                                f"{args.contract}. Update the plugin, then run this again."},
                    args.mode, EXIT_CONTRACT)
    try:
        if args.mode == "existing":
            if not args.file or not args.root:
                raise Internal("`existing` needs --file <code-of-conduct> and --root <repository>.")
            report = review_existing(args.file, args.root)
        else:
            envelope = read_envelope(stdin if stdin is not None else sys.stdin)
            report = (lint_markdown(envelope.get("markdown")) if args.mode == "lint"
                      else judge(envelope))
    except Refused as exc:
        return emit({"error": "refused", "rule": exc.rule, "message": exc.message,
                     "findings": [finding(exc.rule, "", exc.message)]}, args.mode, EXIT_REFUSED)
    except Internal as exc:
        return emit({"error": "internal", "message": exc.message}, args.mode, EXIT_INTERNAL)
    except Exception as exc:  # fail closed: an unclassified error is never a pass
        return emit({"error": "internal", "message": f"Nothing was judged. {exc}"},
                    args.mode, EXIT_INTERNAL)
    if report["findings"] or report.get("band") == "ceiling":
        return emit(report, args.mode, EXIT_REFUSED)
    return emit(report, args.mode, EXIT_OK)


if __name__ == "__main__":  # pragma: no cover - exercised via main() in tests
    sys.exit(main())
