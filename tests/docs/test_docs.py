"""Docs match the shipped (marketplace) reality, and contributor rules are recorded (spec 04)."""

from __future__ import annotations

import json
import re

from tests.conftest import ALL_COMMANDS, section


def test_readme_explains_how_to_install_via_the_marketplace(read_file):
    """New users reading the README must find the exact commands for adding the marketplace
    and installing the plugin, so they can get Hercules running without guessing at command
    names."""
    content = read_file("README.md")
    assert "/plugin marketplace add" in content, "README must show the marketplace-add command"
    assert "/plugin install" in content, "README must show the plugin-install command"


def test_readme_never_mentions_the_removed_auto_sync_cli(read_file):
    """The README must not mention the auto-sync CLI flags and schedule that were removed
    from the product; a leftover reference would send users hunting for commands that no
    longer exist."""
    content = read_file("README.md")
    for banned in ["--sync", "--branch", "auto-sync", "every 30 min"]:
        assert banned not in content, f"README still references removed CLI surface: {banned!r}"


def test_readme_explains_how_teams_can_install_without_clicking_through_prompts(read_file):
    """Teams and CI pipelines need to install Hercules by editing settings.json rather than
    answering interactive prompts; the README must show that settings.json block (marketplace
    entry plus enabled plugin) so automated setups aren't left guessing."""
    content = read_file("README.md")
    assert "enabledPlugins" in content and "extraKnownMarketplaces" in content, \
        "README must show the settings.json team install block (extraKnownMarketplaces + enabledPlugins)"


def test_readme_never_implies_updates_happen_automatically_by_default(read_file):
    """Auto-update exists but is off by default for third-party marketplaces, so the README
    must describe the manual update steps (the per-plugin update command, then reloading
    plugins) and present automatic updates only as an opt-in feature -- never as something
    that just happens on its own."""
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


def test_the_published_version_number_matches_across_packaging_files(repo_root, read_file):
    """The version number declared for the Python package and the version shipped inside the
    plugin manifest must always agree, so users and package managers never see two different
    version numbers for the same release."""
    py = read_file("pyproject.toml")
    m = re.search(r'(?m)^version\s*=\s*"([^"]+)"', py)
    assert m, "pyproject.toml must declare a version"
    plugin_version = json.loads(
        (repo_root / "dist" / "claude-code" / ".claude-plugin" / "plugin.json").read_text()
    )["version"]
    assert m.group(1) == plugin_version, (
        f"version drift: pyproject {m.group(1)!r} != plugin manifest {plugin_version!r}"
    )


def test_shipped_documentation_never_mentions_the_removed_sync_feature(repo_root):
    """None of the documentation files packaged with the plugin may describe the removed
    'sync source' or 'auto-sync' feature; a stray mention would describe functionality that
    no longer exists and mislead anyone reading the shipped docs."""
    for path in (repo_root / "dist" / "claude-code").rglob("*.md"):
        low = path.read_text().lower()
        assert "sync source" not in low, f"{path} references a removed 'sync source'"
        assert "auto-sync" not in low, f"{path} references removed auto-sync"


def test_readme_explains_how_to_fully_uninstall_the_plugin(read_file):
    """Users who want to remove Hercules must be able to find the uninstall command and
    instructions for removing the marketplace entry in the README's Uninstalling section."""
    content = read_file("README.md")
    assert "/plugin uninstall" in content, "README must show the /plugin uninstall command"
    assert "## Uninstalling" in content, "README must have an Uninstalling section"


def test_readme_explains_the_one_time_setup_step_for_new_projects(read_file):
    """New repositories need a one-time onboarding step that generates a code of conduct;
    the README must mention this skill by name and explain that it is a one-time per-repo
    step, so users don't miss it or think it needs to run every session."""
    content = read_file("README.md")
    assert "code-of-conduct-generator" in content, \
        "README must mention the code-of-conduct-generator skill"
    assert "set up this project" in content.lower() or "onboarding" in content.lower(), \
        "README must explain the one-time per-repo onboarding step"


def test_readme_truthfully_discloses_that_the_plugin_runs_code_automatically(read_file):
    """The plugin ships executable hooks that run automatically before every edit, so the
    'Plugin permissions' section must disclose this plainly and state the three safety
    guarantees users rely on: the hooks only read (never write) files, make no network calls,
    and fail safely (never block work) rather than crash. An older README claimed the plugin
    had 'no executable code of its own' -- this guarantees that false claim can never quietly
    return alongside the shipped hooks."""
    content = read_file("README.md")
    low = content.lower()
    assert "no executable code of its own" not in low, \
        "README must not claim the plugin has no executable code — it ships src/hooks/*.py"
    assert "hook" in low, "README 'Plugin permissions' must disclose the enforcement hooks"
    assert "pretooluse" in low, "README must name the PreToolUse hook surface"
    # The three safety properties a reader relies on before trusting a shipped hook:
    assert "read-only" in low or "only **read**" in low or "only read" in low, \
        "README must state the hooks are read-only over ~/.hercules"
    assert "fail **open**" in low or "fail open" in low, \
        "README must state the hooks fail open (never block when no active build)"
    assert "no network" in low or "make no network" in low or "network — none" in low, \
        "README must state the hooks make no network calls"


def test_review_and_architecture_agents_can_never_be_granted_edit_permissions(repo_root):
    """The agents whose job is to review and decide, not to write code, must never be granted
    edit or write permissions in their configuration -- otherwise a future change could
    quietly let a reviewer start authoring code instead of only judging it (the same risk
    already guarded for the senior-qa-engineer role)."""
    agents = repo_root / "dist" / "claude-code" / "agents"
    for name in ("cynical-reviewer", "lead-architect"):
        md = (agents / f"{name}.md").read_text()
        tools_line = next(ln for ln in md.splitlines() if ln.startswith("tools:"))
        assert "Edit" not in tools_line and "Write" not in tools_line, (
            f"{name} must not carry Edit/Write — it reviews/decides, it does not author code "
            f"(tools line: {tools_line!r})"
        )


def test_readme_admits_the_safety_hooks_need_python_installed_to_run(read_file):
    """The safety hooks run a Python script on the user's machine every time a file is edited,
    so the Requirements section must not claim Python is only needed by contributors, and the
    introduction must not claim no extra software is required."""
    assert "python3" in read_file("dist/claude-code/hooks/hooks.json")
    readme = read_file("README.md")
    start = readme.index("## Requirements")
    section = readme[start:readme.index("## ", start + 3)]
    assert "only for contributing" not in section.lower(), \
        "hooks need python3 at runtime — Requirements must say so (and that they fail open without it)"
    assert "you don't need any extra executables" not in readme.lower(), \
        "python3 is an extra executable the hooks use"


def test_readme_does_not_claim_only_one_approval_happens_per_phase(read_file):
    """Phases actually ask several clarifying questions (tier confirmation, advisor consent,
    service paths, ship-each) before reaching their approval gate, so the README must not
    claim a single approval is the only thing that happens -- overstating it would mislead
    users about how much they'll be asked along the way."""
    assert "One approval per phase; nothing happens before it" not in read_file("README.md")


def test_uninstall_instructions_mention_that_saved_project_data_survives(read_file):
    """Uninstalling the plugin does not delete the user's saved project paths and delivery
    history stored outside the plugin; the Uninstalling section must disclose that this data
    survives, so users aren't caught off guard by leftover state after they thought they'd
    removed everything."""
    readme = read_file("README.md")
    start = readme.index("## Uninstalling")
    assert ".hercules" in readme[start:readme.index("## ", start + 3)]


def test_readme_discloses_that_commands_write_files_into_the_users_repository(read_file):
    """Running commands creates docs/INDEX.md and docs/learnings.md inside the user's own
    repository; the README must mention both files so users aren't surprised to find new
    files added by the tool."""
    readme = read_file("README.md")
    assert "INDEX.md" in readme and "learnings" in readme.lower()


def test_readme_never_claims_the_advisory_board_runs_without_approval(read_file):
    """The advisory board is only ever a recommendation the user must approve -- the README
    must not contain a sentence claiming it runs unconditionally on other tiers, which would
    misrepresent it as fully automatic."""
    assert "every other tier runs it" not in read_file("README.md")


def test_the_declared_license_matches_across_packaging_files(repo_root, read_file):
    """The license named in the Python package metadata and the license named in the shipped
    plugin manifest must agree, so the license a user sees on installation matches what is
    actually shipped."""
    import json as _json
    py = read_file("pyproject.toml")
    plugin = _json.loads((repo_root / "dist" / "claude-code" / ".claude-plugin" / "plugin.json").read_text())
    lic = plugin.get("license", "")
    assert lic and lic.split("-")[0] in py, \
        f"pyproject license must match plugin.json's {lic!r}"


def test_readme_warns_windows_users_the_safety_guard_may_silently_never_activate(read_file):
    """Stock Windows installs ship 'python' or 'py' but not a 'python3' command, so on those
    machines the safety guard can silently never turn on. The README's Python requirement
    must call out this Windows-specific gap, or Windows users would believe they have
    protection they don't actually have."""
    readme = read_file("README.md")
    req = readme[readme.index("**Python 3"):]
    req = req[:req.index("\n\n")]
    assert "Windows" in req, \
        "the python3 requirement must name the Windows gap (python/py, no python3 alias)"


def test_readme_explains_that_shell_edits_are_covered_by_a_different_safeguard(read_file):
    """The safety hook only watches the built-in editing tools, so an edit made through a
    shell command (like sed) can slip past it; that gap is closed instead by a separate
    git-diff check before a phase advances. The README must name that backstop, or it would
    overstate the hook as catching every possible edit."""
    readme = read_file("README.md")
    hooks = readme[readme.index("**Hooks**"):]
    hooks = hooks[:hooks.index("- **Shell**")]
    assert "git diff" in hooks or "diff backstop" in hooks, \
        "the disclosure must name the git-diff backstop that covers shell-side edits"


def test_readme_correctly_describes_the_generated_file_as_lowercase_named(read_file):
    """The README explains the difference between the uppercase CODE_OF_CONDUCT.md and the
    lowercase code-of-conduct.md, and the generator is required to produce the lowercase
    file -- the README's own description of what the generator creates must not contradict
    that rule."""
    readme = read_file("README.md")
    assert "a `CODE_OF_CONDUCT.md` with" not in readme, \
        "the generator produces the lowercase per-project file, not this repo's CoC"
    assert "a `code-of-conduct.md` with" in readme


def test_the_first_run_setup_prompt_never_interrupts_unrelated_work(read_file):
    """The persona runs on every session, so the one-time setup prompt for un-configured
    repositories must explicitly promise never to interrupt unrelated requests and must limit
    itself to requests actually directed at Hercules -- otherwise it would hijack ordinary
    work and contradict the README's promise that onboarding is optional."""
    agent = read_file("dist/claude-code/agents/hercules.md")
    gate = agent[agent.index("**First-run onboarding.**"):]
    assert "unrelated" in gate, "the gate must promise never to intercept unrelated work"
    assert "/hercules:" in gate, "the gate must scope itself to Hercules-directed requests"


def test_the_default_persona_is_configured_to_use_the_opus_model(read_file):
    """The persona's configuration must declare 'opus' as its default model, using the
    version-flexible alias rather than a pinned model id, so the assistant runs on the
    intended model out of the box. Whether a user's runtime `/model` override actually takes
    effect is separately verified by hand, not by this check."""
    agent = read_file("dist/claude-code/agents/hercules.md")
    head = agent[:agent.index("\n---", 3)]
    assert re.search(r"(?m)^model:\s*opus\s*$", head), \
        "hercules.md frontmatter must declare `model: opus`"


def test_readme_tells_users_the_default_model_is_opus_and_how_to_change_it(read_file):
    """The 'Plugin permissions' Models bullet must state that the persona defaults to the
    opus model and that users can switch models with the /model command -- without this,
    users would have no documented way to discover or change which model they're running."""
    readme = read_file("README.md")
    match = re.search(r"## Plugin permissions\n(.*?)(?=\n## |\Z)", readme, re.DOTALL)
    assert match, "README must have a '## Plugin permissions' section"
    perms = match.group(1)
    assert re.search(r"defaults to `?opus`?", perms, re.I), \
        "Models bullet must state the persona defaults to opus"
    assert "/model" in perms, "Models bullet must document the /model override"


def test_readme_cites_the_correct_published_paper_not_a_dead_link(read_file):
    """The README's one evidence citation must point to the real, resolvable paper (Cheng et
    al., Science 2026) and must not still contain the old identifier that resolves to
    nothing -- a dead citation would turn the README's evidence section from genuine support
    into empty decoration."""
    readme = read_file("README.md")
    assert "science.aec8352" in readme, "cite Cheng et al., Science 2026 (aec8352)"
    assert "adp9289" not in readme, "the old DOI resolves to nothing"


def test_uninstall_instructions_mention_files_left_behind_in_the_repository(read_file):
    """Onboarding writes a code-of-conduct.md file and a reference line into the user's
    CLAUDE.md; those keep influencing sessions even after the plugin is uninstalled. The
    Uninstalling section must name both files, not just the separate saved-state data, so
    users know everything they may want to remove for a clean break."""
    readme = read_file("README.md")
    section = readme[readme.index("## Uninstalling"):]
    section = section[:section.index("\n## ") if "\n## " in section else len(section)]
    assert "code-of-conduct.md" in section and "CLAUDE.md" in section, \
        "uninstall must name the repo-side artifacts the user may want to remove or keep"


def test_the_workflow_protocol_document_is_named_the_single_authority_on_the_workflow(read_file):
    """The workflow protocol file, not the commands or CLAUDE.md, must be the one place
    declared as the authority on how the workflow works, and the code of conduct must point
    to it as such. This exact reversal (crowning a command as the authority instead) has
    shipped twice before, so this check also scans the code of conduct and every command for
    that specific wrong phrasing and fails if it reappears a third time."""
    # Positive: the protocol crowns itself, and the CoC names it as the owner.
    protocol = read_file("dist/claude-code/protocols/workflow-protocol.md").lower()
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


def test_claude_md_defines_one_consistent_way_to_find_the_code_of_conduct_file(read_file):
    """Every phase must locate a project's code of conduct file the same way: matching its
    name case-insensitively within the correct repository, never assuming a fixed filename
    and never grabbing whichever copy happens to be nearest on disk. This resolution rule
    must be defined once in CLAUDE.md."""
    resolution = section((read_file("dist/claude-code/CLAUDE.md") + "\n" + read_file("dist/claude-code/skills/hercules-reference/SKILL.md")),
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


def test_build_looks_up_the_service_code_of_conduct_by_matching_not_a_fixed_path(read_file):
    """If Build assumed a fixed lowercase path like {service-path}/code-of-conduct.md, it
    would miss a real code of conduct file named CODE_OF_CONDUCT.md on case-sensitive
    filesystems like Linux. Build's instructions must resolve the file by name-matching
    instead of a hardcoded filename."""
    assert "{service-path}/code-of-conduct.md" not in read_file("dist/claude-code/commands/build.md"), \
        "build must not read a fixed-lowercase service CoC path — resolve it by matcher"
