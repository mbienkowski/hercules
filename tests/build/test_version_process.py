"""Spec 05 — the release/CI integration seam.

Pins the single-source version process and the CI job graph so the writer (``set_version``), the
reader (CI ``validate``), and the drift/determinism gates can never silently disagree.

Frozen for spec-05-ci-release-integration.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from scripts.build import cli
from scripts.build.version_targets import (
    VERSION_TARGETS,
    check_in_sync,
    read_versions,
    write_version,
)
from scripts.set_version import set_version

REPO_ROOT = Path(__file__).resolve().parents[2]
CI = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
RELEASE = (REPO_ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")


# ── The canonical version list: writer + reader pinned at both ends ──────────
def _seed(root: Path, version: str = "0.1.0") -> None:
    """Materialise every canonical file under *root* carrying *version*."""
    for rel, fmt in VERSION_TARGETS:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if fmt == "toml":
            p.write_text(f'[project]\nname = "hercules"\nversion = "{version}"\n', encoding="utf-8")
        else:
            p.write_text(f'{{\n  "name": "hercules",\n  "version": "{version}"\n}}\n', encoding="utf-8")


def test_bumping_the_version_updates_every_canonical_file(tmp_path):
    """Running the version bump writes the new version number into every file that is supposed
    to track it, not just some of them. If any canonical file were missed, that file would
    silently keep announcing the old, wrong version to users or tooling."""
    _seed(tmp_path)
    set_version("9.9.9", root=tmp_path)
    # Parametrized over the list itself: adding a file to VERSION_TARGETS auto-extends the apply check.
    assert read_versions(tmp_path) == {rel: "9.9.9" for rel, _ in VERSION_TARGETS}


@pytest.mark.parametrize("target_rel", [rel for rel, _ in VERSION_TARGETS])
def test_editing_one_version_file_by_hand_is_caught_no_matter_which_file(tmp_path, target_rel):
    """If someone manually edits the version number in any single one of the tracked files so
    it no longer matches the rest, the sync check must catch the mismatch -- regardless of which
    file was touched. This guarantees a partial, out-of-band edit can never slip through
    unnoticed."""
    _seed(tmp_path, "1.0.0")
    check_in_sync(tmp_path)  # in sync → no raise
    # Hand-edit exactly one file out of sync — validate must catch it, whichever file it is.
    drifted = tmp_path / target_rel
    drifted.write_text(drifted.read_text(encoding="utf-8").replace("1.0.0", "1.0.1"), encoding="utf-8")
    with pytest.raises(SystemExit, match="drift"):
        check_in_sync(tmp_path)


def test_sync_check_rejects_a_version_that_doesnt_match_the_expected_release_tag(tmp_path):
    """When a specific version is expected (for example, a release tag), the sync check passes
    only if every file actually carries that exact version, and fails otherwise. This stops a
    build from being tagged and shipped under the wrong version number."""
    _seed(tmp_path, "2.0.0")
    check_in_sync(tmp_path, expected="2.0.0")  # equals tag → ok
    with pytest.raises(SystemExit, match="expected"):
        check_in_sync(tmp_path, expected="2.0.1")


def test_the_real_repositorys_committed_files_all_report_the_same_version(monkeypatch):
    """Running the sync check against the actual project (the same way the CI job does) confirms
    that every committed file which records a version currently agrees on one single value. This
    is the live guardrail that keeps the real repository's release files from drifting apart."""
    # Exercises the production default-root path (what CI `validate` runs) against the real repo:
    # every committed manifest must already carry one identical version.
    monkeypatch.chdir(REPO_ROOT)
    check_in_sync()  # no root arg → Path(".")
    assert len(set(read_versions().values())) == 1


def test_bumping_the_version_fails_loudly_if_a_file_has_no_version_line(tmp_path):
    """If one of the canonical files is missing its version line entirely, attempting to bump the
    version stops with an error instead of silently doing nothing. A silent no-op here would leave
    that file frozen on a stale version forever."""
    # If a canonical file has no version line, the bump fails loudly rather than silently no-op.
    _seed(tmp_path, "0.1.0")
    rel = VERSION_TARGETS[0][0]
    (tmp_path / rel).write_text('[project]\nname = "hercules"\n', encoding="utf-8")  # strip version
    with pytest.raises(SystemExit):
        write_version("1.0.0", tmp_path)


# ── B1: the versioned Claude manifest must be a build SOURCE, not a build OUTPUT ──
def test_a_release_version_bump_survives_the_next_build(tmp_path):
    """A version number bumped during a release must still be in place after the project is
    rebuilt from source. Regression: the version used to be recorded only in a generated build
    output, which gets overwritten from source on every build -- so a release bump was silently
    erased by the very next build, and then flagged as drifted. The fix keeps the version
    recorded in the source file the build reads from, not in a file the build overwrites."""
    version_paths = [rel for rel, _ in VERSION_TARGETS]
    assert "src/targets/claude-code/plugin.json" in version_paths
    assert not any(rel.startswith("dist/") for rel in version_paths), (
        "a build OUTPUT must never be a version target — it is regenerated from src on every build"
    )
    # Behavioural: the version in the (source) target file is exactly what a fresh build emits.
    src_version = read_versions(REPO_ROOT)["src/targets/claude-code/plugin.json"]
    out = tmp_path / "claude-code"
    cli.build_target("claude-code", out)
    built = json.loads((out / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert built["version"] == src_version


def test_the_release_process_rebuilds_and_commits_the_output_after_bumping_the_version():
    """The release workflow must rebuild the distributable build output after bumping the
    version, and include that rebuilt output in the release commit. Skipping the rebuild would
    leave the shipped build carrying the old version number, causing the very next unrelated
    change to fail the version-sync check.

    CI is Makefile-driven (CODE_OF_CONDUCT \u00a7 Invariants): the workflow runs `make` targets in order,
    and the underlying commands live in the Makefile + scripts/ci/ \u2014 so this pins the behaviour at
    its real home, not an inline YAML block."""
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    commit_sh = (REPO_ROOT / "scripts" / "ci" / "release_commit.sh").read_text(encoding="utf-8")
    # The workflow runs the three make targets in order: bump \u2192 rebuild \u2192 commit.
    ver_idx = RELEASE.find("make release-version")
    build_idx = RELEASE.find("make build")
    commit_idx = RELEASE.find("make release-commit")
    assert -1 not in (ver_idx, build_idx, commit_idx), \
        "release must run `make release-version`, `make build`, `make release-commit`"
    assert ver_idx < build_idx < commit_idx, "order must be version-bump \u2192 rebuild \u2192 commit"
    # `make release-version` bumps via the MODULE form (`python -m scripts.set_version`), so its
    # `from scripts.build...` import resolves; the file-path form raises ModuleNotFoundError.
    assert "-m scripts.set_version" in makefile, \
        "make release-version must bump via `python -m scripts.set_version` (module form)"
    # release_commit.sh stages the rebuilt dist/ into the bump commit.
    assert re.search(r"git add[^\n]*\bdist\b", commit_sh), \
        "release_commit.sh must stage dist/ in the bump commit"


def test_release_acts_only_on_the_ci_validated_commit():
    """The release runs on a ``workflow_run`` event, whose checkout resolves to main's CURRENT tip
    -- which can advance past the commit whose CI actually passed. Releasing that unvalidated tree
    would defeat the green-CI gate. Guard the fix so it cannot silently regress: the release job
    must EITHER pin the checkout ref to ``github.event.workflow_run.head_sha``, OR contain a step
    that compares ``git rev-parse HEAD`` to that sha and exits non-zero on mismatch."""
    verify_sh = (REPO_ROOT / "scripts" / "ci" / "release_verify_checkout.sh").read_text(encoding="utf-8")
    head_sha = "github.event.workflow_run.head_sha"
    pinned = f"ref: ${{{{ {head_sha} }}}}" in RELEASE
    # Guarded: the workflow passes the CI-validated sha (as WANT_SHA) to `make release-verify`, whose
    # script compares it to `git rev-parse HEAD` and exits non-zero on mismatch.
    guarded = (head_sha in RELEASE) and ("rev-parse HEAD" in verify_sh) and ("exit 1" in verify_sh)
    assert pinned or guarded, (
        "release must act only on the CI-validated commit: pin the checkout ref to "
        "${{ github.event.workflow_run.head_sha }}, or pass that sha to a release-verify step whose "
        "script compares `git rev-parse HEAD` to it and exits non-zero on mismatch (workflow_run "
        "checks out the branch tip, which can advance past the validated commit)"
    )


# ── CI job graph invariants (build precedes test/validate) ───────────────────
def _job_needs(text: str) -> dict[str, list[str]]:
    """Parse ``jobs.<name>.needs`` from a workflow (inline ``needs: [a, b]`` form)."""
    jobs: dict[str, list[str]] = {}
    in_jobs = False
    current: str | None = None
    for line in text.splitlines():
        if re.match(r"^jobs:\s*$", line):
            in_jobs = True
            continue
        if not in_jobs:
            continue
        job = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
        if job:
            current = job.group(1)
            jobs[current] = []
            continue
        needs = re.match(r"^    needs:\s*\[([^\]]*)\]", line)
        if needs and current:
            jobs[current] = [x.strip() for x in needs.group(1).split(",") if x.strip()]
    return jobs


def test_automated_checks_only_run_against_a_freshly_built_project():
    """The continuous-integration pipeline runs its test and validation checks only after the
    project has been built, never before. Running these checks against a stale or missing build
    would let real problems slip through undetected."""
    jobs = _job_needs(CI)
    assert "build" in jobs, "CI must declare a build job"
    assert "build" in jobs.get("test", []), "test must run after build (drift gate first)"
    assert "build" in jobs.get("validate", []), "validate must run after build"


def test_the_slow_mutation_check_waits_for_both_quick_checks_to_pass_first():
    """The expensive, long-running mutation check only starts after both the fast test run and
    the fast validation check have succeeded. This way a quick, obvious failure stops the
    pipeline immediately instead of wasting around 40 minutes running the slow check anyway."""
    # The expensive (~40 min) mutation job must wait for BOTH quick gates, so a red test or a red
    # validate stops it before it burns minutes.
    jobs = _job_needs(CI)
    assert {"test", "validate"} <= set(jobs.get("mutation", [])), \
        "mutation must need both test and validate"


def test_the_pipeline_fails_if_the_build_output_is_not_committed_to_source_control():
    """The continuous-integration pipeline includes a dedicated check that fails the build if
    the generated output folder is left untracked by version control. Without this guard, a
    release tag could silently capture an empty or missing build."""
    # dist/ must be tracked, not silently git-ignored (a tag would then snapshot an empty tree).
    # The guard runs via `make ci-build`; its logic lives in scripts/ci/build_gates.sh (CI is
    # Makefile-driven — no inline YAML). Anchor the check to that script, not a whole-file substring.
    gates_sh = (REPO_ROOT / "scripts" / "ci" / "build_gates.sh").read_text(encoding="utf-8")
    assert "make ci-build" in CI, "CI must run the build gates via `make ci-build`"
    assert "git status --porcelain" in gates_sh and "dist" in gates_sh, \
        "build_gates.sh must check git status on dist/ (the untracked-dist guard)"


# ── Determinism: two builds are byte-identical ───────────────────────────────
def _files(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): p.read_text(encoding="utf-8")
            for p in root.rglob("*") if p.is_file()}


def test_building_the_project_twice_produces_byte_identical_output(tmp_path):
    """Running the build process twice from the same source must produce exactly the same
    files, byte for byte. If two builds could differ, released artifacts would not be
    reproducible and could not be trusted to match their source."""
    a, b = tmp_path / "a", tmp_path / "b"
    cli.build_target("claude-code", a)
    cli.build_target("claude-code", b)
    assert _files(a) == _files(b)


def test_a_stale_build_output_is_reported_with_instructions_to_fix_it(tmp_path, monkeypatch, capsys):
    """When the committed build output no longer matches what a fresh build would produce, the
    check step fails and prints the exact command the developer needs to run to fix it. This
    turns a confusing drift failure into an actionable, one-line remedy."""
    committed = tmp_path / "claude-code"
    cli.build_target("claude-code", committed)
    (committed / "CLAUDE.md").write_text("STALE", encoding="utf-8")
    monkeypatch.setattr(cli, "DIST", tmp_path)
    rc = cli.main(["--target", "claude-code", "--check"])
    assert rc != 0
    assert "make build" in capsys.readouterr().err
