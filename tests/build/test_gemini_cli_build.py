"""The Gemini CLI target: an extension (``gemini-extension.json`` + subagents, TOML commands, a
``GEMINI.md`` context). Determinism, routing/extensions, no per-agent model, the version-injected
manifest, protocol-citation resolution, and ecosystem neutrality (no Claude-only idioms/tokens).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from scripts.build.cli import build_target
from scripts.build.version_targets import read_canonical_version

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_CONTENT = REPO_ROOT / "src" / "content"
CLAUDE_ISM = re.compile(r"CLAUDE\.md|E(?:nter|xit)PlanMode|\bClaude\b")


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
    out = tmp_path / "gemini-cli"
    build_target("gemini-cli", out)
    return out


def test_building_gemini_twice_produces_identical_output(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    build_target("gemini-cli", a)
    build_target("gemini-cli", b)
    assert _files(a) == _files(b)


def test_persona_ships_as_the_plain_gemini_md_context_file(tmp_path):
    """The persona becomes GEMINI.md — a plain context file (no frontmatter), named by the manifest's
    contextFileName — and renders the Gemini product name, not Claude's."""
    out = _build(tmp_path)
    gemini_md = out / "GEMINI.md"
    assert gemini_md.is_file(), "persona must land at GEMINI.md"
    text = gemini_md.read_text(encoding="utf-8")
    assert not text.startswith("---"), "GEMINI.md is a plain context file, not a frontmatter'd rule"
    assert "Gemini CLI plugin" in text, "the ${product} token must render to 'Gemini CLI'"


def test_agents_ship_as_subagents_with_name_and_description_and_no_model(tmp_path):
    """Every specialist ships at agents/<name>.md with name+description frontmatter and NO per-agent
    model/model_tier/tools — Gemini subagents inherit the user's selected model."""
    out = _build(tmp_path)
    for name in _src_names("agents"):
        f = out / "agents" / f"{name}.md"
        assert f.is_file(), f"agent {name} must ship at agents/{name}.md"
        fm = _frontmatter(f.read_text(encoding="utf-8"))
        assert fm.get("name") == name and fm.get("description")
        assert "model" not in fm and "model_tier" not in fm and "tools" not in fm, \
            f"{name}: Gemini subagents carry no model tier/tools"


def test_commands_ship_as_toml_with_prompt_and_description(tmp_path):
    """Each command lands at commands/<name>.toml (a .md command is ignored by Gemini) carrying a
    required ``prompt`` and a ``description``, and dropping Claude's disable-model-invocation marker.
    The embedded prompt must have rendered its plan-mode branch (not an empty switch)."""
    out = _build(tmp_path)
    for name in _src_names("commands"):
        assert not (out / "commands" / f"{name}.md").exists(), f"{name}: a .md command must not ship"
        f = out / "commands" / f"{name}.toml"
        assert f.is_file(), f"command {name} must ship at commands/{name}.toml"
        text = f.read_text(encoding="utf-8")
        assert re.search(r'^description = ".+"$', text, re.M), f"{name}: needs a TOML description"
        assert 'prompt = """\n' in text, f"{name}: needs a multiline TOML prompt"
        assert "disable-model-invocation" not in text, "Claude's slash marker must be dropped"
        assert "plan mode" in text.lower(), f"{name}: plan-mode default branch rendered empty"


def test_emitted_command_toml_parses_with_the_prompt_preserved(tmp_path):
    """Every emitted command file must be valid TOML with the plan-mode prompt intact — the real safety
    net. A source-only invariant can't catch a token that renders a backslash or ``\"\"\"`` into a body;
    parsing the *rendered* ``.toml`` (and escaping the body in the emitter) does. Closes the whole class."""
    try:
        import tomllib  # Python >= 3.11
    except ModuleNotFoundError:  # Python 3.9/3.10 (the project's floor is 3.9) — use the tomli backport
        import tomli as tomllib
    out = _build(tmp_path)
    toml_files = sorted((out / "commands").glob("*.toml"))
    assert toml_files, "gemini commands must emit .toml files"
    for f in toml_files:
        data = tomllib.loads(f.read_text(encoding="utf-8"))
        assert data.get("prompt"), f"{f.name}: prompt missing/empty after TOML parse"
        assert "Plan mode — required" in data["prompt"], f"{f.name}: plan-mode instruction lost in the prompt"


def test_toml_escapers_handle_backslashes_and_triple_quotes():
    """Direct coverage for the TOML escapers (mutation-gated in serialize.py): the basic string escapes
    backslash then double-quote; the multiline escaper doubles backslashes and breaks any run of three
    quotes that would close the ``\"\"\"`` delimiter early, and leaves plain text untouched."""
    from scripts.build.serialize import _gemini_toml_basic, _gemini_toml_multiline
    assert _gemini_toml_basic('a"b\\c') == '"a\\"b\\\\c"'
    assert _gemini_toml_multiline("plain") == "plain"
    assert _gemini_toml_multiline("a\\b") == "a\\\\b"
    assert _gemini_toml_multiline('a""b') == 'a""b'          # a 2-quote run stays — only 3+ closes """
    assert _gemini_toml_multiline('x"""y') == 'x""\\"y'      # exactly the 3rd quote is escaped
    assert _gemini_toml_multiline('""""') == '""\\""'        # 4 quotes: 3rd escaped, run resets


def test_extension_manifest_is_valid_and_version_injected_from_canonical(tmp_path):
    """gemini-extension.json is the source manifest with its ${version} token filled from the canonical
    version (pyproject.toml) at build time — a kebab name, a version equal to canonical, contextFileName
    = GEMINI.md, and identical to the source in every other field."""
    out = _build(tmp_path)
    manifest = json.loads((out / "gemini-extension.json").read_text(encoding="utf-8"))
    assert re.fullmatch(r"[a-z0-9]([a-z0-9-]*[a-z0-9])?", manifest["name"]), "name must be kebab-case"
    assert manifest.get("contextFileName") == "GEMINI.md"
    from scripts.build.descriptor import discover
    art = next(a for a in discover()["gemini-cli"].artifacts if a.dest == "gemini-extension.json")
    source_text = json.dumps(art.content, indent=2, ensure_ascii=False) + "\n"
    assert '"version": "${version}"' in source_text, "source manifest must carry the token, not a literal"
    canonical = read_canonical_version(REPO_ROOT)
    assert manifest["version"] == canonical
    assert manifest == json.loads(source_text.replace("${version}", canonical)), \
        "injection must change ONLY the version field"


def test_gemini_output_has_no_leftover_tokens_or_claude_idioms(tmp_path):
    """No unrendered Hercules ${token}/${target:…} switch survives, and no Claude-only idiom
    (EnterPlanMode/ExitPlanMode, the ``(auto)`` marker, a ``call `plan mode``` tool call) leaks — none
    of which exist in Gemini CLI. CAPABILITIES.md legitimately names Claude Code to disclose gaps, and
    hooks/ ships the canonical guard whose comments name Claude — both are exempt."""
    out = _build(tmp_path)
    for rel, text in _files(out).items():
        assert "${target:" not in text, f"{rel}: unrendered target switch"
        for tok in ("${plan_enter}", "${plan_exit}", "${ns}", "${host}", "${product}", "${version}"):
            assert tok not in text, f"{rel}: unrendered token {tok}"
        assert "(`auto`)" not in text, f"{rel}: Claude ExitPlanMode '(auto)' leaked"
        assert not re.search(r"call\s+`plan mode`", text, re.IGNORECASE), f"{rel}: fake plan-mode tool call"
        if rel == "CAPABILITIES.md" or rel.startswith("hooks/"):
            continue
        assert not CLAUDE_ISM.search(text), f"Claude-ism leaked into gemini {rel}"


def test_protocol_citations_resolve_to_shipped_files_under_the_extension_path(tmp_path):
    """Content cites protocol docs via ${plugin_root}protocols/<file>; on Gemini plugin_root is
    ${extensionPath}/, so each citation must point at a protocol file the extension actually ships."""
    out = _build(tmp_path)
    joined = "\n".join(_files(out).values())
    assert "${extensionPath}/protocols/a2a-communication-protocol.md" in joined
    cited = set()
    for text in _files(out).values():
        for m in re.finditer(r"protocols/([A-Za-z0-9-]+\.md)", text):
            cited.add(m.group(1))
    assert cited, "expected at least one protocol citation"
    for fname in sorted(cited):
        assert (out / "protocols" / fname).is_file(), f"cited protocols/{fname} not shipped"
