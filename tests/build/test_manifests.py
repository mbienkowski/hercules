"""Spec 03 — the OpenCode manifest/plugin-entry emitters (JS-literal rendering).

Frozen for spec-03-opencode-target.
"""
from scripts.build.manifests import (
    escape_ts_string,
    generate_opencode_json,
    generate_plugin_js,
    ts_object_literal,
)


def test_a_double_quote_in_text_is_escaped_so_generated_code_stays_valid():
    """When text destined for a generated JavaScript/TypeScript config file contains a
    double quote, it is escaped so the emitted file remains valid, loadable code instead
    of breaking on the unescaped character."""
    assert escape_ts_string('a"b') == '"a\\"b"'


def test_non_english_characters_and_symbols_survive_unchanged():
    """Text containing arrows, emoji, or other non-ASCII characters (common throughout the
    prompt content Hercules ships) is written out literally rather than being mangled into
    escape sequences, so the generated file stays human-readable."""
    # ensure_ascii=False keeps arrows/emoji literal (the corpus is full of them).
    assert escape_ts_string("a→b") == '"a→b"'


def test_simple_values_render_as_their_native_javascript_equivalents():
    """Basic values -- booleans, an absent value, numbers, and text -- are each converted to
    the matching JavaScript literal (true/false/null/number/quoted string) when building a
    generated config file, so the file parses correctly wherever it's loaded."""
    assert ts_object_literal(True) == "true"
    assert ts_object_literal(False) == "false"
    assert ts_object_literal(None) == "null"
    assert ts_object_literal(42) == "42"
    assert ts_object_literal("x") == '"x"'


def test_empty_groups_and_lists_render_as_empty_javascript_collections():
    """An empty group of settings or an empty list of items is rendered as an empty
    JavaScript object or array, not omitted or replaced with a placeholder that would break
    the generated file."""
    assert ts_object_literal({}) == "{}"
    assert ts_object_literal([]) == "[]"


def test_a_list_of_text_values_renders_as_a_javascript_array():
    """A list of text values is rendered as a comma-separated JavaScript array of quoted
    strings, matching what any JavaScript or TypeScript file expects to parse."""
    assert ts_object_literal(["a", "b"]) == '["a", "b"]'


def test_property_names_are_only_quoted_when_javascript_requires_it():
    """Property names that are plain words are written without quotes for readability, while
    names containing special characters like a colon are quoted so the generated file remains
    valid JavaScript."""
    out = ts_object_literal({"ok_key": 1, "needs:quote": 2})
    assert "ok_key: 1," in out
    assert '"needs:quote": 2,' in out


def test_generated_opencode_config_has_the_required_top_level_fields():
    """The configuration generated for the OpenCode integration always references the
    correct schema, names "hercules" as the default agent, and includes non-empty
    instructions and skill paths -- if any of these were missing, OpenCode would fail to
    load Hercules correctly."""
    cfg = generate_opencode_json()
    assert cfg["$schema"] == "https://opencode.ai/config.json"
    assert cfg["default_agent"] == "hercules"
    assert cfg["instructions"] and cfg["skills"]["paths"]


def test_generated_plugin_file_embeds_agent_and_command_details_regardless_of_install_location():
    """The generated OpenCode plugin file locates its own root directory relative to itself
    rather than via a fixed parent-folder path, so it keeps working no matter how deep it
    ends up installed. It also embeds each agent's description, mode, and prompt, and each
    command's description, agent, and template directly, with commands namespaced under the
    plugin name so they don't collide with commands from other plugins."""
    js = generate_plugin_js(
        "hercules",
        agents=[("hercules", {"description": "d", "mode": "primary"}, "PROMPT")],
        commands=[("discover", {}, "TEMPLATE")],
    )
    assert "PLUGIN_ROOT = path.resolve(__dirname)" in js  # not "..": entry lives in dist/opencode/
    assert 'cfg.default_agent = "hercules"' in js
    assert '"hercules:discover"' in js          # command key namespaced
    # exact inlined keys + values (agents: description/mode/prompt; commands: description/agent/template)
    assert 'description: "d"' in js
    assert 'mode: "primary"' in js
    assert 'prompt: "PROMPT"' in js
    assert 'agent: "hercules"' in js
    assert 'template: "TEMPLATE"' in js


def test_an_agent_missing_optional_details_still_gets_sensible_defaults():
    """When an agent's definition omits its mode or description, the generated plugin file
    falls back to safe defaults ("subagent" mode, empty description) instead of producing
    broken or missing configuration."""
    js = generate_plugin_js("hercules", agents=[("x", {}, "P")], commands=[])
    assert 'mode: "subagent"' in js  # default mode
    assert 'description: ""' in js   # default description
