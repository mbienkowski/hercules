"""Spec 03 — the OpenCode manifest/plugin-entry emitters (JS-literal rendering).

Frozen for spec-03-opencode-target.
"""
from scripts.build.manifests import (
    escape_ts_string,
    generate_opencode_json,
    generate_plugin_js,
    ts_object_literal,
)


def test_escape_ts_string_quotes_and_escapes():
    assert escape_ts_string('a"b') == '"a\\"b"'


def test_escape_ts_string_preserves_non_ascii():
    # ensure_ascii=False keeps arrows/emoji literal (the corpus is full of them).
    assert escape_ts_string("a→b") == '"a→b"'


def test_ts_object_literal_primitives():
    assert ts_object_literal(True) == "true"
    assert ts_object_literal(False) == "false"
    assert ts_object_literal(None) == "null"
    assert ts_object_literal(42) == "42"
    assert ts_object_literal("x") == '"x"'


def test_ts_object_literal_empty_collections():
    assert ts_object_literal({}) == "{}"
    assert ts_object_literal([]) == "[]"


def test_ts_object_literal_list_of_values():
    assert ts_object_literal(["a", "b"]) == '["a", "b"]'


def test_ts_object_literal_bare_vs_quoted_keys():
    out = ts_object_literal({"ok_key": 1, "needs:quote": 2})
    assert "ok_key: 1," in out
    assert '"needs:quote": 2,' in out


def test_generate_opencode_json_shape():
    cfg = generate_opencode_json()
    assert cfg["$schema"] == "https://opencode.ai/config.json"
    assert cfg["default_agent"] == "hercules"
    assert cfg["instructions"] and cfg["skills"]["paths"]


def test_generate_plugin_js_inlines_agents_and_commands_with_depth_independent_root():
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


def test_generate_plugin_js_uses_defaults_when_metadata_missing():
    js = generate_plugin_js("hercules", agents=[("x", {}, "P")], commands=[])
    assert 'mode: "subagent"' in js  # default mode
    assert 'description: ""' in js   # default description
