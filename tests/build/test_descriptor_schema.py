"""The ecosystem-descriptor schema (closed vocabulary) — ``scripts/build/descriptor.py``.

Every shipped ``src/ecosystems/<name>.json`` must validate; every unknown key or enum value must
fail LOUD (``DescriptorError`` naming the offending key and the allowed set), never fall through to
a silent default. The failure tests each mutate one aspect of a minimal valid descriptor, proving
the vocabulary is closed on all axes: top-level keys, role modes, field generators, route kinds,
generator names, and path safety.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.build.descriptor import DescriptorError, discover, load, parse_descriptor

REPO_ROOT = Path(__file__).resolve().parents[2]
ECOSYSTEMS = REPO_ROOT / "src" / "ecosystems"

_MINIMAL = {
    "schema": 1,
    "name": "eco",
    "vars": {"product": "Eco"},
    "models": {"high": None, "medium": None, "low": None},
    "smoke": {"cli": "eco", "test": "tests/build/test_eco_smoke.py"},
    "dispatch": "path",
    "roles": {
        "agent": {"mode": "preserve"},
        "command": {"mode": "preserve"},
        "persona": {"mode": "plain"},
        "default": {"mode": "preserve"},
    },
    "routes": [],
}


def _minimal(**overrides) -> dict:
    raw = copy.deepcopy(_MINIMAL)
    raw.update(overrides)
    return raw


def test_every_shipped_descriptor_validates_and_registry_matches_filenames():
    """All six ecosystems load; discover() keys them by filename stem — the registry IS the dir."""
    found = discover(ECOSYSTEMS)
    assert sorted(found) == [
        "claude-code", "copilot-cli", "cursor", "gemini-cli", "grok-build", "opencode",
    ]
    for name, desc in found.items():
        assert desc.name == name


def test_shipped_descriptors_pin_the_model_rows():
    """claude-code carries the real tier map; every other ecosystem is all-null (inherit user model)."""
    found = discover(ECOSYSTEMS)
    assert found["claude-code"].models == {"high": "opus", "medium": "sonnet", "low": "haiku"}
    for name in ("opencode", "cursor", "grok-build", "gemini-cli", "copilot-cli"):
        assert found[name].models == {"high": None, "medium": None, "low": None}, name


def test_shipped_descriptors_pin_the_token_vars():
    """Spot-pin the load-bearing vars the content render depends on (one per ecosystem family)."""
    found = discover(ECOSYSTEMS)
    assert found["claude-code"].vars["plan_exit"] == "ExitPlanMode"
    assert found["claude-code"].vars["plugin_root"] == "${CLAUDE_PLUGIN_ROOT}/"
    assert found["gemini-cli"].vars["instructions_file"] == "GEMINI.md"
    assert found["opencode"].vars["plugin_root"] == ""
    assert found["copilot-cli"].vars["product"] == "GitHub Copilot CLI"


def test_unknown_top_level_key_fails_naming_the_allowed_set():
    with pytest.raises(DescriptorError) as err:
        parse_descriptor("eco", _minimal(surprises=[]))
    assert "surprises" in str(err.value) and "allowed" in str(err.value)


def test_missing_required_key_fails():
    raw = _minimal()
    del raw["roles"]
    with pytest.raises(DescriptorError, match="'roles'"):
        parse_descriptor("eco", raw)


def test_wrong_schema_version_fails():
    with pytest.raises(DescriptorError, match="'schema' must be 1"):
        parse_descriptor("eco", _minimal(schema=2))


def test_name_must_equal_filename_stem():
    with pytest.raises(DescriptorError, match="filename stem"):
        parse_descriptor("other", _minimal())


def test_non_string_var_fails():
    with pytest.raises(DescriptorError, match="must be a string"):
        parse_descriptor("eco", _minimal(vars={"product": 7}))


def test_unknown_model_tier_fails():
    with pytest.raises(DescriptorError, match="'models'"):
        parse_descriptor("eco", _minimal(models={"high": None, "turbo": "x"}))


def test_unknown_dispatch_fails():
    with pytest.raises(DescriptorError, match="'dispatch'"):
        parse_descriptor("eco", _minimal(dispatch="magic"))


def test_roles_must_be_exactly_the_four_role_names():
    raw = _minimal()
    raw["roles"] = {"agent": {"mode": "preserve"}}
    with pytest.raises(DescriptorError, match="exactly"):
        parse_descriptor("eco", raw)


def test_unknown_role_mode_fails_naming_the_allowed_set():
    raw = _minimal()
    raw["roles"]["agent"] = {"mode": "improvise"}
    with pytest.raises(DescriptorError) as err:
        parse_descriptor("eco", raw)
    assert "improvise" in str(err.value) and "preserve" in str(err.value)


def test_role_key_outside_its_mode_vocabulary_fails():
    """`fields` is meaningless on a preserve role — the per-mode key set is closed."""
    raw = _minimal()
    raw["roles"]["agent"] = {"mode": "preserve", "fields": []}
    with pytest.raises(DescriptorError, match="unknown key"):
        parse_descriptor("eco", raw)


def test_unknown_field_generator_fails_naming_the_allowed_set():
    raw = _minimal()
    raw["roles"]["agent"] = {"mode": "fields", "fields": [{"key": "x", "from": "conditional"}]}
    with pytest.raises(DescriptorError) as err:
        parse_descriptor("eco", raw)
    assert "conditional" in str(err.value) and "frontmatter" in str(err.value)


def test_wrap_mode_rejects_non_literal_fields():
    """wrap frontmatter is generated statics only — no source-dependent generators sneak in."""
    raw = _minimal()
    raw["roles"]["persona"] = {"mode": "wrap",
                               "fields": [{"key": "name", "from": "frontmatter", "field": "name"}]}
    with pytest.raises(DescriptorError, match="literal"):
        parse_descriptor("eco", raw)


def test_toml_command_requires_exactly_the_description_field():
    raw = _minimal()
    raw["roles"]["command"] = {"mode": "toml_command",
                               "fields": [{"key": "name", "from": "stem"}]}
    with pytest.raises(DescriptorError, match="description"):
        parse_descriptor("eco", raw)


def test_unknown_route_kind_fails_naming_the_allowed_set():
    with pytest.raises(DescriptorError) as err:
        parse_descriptor("eco", _minimal(routes=[{"kind": "regex", "pattern": ".*"}]))
    assert "regex" in str(err.value) and "suffix_swap" in str(err.value)


def test_route_dest_may_not_escape_the_tree():
    routes = [{"kind": "exact", "src": "persona.md", "dest": "../evil.md"}]
    with pytest.raises(DescriptorError, match="without '\\.\\.'"):
        parse_descriptor("eco", _minimal(routes=routes))


def test_artifact_content_must_be_a_json_object():
    artifacts = [{"dest": "plugin.json", "content": "raw text"}]
    with pytest.raises(DescriptorError, match="JSON object"):
        parse_descriptor("eco", _minimal(artifacts=artifacts))


def test_asset_src_must_be_a_flat_sibling_filename():
    assets = [{"src": "nested/logo.svg", "dest": "logo.svg"}]
    with pytest.raises(DescriptorError, match="flat sibling"):
        parse_descriptor("eco", _minimal(assets=assets))


def test_unknown_generator_name_fails_naming_the_allowed_set():
    with pytest.raises(DescriptorError) as err:
        parse_descriptor("eco", _minimal(generate=[{"name": "make_website"}]))
    assert "make_website" in str(err.value) and "opencode_plugin_js" in str(err.value)


def test_generator_missing_required_arg_fails():
    with pytest.raises(DescriptorError, match="default_agent"):
        parse_descriptor("eco", _minimal(generate=[{"name": "opencode_plugin_js"}]))


def test_generator_unknown_arg_fails():
    gen = [{"name": "opencode_json", "args": {"mystery": "x"}}]
    with pytest.raises(DescriptorError, match="mystery"):
        parse_descriptor("eco", _minimal(generate=gen))


def test_guard_entries_are_module_filenames():
    with pytest.raises(DescriptorError, match="module filenames"):
        parse_descriptor("eco", _minimal(guard=["hooks/frozen_tests.py"]))


def _with_role(agent_role: dict) -> dict:
    raw = _minimal()
    raw["roles"]["agent"] = agent_role
    return raw


_GATE_OK = {"protocol": "pre_tool", "tools": {"edit": "Edit"}, "path_keys": ["path"],
            "deny": {"d": "deny"}, "reason_key": "r"}

# Every malformed SHAPE the validator must reject — one case per reject branch, so the closed
# vocabulary can't silently grow a lenient fallback anywhere.
_MALFORMED = [
    ("descriptor-not-object", lambda: []),
    ("vars-empty", lambda: _minimal(vars={})),
    ("models-not-object", lambda: _minimal(models=[])),
    ("models-value-not-str-or-null", lambda: _minimal(models={"high": 5})),
    ("smoke-not-object", lambda: _minimal(smoke=[])),
    ("roles-not-object", lambda: _minimal(roles=[])),
    ("routes-not-list", lambda: _minimal(routes={})),
    ("route-not-object", lambda: _minimal(routes=["x"])),
    ("artifact-not-object", lambda: _minimal(artifacts=["x"])),
    ("artifact-versioned-not-bool", lambda: _minimal(
        artifacts=[{"dest": "p.json", "content": {}, "versioned": "yes"}])),
    ("asset-not-object", lambda: _minimal(assets=["x"])),
    ("generate-step-not-object", lambda: _minimal(generate=["x"])),
    ("generate-args-not-object", lambda: _minimal(generate=[{"name": "opencode_json", "args": []}])),
    ("role-not-object", lambda: _with_role("preserve")),
    ("role-body-unknown", lambda: _with_role(
        {"mode": "fields", "body": "trim", "fields": [{"key": "k", "from": "stem"}]})),
    ("role-fields-empty", lambda: _with_role({"mode": "fields", "fields": []})),
    ("role-resolve-not-bool", lambda: _with_role({"mode": "preserve", "resolve_model_tier": "yes"})),
    ("role-required-not-list", lambda: _with_role({"mode": "preserve", "required": "name"})),
    ("field-not-object", lambda: _with_role({"mode": "fields", "fields": ["k"]})),
    ("field-render-not-bool", lambda: _with_role({"mode": "fields", "fields": [
        {"key": "d", "from": "frontmatter", "field": "d", "render": "yes"}]})),
    ("field-names-empty", lambda: _with_role({"mode": "fields", "fields": [
        {"key": "r", "from": "flag_if_name_in", "names": [], "value": "true"}]})),
    ("gate-not-object", lambda: _minimal(gate="x")),
    ("gate-protocol-unknown", lambda: _minimal(gate={"protocol": "magic"})),
    ("gate-tools-empty", lambda: _minimal(gate={**_GATE_OK, "tools": {}})),
    ("gate-path-keys-empty", lambda: _minimal(gate={**_GATE_OK, "path_keys": []})),
    ("gate-deny-not-object", lambda: _minimal(gate={**_GATE_OK, "deny": "deny"})),
    ("gate-allow-not-object", lambda: _minimal(gate={**_GATE_OK, "allow": "allow"})),
    ("gate-nested-keys-not-list", lambda: _minimal(gate={**_GATE_OK, "nested_keys": "edits"})),
]


@pytest.mark.parametrize("case", _MALFORMED, ids=lambda c: c[0])
def test_every_malformed_shape_is_rejected_loudly(case):
    _, build = case
    with pytest.raises(DescriptorError):
        parse_descriptor("eco", build())


def test_load_uses_the_filename_stem_as_the_name(tmp_path):
    path = tmp_path / "eco.json"
    path.write_text(json.dumps(_minimal()), encoding="utf-8")
    assert load(path).name == "eco"


def test_smoke_requires_cli_and_test():
    with pytest.raises(DescriptorError, match="smoke"):
        parse_descriptor("eco", _minimal(smoke={"cli": "eco"}))
