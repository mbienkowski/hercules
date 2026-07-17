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


def test_set_version_bumps_every_canonical_file(tmp_path):
    _seed(tmp_path)
    set_version("9.9.9", root=tmp_path)
    # Parametrized over the list itself: adding a file to VERSION_TARGETS auto-extends the apply check.
    assert read_versions(tmp_path) == {rel: "9.9.9" for rel, _ in VERSION_TARGETS}


@pytest.mark.parametrize("target_rel", [rel for rel, _ in VERSION_TARGETS])
def test_validate_flags_a_hand_edited_drift_in_any_file(tmp_path, target_rel):
    _seed(tmp_path, "1.0.0")
    check_in_sync(tmp_path)  # in sync → no raise
    # Hand-edit exactly one file out of sync — validate must catch it, whichever file it is.
    drifted = tmp_path / target_rel
    drifted.write_text(drifted.read_text(encoding="utf-8").replace("1.0.0", "1.0.1"), encoding="utf-8")
    with pytest.raises(SystemExit, match="drift"):
        check_in_sync(tmp_path)


def test_check_in_sync_enforces_the_expected_tag(tmp_path):
    _seed(tmp_path, "2.0.0")
    check_in_sync(tmp_path, expected="2.0.0")  # equals tag → ok
    with pytest.raises(SystemExit, match="expected"):
        check_in_sync(tmp_path, expected="2.0.1")


def test_committed_manifests_agree_at_the_default_root(monkeypatch):
    # Exercises the production default-root path (what CI `validate` runs) against the real repo:
    # every committed manifest must already carry one identical version.
    monkeypatch.chdir(REPO_ROOT)
    check_in_sync()  # no root arg → Path(".")
    assert len(set(read_versions().values())) == 1


def test_write_version_raises_when_a_version_line_is_missing(tmp_path):
    # If a canonical file has no version line, the bump fails loudly rather than silently no-op.
    _seed(tmp_path, "0.1.0")
    rel = VERSION_TARGETS[0][0]
    (tmp_path / rel).write_text('[project]\nname = "hercules"\n', encoding="utf-8")  # strip version
    with pytest.raises(SystemExit):
        write_version("1.0.0", tmp_path)


# ── B1: the versioned Claude manifest must be a build SOURCE, not a build OUTPUT ──
def test_versioned_claude_manifest_is_the_build_source_not_output(tmp_path):
    """A release bump must survive the next rebuild.

    Regression: ``VERSION_TARGETS`` used to name the *built* ``dist/claude-code/.claude-plugin/
    plugin.json``, which ``build_target`` overwrites from ``src/`` on every build — so a release
    bump was silently reverted on the next rebuild (and then failed the drift gate). The versioned
    Claude manifest must be the *source* file the build copies FROM.
    """
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


def test_release_rebuilds_dist_after_version_bump_and_stages_it():
    """release.yml must rebuild dist/ AFTER bumping the (source) version and stage it in the commit.

    Without the rebuild, the committed/published dist/ keeps the old version and the drift gate
    fails on the next unrelated push. (Companion to B1's version_targets change.)
    """
    set_idx = RELEASE.find("set_version.py")
    build_idx = RELEASE.find("scripts.build.cli")
    assert set_idx != -1, "release must bump the version via set_version.py"
    assert build_idx != -1, "release must rebuild dist/ (python -m scripts.build.cli)"
    assert build_idx > set_idx, "the dist/ rebuild must run AFTER the version bump"
    assert re.search(r"git add[^\n]*\bdist\b", RELEASE), "release must stage dist/ in the bump commit"


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


def test_build_precedes_test_and_validate():
    jobs = _job_needs(CI)
    assert "build" in jobs, "CI must declare a build job"
    assert "build" in jobs.get("test", []), "test must run after build (drift gate first)"
    assert "build" in jobs.get("validate", []), "validate must run after build"


def test_mutation_gates_behind_both_quick_checks():
    # The expensive (~40 min) mutation job must wait for BOTH quick gates, so a red test or a red
    # validate stops it before it burns minutes.
    jobs = _job_needs(CI)
    assert {"test", "validate"} <= set(jobs.get("mutation", [])), \
        "mutation must need both test and validate"


# ── Determinism: two builds are byte-identical ───────────────────────────────
def _files(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): p.read_text(encoding="utf-8")
            for p in root.rglob("*") if p.is_file()}


def test_claude_build_is_deterministic(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    cli.build_target("claude-code", a)
    cli.build_target("claude-code", b)
    assert _files(a) == _files(b)


def test_build_check_prints_make_build_remedy_on_stale_dist(tmp_path, monkeypatch, capsys):
    committed = tmp_path / "claude-code"
    cli.build_target("claude-code", committed)
    (committed / "CLAUDE.md").write_text("STALE", encoding="utf-8")
    monkeypatch.setattr(cli, "DIST", tmp_path)
    rc = cli.main(["--target", "claude-code", "--check"])
    assert rc != 0
    assert "make build" in capsys.readouterr().err
