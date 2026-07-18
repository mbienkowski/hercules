"""Tests that verify plugin file hygiene and shared settings correctness."""

import json
import warnings
import re
from pathlib import Path

import pytest

from tests.metrics.threshold_runner import load_thresholds, run_threshold_checks
from tests.metrics.token_counter import count_tokens


_CONTENT_DIRS = ["dist/claude-code/commands", "dist/claude-code/agents", "dist/claude-code/skills"]
_LOWERCASE_EXCEPT = {"SKILL.md"}


def _walk_markdown(repo_root: Path):
    """Yield all markdown files under commands/, agents/, skills/."""
    for d in _CONTENT_DIRS:
        base = repo_root / d
        if base.exists():
            yield from base.rglob("*.md")


def test_shipped_content_never_exceeds_its_size_budget(repo_root):
    """Every command, agent, and skill file shipped with the plugin must stay within its configured
    size limit, and any file that is getting close to that limit raises a warning rather than failing
    silently. This keeps loaded prompts small enough to stay fast and avoids one oversized file
    quietly ballooning until it blows through the limit unnoticed."""
    # Given
    threshold_file = repo_root / "tests" / "testdata" / "thresholds.json"
    checks = load_thresholds(threshold_file)

    # When
    results = run_threshold_checks(repo_root, checks)

    # Then
    failures = [r for r in results if not r.passed and r.severity == "gate"]
    assert not failures, "Token budget gate failures:\n" + "\n".join(
        f"  {r.message}" for r in failures
    )
    # warn_at exists to give a pre-limit signal — surface it, or it is a dead feature.
    for r in results:
        if r.near_warn:
            warnings.warn(f"approaching budget limit: {r.message}", stacklevel=1)


def test_shipped_file_names_are_always_lowercase(repo_root):
    """Every command, agent, and skill file shipped with the plugin (aside from the standard
    SKILL.md name) must have an all-lowercase filename. A mixed-case filename that happens to work
    on a Mac or Windows machine can silently fail to load once a user runs Hercules on Linux, where
    filenames are case-sensitive."""
    # Given
    violations = []

    # When
    for path in _walk_markdown(repo_root):
        name = path.name
        if name in _LOWERCASE_EXCEPT:
            continue
        if name != name.lower():
            violations.append(str(path.relative_to(repo_root)))

    # Then
    assert not violations, f"Uppercase filenames found (will fail to load on Linux): {violations}"


def test_plugin_listing_declares_its_name_version_and_author(repo_root):
    """The plugin's manifest file must be readable and must declare a name, version, description,
    and author. Without these, the plugin cannot be identified or correctly listed for installation
    from a marketplace."""
    # Given
    plugin_json = repo_root / "dist" / "claude-code" / ".claude-plugin" / "plugin.json"

    # When
    fields = json.loads(plugin_json.read_text())

    # Then
    for required in ["name", "version", "description", "author"]:
        assert required in fields and fields[required], (
            f"plugin.json missing required field: {required}"
        )


def test_marketplace_listing_can_actually_find_and_install_hercules(repo_root):
    """The marketplace listing must include an entry named "hercules" whose source path resolves
    to a real, installable copy of the plugin. If this entry were missing or pointed nowhere, a
    user browsing the marketplace would not be able to find or install Hercules at all."""
    # Given
    marketplace = repo_root / ".claude-plugin" / "marketplace.json"

    # When
    data = json.loads(marketplace.read_text())

    # Then
    assert data.get("name"), "marketplace.json missing 'name'"
    plugins = data.get("plugins") or []
    entry = next((p for p in plugins if p.get("name") == "hercules"), None)
    assert entry is not None, "marketplace.json does not list a plugin named 'hercules'"
    source = entry.get("source", "")
    assert source, "hercules plugin entry missing 'source'"
    source_dir = (repo_root / source).resolve()
    assert (source_dir / ".claude-plugin" / "plugin.json").is_file(), (
        f"marketplace source {source!r} must resolve to a dir containing .claude-plugin/plugin.json"
    )


def test_shipped_plugin_never_requires_an_experimental_feature_flag(repo_root):
    """None of the files shipped with the plugin may reference the experimental agent-teams
    feature flag. Hercules runs its multi-agent debates without needing any experimental flag
    turned on, so if a shipped file required it, that feature would silently break for every user
    who hasn't opted into the experimental flag.
    """
    # Given
    flag = "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"
    plugin_dir = repo_root / "dist" / "claude-code"
    offenders = []

    # When
    for path in plugin_dir.rglob("*"):
        if path.is_file() and path.suffix in {".md", ".json"} and flag in path.read_text(errors="ignore"):
            offenders.append(str(path.relative_to(repo_root)))

    # Then
    assert not offenders, f"shipped plugin artifacts must not reference {flag}: {offenders}"


def test_plugin_docs_never_claim_to_make_their_own_network_calls(repo_root):
    """None of the plugin's documentation may claim that it makes direct API calls or opens a
    separate network channel. The plugin is described elsewhere as never talking to the network on
    its own, so any doc that contradicts that would mislead a user, or a security reviewer, about
    what the plugin actually does."""
    for path in (repo_root / "dist" / "claude-code").rglob("*.md"):
        content = path.read_text(encoding="utf-8").lower()
        assert "direct api call" not in content, f"{path} claims direct API calls"
        assert "external network channel" not in content, f"{path} claims external network channel"


def test_documented_permissions_promise_only_one_write_location_and_no_data_collection(repo_root, read_file):
    """The README's "Plugin permissions" section is where users are told what the plugin writes
    outside the project folder, and it must name only ~/.hercules/ as that location while also
    stating that no credentials are stored and no direct network calls are made. This is the safety
    promise a user relies on when deciding whether it's okay to install and run Hercules; the rest
    of the README may separately mention Claude Code's own config file without that being a
    violation of this promise.
    """
    readme = read_file("README.md")
    claude_md = read_file("dist/claude-code/CLAUDE.md").lower()
    assert "~/.hercules/" in readme.lower(), "README must document the ~/.hercules/ write location"
    assert "~/.hercules/" in claude_md, "dist/claude-code/CLAUDE.md must reference ~/.hercules/"

    match = re.search(r"## Plugin permissions\n(.*?)(?=\n## |\Z)", readme, re.DOTALL)
    assert match, "README must contain a '## Plugin permissions' section"
    perms_section = match.group(1).lower()

    home_writes = re.findall(r"~/\.[a-z][a-z0-9_-]+/", perms_section)
    assert all(p == "~/.hercules/" for p in home_writes), (
        f"Plugin permissions section references unexpected home-dir locations: "
        f"{set(home_writes) - {'~/.hercules/'}}"
    )

    assert "no credentials" in perms_section, \
        "Plugin permissions must state no credentials are stored"
    assert "no direct api calls" in perms_section or "no separate network channel" in perms_section, \
        "Plugin permissions must state no direct API calls or separate network channel"


def test_every_agents_declared_name_is_lowercase(repo_root, agent_files):
    """Each agent file declares its own name, which is used to build a URL-safe identifier for
    that agent, and that declared name must be all lowercase. An uppercase letter here would
    produce an identifier that doesn't match what the tooling expects, silently breaking that
    agent's invocation."""
    # Given
    name_re = re.compile(r"(?m)^name:\s*(\S+)\s*$")
    violations = []

    # When
    for path in agent_files:
        m = name_re.search(path.read_text())
        if m and m.group(1) != m.group(1).lower():
            violations.append(f"{path.name}: name={m.group(1)!r}")

    # Then
    assert not violations, f"Agent frontmatter name fields with uppercase: {violations}"
