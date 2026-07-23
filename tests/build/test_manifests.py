"""The generic template mechanism (JS-literal value kinds) — ``scripts/build/genextras.py``.

Descended from the Spec 03 OpenCode emitter tests: the emitter is now the ONE generic template
renderer (``templates`` in the descriptor: a ``<eco>.template.<dest>`` sibling + closed
computed-value vocabulary), so these pin the JS-serialization helpers and the rendered
``dist/opencode/plugin.js`` — every behavioral assertion from the bespoke-emitter era preserved.
"""
from pathlib import Path

from scripts.build.cli import build_target
from scripts.build.descriptor import discover
from scripts.build.genextras import js_object_literal, js_string

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_a_double_quote_in_text_is_escaped_so_generated_code_stays_valid():
    """When text destined for a generated JavaScript/TypeScript config file contains a
    double quote, it is escaped so the emitted file remains valid, loadable code instead
    of breaking on the unescaped character."""
    assert js_string('a"b') == '"a\\"b"'


def test_non_english_characters_and_symbols_survive_unchanged():
    """Text containing arrows, emoji, or other non-ASCII characters (common throughout the
    prompt content Hercules ships) is written out literally rather than being mangled into
    escape sequences, so the generated file stays human-readable."""
    assert js_string("a→b") == '"a→b"'


def test_simple_values_render_as_their_native_javascript_equivalents():
    """Basic values -- booleans, an absent value, numbers, and text -- are each converted to
    the matching JavaScript literal (true/false/null/number/quoted string) when building a
    generated config file, so the file parses correctly wherever it's loaded."""
    assert js_object_literal(True) == "true"
    assert js_object_literal(False) == "false"
    assert js_object_literal(None) == "null"
    assert js_object_literal(42) == "42"
    assert js_object_literal("x") == '"x"'


def test_empty_groups_and_lists_render_as_empty_javascript_collections():
    """An empty group of settings or an empty list of items is rendered as an empty
    JavaScript object or array, not omitted or replaced with a placeholder that would break
    the generated file."""
    assert js_object_literal({}) == "{}"
    assert js_object_literal([]) == "[]"


def test_a_list_of_text_values_renders_as_a_javascript_array():
    """A list of text values is rendered as a comma-separated JavaScript array of quoted
    strings, matching what any JavaScript or TypeScript file expects to parse."""
    assert js_object_literal(["a", "b"]) == '["a", "b"]'


def test_property_names_are_only_quoted_when_javascript_requires_it():
    """Property names that are plain words are written without quotes for readability, while
    names containing special characters like a colon are quoted so the generated file remains
    valid JavaScript."""
    out = js_object_literal({"ok_key": 1, "needs:quote": 2})
    assert "ok_key: 1," in out
    assert '"needs:quote": 2,' in out


def test_opencode_config_artifact_has_the_required_top_level_fields():
    """The opencode.json shipped for the OpenCode integration always references the correct
    schema, names "hercules" as the default agent, and includes non-empty instructions and
    skill paths -- if any of these were missing, OpenCode would fail to load Hercules. It is
    plain descriptor DATA now (an inline artifact), pinned here reader-side."""
    cfg = next(a for a in discover()["opencode"].artifacts if a.dest == "opencode.json").content
    assert cfg["$schema"] == "https://opencode.ai/config.json"
    assert cfg["default_agent"] == "hercules"
    assert cfg["instructions"] and cfg["skills"]["paths"]


def test_rendered_plugin_template_embeds_entries_and_resolves_its_own_root(tmp_path):
    """The rendered OpenCode plugin entry locates its own root relative to itself (not a fixed
    parent path), names the default agent, namespaces command keys under the plugin name, and
    embeds each agent's description/mode/prompt and each command's description/agent/template —
    all computed from the descriptor's role fields through the generic template values."""
    out = tmp_path / "opencode"
    build_target("opencode", out)
    js = (out / "plugin.js").read_text(encoding="utf-8")
    assert "PLUGIN_ROOT = path.resolve(__dirname)" in js  # not "..": entry lives in dist/opencode/
    assert 'cfg.default_agent = "hercules"' in js
    assert '"hercules:discover"' in js                    # command key namespaced
    assert "\n            mode: " in js and "\n            prompt: " in js
    assert '\n            agent: "hercules",' in js and "\n            template: " in js
    assert "__AGENT_ENTRIES__" not in js and "__COMMAND_ENTRIES__" not in js, "unrendered placeholder"


def test_the_template_source_is_sibling_data_not_python(tmp_path):
    """The plugin.js template text is a data file under src/ecosystems/ (schema-validated
    filename), never a Python string literal — a template edit is a data edit."""
    template = REPO_ROOT / "src" / "ecosystems" / "opencode.template.plugin.js"
    assert template.is_file(), "the template must live as a sibling data file"
    text = template.read_text(encoding="utf-8")
    assert "__AGENT_ENTRIES__" in text and "__COMMAND_ENTRIES__" in text
    assert "tool.execute.before" in text, "the JS write-gate wiring lives in the template data"
