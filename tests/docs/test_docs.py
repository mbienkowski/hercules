"""Docs match the shipped (marketplace) reality, and contributor rules are recorded (spec 04)."""

from __future__ import annotations

import json
import re

from tests.conftest import ALL_COMMANDS, section


def test_readme_documents_marketplace_install(read_file):
    """README must document the native marketplace install path."""
    content = read_file("README.md")
    assert "/plugin marketplace add" in content, "README must show the marketplace-add command"
    assert "/plugin install" in content, "README must show the plugin-install command"


def test_readme_has_no_removed_cli_references(read_file):
    """README must not reference the removed auto-sync CLI surface."""
    content = read_file("README.md")
    for banned in ["--sync", "--branch", "auto-sync", "every 30 min"]:
        assert banned not in content, f"README still references removed CLI surface: {banned!r}"


def test_readme_states_claude_code_prerequisite(read_file):
    """README must tell newcomers Hercules runs inside Claude Code (the hard prerequisite)."""
    content = read_file("README.md").lower()
    assert "claude code" in content
    assert "prerequisite" in content or "runs inside" in content or "install claude code" in content, \
        "README must state the Claude Code prerequisite up front"


def test_readme_explains_marketplace_plugin_syntax(read_file):
    """README must explain the plugin@marketplace syntax (otherwise hercules@mbienkowski reads as a typo)."""
    assert "plugin@marketplace" in read_file("README.md"), \
        "README must explain that hercules@mbienkowski is plugin@marketplace"


def test_readme_documents_non_interactive_team_install(read_file):
    """README must document the settings.json team/CI install path."""
    content = read_file("README.md")
    assert "enabledPlugins" in content and "extraKnownMarketplaces" in content, \
        "README must show the settings.json team install block (extraKnownMarketplaces + enabledPlugins)"


def test_readme_has_no_misleading_auto_update_claim(read_file):
    """Auto-update exists but is OFF by default for third-party marketplaces — the README must
    document the manual procedure (per-plugin update + reload) and present auto-update only as
    the opt-in it is, never as an unconditional given."""
    content = read_file("README.md")
    assert "keeps the plugin updated" not in content.lower(), \
        "README must not present auto-update as unconditional — it is opt-in per marketplace"
    assert "claude plugin update hercules" in content, \
        "README must document the real per-plugin update command — the `claude plugin update` CLI"
    assert "cli" in content.lower(), \
        "README must state the per-plugin update is a CLI command, not a Claude Code slash command"
    assert "/reload-plugins" in content, \
        "README must tell users to /reload-plugins so an update actually applies"
    assert "auto-update" in content.lower() and "opt-in" in content.lower(), \
        "README must document the opt-in per-marketplace auto-update path"


def test_plugin_version_is_single_sourced(repo_root, read_file):
    """pyproject version must equal the shipped plugin manifest version (no drift)."""
    py = read_file("pyproject.toml")
    m = re.search(r'(?m)^version\s*=\s*"([^"]+)"', py)
    assert m, "pyproject.toml must declare a version"
    plugin_version = json.loads(
        (repo_root / "plugin" / ".claude-plugin" / "plugin.json").read_text()
    )["version"]
    assert m.group(1) == plugin_version, (
        f"version drift: pyproject {m.group(1)!r} != plugin manifest {plugin_version!r}"
    )


def test_shipped_plugin_describes_no_sync_source(repo_root):
    """No shipped plugin content may describe the removed sync source / auto-sync CLI."""
    for path in (repo_root / "plugin").rglob("*.md"):
        low = path.read_text().lower()
        assert "sync source" not in low, f"{path} references a removed 'sync source'"
        assert "auto-sync" not in low, f"{path} references removed auto-sync"


def test_plugin_claude_md_describes_a_plugin_not_a_wrapper(read_file):
    """plugin/CLAUDE.md must describe Hercules as a plugin, not a Python CLI wrapper."""
    content = read_file("plugin/CLAUDE.md")
    assert "Python wrapper for the `claude` CLI" not in content, \
        "plugin/CLAUDE.md must not call Hercules a Python wrapper for the claude CLI"


def test_readme_documents_uninstall(read_file):
    """README must document how to uninstall the plugin and remove its marketplace entry."""
    content = read_file("README.md")
    assert "/plugin uninstall" in content, "README must show the /plugin uninstall command"
    assert "## Uninstalling" in content, "README must have an Uninstalling section"


def test_readme_documents_onboarding_skill(read_file):
    """README must document the code-of-conduct-generator onboarding step for new repos."""
    content = read_file("README.md")
    assert "code-of-conduct-generator" in content, \
        "README must mention the code-of-conduct-generator skill"
    assert "set up this project" in content.lower() or "onboarding" in content.lower(), \
        "README must explain the one-time per-repo onboarding step"


def test_readme_discloses_the_enforcement_hooks_honestly(read_file):
    """The plugin now ships executable hooks, so 'Plugin permissions' must disclose them truthfully:
    they exist, they run before edits (PreToolUse), they are read-only over ~/.hercules, make no
    network calls, and fail open. A prior README claimed the plugin had 'no executable code of its
    own' — this pins that the claim can never silently return alongside shipped hook code."""
    content = read_file("README.md")
    low = content.lower()
    assert "no executable code of its own" not in low, \
        "README must not claim the plugin has no executable code — it ships plugin/hooks/*.py"
    assert "hook" in low, "README 'Plugin permissions' must disclose the enforcement hooks"
    assert "pretooluse" in low, "README must name the PreToolUse hook surface"
    # The three safety properties a reader relies on before trusting a shipped hook:
    assert "read-only" in low or "only **read**" in low or "only read" in low, \
        "README must state the hooks are read-only over ~/.hercules"
    assert "fail **open**" in low or "fail open" in low, \
        "README must state the hooks fail open (never block when no active build)"
    assert "no network" in low or "make no network" in low or "network — none" in low, \
        "README must state the hooks make no network calls"


def test_review_only_agents_carry_no_edit_or_write_tools(repo_root):
    """Review/architecture agents find and decide; they do not author code. Their tool lists must
    never carry Edit/Write — a positive, ongoing guard so a future edit can't quietly grant a
    reviewer write access (the same risk the QA-role test pins for senior-qa-engineer)."""
    agents = repo_root / "plugin" / "agents"
    for name in ("cynical-reviewer", "lead-architect"):
        md = (agents / f"{name}.md").read_text()
        tools_line = next(ln for ln in md.splitlines() if ln.startswith("tools:"))
        assert "Edit" not in tools_line and "Write" not in tools_line, (
            f"{name} must not carry Edit/Write — it reviews/decides, it does not author code "
            f"(tools line: {tools_line!r})"
        )


def test_diagram_scaffold_and_failing_tests_steps_are_gates(read_file):
    """The Build phase's Scaffold and Write-the-failing-tests steps are both described as gates in
    their own st-sub text — they must carry class="step gate" like the other machine-enforced gate
    steps (Quality gates, Mutation gate, Traceability), not bare class="step"."""
    html = read_file("docs/workflow/workflow-diagram-detailed.html")
    assert 'class="step"><span class="st-n">4</span><span class="st-t">Scaffold' not in html, \
        "Scaffold step must not use the un-classed 'step' form"
    assert 'class="step gate"><span class="st-n">4</span><span class="st-t">Scaffold' in html, \
        "Scaffold step (Gate: must compile) must carry the gate CSS class"
    assert 'class="step gate"><span class="st-n">5</span><span class="st-t">Write the failing tests' in html, \
        "Write-the-failing-tests step (Gate: compile and fail for the right reason) must carry the gate CSS class"


def test_requirements_section_discloses_hook_python_runtime(read_file):
    """hooks.json runs python3 on the user's machine on every edit — the Requirements section
    must not call Python contributor-only, and the intro must not deny extra executables."""
    assert "python3" in read_file("plugin/hooks/hooks.json")
    readme = read_file("README.md")
    start = readme.index("## Requirements")
    section = readme[start:readme.index("## ", start + 3)]
    assert "only for contributing" not in section.lower(), \
        "hooks need python3 at runtime — Requirements must say so (and that they fail open without it)"
    assert "you don't need any extra executables" not in readme.lower(), \
        "python3 is an extra executable the hooks use"


def test_readme_does_not_overstate_single_approval(read_file):
    """Phases ask clarifying questions (tier confirm, advisor consent, service paths, ship-each)
    before the gate — the honest claim is one authorizing GATE, not one prompt."""
    assert "One approval per phase; nothing happens before it" not in read_file("README.md")


def test_worked_example_shows_the_complexity_gate(read_file):
    """Password reset is an auth surface floored at high — the example dialogue must show the
    mandatory tier confirmation instead of jumping question → draft → approved."""
    readme = read_file("README.md")
    example = readme[readme.index("### What that looks like"):readme.index("## Where your delivery docs live")]
    assert "complexity" in example.lower(), "the example omits the tier confirmation step"


def test_readme_coverage_enforcement_is_conditioned_on_coc(read_file):
    """Hercules carries no thresholds of its own — coverage gates only when the CoC sets one;
    only traceability is unconditional."""
    assert "Branch coverage and traceability are always enforced" not in read_file("README.md")


def test_uninstall_section_mentions_hercules_home_cleanup(read_file):
    """~/.hercules (project paths + delivery state) survives /plugin uninstall — disclose it."""
    readme = read_file("README.md")
    start = readme.index("## Uninstalling")
    assert ".hercules" in readme[start:readme.index("## ", start + 3)]


def test_readme_discloses_index_and_learnings_artifacts(read_file):
    """Commands write docs/INDEX.md and docs/learnings.md into the user's repo — say so."""
    readme = read_file("README.md")
    assert "INDEX.md" in readme and "learnings" in readme.lower()


def test_readme_advisor_consent_is_consistent(read_file):
    """The board is a recommendation the user approves ('never automatic') — no sentence may
    claim non-trivial tiers run it unconditionally."""
    assert "every other tier runs it" not in read_file("README.md")


def test_license_is_single_sourced(repo_root, read_file):
    """pyproject and the plugin manifest must declare the same license as LICENSE ships."""
    import json as _json
    py = read_file("pyproject.toml")
    plugin = _json.loads((repo_root / "plugin" / ".claude-plugin" / "plugin.json").read_text())
    lic = plugin.get("license", "")
    assert lic and lic.split("-")[0] in py, \
        f"pyproject license must match plugin.json's {lic!r}"


def test_readme_documents_keeping_specs(read_file):
    """Teams with an existing spec practice must learn they can keep delivered specs via a
    code-of-conduct.md directive instead of the default delete-on-delivery."""
    readme = read_file("README.md")
    assert "keep the specs" in readme.lower(), \
        "README must document the keep-the-specs code-of-conduct override"


def test_requirements_disclose_the_windows_python3_gap(read_file):
    """Stock Windows ships python/py, not python3 — there the guard silently never arms
    (fail-open). A README that claims python3 portability without the caveat oversells
    the flagship guard to Windows users."""
    readme = read_file("README.md")
    req = readme[readme.index("**Python 3"):]
    req = req[:req.index("\n\n")]
    assert "Windows" in req, \
        "the python3 requirement must name the Windows gap (python/py, no python3 alias)"


def test_hooks_disclosure_scopes_the_guard_to_editing_tools(read_file):
    """The hook matches Claude Code's editing tools; a shell edit (sed -i) bypasses it and
    is caught by Build's pre-advance git diff instead. Saying the criteria 'can't be
    silently weakened' without that split overstates the hook."""
    readme = read_file("README.md")
    hooks = readme[readme.index("**Hooks**"):]
    hooks = hooks[:hooks.index("- **Shell**")]
    assert "git diff" in hooks or "diff backstop" in hooks, \
        "the disclosure must name the git-diff backstop that covers shell-side edits"


def test_readme_generator_output_filename_is_lowercase(read_file):
    """The README lectures on the CODE_OF_CONDUCT.md-vs-code-of-conduct.md distinction and
    the generator skill hard-rules lowercase — the README's own description of the
    generator's output must not contradict both."""
    readme = read_file("README.md")
    assert "a `CODE_OF_CONDUCT.md` with" not in readme, \
        "the generator produces the lowercase per-project file, not this repo's CoC"
    assert "a `code-of-conduct.md` with" in readme


def test_readme_first_screen_names_the_category(read_file):
    """A skimming engineer's first question is 'what IS this' — the words 'Claude Code
    plugin' must appear in the first ~10 lines, before any mythology."""
    head = "\n".join(read_file("README.md").splitlines()[:10])
    assert "Claude Code plugin" in head, \
        "the first screen must name the product category before the jokes"


def test_readme_explains_the_coc_directive_budget(read_file):
    """README says every agent reads the CoC — it must state the budget as the sentence
    that IS the feature (bare '30'/'40' substrings matched token lifetimes elsewhere)."""
    readme = read_file("README.md")
    assert "the generator aims for **30–40 directives**" in readme
    assert "70 is the hard ceiling" in readme


def test_first_run_gate_never_intercepts_unrelated_work(read_file):
    """The persona is the default agent for EVERY session — an onboarding block that fires
    on any turn in an un-set-up repo hijacks unrelated work and contradicts the README's
    'Optional'. It must apply only to Hercules-directed requests."""
    agent = read_file("plugin/agents/hercules.md")
    gate = agent[agent.index("**First-run onboarding.**"):]
    assert "unrelated" in gate, "the gate must promise never to intercept unrelated work"
    assert "/hercules:" in gate, "the gate must scope itself to Hercules-directed requests"


def test_persona_model_defaults_to_opus(read_file):
    """The default persona declares its default model as the `opus` alias — version-flexible,
    and (unlike a raw `claude-...` id) the exact-match regex here also pins it to the alias.
    Whether `/model` overrides it at runtime is Claude Code behaviour this static check can't
    prove; it is verified empirically in the PR."""
    agent = read_file("plugin/agents/hercules.md")
    head = agent[:agent.index("\n---", 3)]
    assert re.search(r"(?m)^model:\s*opus\s*$", head), \
        "hercules.md frontmatter must declare `model: opus`"


def test_readme_documents_opus_default_and_override(read_file):
    """The user-facing half of the fix: the Plugin permissions Models bullet must say the
    persona defaults to opus and can be changed with `/model`, or the doc silently regresses."""
    readme = read_file("README.md")
    match = re.search(r"## Plugin permissions\n(.*?)(?=\n## |\Z)", readme, re.DOTALL)
    assert match, "README must have a '## Plugin permissions' section"
    perms = match.group(1)
    assert re.search(r"defaults to `?opus`?", perms, re.I), \
        "Models bullet must state the persona defaults to opus"
    assert "/model" in perms, "Models bullet must document the /model override"


def test_readme_citation_doi_is_the_real_paper(read_file):
    """The one load-bearing citation must resolve — a 404 on LinkedIn day flips the whole
    evidence section from rigor to decoration."""
    readme = read_file("README.md")
    assert "science.aec8352" in readme, "cite Cheng et al., Science 2026 (aec8352)"
    assert "adp9289" not in readme, "the old DOI resolves to nothing"


def test_uninstall_lists_repo_side_artifacts(read_file):
    """Uninstalling only mentions ~/.hercules — but the generator wrote code-of-conduct.md
    and an @-line into the user's CLAUDE.md, which keep steering sessions after uninstall."""
    readme = read_file("README.md")
    section = readme[readme.index("## Uninstalling"):]
    section = section[:section.index("\n## ") if "\n## " in section else len(section)]
    assert "code-of-conduct.md" in section and "CLAUDE.md" in section, \
        "uninstall must name the repo-side artifacts the user may want to remove or keep"


def test_abandoning_a_session_has_a_documented_path(read_file):
    """Every other exit is stated at its friction point; abandoning a half-built feature
    had no user-facing path at all. CLAUDE.md must define the mechanics and the README
    must surface the phrase."""
    md = read_file("plugin/CLAUDE.md")
    assert "abandon" in md.lower() and "clear" in md.lower()
    readme = read_file("README.md")
    assert "abandon" in readme.lower(), "the README must tell users they can bail out"


def test_workflow_source_of_truth_is_the_protocol(read_file):
    """The workflow's source of truth is plugin/protocols/workflow-protocol.md — NOT the commands
    or CLAUDE.md. This exact inversion shipped twice in the CoC; this product pin guards the
    concept (which file owns the workflow) so a third re-inversion fails CI. It is scoped to the
    inverted phrasing, so legitimate 'source of truth' mentions about code/state still pass."""
    # Positive: the protocol crowns itself, and the CoC names it as the owner.
    protocol = read_file("plugin/protocols/workflow-protocol.md").lower()
    assert "source of truth" in protocol and "workflow" in protocol, \
        "workflow-protocol.md must name itself the source of truth for the workflow"
    coc_section = section(read_file("CODE_OF_CONDUCT.md"), "### Changing the workflow", "\n### ",
                          label="CODE_OF_CONDUCT.md")
    assert "workflow-protocol.md" in coc_section, \
        "the CoC 'Changing the workflow' section must name workflow-protocol.md as the source of truth"

    # Negative: the exact twice-shipped inversion — "workflow's source of truth is ... command",
    # with no "protocol" in between — must be absent from the CoC section and every command.
    inverted = re.compile(r"workflow'?s source of truth\s+is\b(?:(?!protocol).){0,60}?command",
                          re.IGNORECASE | re.DOTALL)
    for rel in ["CODE_OF_CONDUCT.md", *ALL_COMMANDS]:
        assert not inverted.search(read_file(rel)), \
            f"{rel} crowns the commands as the workflow's source of truth (the twice-shipped inversion)"


def test_claude_md_defines_code_of_conduct_resolution(read_file):
    """The CoC is resolved by a matcher in the correct repo — defined once in CLAUDE.md so every
    phase resolves it the same way, never a fixed filename and never the path-nearest file."""
    resolution = section(read_file("plugin/CLAUDE.md"),
                         "## Code-of-conduct resolution", "\n## ", label="CLAUDE.md")
    low = resolution.lower()
    assert "any capitalization" in low or "case-insensitiv" in low, \
        "resolution must match the CoC by name-pattern (any capitalization), not a fixed filename"
    assert "repositories" in resolution and "directory" in resolution, \
        "resolution must scope the CoC to the target repo (repositories[service] / directory)"
    assert "nearest" in low or "closest" in low or "launch" in low, \
        "resolution must forbid grabbing the launch/nearest-path CoC over the target repo's"
    assert "validate" in low or "confirm" in low, \
        "resolution must validate the match belongs to the target repo before trusting it"
    # Single-match branch stated explicitly (the none and >1 branches already are): a lone match
    # resolves with no extra prompt, so a phase never over-asks on the common one-file case.
    assert "exactly one" in low and "no extra prompt" in low, \
        "resolution must state the single-match branch: exactly one match → use it, no extra prompt"


def test_build_service_coc_read_uses_the_matcher_not_a_fixed_name(read_file):
    """Build's service-scoped CoC read must resolve by matcher (any capitalization), not a fixed
    lowercase {service-path}/code-of-conduct.md that would miss CODE_OF_CONDUCT.md on Linux."""
    assert "{service-path}/code-of-conduct.md" not in read_file("plugin/commands/build.md"), \
        "build must not read a fixed-lowercase service CoC path — resolve it by matcher"
