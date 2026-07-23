"""The ecosystem-descriptor schema (closed vocabulary) — ``scripts/build/descriptor.py``.

Every shipped ``src/ecosystems/<name>.json`` must validate; every unknown key or enum value must
fail LOUD (``DescriptorError`` naming the offending key and the allowed set), never fall through to
a silent default. The failure tests each mutate one aspect of a minimal valid descriptor, proving
the vocabulary is closed on all axes: top-level keys, role modes, field generators, route kinds,
generator names, and path safety.
"""
from __future__ import annotations

import copy
import dataclasses
import json
from pathlib import Path

import pytest

from scripts.build.descriptor import (
    Artifact,
    DescriptorError,
    EcosystemDescriptor,
    FieldSpec,
    Route,
    RoleSpec,
    Template,
    TemplateValue,
    discover,
    load,
    parse_descriptor,
)

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


def test_suffix_swap_to_suffix_may_not_escape_the_tree():
    """suffix_swap's computed dest gets the same tree-escape guard as an exact route's dest — a
    ``..`` in to_suffix must fail, not silently write outside the plugin tree."""
    routes = [{"kind": "suffix_swap", "prefix": "commands/", "from_suffix": ".md",
               "to_suffix": "../../../etc/x"}]
    with pytest.raises(DescriptorError, match="without '\\.\\.'"):
        parse_descriptor("eco", _minimal(routes=routes))


def test_artifact_content_must_be_a_json_object():
    artifacts = [{"dest": "plugin.json", "content": "raw text"}]
    with pytest.raises(DescriptorError, match="JSON object"):
        parse_descriptor("eco", _minimal(artifacts=artifacts))


def test_a_stray_sibling_file_fails_discovery_loudly(tmp_path):
    """The directory has a definitive schema: a file that is neither a descriptor nor a
    '<eco>.dist.<dest>' shipped file must fail discovery — nothing is ever silently ignored."""
    (tmp_path / "eco.json").write_text(json.dumps(_minimal()), encoding="utf-8")
    (tmp_path / "notes.md").write_text("stray", encoding="utf-8")
    with pytest.raises(DescriptorError, match="dist"):
        discover(tmp_path)


def test_a_dist_file_for_an_unknown_ecosystem_fails_discovery(tmp_path):
    (tmp_path / "eco.json").write_text(json.dumps(_minimal()), encoding="utf-8")
    (tmp_path / "ghost.dist.CAPABILITIES.md").write_text("x", encoding="utf-8")
    with pytest.raises(DescriptorError, match="ghost.dist.CAPABILITIES.md"):
        discover(tmp_path)


def test_a_dist_file_with_an_empty_dest_fails_discovery(tmp_path):
    (tmp_path / "eco.json").write_text(json.dumps(_minimal()), encoding="utf-8")
    (tmp_path / "eco.dist.").write_text("x", encoding="utf-8")
    with pytest.raises(DescriptorError, match="eco.dist"):
        discover(tmp_path)


def test_dist_files_derives_the_destination_purely_from_the_filename(tmp_path):
    """The input→output contract: '<eco>.dist.<dest>' maps to plugin-root '<dest>', nothing else
    consulted — a rename IS a re-route, deterministically."""
    from scripts.build.descriptor import dist_files
    (tmp_path / "eco.json").write_text(json.dumps(_minimal()), encoding="utf-8")
    (tmp_path / "eco.dist.CAPABILITIES.md").write_text("caps", encoding="utf-8")
    (tmp_path / "eco.dist.logo.svg").write_text("<svg/>", encoding="utf-8")
    files = dist_files("eco", tmp_path)
    assert sorted(files) == ["CAPABILITIES.md", "logo.svg"]
    assert files["CAPABILITIES.md"].name == "eco.dist.CAPABILITIES.md"


def test_every_shipped_sibling_lands_at_its_filename_derived_dest_byte_identically(tmp_path):
    """End-to-end determinism over the REAL corpus: for every ecosystem, each
    src/ecosystems/<eco>.dist.<dest> ships byte-identical at dist-root <dest>."""
    from scripts.build.cli import build_target
    from scripts.build.descriptor import dist_files
    checked = 0
    for name in discover(ECOSYSTEMS):
        siblings = dist_files(name)
        if not siblings:
            continue
        out = tmp_path / name
        build_target(name, out)
        for dest, src in siblings.items():
            assert (out / dest).read_bytes() == src.read_bytes(), f"{name}: {dest} diverged"
            checked += 1
    assert checked >= 2, "expected the cursor logo/readme siblings to be covered"


def _capabilities_targets() -> list:
    """The ecosystems whose descriptors route the shared capabilities source to CAPABILITIES.md."""
    return sorted(name for name, d in discover(ECOSYSTEMS).items()
                  if any(r.kind == "exact" and r.src == "capabilities.md" for r in d.routes))


def test_capabilities_are_compiled_from_one_shared_source_for_five_ecosystems():
    """CAPABILITIES.md is CONTENT now — one shared, switch-branched source compiled per ecosystem —
    so a shared claim can never drift between ecosystems (it exists once). claude-code (the
    reference) deliberately omits it."""
    assert _capabilities_targets() == ["copilot-cli", "cursor", "gemini-cli", "grok-build", "opencode"]
    claude = discover(ECOSYSTEMS)["claude-code"]
    assert any(r.kind == "omit" and r.src == "capabilities.md" for r in claude.routes), \
        "claude-code must explicitly omit the capabilities source, not silently ship it"


def test_every_compiled_capabilities_file_follows_the_disclosure_shape():
    """Capabilities prose is testable: every compiled dist CAPABILITIES.md opens with the canonical
    per-product disclosure heading and is substantive (not a stub) — the 'disclose gaps, never
    hide' shape. Reads the committed dist copies (the drift gate pins them to a fresh build)."""
    import re
    for name in _capabilities_targets():
        text = (REPO_ROOT / "dist" / name / "CAPABILITIES.md").read_text(encoding="utf-8")
        product = discover(ECOSYSTEMS)[name].vars["product"]
        assert text.startswith(f"# Hercules on {product} — capabilities & disclosed gaps\n"), \
            f"{name}: must open with the canonical disclosure heading for {product!r}"
        assert text.count("- **") >= 2, f"{name}: must disclose at least two concrete items"
        assert "${target:" not in text and "${product}" not in text, f"{name}: unrendered token"


def test_capabilities_disclosures_match_the_descriptor_gate_wiring():
    """Pin both ends of the disclosure contract: what the prose CLAIMS about the write-gate must
    match the wiring DATA the descriptor actually ships. A matcher/tool renamed in the descriptor
    without updating the disclosure (or vice versa) fails here."""
    found = discover(ECOSYSTEMS)
    gemini = (REPO_ROOT / "dist" / "gemini-cli" / "CAPABILITIES.md").read_text(encoding="utf-8")
    gemini_matcher = found["gemini-cli"].artifacts[0].content["hooks"]["BeforeTool"][0]["matcher"]
    assert f"`{gemini_matcher}`" in gemini, "gemini disclosure must name the exact BeforeTool matcher"
    for tool in found["gemini-cli"].gate["tools"]:
        assert tool in gemini, f"gemini disclosure must name gated tool {tool!r}"
    copilot = (REPO_ROOT / "dist" / "copilot-cli" / "CAPABILITIES.md").read_text(encoding="utf-8")
    for tool in ("create", "edit", "str_replace_editor", "apply_patch"):
        assert tool in found["copilot-cli"].gate["tools"], f"descriptor must gate {tool!r}"
        assert tool in copilot, f"copilot disclosure must name gated tool {tool!r}"


def test_unknown_template_value_kind_fails_naming_the_allowed_set():
    tpl = [{"src": "eco.template.x.js", "dest": "x.js",
            "values": {"__X__": {"from": "run_code"}}}]
    with pytest.raises(DescriptorError) as err:
        parse_descriptor("eco", _minimal(templates=tpl))
    assert "run_code" in str(err.value) and "js_string" in str(err.value)


def test_template_placeholder_must_be_upper_snake_dunder():
    tpl = [{"src": "eco.template.x.js", "dest": "x.js",
            "values": {"{{x}}": {"from": "js_string", "value": "v"}}}]
    with pytest.raises(DescriptorError, match="__UPPER_SNAKE__"):
        parse_descriptor("eco", _minimal(templates=tpl))


def test_template_src_must_be_a_template_sibling():
    tpl = [{"src": "plugin.js", "dest": "plugin.js", "values": {}}]
    with pytest.raises(DescriptorError, match="template"):
        parse_descriptor("eco", _minimal(templates=tpl))


def test_role_entries_value_requires_a_known_role():
    tpl = [{"src": "eco.template.x.js", "dest": "x.js",
            "values": {"__E__": {"from": "role_entries_js", "role": "wizard",
                                 "body_key": "prompt"}}}]
    with pytest.raises(DescriptorError, match="wizard"):
        parse_descriptor("eco", _minimal(templates=tpl))


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
    ("template-not-object", lambda: _minimal(templates=["x"])),
    ("template-values-not-object", lambda: _minimal(
        templates=[{"src": "eco.template.x", "dest": "x", "values": []}])),
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
    # Boolean-operator + guard branches that mutation testing would flag but that carry real
    # security/correctness weight — pinned behaviorally because descriptor.py is off the mutation
    # gate (see [tool.mutmut]). An `... or not X` weakened to `... and X` would let these through.
    ("route-dest-absolute-path", lambda: _minimal(
        routes=[{"kind": "exact", "src": "persona.md", "dest": "/etc/passwd"}])),
    ("route-dest-empty-string", lambda: _minimal(
        routes=[{"kind": "exact", "src": "persona.md", "dest": ""}])),
    ("models-empty-dict", lambda: _minimal(models={})),
    ("template-js-string-list-empty", lambda: _minimal(templates=[
        {"src": "eco.template.x", "dest": "x", "values": {"__X__": {"from": "js_string_list", "values": []}}}])),
    ("template-js-root-joins-empty", lambda: _minimal(templates=[
        {"src": "eco.template.x", "dest": "x", "values": {"__X__": {"from": "js_root_joins", "paths": []}}}])),
    ("template-src-nested-not-flat", lambda: _minimal(templates=[
        {"src": "sub/eco.template.x", "dest": "x", "values": {}}])),
    ("wrap-role-empty-fields", lambda: _minimal(roles={
        **_MINIMAL["roles"], "persona": {"mode": "wrap", "fields": []}})),
    ("toml-command-empty-fields", lambda: _minimal(roles={
        **_MINIMAL["roles"], "command": {"mode": "toml_command", "fields": []}})),
    ("gate-event-guards-missing-user-key", lambda: _minimal(
        gate={"protocol": "event_guards", "allow": {}, "deny": {}, "agent_key": "a"})),
    ("gate-event-guards-missing-agent-key", lambda: _minimal(
        gate={"protocol": "event_guards", "allow": {}, "deny": {}, "user_key": "u"})),
    ("smoke-expect-version-cmd-empty", lambda: _minimal(
        smoke={"cli": "e", "test": "t.py", "expect": {"version_cmd": []}})),
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


@pytest.mark.parametrize("obj", [
    FieldSpec(key="k", source="stem"),
    RoleSpec(mode="preserve"),
    Route(kind="exact", src="a", dest="b"),
    Artifact(dest="p.json"),
    TemplateValue(kind="js_string", value="v"),
    Template(src="eco.template.x", dest="x"),
    EcosystemDescriptor(name="eco", vars={}, models={}, smoke={}, dispatch="path", roles={}),
], ids=lambda o: type(o).__name__)
def test_descriptor_dataclasses_are_frozen(obj):
    """Every parsed descriptor structure is an immutable snapshot — assigning to a field raises,
    so a validated descriptor can't be mutated out from under the build mid-run."""
    field_name = dataclasses.fields(obj)[0].name
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(obj, field_name, "mutated")


def test_a_hidden_dotfile_sibling_is_skipped_not_failed(tmp_path):
    """The layout schema tolerates hidden dotfiles (editor/OS droppings) — a ``.DS_Store`` beside a
    valid descriptor must be silently skipped, NOT fail discovery the way a stray real file does.
    Pins the ``startswith('.')`` skip clause in _validate_layout."""
    (tmp_path / "eco.json").write_text(json.dumps(_minimal()), encoding="utf-8")
    (tmp_path / ".DS_Store").write_text("junk", encoding="utf-8")
    assert sorted(discover(tmp_path)) == ["eco"]
