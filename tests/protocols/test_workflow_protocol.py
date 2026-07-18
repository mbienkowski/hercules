"""The workflow protocol is the source of truth for step order and hard guardrails.

These are structural/policy gates over dist/claude-code/protocols/workflow-protocol.md and its wiring:
anchors resolve, the delegation packet keeps its field order, the guardrail registry stays
well-formed and bidirectionally anchored to the commands, and the one hook-class row maps to a
live PreToolUse hook. Tests assert packet/registry TEXT and STRUCTURE — no test can prove an
agent *obeyed* a prompt-only rule at runtime (see tests/workflow/test_workflow_modes.py).
"""

from __future__ import annotations

import json
import re

import pytest

_PROTOCOL = "dist/claude-code/protocols/workflow-protocol.md"
_SPAWNING_COMMANDS = [
    "dist/claude-code/commands/discover.md",
    "dist/claude-code/commands/design.md",
    "dist/claude-code/commands/build.md",
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


def test_every_core_protocol_section_can_be_linked_to_directly(read_file):
    """Each key section of the workflow protocol (Discover, Design, Build, Ship, the guardrail
    registry, the handoff packet, role expectations) must have a stable link target, even though
    its visible heading text can be reworded freely. Losing one of these link targets would
    silently break every other document that points into that section."""
    anchors = _declared_anchors(read_file(_PROTOCOL))
    missing = _REQUIRED_ANCHORS - anchors
    assert not missing, f"workflow-protocol.md is missing explicit anchors: {sorted(missing)}"


def test_every_link_to_the_protocol_points_to_a_real_section(repo_root, read_file):
    """Every place in the shipped plugin or the Code of Conduct that links to a specific section
    of the workflow protocol must point at a section that actually exists there. A stale link
    would send a reader (or an agent following the reference) to a section that was renamed or
    removed."""
    anchors = _declared_anchors(read_file(_PROTOCOL))
    ref_re = re.compile(r"workflow-protocol\.md#([a-z0-9-]+)")
    targets = [str(p.relative_to(repo_root)) for p in (repo_root / "dist" / "claude-code").rglob("*.md")]
    targets.append("CODE_OF_CONDUCT.md")
    refs = {}
    for rel in targets:
        for m in ref_re.finditer(read_file(rel)):
            refs.setdefault(m.group(1), []).append(rel)
    unresolved = {a: files for a, files in refs.items() if a not in anchors}
    assert not unresolved, f"references to undeclared protocol anchors: {unresolved}"


@pytest.mark.parametrize("rel", _SPAWNING_COMMANDS)
def test_each_command_that_hands_off_work_includes_the_handoff_packet(read_file, rel):
    """Every command that starts a subagent (discover, design, build) must include the standard
    handoff packet at the point it starts that subagent. Without it, the subagent would be
    launched without knowing its phase, expectations, guardrails, or context."""
    assert "workflow-protocol.md#packet" in read_file(rel), \
        f"{rel} must compose the delegation packet (workflow-protocol.md#packet) at its spawns"


def test_agent_handoff_instructions_reference_the_handoff_packet(read_file):
    """The instructions for how one agent hands work to another must explicitly name the
    standard handoff packet that wraps the shared agent-to-agent instructions, so anyone
    following that guidance knows to include it."""
    assert "workflow-protocol.md#packet" in read_file("dist/claude-code/protocols/a2a-communication-protocol.md"), \
        "a2a § How to inject must name the delegation packet wrapping the Core"


def test_the_handoff_packet_lists_its_fields_in_the_required_order(read_file):
    """The template for the handoff packet must present its fields in a fixed order: Phase,
    Expected outcome, Guardrails, Context, optional Round, then the shared instructions. Putting
    Guardrails before Context matters because a long block of context could otherwise bury the
    safety rules where a reader skims past them."""
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


def test_every_guardrail_rule_is_completely_and_correctly_documented(read_file):
    """Every rule in the guardrail rulebook must have a unique ID, say which phase and step it
    applies to, state its scope, spell out the actual rule, and honestly label how strictly it
    is enforced. Reviewers rely on that enforcement label to know which rules are guaranteed
    versus merely requested, so a missing or malformed row would mislead them."""
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


def _hook_wiring(repo_root, read_file):
    """(hook-class registry rows, PreToolUse matchers, wired commands) — shared by the hook tests."""
    hook_rows = [r for r in _registry_rows(_section(read_file(_PROTOCOL), "registry")) if r[-1] == "hook"]
    pre = json.loads((repo_root / "src" / "targets" / "claude-code" / "hooks" / "hooks.json").read_text())["hooks"]["PreToolUse"]
    matchers = [entry["matcher"] for entry in pre]
    # Fold exec-form `args` into the command string — the script path lives in `args` under exec
    # form, in `command` under shell form; joining keeps the wiring checks form-agnostic.
    commands = [
        " ".join([h.get("command", "")] + list(h.get("args", [])))
        for entry in pre for h in entry["hooks"]
    ]
    return hook_rows, matchers, commands


def test_rules_labeled_as_automatically_enforced_actually_name_their_enforcement_mechanism(repo_root, read_file):
    """A guardrail rule that claims to be automatically enforced (rather than just requested) is
    making the strongest promise in the rulebook, so at least one such rule must exist, and each
    one must name the real mechanism that blocks the disallowed action. Otherwise the rulebook
    would advertise a safety guarantee that nothing actually backs up."""
    hook_rows, _m, _c = _hook_wiring(repo_root, read_file)
    assert hook_rows, "the registry must carry at least one hook-class (runtime-enforced) row"
    for r in hook_rows:
        assert "PreToolUse" in " ".join(r), \
            f"{r[0]} claims class=hook but its rule text names no PreToolUse mechanism"


def test_the_automatic_safety_checks_are_installed_and_watch_file_edits(repo_root, read_file):
    """Every automatic safety check that the configuration says should run before a tool
    executes must actually be present on disk, and file-editing actions specifically must be
    covered (this is what protects frozen tests from being silently changed). A missing script
    or an uncovered edit action would leave the safety check advertised but not actually running."""
    _hr, matchers, commands = _hook_wiring(repo_root, read_file)
    assert any("Edit" in m for m in matchers), "PreToolUse must match Edit for the frozen guard"
    for cmd in commands:
        script = cmd.split("${CLAUDE_PLUGIN_ROOT}/")[-1].strip('"')
        assert (repo_root / "dist" / "claude-code" / script).is_file(), f"hook script missing: {script}"


def test_the_frozen_test_protection_is_actually_installed_and_active(repo_root, read_file):
    """The rule that claims runtime enforcement must be the one protecting frozen tests from
    being edited, and the actual protection script it names must be wired up to run. If either
    were missing, a frozen test could be quietly changed even though the rulebook promises it
    can't be."""
    hook_rows, _m, commands = _hook_wiring(repo_root, read_file)
    assert next((r for r in hook_rows if "frozen" in " ".join(r).casefold()), None), \
        "the hook-class row must be the frozen-tests guard"
    assert any("frozen_tests.py" in c for c in commands), \
        "hooks.json must wire the frozen_tests.py script the registry row claims"


# Bidirectional drift anchors: the token must appear in the registry ROW text AND in the
# command file that owns the rule — the protocol can neither invent a rule the commands don't
# carry, nor can a command drop a rule the registry still claims.
_DRIFT_ANCHORS = [
    ("G1", "frozen", "dist/claude-code/commands/build.md"),
    ("G2", "3 implementation rounds", "dist/claude-code/commands/build.md"),
    ("G3", "scaffold", "dist/claude-code/commands/build.md"),
    ("G4", "named passing test", "dist/claude-code/commands/build.md"),
    ("G5", "high-risk", "dist/claude-code/commands/build.md"),
    ("G6", "build_complete", "dist/claude-code/commands/ship.md"),
    ("G7", "scored once", "dist/claude-code/skills/hercules-reference/SKILL.md"),
]


@pytest.mark.parametrize("gid,token,command", _DRIFT_ANCHORS)
def test_a_documented_rule_and_the_command_that_carries_it_stay_in_sync(read_file, gid, token, command):
    """For each key rule in the guardrail rulebook (e.g. frozen tests, the 3-round build limit),
    the rulebook's own description and the command file that actually carries that rule out must
    both mention the same identifying phrase. If one side drifted from the other, the rulebook
    would be documenting a rule the command no longer enforces, or vice versa."""
    rows = _registry_rows(_section(read_file(_PROTOCOL), "registry"))
    row = next((r for r in rows if r[0] == gid), None)
    assert row, f"registry must carry row {gid}"
    assert token.casefold() in " ".join(row).casefold(), (
        f"{gid}'s row text must anchor on {token!r}"
    )
    assert token.casefold() in read_file(command).casefold(), (
        f"{command} must carry the {token!r} rule that {gid} claims"
    )


_PROTO_BUILD_TOKENS = [r"scaffold", r"write failing tests", r"\bimplement\b", r"quality gates",
                       r"mutation gate", r"traceability", r"\badvance\b", r"checkpoint",
                       r"retire spec", r"cross-check"]
_BUILD_MD_TOKENS = [r"\*\*scaffold\.\*\*", r"\*\*write failing tests\.\*\*", r"\*\*implement\.\*\*",
                    r"\*\*quality gates\.\*\*", r"\*\*mutation gate\.\*\*", r"\*\*traceability\.\*\*",
                    r"\*\*advance\.\*\*", r"\*\*write the checkpoint\.\*\*", r"\*\*retire the spec\.\*\*",
                    r"## cross-check validation"]


def _assert_tokens_in_order(text, tokens, name):
    """Each token appears, and their positions form an increasing (ordered) subsequence."""
    idxs = []
    for tok in tokens:
        m = re.search(tok, text)
        assert m, f"{name} must contain step token {tok!r}"
        idxs.append(m.start())
    assert idxs == sorted(idxs), f"{name} steps out of order: {list(zip(tokens, idxs))}"


def test_the_build_phase_steps_are_documented_in_the_correct_order(read_file):
    """The workflow protocol's description of the Build phase must present its steps — scaffold,
    write failing tests, implement, run quality gates, mutation testing, traceability, advance,
    checkpoint, retire the spec, cross-check — in that exact order, matching how Build actually
    has to be carried out."""
    proto = _section(read_file(_PROTOCOL), "phase-build").casefold()
    _assert_tokens_in_order(proto, _PROTO_BUILD_TOKENS, "protocol {#phase-build}")


def test_the_build_commands_steps_follow_the_same_order_as_the_protocol(read_file):
    """The build command's own execution instructions must walk through the same Build-phase
    steps, in the same order, as the workflow protocol describes. If the two drifted apart, an
    agent following the command would end up doing steps out of the order the protocol
    guarantees."""
    build = read_file("dist/claude-code/commands/build.md").casefold()
    _assert_tokens_in_order(build[build.index("## execution"):], _BUILD_MD_TOKENS, "build.md ## Execution")


@pytest.mark.parametrize("source", ["protocol", "design.md", "diagram"])
def test_the_design_phase_checks_the_project_tier_before_asking_design_questions(read_file, source):
    """Wherever the Design phase is described — the protocol, the design command, or the
    workflow diagram — it must determine the project's tier before it starts asking design
    questions. Asking the questions first would mean tier-specific guidance arrives too late to
    shape them."""
    text = {
        "protocol": _section(read_file(_PROTOCOL), "phase-design"),
        "design.md": read_file("dist/claude-code/commands/design.md"),
        "diagram": read_file("docs/workflow/workflow-diagram-detailed.html"),
    }[source].casefold()
    m = re.search(r"read (?:the )?tier", text)
    assert m, f"{source} must carry a read-the-tier step"
    assert m.start() < text.index("design questions"), f"{source} must read the tier before the design questions"


def test_handoff_specific_fields_never_leak_into_the_shared_core_instructions(repo_root, read_file):
    """The handoff packet wraps the shared agent-to-agent instructions but must never change
    them: the packet template does declare its own Expected/Guardrails fields, but those field
    labels must never appear inside the reference copy of the shared instructions. If they did,
    the process used to refresh that reference copy could quietly absorb packet-only fields into
    instructions every agent shares."""
    section = _section(read_file(_PROTOCOL), "packet")
    assert "Expected:" in section and "Guardrails:" in section
    golden = (repo_root / "tests" / "testdata" / "core.golden").read_text()
    for label in ("Expected:", "Guardrails:", "Phase: {phase}"):
        assert label not in golden, (
            f"packet label {label!r} leaked into the golden a2a Core — the packet must wrap, "
            "never mutate, the Core"
        )


def test_role_expectations_only_reference_sections_that_exist_in_the_spec_template(read_file):
    """Every named section that the role-expectations text points a role to (e.g. "read §Scope")
    must be a heading the design command's spec template actually produces, checked against the
    template's real current headings rather than a copy that could go stale. A role pointed at a
    section the template no longer produces would be told to read something that isn't there."""
    template_headings = {
        m.group(1).strip()
        for m in re.finditer(r"(?m)^## ([A-Z][^\n]*)$", read_file("dist/claude-code/commands/design.md"))
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
