"""Read a repository and report what it can be shown to do — the evidence behind the code-of-conduct
(CoC) generator's scan step. It answers three questions a draft needs and an agent should not guess:
what this project declares about itself, how its history says it is worked on, and which of its code
is still being worked on at all.

Three properties are not negotiable. It opens NO FILE — it asks git and nothing else, so the whole
class of worktree escapes (a tracked symlink pointing outside the checkout, a backslash name that is
a separator on one platform) cannot arise here at all; the extractor that does read files carries
those guards instead. It treats the repository as UNTRUSTED: paths arrive NUL-delimited so a crafted
filename cannot fabricate one, git runs with the repository's own quoting settings overridden, every
emitted string is made inert, and no author identity is emitted. And it fails CLOSED — an
unreadable repository is a refusal, never a report of an empty one, because a wrong answer shaped like
a finding is indistinguishable downstream from the truth.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys

# Bumped only when the document shape or the argument surface breaks; the skill passes the version it
# was written against, and a mismatch refuses rather than being read against the wrong grammar.
# Version 2: the architecture facts — families, import graph, chokepoints, entrypoints, consumers.
CONTRACT_VERSION = 2

EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_CONTRACT = 2
EXIT_INTERNAL = 4

# Bounds. A repository can be arbitrarily large or arbitrarily hostile; every one of these degrades
# to an explicit unknown rather than to a stall or a silent truncation.
MAX_COMMITS = 4000
MAX_PATHS = 60_000
MAX_SUBJECT_CHARS = 200
# A path may legitimately be long; the cap is a flood guard, not a formatting rule.
MAX_EMITTED_CHARS = 400
GIT_TIMEOUT_SECONDS = 60

TOP_FILES = 50


# Trees a build produces. They can out-commit every hand-written module in a repository, so they are
# tagged rather than ranked; the skill confirms with the user rather than assuming.
GENERATED_DIR_HINTS = ("dist/", "build/", "vendor/", "node_modules/", "target/", ".next/",
                       "out/", "generated/", "__generated__/", "__pycache__/")
GENERATED_FILE_HINTS = ()


# Probes are GLOBS, not filenames: a real project spelled its lint config `.eslintrc.yml`, which an
# exact-name list missed entirely.
FILE_PROBES = {
    "cfg.format.editorconfig": ([".editorconfig"], "EditorConfig present"),
    "cfg.ci.github": ([".github/workflows/*"], "GitHub Actions workflows present"),
    "cfg.ci.gitlab": ([".gitlab-ci.yml"], "GitLab CI configuration present"),
    "cfg.build.makefile": (["Makefile"], "Makefile present"),
    "cfg.container.dockerfile": (["Dockerfile", "*/Dockerfile"], "Dockerfile present"),
    "cfg.review.codeowners": (["CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS"],
                              "CODEOWNERS present"),
    "cfg.deps.autoupdate": ([".github/dependabot.yml", "renovate.json", ".renovaterc*"],
                            "Automated dependency updates configured"),
    "cfg.hooks.precommit": ([".pre-commit-config.yaml", ".githooks", ".husky"],
                            "Pre-commit hooks present"),
    "cfg.docs.contributing": (["CONTRIBUTING.md", ".github/CONTRIBUTING.md"],
                              "Contributing guide present"),
    "cfg.docs.security": (["SECURITY.md", ".github/SECURITY.md"], "Security policy present"),
    "cfg.license": (["LICENSE*", "COPYING"], "License file present"),
}






# ── Architecture: what the valuable rules stand on ────────────────────────────────────────────
# The quality-bearing facts of a repository are architectural — the engine everything renders
# through, the directory that grows by one-more-file-of-a-kind — and none of them is a config probe.
# Everything here is derived by regex over import lines and file lists: deterministic, bounded, and
# honest about being INFERRED, never measured. A rule citing these can see that.

# Measured against Hercules's own tree: 24 real families (>=4 files) exist, and a cap of 12 dropped
# src/content/commands — the extension point a user actually invokes — with no signal that anything
# was cut. 24 clears that with headroom without being tuned to this one repository's exact count;
# a repository with more still gets a truncation signal rather than a silently shorter list.
MIN_FAMILY_FILES = 4
MAX_FAMILIES = 32

# No suffix allowlist. A family is a directory several files share a suffix in — and WHICH suffix
# is exactly the thing this tool must not have an opinion about. A list would be one more catalogue
# of languages to fall behind, and it would miss the extension points that matter most in
# repositories built out of things nobody thought to enumerate.
MIN_SUFFIX_CHARS, MAX_SUFFIX_CHARS = 2, 12




CONVENTIONAL_SUBJECT = re.compile(
    r"^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([^)]+\))?!?: ")
TICKET_REFERENCE = re.compile(r"(#\d+|[A-Z]{2,}-\d+)")
TOOL_SECTION = re.compile(r"^\[tool\.([A-Za-z0-9_-]+)")


class Refused(Exception):
    """A rule of this tool rejected the target. Carries the identifier and the scripted message."""

    def __init__(self, rule: str, message: str):
        super().__init__(message)
        self.rule = rule
        self.message = message


class Internal(Exception):
    """The repository could not be read. Never a reason to report it as empty."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


# ── Talking to git ────────────────────────────────────────────────────────────────────────────

def git(root, args, binary=False):
    """Run one git command against `root`. The repository's own configuration is overridden, not
    trusted: `core.quotePath` decides how paths are printed, and it is set by the thing being read."""
    argv = ["git", "-C", str(root), "-c", "core.quotePath=false", "-c", "core.fsmonitor=",
            "-c", "core.pager=cat", "-c", "log.showSignature=false"] + list(args)
    # Inherited GIT_* variables are dropped, not passed through: GIT_DIR alone overrides `-C`
    # discovery, silently answering about a different repository than the one `--root` names.
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith("GIT_")}
    environment.update(GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0")
    try:
        done = subprocess.run(argv, capture_output=True, timeout=GIT_TIMEOUT_SECONDS,
                              env=environment)
    except (OSError, subprocess.SubprocessError) as exc:
        raise Internal(f"Could not run git in that directory. {exc}") from exc
    if done.returncode != 0:
        raise Refused("not_a_repository",
                      "That directory is not a readable git repository, so there is no history to "
                      "scan. Re-run this inside the repository the code-of-conduct is for.")
    return done.stdout if binary else done.stdout.decode("utf-8", "replace")


def nul_paths(blob: bytes) -> list:
    """NUL-delimited git output as text. Splitting on newlines instead is what lets a filename
    containing one invent a second path."""
    return [chunk.decode("utf-8", "replace") for chunk in blob.split(b"\0") if chunk]


def head_files(root) -> tuple:
    """Every path at HEAD, which route found them, and which of them are SYMLINKS. `ls-files` reads
    the index, which a bare repository does not have — without the fallback a bare clone reports an
    empty repository.

    The mode is read here because a tracked name is chosen by the repository and must never decide
    what gets opened: a `package.json` that is really a link to a credentials file outside the
    checkout was read, and its values reached the emitted document. Links stay in the inventory —
    they are real entries a citation may resolve against — and are refused a read."""
    listing = nul_paths(git(root, ["ls-files", "-sz"], binary=True))
    if listing:
        files = []
        for entry in listing[:MAX_PATHS]:
            _, _, rest = entry.partition(" ")
            files.append(rest.split("\t", 1)[-1] if "\t" in rest else rest)
        return files, "worktree"
    files = nul_paths(git(root, ["ls-tree", "-r", "-z", "--name-only", "HEAD"], binary=True))
    if files:
        return files[:MAX_PATHS], "bare"
    raise Refused("empty_repository",
                  "That repository has no files at HEAD. There is nothing to draw standards from.")


# ── Classifying paths ─────────────────────────────────────────────────────────────────────────



def is_generated(path: str) -> bool:
    return path.endswith(GENERATED_FILE_HINTS) or any(h in path for h in GENERATED_DIR_HINTS)


def directory_of(path: str, depth: int) -> str:
    parts = path.split("/")
    if len(parts) <= 1:
        return "."
    return "/".join(parts[:depth]) if len(parts) > depth else "/".join(parts[:-1])


def clean_text(value: str, limit: int) -> str:
    """Repository-authored text, made safe to carry: control characters stripped and length capped,
    so a crafted subject cannot reshape the document or flood whatever reads it."""
    stripped = "".join(ch for ch in value if ch == " " or (ch.isprintable() and ch != "﻿"))
    return stripped[:limit].strip()


def fact(fact_id, claim, value, citations, confidence="inferred-high") -> dict:
    return {"id": fact_id, "claim": claim, "value": value, "confidence": confidence,
            "citations": citations}


# ── What the repository declares ──────────────────────────────────────────────────────────────

def probe_facts(files: list) -> tuple:
    """Facts from the presence of known configuration, with the probes tried alongside those that
    matched — otherwise a catalogue that has fallen behind an ecosystem looks like a repository
    that uses none of it."""
    found, matched = [], 0
    for fact_id in sorted(FILE_PROBES):
        globs, claim = FILE_PROBES[fact_id]
        hits = sorted({f for f in files for g in globs if fnmatch.fnmatch(f, g)})
        if not hits:
            continue
        matched += 1
        found.append(fact(fact_id, claim, hits[:6],
                          [{"kind": "file", "path": h} for h in hits[:3]]))
    return found, len(FILE_PROBES), matched








# ── What the history says ─────────────────────────────────────────────────────────────────────

def history_facts(root, commits: int) -> list:
    """Conventions the project follows without having written them down. The format string names
    only the subject: author and committer identities are personal data the standards never need."""
    raw = git(root, ["log", f"-n{commits}", "--no-merges", "--format=%s"])
    subjects = [clean_text(line, MAX_SUBJECT_CHARS) for line in raw.splitlines() if line.strip()]
    if not subjects:
        return []
    conventional = [s for s in subjects if CONVENTIONAL_SUBJECT.match(s)]
    share = len(conventional) / len(subjects)
    classification = ("conventional-commits" if share >= 0.8
                      else "mixed" if share >= 0.3 else "free-form")
    scopes = sorted({m.group(2)[1:-1] for m in
                     (CONVENTIONAL_SUBJECT.match(s) for s in conventional) if m and m.group(2)})
    merges = [line for line in
              git(root, ["log", f"-n{commits}", "--merges", "--format=%h"]).splitlines() if line]
    tags = [t for t in git(root, ["tag", "--list"]).splitlines() if t.strip()]
    semver = [t for t in tags if re.match(r"^v?\d+\.\d+\.\d+$", t.strip())]
    found = [
        fact("hist.commit.convention",
             f"Dominant commit-subject convention over the last {len(subjects)} commits",
             {"classification": classification,
              "conventional_share": round(share, 3),
              "scopes_seen": [clean_text(s, 40) for s in scopes[:12]],
              "ticket_reference_share": round(
                  sum(1 for s in subjects if TICKET_REFERENCE.search(s)) / len(subjects), 3)},
             [{"kind": "count", "pattern": "conventional-commit subject",
               "matched": len(conventional), "sampled": len(subjects)}],
             "inferred-high" if share >= 0.8 or share <= 0.1 else "inferred-medium"),
        fact("hist.merge.shape", f"Merge commits among the last {len(subjects)} commits",
             {"merge_commits": len(merges)},
             [{"kind": "count", "pattern": "merge commits", "matched": len(merges),
               "sampled": len(subjects)}]),
    ]
    if tags:
        found.append(fact("hist.release.tagging", "Release tagging scheme",
                          {"tags": len(tags), "semver_like": len(semver)},
                          [{"kind": "count", "pattern": "semantic-version tag",
                            "matched": len(semver), "sampled": len(tags)}]))
    return found


# ── Which code is alive ───────────────────────────────────────────────────────────────────────

def head_epoch(root) -> int:
    """The anchor every window is measured back from. The commit's own date, never the clock: the
    same commit must produce the same answer tomorrow."""
    try:
        return int(git(root, ["log", "-1", "--format=%ct"]).strip())
    except ValueError as exc:
        raise Refused("no_history",
                      "That repository has no commits, so there is no history to scan.") from exc


def touches(root, since_epoch: int, commits: int) -> list:
    """`(epoch, path)` for every file touch in the window, read NUL-delimited. Commit headers are
    wrapped in delimiters of their own so a header and a path can never be confused."""
    blob = git(root, ["log", f"-n{commits}", "--no-merges", f"--since={since_epoch}",
                      "--name-only", "-z", "--no-renames", "--format=%x01%ct%x02"], binary=True)
    found, epoch, expect_frame = [], None, False
    for chunk in blob.split(b"\0"):
        if not chunk:
            continue
        text = chunk.decode("utf-8", "replace")
        if text.startswith("\x01"):
            # A genuine header: git NUL-terminates the format output, so a header is always a
            # chunk of its own — and a crafted filename cannot open one, because \x01 sorts first
            # among a commit's paths, making any such name the commit's first path, and first
            # paths arrive newline-prefixed.
            header, _, _ = text[1:].partition("\x02")
            try:
                epoch = int(header.strip() or 0)
            except ValueError:
                epoch = None
            expect_frame = True
            continue
        if expect_frame:
            # git writes one newline between the format output and a commit's first path. Exactly
            # one: stripping more would fold a filename that itself begins with a newline onto the
            # name after it, letting a crafted twin inflate a real file's count.
            if text.startswith("\n"):
                text = text[1:]
            expect_frame = False
        if text and epoch is not None:
            found.append((epoch, text))
    return found


def liveness(root, files: list, months: float, recent_months: float, depth: int,
             commits: int) -> dict:
    anchor = head_epoch(root)
    long_since = anchor - int(months * 30.44 * 86400)
    recent_since = anchor - int(recent_months * 30.44 * 86400)
    at_head = set(files)

    long_counts, recent_counts, file_counts = {}, {}, {}
    ghosts = 0
    for epoch, path in touches(root, long_since, commits):
        if path not in at_head:
            # Its history is real and its file is gone; ranking it ranks code nobody can read.
            ghosts += 1
            continue
        where = directory_of(path, depth)
        long_counts[where] = long_counts.get(where, 0) + 1
        file_counts[path] = file_counts.get(path, 0) + 1
        if epoch >= recent_since:
            recent_counts[where] = recent_counts.get(where, 0) + 1

    files_per_directory, generated_per_directory = {}, {}
    for path in files:
        where = directory_of(path, depth)
        files_per_directory[where] = files_per_directory.get(where, 0) + 1
        if is_generated(path):
            generated_per_directory[where] = generated_per_directory.get(where, 0) + 1

    total_long = sum(long_counts.values()) or 1
    total_recent = sum(recent_counts.values()) or 1
    directories = []
    for where in sorted(files_per_directory):
        long_n = long_counts.get(where, 0)
        recent_n = recent_counts.get(where, 0)
        directories.append({
            "path": where,
            "touches": long_n,
            "recent_touches": recent_n,
            "share": round(long_n / total_long, 4),
            "recent_share": round(recent_n / total_recent, 4),
            "files_at_head": files_per_directory[where],
            "status": "alive" if recent_n else ("cooling" if long_n else "dormant"),
            "generated": generated_per_directory.get(where, 0) == files_per_directory[where],
        })
    directories.sort(key=lambda entry: (-entry["touches"], entry["path"]))

    ranked = sorted(file_counts, key=lambda path: (-file_counts[path], path))
    top = [{"path": path, "touches": file_counts[path]}
           for path in ranked if not is_generated(path)][:TOP_FILES]
    return {"months": months, "recent_months": recent_months,
            "directories": directories, "top_files": top,
            "ghost_touches_dropped": ghosts}


# ── Numbers a rule can cite ───────────────────────────────────────────────────────────────────









def code_families(files: list) -> tuple:
    """The extension points — the standard ways this repository grows — in both shapes that exist:
    a directory of same-suffixed FILES (`agents/*.md`: add one more file), and sibling DIRECTORIES
    each holding one same-named file (`skills/*/SKILL.md`: add one more directory). Missing the
    second shape hid a real extension point on the very repository this shipped from. Read from the
    file list alone, so it holds even where the sample was bounded. Returns `(families, truncated)`:
    silently dropping a family drops its worked example with it, so a cut list says it was cut."""
    file_groups, directory_groups = {}, {}
    for path in files:
        if is_generated(path) or "/" not in path:
            continue
        directory, name = path.rsplit("/", 1)
        dot = name.rfind(".")
        suffix = name[dot:] if dot > 0 else ""
        if MIN_SUFFIX_CHARS <= len(suffix) <= MAX_SUFFIX_CHARS:
            file_groups.setdefault((directory, suffix), []).append(path)
        # The item is the directory, identified by the file every sibling carries under the same
        # name. Scaffolding names (`__init__.py`, `conftest.py`) would make every package tree a
        # family, so they identify nothing.
        if "/" in directory and MIN_SUFFIX_CHARS <= len(suffix) <= MAX_SUFFIX_CHARS \
                and not name.startswith("_") and name != "conftest.py":
            parent, item = directory.rsplit("/", 1)
            directory_groups.setdefault((parent, name), {})[item] = path
    families = [{"path": directory, "unit": "file", "suffix": suffix, "files": len(members),
                 "examples": sorted(members)[:3]}
                for (directory, suffix), members in file_groups.items()
                if len(members) >= MIN_FAMILY_FILES]
    families.extend(
        {"path": parent, "unit": "directory", "suffix": "/" + name, "files": len(items),
         "examples": [items[key] for key in sorted(items)][:3]}
        for (parent, name), items in directory_groups.items()
        if len(items) >= MIN_FAMILY_FILES)
    families.sort(key=lambda entry: (-entry["files"], entry["path"], entry["suffix"]))
    return families[:MAX_FAMILIES], len(families) > MAX_FAMILIES
























# ── The document ──────────────────────────────────────────────────────────────────────────────

def scan(root, months: float, recent_months: float, depth: int, commits: int) -> dict:
    """What holds in ANY repository: what it declares by the presence of a file, how its history
    reads, which directories are still worked on, and which of them grow by one-more-of-a-kind.

    Nothing here parses a language. The catalogue that used to — import patterns, entrypoint
    markers, competing-idiom regexes, per-ecosystem manifest readers — was removed on purpose: a
    list of languages is incomplete by construction, and worse, it reported its own coverage as
    complete while missing the two commonest Python layouts. Architecture is derived instead by an
    extractor the agent writes for the repository in front of it, and arrives through `architecture`
    below, where it is validated rather than trusted."""
    files, root_kind = head_files(root)
    truncated = len(files) >= MAX_PATHS
    probes, attempted, matched = probe_facts(files)
    families, families_truncated = code_families(files)

    collected = {}
    for entry in probes + history_facts(root, commits):
        collected.setdefault(entry["id"], entry)
    if families:
        collected["arch.families"] = fact(
            "arch.families", "Directories that grow by adding one more of a kind", families,
            [{"kind": "file", "path": entry["examples"][0]} for entry in families[:3]])
    facts = sorted(collected.values(), key=lambda entry: entry["id"])

    alive = liveness(root, files, months, recent_months, depth, commits)
    unknowns = sorted(({"liveness.complete"} if truncated else set())
                      | ({"arch.families_truncated"} if families_truncated else set()))
    return {
        "schema_version": 3,
        "head": git(root, ["rev-parse", "HEAD"]).strip(),
        "root_kind": root_kind,
        "files_at_head": len(files),
        "probes_attempted": attempted,
        "probes_matched": matched,
        "facts": facts,
        "liveness": alive,
        "unknowns": unknowns,
        "truncated": truncated,
    }


# ── The architecture artifact ─────────────────────────────────────────────────────────────────
# The agent writes an extractor for whatever language is in front of it, runs it, and submits its
# output here. This tool never learns a language; it learns the SHAPE an answer must take, and
# refuses anything that does not take it. Every path is held against HEAD, so a claim about a file
# the repository does not have cannot enter the record — which is the whole reason the extractor's
# output is validated rather than believed.
ARCHITECTURE_SHAPE = {
    "areas": ("path", "role"),
    "edges": ("from", "to"),
    "chokepoints": ("path", "fan_in"),
    "entrypoints": ("path", "kind"),
    "conventions": ("concern", "sides"),
    "toolchain": ("name", "role", "evidence"),
}
# Which member of each entry names a repository path, and must therefore resolve at HEAD.
ARCHITECTURE_PATHS = {"areas": ("path",), "edges": ("from", "to"), "chokepoints": ("path",),
                      "entrypoints": ("path",), "toolchain": ("evidence",)}
MAX_ARTIFACT_BYTES = 1024 * 1024
MAX_ARTIFACT_ENTRIES = 200


def read_artifact(stream) -> dict:
    """The extractor's output, read whole and bounded. Reading one byte past the cap is enough to
    know the cap is breached, so a huge submission is refused rather than held."""
    try:
        text = stream.read(MAX_ARTIFACT_BYTES + 1)
    except Exception as exc:
        raise Internal(f"The architecture artifact could not be read. {exc}") from exc
    if text is None or not str(text).strip():
        raise Internal("No artifact was submitted. Send the extractor's JSON on standard input.")
    if len(text) > MAX_ARTIFACT_BYTES:
        raise Internal(f"The artifact exceeds {MAX_ARTIFACT_BYTES} bytes. Nothing was read.")
    try:
        artifact = json.loads(text)
    except ValueError as exc:
        raise Internal(f"The artifact is not valid JSON. {exc}") from exc
    if not isinstance(artifact, dict):
        raise Internal("The artifact must be one JSON object carrying the architecture sections.")
    return artifact


def validate_architecture(artifact: dict, at_head: set) -> tuple:
    """The artifact as facts, plus what it got wrong. An extractor is a program the agent wrote
    minutes ago against a repository nobody here has seen: its output is evidence only once its
    shape holds and its paths resolve."""
    findings, facts = [], []
    for section, required in sorted(ARCHITECTURE_SHAPE.items()):
        entries = artifact.get(section)
        if entries is None:
            continue
        if not isinstance(entries, list):
            findings.append({"rule": "section_malformed", "section": section,
                             "message": f"`{section}` must be a list of entries."})
            continue
        if len(entries) > MAX_ARTIFACT_ENTRIES:
            findings.append({"rule": "section_oversized", "section": section,
                             "message": f"`{section}` carries {len(entries)} entries, past the "
                                        f"{MAX_ARTIFACT_ENTRIES} a reader can use."})
            continue
        clean = []
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                findings.append({"rule": "entry_malformed", "section": section,
                                 "message": f"`{section}[{index}]` is not an object."})
                continue
            missing = [key for key in required if not str(entry.get(key, "")).strip()]
            if missing:
                findings.append({"rule": "entry_incomplete", "section": section,
                                 "message": f"`{section}[{index}]` omits {', '.join(missing)}."})
                continue
            dangling = [entry[key] for key in ARCHITECTURE_PATHS.get(section, ())
                        if not _resolves(str(entry[key]), at_head)]
            if dangling:
                findings.append({"rule": "path_not_at_head", "section": section,
                                 "message": f"`{section}[{index}]` names {dangling[0]}, which the "
                                            "repository does not have. An extractor reporting a "
                                            "path nobody can open reported something else too."})
                continue
            clean.append(entry)
        if clean:
            citation = next(({"kind": "file", "path": str(item[key])}
                             for item in clean
                             for key in ARCHITECTURE_PATHS.get(section, ())), None)
            facts.append(fact(f"arch.{section}", f"Architecture reported by the extractor: {section}",
                              clean, [citation] if citation else [], "inferred-medium"))
    return facts, findings


def _resolves(path: str, at_head: set) -> bool:
    candidate = path.strip().rstrip("/")
    return bool(candidate) and (candidate in at_head
                                or any(p.startswith(candidate + "/") for p in at_head))


def architecture(root, stream) -> dict:
    """Validate one extractor artifact against the repository it claims to describe."""
    files, _ = head_files(root)
    facts, findings = validate_architecture(read_artifact(stream), set(files))
    return {"schema_version": 3, "head": git(root, ["rev-parse", "HEAD"]).strip(),
            "facts": facts, "findings": findings, "sections": sorted(ARCHITECTURE_SHAPE)}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="coc_scan", add_help=False)
    parser.add_argument("mode", choices=["all", "architecture"])
    parser.add_argument("--root", required=True)
    parser.add_argument("--contract", type=int, required=True)
    parser.add_argument("--months", type=float, default=12.0)
    parser.add_argument("--recent-months", type=float, default=3.0)
    parser.add_argument("--depth", type=int, default=2)
    parser.add_argument("--commits", type=int, default=MAX_COMMITS)
    return parser


def sanitize(value):
    """Every string in the emitted document, made inert and capped. Applied once at the exit rather
    than at each of the dozen places a value is built: a FILENAME is the most attacker-controlled
    string here — a crafted one carrying a newline, a fake heading or an ANSI escape reached an
    agent's context and its terminal verbatim, while commit subjects had been cleaned all along.
    One pass at the boundary also covers whatever field is added next.

    Control characters are ESCAPED, never dropped. Dropping them would fold two genuinely different
    tracked names into one presented name — the crafted twin and the real file it shadows would
    read identically, which is the very confusion the escaping exists to prevent."""
    if isinstance(value, str):
        escaped = "".join(ch if ch == " " or (ch.isprintable() and ch != "\ufeff")
                          else "\\x%02x" % ord(ch) for ch in value)
        return escaped[:MAX_EMITTED_CHARS]
    if isinstance(value, dict):
        return {sanitize(key): sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    return value


def emit(payload: dict, mode: str, code: int) -> int:
    """Print the document as one JSON object and return the exit code. Every path emits, refusals
    included, so the skill parses one shape and never has to guess. Keys are sorted and no field
    reads the clock: two runs at one commit are byte-identical, and that is a tested promise."""
    print(json.dumps(sanitize(dict({"contract": CONTRACT_VERSION, "mode": mode}, **payload)),
                     sort_keys=True, indent=1))
    return code


def main(argv=None, home=None, stdin=None) -> int:
    """Resolve, read, and turn every failure into a scripted refusal — nothing escapes as a
    traceback. `home` is accepted for a uniform tool signature and unused: this tool keeps no
    record."""
    try:
        args = build_parser().parse_args(list(argv) if argv is not None else None)
    except SystemExit:
        return emit({"error": "usage",
                     "message": "The arguments were not understood. Expected: "
                                f"all --root <path> --contract {CONTRACT_VERSION}, or "
                                f"architecture --root <path> --contract {CONTRACT_VERSION} "
                                "with the extractor's JSON on stdin"},
                    "all", EXIT_INTERNAL)
    if args.contract != CONTRACT_VERSION:
        return emit({"error": "contract",
                     "message": f"This tool speaks version {CONTRACT_VERSION}; the skill asked for "
                                f"{args.contract}. Update the plugin, then run this again."},
                    args.mode, EXIT_CONTRACT)
    commits = max(1, min(args.commits, MAX_COMMITS))
    try:
        if args.mode == "architecture":
            document = architecture(args.root, stdin if stdin is not None else sys.stdin)
        else:
            document = scan(args.root, args.months, args.recent_months, max(1, args.depth), commits)
    except Refused as exc:
        return emit({"error": "refused", "rule": exc.rule, "message": exc.message},
                    args.mode, EXIT_REFUSED)
    except Internal as exc:
        return emit({"error": "internal", "message": exc.message}, args.mode, EXIT_INTERNAL)
    except Exception as exc:  # fail closed: an unreadable repository is never an empty one
        return emit({"error": "internal", "message": f"Nothing was scanned. {exc}"},
                    args.mode, EXIT_INTERNAL)
    # An artifact whose shape or paths did not hold is a refusal: the agent fixes what the findings
    # name and submits again, exactly as the draft gate works.
    if document.get("findings"):
        return emit(document, args.mode, EXIT_REFUSED)
    return emit(document, args.mode, EXIT_OK)


if __name__ == "__main__":  # pragma: no cover - exercised via main() in tests
    sys.exit(main())
