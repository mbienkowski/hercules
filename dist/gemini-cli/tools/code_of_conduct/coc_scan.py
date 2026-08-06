"""Read a repository and report what it can be shown to do — the evidence behind the code-of-conduct
(CoC) generator's scan step. It answers three questions a draft needs and an agent should not guess:
what this project declares about itself, how its history says it is worked on, and which of its code
is still being worked on at all.

Three properties are not negotiable. It is READ-ONLY — it runs `git` and opens files, and writes
nothing anywhere. It treats the repository as UNTRUSTED: paths arrive NUL-delimited so a crafted
filename cannot fabricate one, git runs with the repository's own quoting settings overridden, no
author identity is emitted, and secret-bearing paths are never opened. And it fails CLOSED — an
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
MAX_FILES_READ = 1200
MAX_FILE_BYTES = 400_000
MAX_SUBJECT_CHARS = 200
# A path may legitimately be long; the cap is a flood guard, not a formatting rule.
MAX_EMITTED_CHARS = 400
GIT_TIMEOUT_SECONDS = 60

TOP_FILES = 50

# Never opened. Structure may be recorded, contents never — this document is read by a model and
# persisted to disk, so a credential that enters it does not leave.
SECRET_GLOBS = ("*.env", ".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", "*id_rsa*",
                "*id_ed25519*", "*.keystore", "*secrets*.y*ml", "*credentials*")

# Trees a build produces. They can out-commit every hand-written module in a repository, so they are
# tagged rather than ranked; the skill confirms with the user rather than assuming.
GENERATED_DIR_HINTS = ("dist/", "build/", "vendor/", "node_modules/", "target/", ".next/",
                       "out/", "generated/", "__generated__/", "__pycache__/")
GENERATED_FILE_HINTS = ("package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
                        "uv.lock", "Cargo.lock", "go.sum", "Gemfile.lock", "composer.lock")

CODE_SUFFIXES = (".py", ".ts", ".tsx", ".mts", ".js", ".jsx", ".mjs", ".go", ".rs", ".java",
                 ".kt", ".rb", ".cs", ".swift", ".php", ".scala", ".c", ".cc", ".cpp", ".h")

# Probes are GLOBS, not filenames: a real project spelled its lint config `.eslintrc.yml`, which an
# exact-name list missed entirely.
FILE_PROBES = {
    "cfg.eco.node": (["package.json"], "Node manifest present"),
    "cfg.eco.python": (["pyproject.toml", "setup.py", "requirements*.txt"], "Python manifest present"),
    "cfg.eco.go": (["go.mod"], "Go module present"),
    "cfg.eco.rust": (["Cargo.toml"], "Rust crate present"),
    "cfg.eco.jvm": (["pom.xml", "build.gradle", "build.gradle.kts"], "JVM build present"),
    "cfg.eco.ruby": (["Gemfile"], "Ruby bundle present"),
    "cfg.workspace": (["pnpm-workspace.yaml", "lerna.json", "nx.json", "turbo.json", "go.work",
                       "rush.json"], "Workspace or monorepo configuration present"),
    "cfg.deps.lockfile": (list(GENERATED_FILE_HINTS), "Dependency lockfile present"),
    "cfg.lint.eslint": ([".eslintrc*", "eslint.config.*"], "ESLint configuration present"),
    "cfg.lint.golangci": ([".golangci.*"], "golangci-lint configuration present"),
    "cfg.lint.rubocop": ([".rubocop.yml"], "RuboCop configuration present"),
    "cfg.format.prettier": ([".prettierrc*", "prettier.config.*"], "Prettier configuration present"),
    "cfg.format.editorconfig": ([".editorconfig"], "EditorConfig present"),
    "cfg.types.tsconfig": (["tsconfig.json", "tsconfig.*.json"], "TypeScript configuration present"),
    "cfg.test.vitest_config": (["vitest.config.*"], "Vitest configuration file present"),
    "cfg.test.jest_config": (["jest.config.*"], "Jest configuration file present"),
    "cfg.test.pytest_ini": (["pytest.ini", "tox.ini"], "Pytest or tox configuration file present"),
    "cfg.ci.github": ([".github/workflows/*"], "GitHub Actions workflows present"),
    "cfg.ci.gitlab": ([".gitlab-ci.yml"], "GitLab CI configuration present"),
    "cfg.build.makefile": (["Makefile"], "Makefile present"),
    "cfg.build.maven": (["pom.xml"], "Maven build present"),
    "cfg.build.gradle": (["build.gradle", "build.gradle.kts", "settings.gradle",
                          "settings.gradle.kts"], "Gradle build present"),
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

# Tooling a modern Python project declares INSIDE its manifest. A `[tool.<name>]` header is
# line-anchored, so it reads reliably without the TOML parser this runtime floor does not have.
PYPROJECT_SECTIONS = {
    "ruff": ("cfg.lint.ruff", "Ruff configured in pyproject"),
    "black": ("cfg.format.black", "Black configured in pyproject"),
    "isort": ("cfg.format.isort", "isort configured in pyproject"),
    "flake8": ("cfg.lint.flake8", "Flake8 configured in pyproject"),
    "mypy": ("cfg.types.mypy", "mypy configured in pyproject"),
    "pyright": ("cfg.types.pyright", "Pyright configured in pyproject"),
    "pytest": ("cfg.test.pytest", "Pytest configured in pyproject"),
    "coverage": ("cfg.test.coverage", "Coverage configured in pyproject"),
    "mutmut": ("cfg.test.mutation", "Mutation testing configured in pyproject"),
}

# Tooling carried as a dependency, which a project may do with no config file of its own.
NODE_PACKAGES = {
    "eslint": ("cfg.lint.eslint", "ESLint present as a dependency"),
    "prettier": ("cfg.format.prettier", "Prettier present as a dependency"),
    "typescript": ("cfg.types.typescript", "TypeScript present as a dependency"),
    "vitest": ("cfg.test.vitest", "Vitest present as a dependency"),
    "jest": ("cfg.test.jest", "Jest present as a dependency"),
    "mocha": ("cfg.test.mocha", "Mocha present as a dependency"),
    "@playwright/test": ("cfg.test.e2e", "Playwright present as a dependency"),
    "cypress": ("cfg.test.e2e", "Cypress present as a dependency"),
    "husky": ("cfg.hooks.precommit", "Husky present as a dependency"),
}

# Two ways of doing one thing, where a file commits to one of them visibly. Deliberately small: every
# pair costs a pass over each sampled file, and a pair nobody's repository uses is pure maintenance.
# Sides are ordered — the FIRST that matches wins, because the markers are not mutually exclusive
# (a `unittest.TestCase` method is still spelled `def test_…`), and the more specific one is listed
# first so a file is attributed to the convention it actually commits to.
#
# Each pair is SCOPED to the files the question is about. Without that, any file that merely mentions
# a marker is counted as using it — this scanner's own source names every pattern below, and would
# otherwise report itself as the repository's one holdout.
IDIOM_PAIRS = {
    "test.style.python": ("How Python tests are written", ("*test*.py", "*_test.py"), [
        ("unittest-class", re.compile(r"\bunittest\.TestCase\b")),
        ("pytest-function", re.compile(r"^\s*def test_", re.M)),
    ]),
    "assertion.python": ("How Python tests assert", ("*test*.py", "*_test.py"), [
        ("unittest-assert", re.compile(r"\bself\.assert[A-Z]")),
        ("bare-assert", re.compile(r"^\s*assert\s", re.M)),
    ]),
    "http.client.python": ("Which HTTP client Python code reaches for", ("*.py",), [
        ("httpx", re.compile(r"^\s*(?:import|from) httpx\b", re.M)),
        ("requests", re.compile(r"^\s*(?:import|from) requests\b", re.M)),
    ]),
    "test.runner.js": ("Which test runner JavaScript and TypeScript tests import",
                       ("*.test.*", "*.spec.*"), [
        ("vitest", re.compile(r"""from ['"]vitest['"]""")),
        ("jest", re.compile(r"""from ['"]@jest/globals['"]""")),
    ]),
    "test.framework.jvm": ("Which JUnit generation JVM tests import",
                           ("*Test.java", "*Tests.java", "*Test.kt"), [
        ("junit5", re.compile(r"\borg\.junit\.jupiter\b")),
        ("junit4", re.compile(r"\borg\.junit\.Test\b")),
    ]),
    "test.framework.ruby": ("Which Ruby test framework the suite uses",
                            ("*_spec.rb", "*_test.rb", "test_*.rb"), [
        ("rspec", re.compile(r"\bRSpec\.describe\b")),
        ("minitest", re.compile(r"\bMinitest::Test\b")),
    ]),
}

# Tools that genuinely compete for one job, named explicitly rather than grouped by the middle of
# their fact id. Grouping by concern reads `cfg.test.pytest` and `cfg.test.vitest` as rivals, when a
# repository with Python and TypeScript in it needs both — and pairs a coverage tool against a test
# runner, which answer different questions. Rivalry is a fact about tools, so it is stated.
CONFIG_RIVALS = (
    ("Which JavaScript test runner is authoritative",
     ("cfg.test.vitest", "cfg.test.jest", "cfg.test.mocha")),
    ("Which JavaScript test runner the configuration files declare",
     ("cfg.test.vitest_config", "cfg.test.jest_config")),
    ("Which Python linter is authoritative", ("cfg.lint.ruff", "cfg.lint.flake8")),
    ("Which Python formatter is authoritative", ("cfg.format.black", "cfg.format.isort")),
    ("Which Python type checker is authoritative", ("cfg.types.mypy", "cfg.types.pyright")),
    ("Which end-to-end runner is authoritative", ("cfg.test.e2e",)),
    ("Which JVM build is authoritative", ("cfg.build.maven", "cfg.build.gradle")),
)

# More than one of these means two package managers are both claiming to pin the same dependencies.
RIVAL_LOCKFILES = ("package-lock.json", "yarn.lock", "pnpm-lock.yaml")

# ── Architecture: what the valuable rules stand on ────────────────────────────────────────────
# The quality-bearing facts of a repository are architectural — the engine everything renders
# through, the directory that grows by one-more-file-of-a-kind — and none of them is a config probe.
# Everything here is derived by regex over import lines and file lists: deterministic, bounded, and
# honest about being INFERRED, never measured. A rule citing these can see that.

MAX_IMPORTS_PER_FILE = 200
MAX_IMPORT_CHARS = 120      # a longer specifier is generated or hostile, never an architecture
MAX_EDGES = 40
MAX_CHOKEPOINTS = 12
MIN_CHOKEPOINT_FAN_IN = 3
# Measured against Hercules's own tree: 24 real families (>=4 files) exist, and a cap of 12 dropped
# src/content/commands — the extension point a user actually invokes — with no signal that anything
# was cut. 24 clears that with headroom without being tuned to this one repository's exact count;
# a repository with more still gets a truncation signal rather than a silently shorter list.
MIN_FAMILY_FILES = 4
MAX_FAMILIES = 32
MAX_ENTRYPOINT_FILES = 20

FAMILY_SUFFIXES = CODE_SUFFIXES + (".md", ".json", ".yml", ".yaml", ".toml")
CONFIG_FAMILY_SUFFIXES = (".json", ".yml", ".yaml", ".toml")
JS_SUFFIXES = (".ts", ".tsx", ".mts", ".js", ".jsx", ".mjs")
JVM_SUFFIXES = (".java", ".kt")

# One extraction pattern per language the resolver can place. These are a HEAD START, never the
# ceiling: a language with no pattern contributes no edges, and the scan SAYS SO — per-suffix parse
# coverage is reported and `arch.graph.partial` lands in `unknowns`, so the drafting agent derives
# the missing architecture by reading and records it as observations. The pipeline is complete for
# every language; the parser only decides how much of the work arrives pre-measured.
PYTHON_IMPORT = re.compile(r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))", re.M)
JS_IMPORT = re.compile(
    r"""(?:from\s+|require\(\s*|import\(\s*|^import\s+)['"]([^'"\n]{1,200})['"]""", re.M)
GO_IMPORT_SINGLE = re.compile(r'^import\s+(?:\w+\s+)?"([^"\n]{1,200})"', re.M)
GO_IMPORT_BLOCK = re.compile(r"^import\s+\(([^)]{0,4000})\)", re.M)
GO_QUOTED = re.compile(r'"([^"\n]{1,200})"')
JVM_IMPORT = re.compile(r"^import\s+(?:static\s+)?([\w.]+?)(\.\*)?\s*;?\s*$", re.M)
RUBY_RELATIVE = re.compile(r"""require_relative\s+['"]([^'"\n]{1,200})['"]""")
RUST_USE = re.compile(r"^\s*use\s+crate::([\w:]+)", re.M)
GO_MODULE = re.compile(r"^module\s+(\S+)", re.M)

# Where execution enters, per language. Go demands both marks: `func main` inside `package main`.
MAIN_PATTERNS = (
    ((".py",), re.compile(r"""^if __name__ == ['"]__main__['"]""", re.M)),
    ((".go",), re.compile(r"^func main\(\)", re.M)),
    ((".java", ".kt"), re.compile(r"\bstatic\s+void\s+main\s*\(|^fun\s+main\s*\(", re.M)),
    ((".rs",), re.compile(r"^fn main\(\)", re.M)),
)
GO_PACKAGE_MAIN = re.compile(r"^package main\b", re.M)

# The suffixes the import extractor and the entrypoint patterns actually understand. Everything
# else that was sampled is reported as unparsed rather than silently contributing nothing.
IMPORT_PARSED_SUFFIXES = (".py",) + JS_SUFFIXES + JVM_SUFFIXES + (".go", ".rb", ".rs")

CONVENTIONAL_SUBJECT = re.compile(
    r"^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([^)]+\))?!?: ")
TICKET_REFERENCE = re.compile(r"(#\d+|[A-Z]{2,}-\d+)")
TOOL_SECTION = re.compile(r"^\[tool\.([A-Za-z0-9_-]+)")
MARKER = re.compile(r"\b(TODO|FIXME|XXX|HACK)\b")


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


SYMLINK_MODE = "120000"


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
        files, links = [], set()
        for entry in listing[:MAX_PATHS]:
            mode, _, rest = entry.partition(" ")
            path = rest.split("\t", 1)[-1] if "\t" in rest else rest
            files.append(path)
            if mode == SYMLINK_MODE:
                links.add(path)
        return files, "worktree", links
    files = nul_paths(git(root, ["ls-tree", "-r", "-z", "--name-only", "HEAD"], binary=True))
    if files:
        return files[:MAX_PATHS], "bare", set()
    raise Refused("empty_repository",
                  "That repository has no files at HEAD. There is nothing to draw standards from.")


# ── Classifying paths ─────────────────────────────────────────────────────────────────────────

def is_secret_path(path: str) -> bool:
    """Case-folded on both sides. `fnmatch` is case-sensitive, but the filesystems this ships to
    mostly are not: `ID_RSA` and `id_rsa` name the same file there, and only one of them was ever
    matched — so the exclusion depended on which spelling the repository happened to choose."""
    lowered = path.lower()
    name = lowered.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatch(lowered, g.lower()) or fnmatch.fnmatch(name, g.lower())
               for g in SECRET_GLOBS)


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


def read_file(root, relative: str, links=frozenset()):
    """One repository file, bounded, and never a way out of the worktree.

    Four refusals before anything is opened, because every one of them was reachable from a name
    the repository chose: a secret-bearing name, a tracked SYMLINK (whose target is wherever its
    author pointed it, inside the checkout or not), a name carrying a backslash (an ordinary byte
    on POSIX and a separator on the platform this also ships to), and — last, as the check that
    does not depend on knowing the trick — a resolved path that does not sit under the root."""
    if is_secret_path(relative) or relative in links or "\\" in relative:
        return None
    joined = os.path.join(str(root), relative)
    try:
        base = os.path.realpath(str(root))
        target = os.path.realpath(joined)
        if target != base and not target.startswith(base + os.sep):
            return None
        if not os.path.isfile(target) or os.path.islink(joined):
            return None
        with open(joined, "rb") as handle:
            return handle.read(MAX_FILE_BYTES).decode("utf-8", "replace")
    except OSError:
        return None


def pyproject_facts(root, files: list, links=frozenset()) -> list:
    if "pyproject.toml" not in files:
        return []
    text = read_file(root, "pyproject.toml", links)
    if text is None:
        return []
    found, seen = [], set()
    for line_number, line in enumerate(text.splitlines(), 1):
        match = TOOL_SECTION.match(line)
        if not match:
            continue
        entry = PYPROJECT_SECTIONS.get(match.group(1).lower())
        if entry and entry[0] not in seen:
            seen.add(entry[0])
            found.append(fact(entry[0], entry[1], match.group(1).lower(),
                              [{"kind": "file", "path": "pyproject.toml", "line": line_number}]))
    return found


def package_json_facts(root, files: list, links=frozenset()) -> list:
    if "package.json" not in files:
        return []
    text = read_file(root, "package.json", links)
    if text is None:
        return []
    try:
        data = json.loads(text)
    except ValueError:
        return []
    if not isinstance(data, dict):
        return []
    dependencies = {}
    for key in ("dependencies", "devDependencies"):
        if isinstance(data.get(key), dict):
            dependencies.update(data[key])
    found, seen = [], set()
    for name, (fact_id, claim) in sorted(NODE_PACKAGES.items()):
        if name in dependencies and fact_id not in seen:
            seen.add(fact_id)
            found.append(fact(fact_id, claim, name,
                              [{"kind": "file", "path": "package.json"}]))
    if dependencies:
        pinned = sum(1 for value in dependencies.values() if re.match(r"^\d", str(value)))
        found.append(fact("cfg.deps.pinning", "Share of exact-pinned dependency versions",
                          {"pinned": pinned, "total": len(dependencies)},
                          [{"kind": "file", "path": "package.json"}]))
    if isinstance(data.get("engines"), dict):
        engines = {clean_text(str(k), 40): clean_text(str(v), 40)
                   for k, v in sorted(data["engines"].items())}
        found.append(fact("cfg.runtime.engines", "Declared runtime engine constraint", engines,
                          [{"kind": "file", "path": "package.json"}]))
    if isinstance(data.get("workspaces"), (list, dict)):
        found.append(fact("cfg.workspace", "Workspace or monorepo configuration present",
                          "package.json workspaces",
                          [{"kind": "file", "path": "package.json"}]))
    return found


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

def classify_idioms(relative: str, text: str) -> dict:
    """Which side of each competing idiom this one file takes, at most one side per concern."""
    taken = {}
    for concern, (_, scope, sides) in IDIOM_PAIRS.items():
        name_only = relative.rsplit("/", 1)[-1]
        if not any(fnmatch.fnmatch(name_only, g) for g in scope):
            continue
        for name, pattern in sides:
            if pattern.search(text):
                taken[concern] = name
                break
    return taken


def conflicts_from_idioms(idioms: dict, directories: list, depth: int) -> list:
    """Where a repository does one thing two ways, both ways with their standing: how much of the
    code takes each side, and how much of the RECENT work happens where that side lives.

    It reports both and resolves neither. Recency is a good argument and a bad decision procedure —
    code is edited when it is being adopted and equally when it is being removed, and this cannot
    tell those apart. A rule the repository will be held to is worth one question."""
    recent = {entry["path"]: entry["recent_touches"] for entry in directories}
    found = []
    for concern in sorted(idioms):
        sides = idioms[concern]
        if len(sides) < 2:
            continue  # one way of doing something is a convention, not a conflict
        total_files = sum(len(paths) for paths in sides.values())
        total_recent = sum(sum(recent.get(directory_of(p, depth), 0) for p in paths)
                           for paths in sides.values())
        candidates = []
        for name in sorted(sides):
            paths = sorted(sides[name])
            touches = sum(recent.get(directory_of(p, depth), 0) for p in paths)
            candidates.append({
                "name": name,
                "files": len(paths),
                "file_share": round(len(paths) / total_files, 4),
                "recent_touches": touches,
                "recent_share": round(touches / total_recent, 4) if total_recent else 0.0,
                "example": paths[0],
            })
        candidates.sort(key=lambda c: (-c["files"], c["name"]))
        found.append({
            "id": f"conflict.{concern}",
            "concern": IDIOM_PAIRS[concern][0],
            "candidates": candidates,
            "resolution": "question",
        })
    return found


def _config_candidates(names: list) -> list:
    return [{"name": name, "files": 1, "file_share": round(1 / len(names), 4),
             "recent_touches": 0, "recent_share": 0.0, "example": name}
            for name in sorted(names)]


def conflicts_from_config(facts: list) -> list:
    """Two rival tools both declared for one job. Which is authoritative is a decision nobody wrote
    down anywhere the scan can read, so it is asked rather than inferred from which config is newer."""
    present = {entry["id"] for entry in facts}
    found = []
    for index, (concern, rivals) in enumerate(CONFIG_RIVALS):
        declared = [name for name in rivals if name in present]
        if len(declared) > 1:
            found.append({"id": f"conflict.cfg.{index}", "concern": concern,
                          "candidates": _config_candidates(declared), "resolution": "question"})
    lockfiles = next((entry["value"] for entry in facts if entry["id"] == "cfg.deps.lockfile"), [])
    rival_locks = [name for name in RIVAL_LOCKFILES
                   if any(str(value).endswith(name) for value in lockfiles)]
    if len(rival_locks) > 1:
        found.append({"id": "conflict.cfg.lockfile",
                      "concern": "Which package manager pins the dependencies",
                      "candidates": _config_candidates(rival_locks), "resolution": "question"})
    return found


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
        if suffix in FAMILY_SUFFIXES:
            file_groups.setdefault((directory, suffix), []).append(path)
        # The item is the directory, identified by the file every sibling carries under the same
        # name. Scaffolding names (`__init__.py`, `conftest.py`) would make every package tree a
        # family, so they identify nothing.
        if "/" in directory and suffix in FAMILY_SUFFIXES \
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


def _join_relative(directory: str, spec: str):
    """A relative import specifier resolved against its importer's directory, inside the repository
    or not at all — a specifier is repository-authored text, and one that climbs out resolves to
    nothing rather than to a path this document would then carry."""
    parts = directory.split("/") if directory else []
    for piece in spec.split("/"):
        if piece in ("", "."):
            continue
        if piece == "..":
            if not parts:
                return None
            parts.pop()
        else:
            parts.append(piece)
    return "/".join(parts)


def _import_specs(relative: str, text: str) -> list:
    if relative.endswith(".py"):
        matches = [first or second for first, second in PYTHON_IMPORT.findall(text)]
    elif relative.endswith(JS_SUFFIXES):
        matches = JS_IMPORT.findall(text)
    elif relative.endswith(".go"):
        matches = GO_IMPORT_SINGLE.findall(text)
        for block in GO_IMPORT_BLOCK.findall(text):
            matches.extend(GO_QUOTED.findall(block))
    elif relative.endswith(JVM_SUFFIXES):
        matches = [dotted + (star or "") for dotted, star in JVM_IMPORT.findall(text)]
    elif relative.endswith(".rb"):
        matches = RUBY_RELATIVE.findall(text)
    elif relative.endswith(".rs"):
        matches = RUST_USE.findall(text)
    else:
        matches = []
    return matches[:MAX_IMPORTS_PER_FILE]


def build_import_indexes(root, files: list, links=frozenset()) -> dict:
    """Everything resolution needs precomputed once, so no import pays a scan over the whole file
    list: Go's module prefix and package directories, and the JVM's basename-to-paths map — a
    dotted Java import only ever matches by its tail, and the basename shrinks the candidates to a
    handful."""
    indexes = {"go_module": None, "go_dirs": set(), "jvm_names": {}}
    if any(f.endswith(".go") for f in files):
        text = read_file(root, "go.mod", links) if "go.mod" in files else None
        match = GO_MODULE.search(text) if text else None
        if match:
            indexes["go_module"] = match.group(1).rstrip("/")
        indexes["go_dirs"] = {f.rsplit("/", 1)[0] for f in files
                              if f.endswith(".go") and "/" in f}
    for path in files:
        if path.endswith(JVM_SUFFIXES):
            indexes["jvm_names"].setdefault(path.rsplit("/", 1)[-1], []).append(path)
    return indexes


def _resolve_import(spec: str, importer: str, at_head: set, indexes: dict):
    """The file (or, for Go and star imports, the package directory) a specifier names, by
    membership at HEAD, or None. Python and Rust resolve from the repository root, JavaScript and
    Ruby resolve relative specifiers only, Go resolves under its own module prefix, and JVM dotted
    names resolve by their path tail — a specifier none of those place names a dependency, which is
    outside the repository and outside this graph."""
    if not spec or len(spec) > MAX_IMPORT_CHARS:
        return None
    if importer.endswith(".py"):
        if spec.startswith("."):
            # Relative: each dot past the first climbs one package. Resolved against the importing
            # file's own directory — the layouts real projects use most, and exactly the ones a
            # root-relative reading was blind to.
            dots = len(spec) - len(spec.lstrip("."))
            remainder = spec[dots:].replace(".", "/")
            package = importer.split("/")[:-1]
            climb = dots - 1
            if climb > len(package):
                return None
            base = "/".join(package[:len(package) - climb] + ([remainder] if remainder else []))
            if not base:
                return None
            candidates = [base + ".py", base + "/__init__.py"]
        else:
            base = spec.replace(".", "/")
            # `src/` second: an src-layout package is imported bare (`pkg.mod`) but lives under
            # `src/pkg/mod.py`, so a root-relative reading alone misses the whole graph.
            candidates = [base + ".py", base + "/__init__.py",
                          "src/" + base + ".py", "src/" + base + "/__init__.py"]
    elif importer.endswith(JS_SUFFIXES) or importer.endswith(".rb"):
        if not spec.startswith("."):
            return None
        directory = importer.rsplit("/", 1)[0] if "/" in importer else ""
        base = _join_relative(directory, spec)
        if base is None:
            return None
        dot, slash = base.rfind("."), base.rfind("/")
        stem = base[:dot] if dot > slash else base
        if importer.endswith(".rb"):
            candidates = [base, stem + ".rb"]
        else:
            candidates = ([base] + [stem + suffix for suffix in JS_SUFFIXES]
                          + [stem + "/index" + suffix for suffix in JS_SUFFIXES])
    elif importer.endswith(".go"):
        module = indexes.get("go_module")
        if not module or not spec.startswith(module + "/"):
            return None
        package = spec[len(module) + 1:]
        return package if package in indexes["go_dirs"] else None
    elif importer.endswith(JVM_SUFFIXES):
        if spec.endswith(".*"):
            tail = spec[:-2].replace(".", "/")
            matches = sorted(d for d in {p.rsplit("/", 1)[0]
                                         for paths in indexes["jvm_names"].values()
                                         for p in paths}
                             if d == tail or d.endswith("/" + tail))
            return matches[0] if matches else None
        tail = spec.replace(".", "/")
        for extension in JVM_SUFFIXES:
            name = tail.rsplit("/", 1)[-1] + extension
            matches = sorted(p for p in indexes["jvm_names"].get(name, [])
                             if p == tail + extension or p.endswith("/" + tail + extension))
            if matches:
                return matches[0]
        return None
    elif importer.endswith(".rs"):
        base = spec.replace("::", "/")
        candidates = ["src/" + base + ".rs", "src/" + base + "/mod.rs", base + ".rs"]
    else:
        return None
    for candidate in candidates:
        if candidate in at_head:
            return candidate
    return None


def _containing_directory(path: str) -> str:
    """The directory a resolved target lives in — or the target itself where resolution already
    returned a directory (a Go package, a JVM star import), told apart by the last segment carrying
    no suffix dot."""
    last = path.rsplit("/", 1)[-1]
    if "." not in last:
        return path
    return path.rsplit("/", 1)[0] if "/" in path else "."


def _edge_between(importer: str, target: str):
    """The dependency edge at the level where the two paths actually diverge — one segment past
    their common prefix. A fixed depth is a property of one repository's layout: depth two reads a
    Maven tree as `src/main` importing `src/main`, and every real edge vanishes into a self-loop."""
    from_parts = _containing_directory(importer).split("/")
    to_parts = _containing_directory(target).split("/")
    shared = 0
    while (shared < len(from_parts) and shared < len(to_parts)
           and from_parts[shared] == to_parts[shared]):
        shared += 1
    if shared == len(from_parts) and shared == len(to_parts):
        return None  # one directory — a local import, not an edge between areas
    source = "/".join(from_parts[:shared + 1]) if shared < len(from_parts) else "/".join(from_parts)
    destination = "/".join(to_parts[:shared + 1]) if shared < len(to_parts) else "/".join(to_parts)
    if source == destination:
        return None
    return source, destination


def _is_entrypoint(relative: str, text: str) -> bool:
    for suffixes, pattern in MAIN_PATTERNS:
        if relative.endswith(suffixes) and pattern.search(text):
            return not relative.endswith(".go") or bool(GO_PACKAGE_MAIN.search(text))
    return False


def read_code_sample(root, files: list, config_dirs: list, depth: int,
                     links=frozenset()) -> dict:
    """One bounded pass over the repository's own code, answering everything that needs the file
    contents: how long its modules run, how many markers they carry, which side of a competing idiom
    each file takes, what it imports, where execution enters, and which modules read the
    configuration families. One pass because each of those alone would not justify the reads."""
    code = [f for f in sorted(files)
            if f.endswith(CODE_SUFFIXES) and not is_generated(f) and not is_secret_path(f)]
    at_head = set(files)
    indexes = build_import_indexes(root, files, links)
    sample = {"lengths": [], "markers": 0, "read": 0, "total": len(code), "idioms": {},
              "imported_by": {}, "edges": {}, "resolved_imports": 0, "main_guards": [],
              "config_consumers": {}, "suffix_reads": {}}
    for relative in code[:MAX_FILES_READ]:
        text = read_file(root, relative, links)
        if text is None:
            continue
        sample["read"] += 1
        suffix = "." + relative.rsplit(".", 1)[-1]
        sample["suffix_reads"][suffix] = sample["suffix_reads"].get(suffix, 0) + 1
        sample["lengths"].append(len(text.splitlines()))
        sample["markers"] += len(MARKER.findall(text))
        for concern, side in classify_idioms(relative, text).items():
            sample["idioms"].setdefault(concern, {}).setdefault(side, []).append(relative)
        for spec in _import_specs(relative, text):
            target = _resolve_import(spec, relative, at_head, indexes)
            if target is None or target == relative:
                continue
            sample["resolved_imports"] += 1
            sample["imported_by"].setdefault(target, set()).add(relative)
            edge = _edge_between(relative, target)
            if edge is not None:
                sample["edges"][edge] = sample["edges"].get(edge, 0) + 1
        if _is_entrypoint(relative, text):
            sample["main_guards"].append(relative)
        for config_dir in config_dirs:
            if config_dir in text:
                sample["config_consumers"].setdefault(config_dir, set()).add(relative)
    sample["lengths"].sort()
    return sample


def architecture_facts(files: list, families: list, sample: dict, manifest_bins: list) -> list:
    """The architecture the sample can show. Absent evidence yields no fact — an empty graph would
    read as 'measured: independent' when nothing was resolved at all."""
    found = []
    count_citation = [{"kind": "count", "pattern": "internal imports resolved",
                      "matched": sample["resolved_imports"], "sampled": sample["read"]}]
    # Which languages the graph below actually saw. Sampled code the extractor has no pattern for
    # is named here, so a missing edge reads as "not measured" and never as "independent" — and the
    # drafting agent knows exactly where its own reading must carry the architecture.
    parsed = sorted(s for s in sample["suffix_reads"] if s in IMPORT_PARSED_SUFFIXES)
    unparsed = [{"suffix": s, "files": n} for s, n in sorted(sample["suffix_reads"].items())
                if s not in IMPORT_PARSED_SUFFIXES]
    if sample["read"]:
        found.append(fact(
            "arch.import_coverage",
            "Which sampled languages the import extractor parsed, and which it could not",
            {"parsed": parsed, "unparsed": unparsed},
            [{"kind": "count", "pattern": "code files read", "matched": sample["read"],
              "sampled": sample["total"]}]))
    if families:
        found.append(fact(
            "arch.families", "Directories that grow by adding one more file of a kind", families,
            [{"kind": "file", "path": entry["examples"][0]} for entry in families[:3]]))
    edges = [{"from": source, "to": target, "imports": count}
             for (source, target), count in sample["edges"].items()]
    edges.sort(key=lambda entry: (-entry["imports"], entry["from"], entry["to"]))
    if edges:
        mutual = sorted({tuple(sorted((entry["from"], entry["to"]))) for entry in edges
                         if any(other["from"] == entry["to"] and other["to"] == entry["from"]
                                for other in edges)})
        found.append(fact(
            "arch.graph", "Import dependencies between areas, read from import lines",
            {"edges": edges[:MAX_EDGES], "mutual": [list(pair) for pair in mutual]},
            count_citation, "inferred-medium"))
    chokepoints = [{"path": target, "fan_in": len(importers)}
                   for target, importers in sample["imported_by"].items()
                   if len(importers) >= MIN_CHOKEPOINT_FAN_IN]
    chokepoints.sort(key=lambda entry: (-entry["fan_in"], entry["path"]))
    if chokepoints:
        found.append(fact(
            "arch.chokepoints", "Modules that many files import — the paths every change flows through",
            chokepoints[:MAX_CHOKEPOINTS],
            [{"kind": "file", "path": entry["path"]}
             for entry in chokepoints[:3]], "inferred-medium"))
    bin_files = sorted(f for f in files if f.startswith("bin/")
                       and not is_generated(f))[:MAX_ENTRYPOINT_FILES]
    main_guards = sorted(sample["main_guards"])[:MAX_ENTRYPOINT_FILES]
    if bin_files or main_guards or manifest_bins:
        cited = (bin_files or main_guards or manifest_bins)[0]
        found.append(fact(
            "arch.entrypoints", "Where execution enters the repository",
            {"bin_files": bin_files, "main_guards": main_guards, "manifest": manifest_bins},
            [{"kind": "file", "path": cited}], "inferred-medium"))
    consumers = [{"family": config_dir, "consumers": sorted(readers)[:3]}
                 for config_dir, readers in sample["config_consumers"].items() if readers]
    consumers.sort(key=lambda entry: entry["family"])
    if consumers:
        found.append(fact(
            "arch.config_consumers",
            "Modules that name a configuration family — the code its files are read by",
            consumers, [{"kind": "file", "path": consumers[0]["consumers"][0]}],
            "inferred-medium"))
    return found


def manifest_entrypoints(root, files: list, links=frozenset()) -> list:
    """The entry points the Node manifest declares. Values are repository-authored text, cleaned
    and bounded like every other."""
    if "package.json" not in files:
        return []
    text = read_file(root, "package.json", links)
    try:
        data = json.loads(text or "")
    except ValueError:
        return []
    if not isinstance(data, dict):
        return []
    declared = []
    bins = data.get("bin")
    if isinstance(bins, str):
        declared.append(bins)
    elif isinstance(bins, dict):
        declared.extend(value for value in bins.values() if isinstance(value, str))
    if isinstance(data.get("main"), str):
        declared.append(data["main"])
    cleaned = {clean_text(re.sub(r"^\./", "", value), 200) for value in declared}
    return sorted(entry for entry in cleaned if entry)[:MAX_ENTRYPOINT_FILES]


def shape_facts(lengths: list, markers: int, read: int, total: int) -> tuple:
    """Module sizes and marker density, so a threshold can quote this repository instead of a
    default nobody measured. Bounded: a large repository yields a sample, and says so."""
    if not lengths:
        return [], ["shape.module_size"]
    def percentile(fraction: float) -> int:
        return lengths[min(len(lengths) - 1, int(len(lengths) * fraction))]

    citation = [{"kind": "count", "pattern": "code files read",
                 "matched": read, "sampled": total}]
    found = [
        fact("shape.module_size", "Module length percentiles across the sampled code files",
             {"p50": percentile(0.5), "p90": percentile(0.9), "p99": percentile(0.99),
              "max": lengths[-1]}, citation,
             "inferred-high" if read == total else "inferred-medium"),
        fact("shape.marker_density", "TODO, FIXME, XXX and HACK markers per sampled file",
             {"markers": markers, "files": read,
              "per_file": round(markers / read, 3) if read else 0.0}, citation),
    ]
    return found, ([] if read == total else ["shape.sampled_only"])


# ── The document ──────────────────────────────────────────────────────────────────────────────

def scan(root, months: float, recent_months: float, depth: int, commits: int) -> dict:
    files, root_kind, links = head_files(root)
    truncated = len(files) >= MAX_PATHS
    probes, attempted, matched = probe_facts(files)
    families, families_truncated = code_families(files)
    config_dirs = sorted({entry["path"] for entry in families
                          if entry["suffix"] in CONFIG_FAMILY_SUFFIXES})
    sample = read_code_sample(root, files, config_dirs, depth, links)
    shape, shape_unknowns = shape_facts(sample["lengths"], sample["markers"],
                                        sample["read"], sample["total"])
    architecture = architecture_facts(files, families, sample,
                                      manifest_entrypoints(root, files, links))

    collected = {}
    for entry in (probes + pyproject_facts(root, files, links) + package_json_facts(root, files, links)
                  + history_facts(root, commits) + shape + architecture):
        collected.setdefault(entry["id"], entry)
    facts = sorted(collected.values(), key=lambda entry: entry["id"])

    alive = liveness(root, files, months, recent_months, depth, commits)
    graph_partial = any(s not in IMPORT_PARSED_SUFFIXES for s in sample["suffix_reads"])
    unknowns = sorted(set(shape_unknowns) | ({"liveness.complete"} if truncated else set())
                      | ({"arch.families_truncated"} if families_truncated else set())
                      | ({"arch.graph.partial"} if graph_partial else set()))
    return {
        "schema_version": 2,
        "head": git(root, ["rev-parse", "HEAD"]).strip(),
        "root_kind": root_kind,
        "files_at_head": len(files),
        "probes_attempted": attempted,
        "probes_matched": matched,
        "facts": facts,
        "liveness": alive,
        "conflicts": conflicts_from_config(facts)
                     + conflicts_from_idioms(sample["idioms"], alive["directories"], depth),
        "unknowns": unknowns,
        "truncated": truncated,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="coc_scan", add_help=False)
    parser.add_argument("mode", choices=["all"])
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


def main(argv=None, home=None) -> int:
    """Resolve, read, and turn every failure into a scripted refusal — nothing escapes as a
    traceback. `home` is accepted for a uniform tool signature and unused: this tool keeps no
    record."""
    try:
        args = build_parser().parse_args(list(argv) if argv is not None else None)
    except SystemExit:
        return emit({"error": "usage",
                     "message": "The arguments were not understood. Expected: "
                                f"all --root <path> --contract {CONTRACT_VERSION}"},
                    "all", EXIT_INTERNAL)
    if args.contract != CONTRACT_VERSION:
        return emit({"error": "contract",
                     "message": f"This tool speaks version {CONTRACT_VERSION}; the skill asked for "
                                f"{args.contract}. Update the plugin, then run this again."},
                    args.mode, EXIT_CONTRACT)
    commits = max(1, min(args.commits, MAX_COMMITS))
    try:
        document = scan(args.root, args.months, args.recent_months, max(1, args.depth), commits)
    except Refused as exc:
        return emit({"error": "refused", "rule": exc.rule, "message": exc.message},
                    args.mode, EXIT_REFUSED)
    except Internal as exc:
        return emit({"error": "internal", "message": exc.message}, args.mode, EXIT_INTERNAL)
    except Exception as exc:  # fail closed: an unreadable repository is never an empty one
        return emit({"error": "internal", "message": f"Nothing was scanned. {exc}"},
                    args.mode, EXIT_INTERNAL)
    return emit(document, args.mode, EXIT_OK)


if __name__ == "__main__":  # pragma: no cover - exercised via main() in tests
    sys.exit(main())
