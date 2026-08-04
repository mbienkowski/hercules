"""Report what is wrong with a code-of-conduct (CoC) document, so it can be fixed. It answers one
question — *what would a reader trip over here?* — in two halves that a document fails independently:
its SHAPE (non-negotiables first, every rule tagged, one reason per group, examples paired and short)
and its CITATIONS (a path or make target it names that the repository no longer has).

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
CONTRACT_VERSION = 1

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


def review_citations(text: str, root: str) -> dict:
    """Which of the document's backticked references the repository still has. A dangling one is a
    finding for a person to weigh — the rule may be right and the path merely moved — so it is
    reported at its line rather than acted on."""
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


# ── Command surface ───────────────────────────────────────────────────────────────────────────

def read_stdin_markdown(stream) -> str:
    """A draft submitted before it exists on disk, as `{"contract": 1, "markdown": "…"}`."""
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
    return envelope.get("markdown")


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


def review(markdown: str, file_path, root) -> dict:
    """Both halves of the answer. Shape binds a draft and only informs about a document that already
    exists: an existing bullet is never retro-fitted with a tag or a reason, so listing its shape as
    something to fix would invite exactly the edit the additions-only rule forbids. A rotted citation
    is a finding either way — it is wrong no matter who wrote it."""
    report = lint_markdown(markdown)
    if file_path:
        report["shape_notes"] = report.pop("findings")
        report["findings"] = []
    if root:
        citations = review_citations(markdown, root)
        report["findings"] = report["findings"] + citations.pop("findings")
        report.update(citations)
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
        markdown = (read_document(args.file) if args.file
                    else read_stdin_markdown(stdin if stdin is not None else sys.stdin))
        report = review(markdown, args.file, args.root)
    except Refused as exc:
        return emit({"error": "refused", "rule": exc.rule, "message": exc.message}, EXIT_REFUSED)
    except Internal as exc:
        return emit({"error": "internal", "message": exc.message}, EXIT_INTERNAL)
    except Exception as exc:  # fail closed: an unread document is never a clean one
        return emit({"error": "internal", "message": f"Nothing was checked. {exc}"}, EXIT_INTERNAL)
    return emit(report, EXIT_REFUSED if report["findings"] else EXIT_OK)


if __name__ == "__main__":  # pragma: no cover - exercised via main() in tests
    sys.exit(main())
