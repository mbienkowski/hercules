"""OpenCode command serialization — the advisory-panel fix.

The panel (source-checker + architect + challenger, all doc-grounded against opencode.ai/docs) found
commands were the one path that skipped the target-aware serializer: the inline ``plugin.js`` templates
embedded raw YAML frontmatter with an empty description, and the standalone ``commands/*.md`` kept the
Claude-only ``disable-model-invocation`` key while losing the ``agent`` binding. OpenCode command files
carry ``{description, agent, ...}`` and ``template`` is the prompt BODY only.
"""
from pathlib import Path

from scripts.build.cli import SRC_CONTENT, _load_tokens, build_target
from scripts.build.targets.opencode import _agents_and_commands


def test_opencode_commands_have_real_descriptions_and_clean_prompt_text():
    """Every slash command generated for OpenCode must show a real, non-blank description in the
    UI, must be wired to the hercules agent, and its prompt text must not still contain leftover
    Claude-only formatting or settings -- otherwise the command would look broken or run through
    the wrong agent when a user tries to use it in OpenCode."""
    _, commands = _agents_and_commands(SRC_CONTENT, _load_tokens("opencode"))
    assert commands, "expected inline command entries"
    for name, meta, template in commands:
        assert meta.get("description"), f"{name}: empty command description reaches the UI"
        assert meta.get("agent") == "hercules", f"{name}: command not bound to the hercules agent"
        assert not template.lstrip().startswith("---"), f"{name}: template still embeds YAML frontmatter"
        assert "disable-model-invocation" not in template, f"{name}: Claude key leaked into template"


def test_generated_opencode_plugin_bundle_has_no_leftover_claude_settings(tmp_path):
    """When Hercules builds the OpenCode plugin bundle, the commands packed into it must not carry
    the Claude-only "disable model invocation" setting or an unstripped YAML header on their prompt
    text -- either one would confuse OpenCode or cause it to misconfigure the command."""
    out = tmp_path / "opencode"
    build_target("opencode", out)
    js = (out / "plugin.js").read_text(encoding="utf-8")
    assert "disable-model-invocation" not in js, "Claude-only command key leaked into plugin.js"
    assert 'template: "---' not in js, "command template still opens with a YAML fence"


def test_standalone_opencode_command_files_are_bound_to_the_right_agent(tmp_path):
    """Each individual command file Hercules writes for OpenCode must declare which agent runs it
    and must not retain the Claude-only "disable model invocation" setting -- without the agent
    binding a user's command would silently fail to run, or run through the wrong agent."""
    out = tmp_path / "opencode"
    build_target("opencode", out)
    files = list((out / "commands").glob("*.md"))
    assert files, "expected standalone command files"
    for cmd in files:
        text = cmd.read_text(encoding="utf-8")
        assert "disable-model-invocation" not in text, f"{cmd.name}: Claude-only key kept"
        assert "\nagent: hercules\n" in text, f"{cmd.name}: missing OpenCode agent binding"
