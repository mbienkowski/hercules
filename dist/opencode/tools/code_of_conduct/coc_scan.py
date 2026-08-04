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
CONTRACT_VERSION = 1

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
)

# More than one of these means two package managers are both claiming to pin the same dependencies.
RIVAL_LOCKFILES = ("package-lock.json", "yarn.lock", "pnpm-lock.yaml")

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
            "-c", "core.pager=cat"] + list(args)
    environment = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0")
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
    """Every path at HEAD, and which route found them. `ls-files` reads the index, which a bare
    repository does not have — without the fallback a bare clone reports an empty repository."""
    files = nul_paths(git(root, ["ls-files", "-z"], binary=True))
    if files:
        return files[:MAX_PATHS], "worktree"
    files = nul_paths(git(root, ["ls-tree", "-r", "-z", "--name-only", "HEAD"], binary=True))
    if files:
        return files[:MAX_PATHS], "bare"
    raise Refused("empty_repository",
                  "That repository has no files at HEAD. There is nothing to draw standards from.")


# ── Classifying paths ─────────────────────────────────────────────────────────────────────────

def is_secret_path(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatch(path, g) or fnmatch.fnmatch(name, g) for g in SECRET_GLOBS)


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


def read_file(root, relative: str):
    """One repository file, bounded, and never a secret-bearing path."""
    if is_secret_path(relative):
        return None
    try:
        with open(os.path.join(str(root), relative), "rb") as handle:
            return handle.read(MAX_FILE_BYTES).decode("utf-8", "replace")
    except OSError:
        return None


def pyproject_facts(root, files: list) -> list:
    if "pyproject.toml" not in files:
        return []
    text = read_file(root, "pyproject.toml")
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


def package_json_facts(root, files: list) -> list:
    if "package.json" not in files:
        return []
    text = read_file(root, "package.json")
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
    found, epoch = [], None
    for chunk in blob.split(b"\0"):
        if not chunk:
            continue
        text = chunk.decode("utf-8", "replace")
        while text.startswith("\x01"):
            header, _, text = text[1:].partition("\x02")
            try:
                epoch = int(header.strip() or 0)
            except ValueError:
                epoch = None
        # git writes a newline between the format output and the first path of each commit, so the
        # first file of every commit arrives carrying one. Left on, it makes that path match nothing
        # at HEAD — which reads as a repository whose every commit touched only deleted files.
        text = text.lstrip("\n")
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


def read_code_sample(root, files: list) -> tuple:
    """One bounded pass over the repository's own code, answering everything that needs the file
    contents: how long its modules run, how many markers they carry, and which side of a competing
    idiom each file takes. One pass because each of those alone would not justify the reads."""
    code = [f for f in sorted(files)
            if f.endswith(CODE_SUFFIXES) and not is_generated(f) and not is_secret_path(f)]
    lengths, markers, read, idioms = [], 0, 0, {}
    for relative in code[:MAX_FILES_READ]:
        text = read_file(root, relative)
        if text is None:
            continue
        read += 1
        lengths.append(len(text.splitlines()))
        markers += len(MARKER.findall(text))
        for concern, side in classify_idioms(relative, text).items():
            idioms.setdefault(concern, {}).setdefault(side, []).append(relative)
    return sorted(lengths), markers, read, len(code), idioms


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
    files, root_kind = head_files(root)
    truncated = len(files) >= MAX_PATHS
    probes, attempted, matched = probe_facts(files)
    lengths, markers, read, total_code, idioms = read_code_sample(root, files)
    shape, shape_unknowns = shape_facts(lengths, markers, read, total_code)

    collected = {}
    for entry in (probes + pyproject_facts(root, files) + package_json_facts(root, files)
                  + history_facts(root, commits) + shape):
        collected.setdefault(entry["id"], entry)
    facts = sorted(collected.values(), key=lambda entry: entry["id"])

    alive = liveness(root, files, months, recent_months, depth, commits)
    unknowns = sorted(set(shape_unknowns) | ({"liveness.complete"} if truncated else set()))
    return {
        "schema_version": 1,
        "head": git(root, ["rev-parse", "HEAD"]).strip(),
        "root_kind": root_kind,
        "files_at_head": len(files),
        "probes_attempted": attempted,
        "probes_matched": matched,
        "facts": facts,
        "liveness": alive,
        "conflicts": conflicts_from_config(facts)
                     + conflicts_from_idioms(idioms, alive["directories"], depth),
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


def emit(payload: dict, mode: str, code: int) -> int:
    """Print the document as one JSON object and return the exit code. Every path emits, refusals
    included, so the skill parses one shape and never has to guess. Keys are sorted and no field
    reads the clock: two runs at one commit are byte-identical, and that is a tested promise."""
    print(json.dumps(dict({"contract": CONTRACT_VERSION, "mode": mode}, **payload),
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
