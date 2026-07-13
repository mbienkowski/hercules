"""OpenCode command serialization — the advisory-panel fix.

The panel (source-checker + architect + challenger, all doc-grounded against opencode.ai/docs) found
commands were the one path that skipped the target-aware serializer: the inline ``plugin.js`` templates
embedded raw YAML frontmatter with an empty description, and the standalone ``commands/*.md`` kept the
Claude-only ``disable-model-invocation`` key while losing the ``agent`` binding. OpenCode command files
carry ``{description, agent, ...}`` and ``template`` is the prompt BODY only.
"""
from pathlib import Path

from scripts.build.cli import _load_tokens, _opencode_agents_and_commands, build_target


def test_inline_command_templates_are_body_only_with_real_descriptions():
    _, commands = _opencode_agents_and_commands(_load_tokens("opencode"))
    assert commands, "expected inline command entries"
    for name, meta, template in commands:
        assert meta.get("description"), f"{name}: empty command description reaches the UI"
        assert meta.get("agent") == "hercules", f"{name}: command not bound to the hercules agent"
        assert not template.lstrip().startswith("---"), f"{name}: template still embeds YAML frontmatter"
        assert "disable-model-invocation" not in template, f"{name}: Claude key leaked into template"


def test_plugin_js_carries_no_claude_command_key(tmp_path):
    out = tmp_path / "opencode"
    build_target("opencode", out)
    js = (out / "plugin.js").read_text(encoding="utf-8")
    assert "disable-model-invocation" not in js, "Claude-only command key leaked into plugin.js"
    assert 'template: "---' not in js, "command template still opens with a YAML fence"


def test_standalone_command_files_are_opencode_shaped(tmp_path):
    out = tmp_path / "opencode"
    build_target("opencode", out)
    files = list((out / "commands").glob("*.md"))
    assert files, "expected standalone command files"
    for cmd in files:
        text = cmd.read_text(encoding="utf-8")
        assert "disable-model-invocation" not in text, f"{cmd.name}: Claude-only key kept"
        assert "\nagent: hercules\n" in text, f"{cmd.name}: missing OpenCode agent binding"
