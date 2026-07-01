"""The workflow protocol is the source of truth for step order and hard guardrails.

These are structural/policy gates over plugin/protocols/workflow-protocol.md and its wiring:
anchors resolve, the delegation packet keeps its field order, the guardrail registry stays
well-formed and bidirectionally anchored to the commands, and the one hook-class row maps to a
live PreToolUse hook. Tests assert packet/registry TEXT and STRUCTURE — no test can prove an
agent *obeyed* a prompt-only rule at runtime (see tests/workflow/test_workflow_modes.py).
"""

from __future__ import annotations

import json
import re

import pytest

_PROTOCOL = "plugin/protocols/workflow-protocol.md"
_SPAWNING_COMMANDS = [
    "plugin/commands/discover.md",
    "plugin/commands/design.md",
    "plugin/commands/build.md",
]

_ANCHOR_RE = re.compile(r"\{#([a-z0-9-]+)\}")
_REQUIRED_ANCHORS = {
    "phase-discover", "phase-design", "phase-build", "phase-ship",
    "registry", "packet", "role-expectations",
}
_ENFORCEMENT_CLASSES = {"hook", "executable", "state-checkable", "prompt-only"}


def _declared_anchors(md: str) -> set:
    return set(_ANCHOR_RE.findall(md))


def _registry_rows(md: str) -> list:
    """Parse the guardrail-registry table rows, tolerant of escaped pipes in rule text."""
    lines = md.splitlines()
    header_i = next(i for i, ln in enumerate(lines) if ln.strip().startswith("| ID |"))
    rows = []
    for ln in lines[header_i + 2:]:  # skip header + dash separator
        if not ln.strip().startswith("|"):
            break
        cells = [c.strip() for c in re.split(r"(?<!\\)\|", ln)]
        cells = [c for c in cells if c != ""]
        rows.append(cells)
    return rows


def _section(md: str, anchor: str) -> str:
    """The slice from a `{#anchor}` heading to the next heading of the same-or-higher level."""
    m = re.search(rf"(?m)^(#+)[^\n]*\{{#{anchor}\}}\s*$", md)
    assert m, f"protocol must declare a heading with {{#{anchor}}}"
    level = len(m.group(1))
    rest = md[m.end():]
    nxt = re.search(rf"(?m)^#{{1,{level}}}\s", rest)
    return rest[: nxt.start()] if nxt else rest


def test_protocol_declares_required_sections_with_explicit_anchors(read_file):
    """Every section the packet composer and these tests slice by must carry an explicit
    {#kebab} anchor — display text can change freely; anchors cannot."""
    anchors = _declared_anchors(read_file(_PROTOCOL))
    missing = _REQUIRED_ANCHORS - anchors
    assert not missing, f"workflow-protocol.md is missing explicit anchors: {sorted(missing)}"


def test_protocol_anchor_references_resolve_and_protocol_is_wired(repo_root, read_file):
    """Every `workflow-protocol.md#X` reference in the shipped plugin + the CoC resolves to a
    declared anchor, and the protocol is actually wired: every spawning command composes the
    delegation packet, and the a2a injection rules name it."""
    anchors = _declared_anchors(read_file(_PROTOCOL))
    ref_re = re.compile(r"workflow-protocol\.md#([a-z0-9-]+)")

    targets = [str(p.relative_to(repo_root)) for p in (repo_root / "plugin").rglob("*.md")]
    targets.append("CODE_OF_CONDUCT.md")
    refs = {}
    for rel in targets:
        for m in ref_re.finditer(read_file(rel)):
            refs.setdefault(m.group(1), []).append(rel)
    unresolved = {a: files for a, files in refs.items() if a not in anchors}
    assert not unresolved, f"references to undeclared protocol anchors: {unresolved}"

    for rel in _SPAWNING_COMMANDS:
        assert "workflow-protocol.md#packet" in read_file(rel), (
            f"{rel} must compose the delegation packet (workflow-protocol.md#packet) at its spawns"
        )
    assert "workflow-protocol.md#packet" in read_file(
        "plugin/protocols/a2a-communication-protocol.md"
    ), "a2a § How to inject must name the delegation packet wrapping the Core"


def test_delegation_packet_keeps_its_field_order(read_file):
    """The packet fence (located via the {#packet} heading, not first-fence luck) must declare
    the full field chain in order: Phase < Expected < Guardrails < Context < [Round < the
    Core-follows marker. Guardrails before Context is what stops a large slice burying rules."""
    section = _section(read_file(_PROTOCOL), "packet")
    fence = re.search(r"```\n(.*?)```", section, re.S)
    assert fence, "the {#packet} section must carry a fenced packet template"
    body = fence.group(1)
    chain = ["Phase:", "Expected:", "Guardrails:", "Context:", "[Round:",
             "A2A Agent-Injected Core follows"]
    idxs = []
    for label in chain:
        assert label in body, f"packet template must declare {label!r}"
        idxs.append(body.index(label))
    assert idxs == sorted(idxs), f"packet fields out of order: {chain} at {idxs}"
    assert "verbatim" in section, "the packet must require verbatim registry-row copies"


def test_guardrail_registry_rows_are_well_formed(read_file):
    """Every registry row: unique G-number ID, a phase·step key, a scope, a non-empty rule, and
    a declared enforcement class from the closed set — the honesty label reviewers rely on."""
    rows = _registry_rows(_section(read_file(_PROTOCOL), "registry"))
    assert len(rows) >= 5, "the registry must carry the workflow's hard rules"
    seen = set()
    for cells in rows:
        assert len(cells) >= 5, f"registry row too few cells: {cells}"
        gid, key, scope, klass = cells[0], cells[1], cells[2], cells[-1]
        rule = " | ".join(cells[3:-1])
        assert re.fullmatch(r"G\d+", gid), f"registry ID must be G<n>: {gid!r}"
        assert gid not in seen, f"duplicate registry ID {gid}"
        seen.add(gid)
        assert "·" in key, f"registry key must be 'phase · step': {key!r}"
        assert scope, f"{gid} must declare a scope (step / span / phase)"
        assert rule.strip(), f"{gid} must carry a non-empty rule"
        assert klass in _ENFORCEMENT_CLASSES, (
            f"{gid} class {klass!r} not in {sorted(_ENFORCEMENT_CLASSES)}"
        )


def test_every_hook_class_row_maps_to_a_live_hook(repo_root, read_file):
    """A `hook`-class registry row claims harness enforcement — the strongest claim in the file.
    Each one must map to a live PreToolUse wiring (matcher covering Edit) whose script exists,
    and at least one such row ships (the frozen-tests flagship)."""
    rows = _registry_rows(_section(read_file(_PROTOCOL), "registry"))
    hook_rows = [r for r in rows if r[-1] == "hook"]
    assert hook_rows, "the registry must carry at least one hook-class (harness-enforced) row"

    hooks = json.loads((repo_root / "plugin" / "hooks" / "hooks.json").read_text())
    pre = hooks["hooks"]["PreToolUse"]
    matchers = [entry["matcher"] for entry in pre]
    commands = [h["command"] for entry in pre for h in entry["hooks"]]
    assert any("Edit" in m for m in matchers), "PreToolUse must match Edit for the frozen guard"
    for cmd in commands:
        script = cmd.split("${CLAUDE_PLUGIN_ROOT}/")[-1].strip('"')
        assert (repo_root / "plugin" / script).is_file(), f"hook script missing: {script}"

    g1 = next((r for r in hook_rows if "frozen" in " ".join(r).casefold()), None)
    assert g1, "the hook-class row must be the frozen-tests guard"
    assert any("frozen_tests.py" in c for c in commands), (
        "hooks.json must wire the frozen_tests.py script the registry row claims"
    )


# Bidirectional drift anchors: the token must appear in the registry ROW text AND in the
# command file that owns the rule — the protocol can neither invent a rule the commands don't
# carry, nor can a command drop a rule the registry still claims.
_DRIFT_ANCHORS = [
    ("G1", "frozen", "plugin/commands/build.md"),
    ("G2", "3 implementation rounds", "plugin/commands/build.md"),
    ("G3", "scaffold", "plugin/commands/build.md"),
    ("G4", "named passing test", "plugin/commands/build.md"),
    ("G5", "high-risk", "plugin/commands/build.md"),
    ("G6", "build_complete", "plugin/commands/ship.md"),
    ("G7", "scored once", "plugin/CLAUDE.md"),
]


@pytest.mark.parametrize("gid,token,command", _DRIFT_ANCHORS)
def test_registry_rules_anchor_bidirectionally(read_file, gid, token, command):
    rows = _registry_rows(_section(read_file(_PROTOCOL), "registry"))
    row = next((r for r in rows if r[0] == gid), None)
    assert row, f"registry must carry row {gid}"
    assert token.casefold() in " ".join(row).casefold(), (
        f"{gid}'s row text must anchor on {token!r}"
    )
    assert token.casefold() in read_file(command).casefold(), (
        f"{command} must carry the {token!r} rule that {gid} claims"
    )


def test_protocol_and_build_md_agree_on_step_order(read_file):
    """Ordered-subsequence agreement: the Build inner loop runs in the same order in the
    protocol's {#phase-build} chain and build.md's ## Execution section; and Design reads the
    tier before its design questions in the protocol, design.md, AND the detailed diagram."""
    protocol = read_file(_PROTOCOL)
    build = read_file("plugin/commands/build.md").casefold()

    proto_slice = _section(protocol, "phase-build").casefold()
    build_slice = build[build.index("## execution"):]

    proto_tokens = [r"scaffold", r"write failing tests", r"\bimplement\b", r"quality gates",
                    r"mutation gate", r"traceability", r"\badvance\b", r"checkpoint",
                    r"retire spec", r"cross-check"]
    build_tokens = [r"\*\*scaffold\.\*\*", r"\*\*write failing tests\.\*\*",
                    r"\*\*implement\.\*\*", r"\*\*quality gates\.\*\*",
                    r"\*\*mutation gate\.\*\*", r"\*\*traceability\.\*\*", r"\*\*advance\.\*\*",
                    r"\*\*write the checkpoint\.\*\*", r"\*\*retire the spec\.\*\*",
                    r"## cross-check validation"]
    for slice_, tokens, name in ((proto_slice, proto_tokens, "protocol {#phase-build}"),
                                 (build_slice, build_tokens, "build.md ## Execution")):
        idxs = []
        for tok in tokens:
            m = re.search(tok, slice_)
            assert m, f"{name} must contain step token {tok!r}"
            idxs.append(m.start())
        assert idxs == sorted(idxs), f"{name} steps out of order: {list(zip(tokens, idxs))}"

    design = read_file("plugin/commands/design.md").casefold()
    diagram = read_file("docs/workflow/workflow-diagram-detailed.html").casefold()
    proto_design = _section(protocol, "phase-design").casefold()
    for text, name in ((proto_design, "protocol {#phase-design}"), (design, "design.md"),
                       (diagram, "detailed diagram")):
        assert text.index("read t") < text.index("design questions"), (
            f"{name} must read the tier before the design questions"
        )


def test_packet_labels_live_in_the_packet_not_the_golden_core(repo_root, read_file):
    """The packet WRAPS the a2a Core, never mutates it. Positive: the packet fence declares the
    Expected/Guardrails labels. Negative: those labels stay out of tests/testdata/core.golden —
    guarding the sanctioned re-bless path from quietly absorbing packet fields into the Core."""
    section = _section(read_file(_PROTOCOL), "packet")
    assert "Expected:" in section and "Guardrails:" in section
    golden = (repo_root / "tests" / "testdata" / "core.golden").read_text()
    for label in ("Expected:", "Guardrails:", "Phase: {phase}"):
        assert label not in golden, (
            f"packet label {label!r} leaked into the golden a2a Core — the packet must wrap, "
            "never mutate, the Core"
        )


def test_role_slices_use_the_spec_template_vocabulary(read_file):
    """Every §-section a role slice names must be a heading design.md's spec template actually
    emits (parsed at test time — the template is the closed vocabulary, not a hardcoded copy)."""
    template_headings = {
        m.group(1).strip()
        for m in re.finditer(r"(?m)^## ([A-Z][^\n]*)$", read_file("plugin/commands/design.md"))
        if not m.group(1).startswith("Step")
    }
    assert "Scope" in template_headings, "sanity: design.md template must carry ## Scope"

    roles = _section(read_file(_PROTOCOL), "role-expectations")
    slice_refs = set(re.findall(r"§([A-Z][a-z]+(?: [a-z]+)*)", roles))
    assert slice_refs, "role expectations must name §-section slices"
    unknown = {s for s in slice_refs if s not in template_headings}
    assert not unknown, (
        f"role slices name sections design.md's spec template does not emit: {sorted(unknown)} "
        f"(template has: {sorted(template_headings)})"
    )
