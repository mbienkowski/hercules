"""A relative `docs_root` — the DOCUMENTED default (`hercules-reference § Artifact root resolution`
says it defaults to `"docs"`) — must resolve against the registry's OWN `directory` field, never
against whatever directory happens to be the calling process's cwd at the moment.

Before this fix, `canon(docs_root)` resolved a relative string with a bare `os.path.realpath`, which
answers relative to the CALLING PROCESS's cwd. That is correct only by coincidence — whenever the
agent's shell happens to sit at the project root, which is the common case but not a guarantee
`build.md`'s own service-scoped instructions make: they explicitly move the shell's cwd to
`{service-path}` for a Bash call. `test_the_documents_root_resolves_regardless_of_process_cwd` below
reproduces the exact condition that made this reachable, and would have failed before the fix — the
default fixture below places `directory` and the pytest process's actual cwd at two DIFFERENT paths,
which the old `canon()`-only check could never bridge.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.scripts.tools.tool_harness import invoke, load_tool, write_hercules_home

main = load_tool("retire_spec")

SLUG = "relproj"
SESSION = "2026-08-04-relative-docs"
SPEC = "2026-08-04-relative-docs-spec-01-thing.md"


def _same_repo_home(tmp_path: Path, *, docs_root="docs", with_directory: bool = True):
    """The SAME-REPO layout the documented default actually describes: docs/ lives INSIDE the
    project directory, not beside it in a separate tree — unlike the shared `build_home` fixture,
    which keeps them apart and so never exercises this join at all."""
    project = tmp_path / "code"
    docs = project / "docs"
    spec_dir = docs / SESSION
    spec_dir.mkdir(parents=True)
    spec_path = spec_dir / SPEC
    spec_path.write_text(f"# {SPEC}\n", encoding="utf-8")

    entry_extra = {"docs_root": docs_root} if with_directory else {}
    home = write_hercules_home(
        tmp_path, slug=SLUG, project=project, docs=docs, docs_root=docs_root,
        sessions={SESSION: {"tier": "medium", "current_phase": "build",
                            "current_spec": SPEC, "pending_specs": []}},
        active_session=SESSION,
    )
    if not with_directory:
        # Simulate a registry entry with docs_root set but no directory recorded — the one case
        # this tool genuinely cannot resolve on its own.
        entry = home.entry()
        entry.pop("directory")
        home.config_path.write_text(
            __import__("json").dumps({"schema_version": 1, "projects": {SLUG: entry}}))
    return home, spec_path


def test_the_documents_root_resolves_regardless_of_process_cwd(tmp_path, monkeypatch):
    """The exact reproduction: docs_root is the relative default, and the calling process's cwd is
    somewhere else entirely — a bare directory alongside the project, sharing no prefix with it."""
    home, spec_path = _same_repo_home(tmp_path)
    elsewhere = tmp_path / "not-the-project-at-all"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    code, payload = invoke(main, home.home, ["plan", "--project-slug", SLUG,
                                            "--session-id", SESSION,
                                            "--spec-file", str(spec_path)])
    assert code == 0, payload
    assert payload["spec"]["name"] == SPEC


def test_a_spec_genuinely_outside_the_resolved_root_is_still_refused(tmp_path, monkeypatch):
    """The fix must not turn the containment check into a no-op — only the RESOLUTION of the root
    changed, not whether a spec outside it is still caught."""
    home, _spec_path = _same_repo_home(tmp_path)
    monkeypatch.chdir(tmp_path)
    outside = tmp_path / "definitely-not-docs" / SPEC
    outside.parent.mkdir()
    outside.write_text("# not really the spec\n", encoding="utf-8")

    code, payload = invoke(main, home.home, ["plan", "--project-slug", SLUG,
                                            "--session-id", SESSION,
                                            "--spec-file", str(outside)])
    assert code == 1
    assert payload["rule"] == "spec_outside_docs_root"


def test_a_missing_docs_root_defaults_to_docs_rather_than_skipping_the_check(tmp_path, monkeypatch):
    """docs_root is documented to default to "docs" when absent. The old behaviour treated a falsy
    docs_root as "no root to check against" and let ANY path through — a weaker assertion here
    (just `code == 0` for a spec that is genuinely under docs/) would pass either way and prove
    nothing, so the discriminating half is the second call: a spec OUTSIDE docs/ must now be
    refused, which only happens if the default is actually being enforced rather than skipped."""
    home, spec_path = _same_repo_home(tmp_path, docs_root="docs")
    entry = home.entry()
    entry.pop("docs_root", None)  # absent, not merely empty — the real "never configured" case
    import json
    home.config_path.write_text(json.dumps({"schema_version": 1, "projects": {SLUG: entry}}))
    monkeypatch.chdir(tmp_path)

    code, payload = invoke(main, home.home, ["plan", "--project-slug", SLUG,
                                            "--session-id", SESSION,
                                            "--spec-file", str(spec_path)])
    assert code == 0, payload  # the spec IS under the defaulted "docs" root, so this still resolves

    outside = home.project / "elsewhere" / SPEC
    outside.parent.mkdir(parents=True)
    outside.write_text("# not under docs/ at all\n", encoding="utf-8")
    code, payload = invoke(main, home.home, ["plan", "--project-slug", SLUG,
                                            "--session-id", SESSION,
                                            "--spec-file", str(outside)])
    assert code == 1, "a defaulted docs_root that enforces nothing is a default that does nothing"
    assert payload["rule"] == "spec_outside_docs_root"


def test_a_relative_docs_root_with_no_directory_on_record_is_refused_not_guessed(tmp_path, monkeypatch):
    """The one case this tool truly cannot resolve on its own. It must refuse clearly rather than
    fall back to the calling process's cwd — the refusal message is what tells the AGENT to ask the
    user for the real path, since a non-interactive CLI cannot ask directly."""
    home, spec_path = _same_repo_home(tmp_path, with_directory=False)
    monkeypatch.chdir(tmp_path)  # even sitting right next to the project, it must not guess

    code, payload = invoke(main, home.home, ["plan", "--project-slug", SLUG,
                                            "--session-id", SESSION,
                                            "--spec-file", str(spec_path)])
    assert code == 1
    assert payload["rule"] == "docs_root_unresolvable"
    assert "ask the user" in payload["message"].lower()


def test_an_absolute_separate_repo_docs_root_is_unaffected(tmp_path, monkeypatch):
    """The other documented case — a dedicated requirements repo — already stores docs_root as an
    absolute, user-confirmed path (resolved once, interactively, at Discover) and must pass through
    exactly as before: this fix changes how a RELATIVE root resolves, never an absolute one."""
    project = tmp_path / "code"
    project.mkdir()
    separate_docs = tmp_path / "requirements-repo"
    spec_dir = separate_docs / SESSION
    spec_dir.mkdir(parents=True)
    spec_path = spec_dir / SPEC
    spec_path.write_text(f"# {SPEC}\n", encoding="utf-8")

    home = write_hercules_home(
        tmp_path, slug=SLUG, project=project, docs=separate_docs,
        docs_root=str(separate_docs),  # absolute, exactly as Discover would have cached it
        sessions={SESSION: {"tier": "medium", "current_phase": "build",
                            "current_spec": SPEC, "pending_specs": []}},
        active_session=SESSION,
    )
    elsewhere = tmp_path / "somewhere-unrelated"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    code, payload = invoke(main, home.home, ["plan", "--project-slug", SLUG,
                                            "--session-id", SESSION,
                                            "--spec-file", str(spec_path)])
    assert code == 0, payload
