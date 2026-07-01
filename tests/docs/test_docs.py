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
    """Updates are manual (/plugin marketplace update); the README must not claim auto-update."""
    content = read_file("README.md")
    assert "keeps the plugin updated" not in content.lower(), \
        "README must not claim Claude Code auto-updates the plugin — updates are manual"
    assert "/plugin marketplace update" in content, "README must document the manual update command"



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
