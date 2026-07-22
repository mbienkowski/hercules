"""The Copilot CLI target: a GitHub Copilot CLI plugin (``plugin.json`` + native component dirs).

Determinism, the ``.agent.md``/``.prompt.md`` routing, the ``AGENTS.md`` persona, no per-agent
``model:``, the version-injected manifest, no token/switch leaks, and no Claude-only idioms.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from scripts.build.cli import build_target

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_CONTENT = REPO_ROOT / "src" / "content"
CLAUDE_ISM = re.compile(r"CLAUDE\.md|E(?:nter|xit)PlanMode|\bClaude\b|\.claude-plugin|\.cursor-plugin")


def _files(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): p.read_text(encoding="utf-8")
            for p in root.rglob("*") if p.is_file()}


def _frontmatter(text: str) -> dict:
    assert text.startswith("---\n"), "component file must open with a YAML frontmatter fence"
    body = text[len("---\n"):]
    return yaml.safe_load(body[:body.index("\n---")]) or {}


def _src_names(subdir: str) -> list[str]:
    return sorted(p.stem for p in (SRC_CONTENT / subdir).glob("*.md"))


def _build(tmp_path: Path) -> Path:
    out = tmp_path / "copilot-cli"
    build_target("copilot-cli", out)
    return out


def test_building_copilot_twice_produces_identical_output(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    build_target("copilot-cli", a)
    build_target("copilot-cli", b)
    assert _files(a) == _files(b)


def test_persona_ships_as_agents_md_without_frontmatter(tmp_path):
    """The persona lands at ``AGENTS.md`` (Copilot's custom-instructions convention) as plain markdown
    with the product token resolved — not a frontmatter'd rule."""
    out = _build(tmp_path)
    agents_md = out / "AGENTS.md"
    assert agents_md.is_file(), "persona must ship as AGENTS.md"
    text = agents_md.read_text(encoding="utf-8")
    assert not text.startswith("---\n"), "AGENTS.md is plain instructions, no frontmatter"
    assert "GitHub Copilot CLI" in text, "the ${product} token must resolve"


def test_agents_ship_as_dot_agent_md_with_name_and_description_only(tmp_path):
    """Every specialist ships at ``agents/<name>.agent.md`` (Copilot derives the id from the stem) with
    name+description and NO per-agent model or tools (agents inherit the user's model)."""
    out = _build(tmp_path)
    for name in _src_names("agents"):
        f = out / "agents" / f"{name}.agent.md"
        assert f.is_file(), f"agent {name} must ship at agents/{name}.agent.md"
        fm = _frontmatter(f.read_text(encoding="utf-8"))
        assert fm.get("name") == name and fm.get("description")
        assert "model" not in fm and "model_tier" not in fm and "tools" not in fm, \
            f"{name}: Copilot agents carry no model tier/tools"


def test_commands_ship_as_prompt_files_with_a_description(tmp_path):
    """Commands ship as Copilot prompt files ``commands/<name>.prompt.md`` with a ``description`` and
    Claude's ``disable-model-invocation`` marker dropped."""
    out = _build(tmp_path)
    for name in _src_names("commands"):
        f = out / "commands" / f"{name}.prompt.md"
        assert f.is_file(), f"command {name} must ship at commands/{name}.prompt.md"
        fm = _frontmatter(f.read_text(encoding="utf-8"))
        assert fm.get("description"), f"command {name} needs a description"
        assert "disable-model-invocation" not in fm, "Claude's slash marker must be dropped"


def test_no_flat_top_level_dirs_and_only_prompt_commands(tmp_path):
    out = _build(tmp_path)
    for p in (out / "commands").rglob("*"):
        if p.is_file():
            assert p.name.endswith(".prompt.md"), f"commands/ must be .prompt.md only, found {p.name}"
    top = {p.name for p in out.iterdir()}
    assert top <= {".github", "AGENTS.md", "CAPABILITIES.md", "agents", "commands", "skills",
                   "protocols", "hooks", "plugin.json"}, f"unexpected top-level entries: {top}"


def test_plugin_manifest_is_valid_and_version_injected_from_canonical(tmp_path):
    """``plugin.json`` is the source manifest with its ``${version}`` token filled from the canonical
    version (pyproject.toml) — kebab name, a real semver equal to canonical, identical elsewhere; the
    source itself carries the token, not a literal (nothing to hand-bump under src/)."""
    from scripts.build.version_targets import read_canonical_version

    out = _build(tmp_path)
    manifest = json.loads((out / "plugin.json").read_text(encoding="utf-8"))
    assert re.fullmatch(r"[a-z0-9]([a-z0-9-]*[a-z0-9])?", manifest["name"]), "name must be kebab-case"
    source_text = (REPO_ROOT / "src" / "targets" / "copilot-cli" / "plugin.json").read_text(encoding="utf-8")
    assert '"version": "${version}"' in source_text, "source manifest must carry the token, not a literal"
    canonical = read_canonical_version(REPO_ROOT)
    assert manifest["version"] == canonical, "dist version must be the injected canonical version"
    assert manifest == json.loads(source_text.replace("${version}", canonical)), \
        "injection must change ONLY the version field"
    for field in ("agents", "commands", "skills", "hooks"):
        assert field in manifest, f"manifest should declare the {field} component path"


def test_marketplace_descriptor_lists_the_hercules_plugin(tmp_path):
    """The plugin ships a ``.github/plugin/marketplace.json`` registry descriptor listing the hercules
    plugin — so ``copilot plugin marketplace add`` resolves it."""
    out = _build(tmp_path)
    mk = json.loads((out / ".github/plugin/marketplace.json").read_text(encoding="utf-8"))
    assert mk.get("name") and mk.get("owner", {}).get("name"), "marketplace needs name + owner"
    assert any(p.get("name") == "hercules" for p in mk.get("plugins", [])), "must list the hercules plugin"


def test_no_unresolved_tokens_or_switch_directives_leak(tmp_path):
    """No ``${token}`` from config and no ``${target:…}`` switch directive may survive into the build —
    only the runtime ``${PLUGIN_ROOT}`` (Copilot substitutes it) is allowed to pass through."""
    out = _build(tmp_path)
    joined = "\n".join(_files(out).values())
    assert "${target:" not in joined, "a ${target:…} switch leaked unrendered"
    leaked = {m for m in re.findall(r"\$\{[a-z_]+\}", joined)}
    assert leaked == set(), f"unresolved config token(s) leaked: {leaked}"


def test_copilot_output_contains_no_claude_specific_wording(tmp_path):
    """Files shipped to Copilot users must not carry Claude/Cursor-only names, except CAPABILITIES.md
    (discloses the cross-ecosystem gaps by name) and hooks/ (the byte-identical canonical guard)."""
    out = _build(tmp_path)
    offenders = {}
    for rel, text in _files(out).items():
        if rel == "CAPABILITIES.md" or rel.startswith("hooks/"):
            continue
        hits = CLAUDE_ISM.findall(text)
        if hits:
            offenders[rel] = sorted(set(hits))
    assert offenders == {}, f"Claude-isms leaked into Copilot: {offenders}"


def test_copilot_build_has_no_leftover_claude_only_plan_mode_idioms(tmp_path):
    """No Claude ExitPlanMode ``(auto)`` marker, ``call `plan mode``` tool call, or ``approval`` tool —
    none exist in Copilot; the copilot switch branch uses plain plan-mode prose."""
    out = _build(tmp_path)
    joined = "\n".join(_files(out).values())
    assert "(`auto`)" not in joined, "Claude ExitPlanMode '(auto)' leaked into Copilot"
    assert not re.search(r"call\s+`plan mode`", joined, re.IGNORECASE), "non-existent 'plan mode' tool call"
    assert "`approval`" not in joined, "non-existent 'approval' tool"


def test_copilot_plan_mode_renders_and_capabilities_disclose_the_veto(tmp_path):
    """A forgotten switch would render the plan-mode block empty silently — assert every command's
    prompt carries the plan-mode instruction (via the shared ${target:default} branch), and that the
    shipped CAPABILITIES.md discloses Copilot's preToolUse write-gate (where host-specific gaps live)."""
    out = _build(tmp_path)
    for name in _src_names("commands"):
        text = (out / "commands" / f"{name}.prompt.md").read_text(encoding="utf-8")
        assert "plan mode" in text.lower(), f"{name}: plan-mode instruction missing (empty switch?)"
    caps = (out / "CAPABILITIES.md").read_text(encoding="utf-8")
    assert "preToolUse" in caps, "CAPABILITIES.md must disclose the preToolUse write-gate"


def test_copilot_protocol_citations_resolve_to_shipped_files(tmp_path):
    """Content cites protocol docs via ``${PLUGIN_ROOT}/protocols/<file>``; each must point at a
    protocol file the plugin actually ships, or the A2A core never reaches a spawned subagent."""
    out = _build(tmp_path)
    cited = set()
    for text in _files(out).values():
        for m in re.finditer(r"protocols/([A-Za-z0-9-]+\.md)", text):
            cited.add(m.group(1))
    assert cited, "expected at least one protocol citation"
    for fname in sorted(cited):
        assert (out / "protocols" / fname).is_file(), f"cited protocols/{fname} is not shipped"
