"""Guards for the per-ecosystem build registry (Spec 06 — generic-build seam).

These pin the invariants that let ``cli.build_target`` stay branch-free: the target registry and the
serializer registry agree, ``Target.dest`` routes correctly, and ``cli.py`` carries no per-ecosystem
special-casing.
"""
from __future__ import annotations

import dataclasses
import re
from pathlib import Path

import pytest

from scripts.build import cli, serialize
from scripts.build import targets as target_registry
from scripts.build.targets.base import ExtrasContext, Target

CLI_SRC = Path(cli.__file__).read_text(encoding="utf-8")


def test_every_build_target_has_a_serializer():
    # The invariant that keeps build_target from KeyError-ing: every registered ecosystem descriptor
    # must have a serializer to dispatch to. (The reverse is intentionally not required — a bare
    # serializer with no descriptor renders content-only, preserving the pre-registry contract; tests
    # register such stubs, so we assert the subset that actually matters, not strict equality.)
    assert set(target_registry.registered_target_names()) <= set(serialize.registered_targets())


def test_registered_target_names_is_the_single_ecosystem_list():
    assert target_registry.registered_target_names() == ["claude-code", "cursor", "opencode"]
    assert tuple(target_registry.registered_target_names()) == cli.TARGETS


def test_registered_target_names_are_sorted_not_registration_order():
    # Guards the `sorted(_REGISTRY)` in registered_target_names(): a `sorted`->`list` regression would
    # return insertion order. Register a name that sorts FIRST but is inserted LAST to force the issue.
    from scripts.build.targets import base
    base.register(Target(name="aaa-registered-last"))
    try:
        names = target_registry.registered_target_names()
        assert names == sorted(names), "registered_target_names must be sorted, not insertion order"
        assert names[0] == "aaa-registered-last"
    finally:
        base._REGISTRY.pop("aaa-registered-last", None)


def test_target_and_extras_context_are_immutable():
    # frozen=True on both is load-bearing: a build descriptor or its extras context must not be
    # mutated mid-build. (Also kills the frozen=True->False mutant on each dataclass.)
    with pytest.raises(dataclasses.FrozenInstanceError):
        Target(name="x").name = "y"
    ctx = ExtrasContext(out_root=Path("/tmp"), src_target_dir=Path("/tmp"),
                        shared_hooks_src=Path("/tmp"), src_content=Path("/tmp"), tokens={})
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.out_root = Path("/other")


def test_target_dest_applies_renames_and_passes_others_through():
    t = Target(name="x", renames={"persona.md": "CLAUDE.md"})
    assert t.dest("persona.md") == "CLAUDE.md"
    assert t.dest("agents/lead-architect.md") == "agents/lead-architect.md"


def test_target_dest_prefers_a_dest_fn_when_present():
    t = Target(name="x", dest_fn=lambda rel: f"rules/{rel}")
    assert t.dest("persona.md") == "rules/persona.md"


def test_cursor_persona_relocates_to_the_mdc_rule_via_dest():
    # The load-bearing .mdc mapping stays in serialize.cursor_dest (mutation-covered); the Target
    # just wires it in. Guard that the wiring is intact.
    assert target_registry.get("cursor").dest("persona.md") == "rules/hercules-persona.mdc"


def test_cli_build_target_has_no_per_ecosystem_branches():
    # The whole point of Spec 06: cli.py dispatches through the registry, never on the target name.
    # (The one literal "claude-code" that remains is the canonical shared-hooks SOURCE path, a
    # build-wide constant, not a dispatch branch — so we assert on branch smells, not name literals.)
    assert "target ==" not in CLI_SRC, "cli.py still branches on the target name"
    assert not re.search(r"\belif\b", CLI_SRC), "cli.py still has an if/elif extras tail"
    assert '"opencode"' not in CLI_SRC and '"cursor"' not in CLI_SRC, \
        "cli.py must not dispatch on a quoted ecosystem name"
