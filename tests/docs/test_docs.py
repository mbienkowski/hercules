"""Docs match the shipped (marketplace) reality, and contributor rules are recorded (spec 04)."""

from __future__ import annotations

import json
import re


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
    assert "/plugin update" in content, "README must document the per-plugin update command"
    assert "/plugin marketplace update" in content, \
        "README must document the marketplace-wide update command"
    assert "/reload-plugins" in content, \
        "README must tell users to /reload-plugins so an update actually applies"
    assert "auto-update" in content.lower() and "opt-in" in content.lower(), \
        "README must document the opt-in per-marketplace auto-update path"



def test_code_of_conduct_whats_tested_rows_point_at_existing_files(repo_root, read_file):
    """Every test path named in CODE_OF_CONDUCT.md must exist (no stale 'what's covered' rows)."""
    content = read_file("CODE_OF_CONDUCT.md")
    referenced = set(re.findall(r"tests/[\w/]+\.py", content))
    missing = [p for p in referenced if not (repo_root / p).exists()]
    assert not missing, f"CODE_OF_CONDUCT.md references non-existent test files: {sorted(missing)}"


def test_code_of_conduct_states_contributor_invariants(read_file):
    """CODE_OF_CONDUCT.md must record the contributor invariants this migration relies on."""
    content = read_file("CODE_OF_CONDUCT.md").lower()
    assert "owning test" in content, "CoC must require every shipped artifact to have an owning test"
    assert "single source" in content or "single-source" in content, \
        "CoC must record version single-sourcing across pyproject and the plugin manifest"


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


def test_coc_agent_rule_spec_lifecycle_admits_keep_specs(read_file):
    """The 'adding an agent' rule states a spec is delete-once — under a keep-specs
    code-of-conduct a delivered spec is refreshed at retire instead, so the contributor rule
    must carry the same carve-out or it forbids behaviour the plugin itself performs."""
    coc = read_file("CODE_OF_CONDUCT.md")
    rule = coc[coc.index("delete-once"):]
    rule = rule[:rule.index("- Replies follow")]
    assert "keep-specs" in rule or "keep_specs" in rule, \
        "the delete-once rule must acknowledge the keep-specs retire mode (orchestrator-only)"


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


def test_coc_adding_an_agent_names_every_synced_surface(read_file):
    """tests/agents enforces settings.json advisors[] ↔ roster sync and a CLAUDE.md
    listing — a contributor following the CoC's steps must not discover extra required
    files only from CI failures."""
    coc = read_file("CODE_OF_CONDUCT.md")
    section = coc[coc.index("### Adding an agent"):coc.index("### Hooks")]
    assert "settings.json" in section, \
        "the adding-an-agent steps must name the settings.json advisors[] roster"
    assert "CLAUDE.md" in section, "…and the CLAUDE.md agent list"


def test_coc_tokens_section_is_honest_about_the_encoding_fetch(read_file):
    """tiktoken downloads the cl100k encoding on first use — 'no network call' is only
    true after a warm cache, and a fresh contributor's make test dies offline. The CoC
    must document the cache instead of denying the fetch."""
    coc = read_file("CODE_OF_CONDUCT.md")
    tokens = coc[coc.index("### Tokens"):coc.index("### Golden files")]
    assert "no network call" not in tokens, \
        "the offline claim only holds after a warm cache — say that instead"
    assert "TIKTOKEN_CACHE_DIR" in tokens, \
        "contributors need the cache variable to run the suite offline"


def test_coc_documents_the_prose_pin_convention(read_file):
    """Most of the suite pins command prose — a contributor rewording a sentence needs
    to know to grep tests/ for it BEFORE CI tells them, or every wording change costs a
    failed run."""
    coc = read_file("CODE_OF_CONDUCT.md").lower()
    assert "grep" in coc and "pinned" in coc, \
        "the CoC must tell contributors that prose is test-pinned and how to find the pins"


def test_readme_explains_the_coc_directive_budget(read_file):
    """README says every agent reads the CoC — it must also say that budget is finite
    (30–40 directives sweet spot) so users don't paste an 80-bullet org standard."""
    readme = read_file("README.md")
    assert "30" in readme and "40" in readme and "directive" in readme.lower(), \
        "README must state the CoC directive budget where it praises the CoC"
