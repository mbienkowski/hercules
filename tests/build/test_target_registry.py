"""Guards for the generic build seam (Spec 06, generalized to the descriptor engine).

The engine has no per-ecosystem registry object any more: the ecosystem list IS the descriptor set
(``descriptor.names()``), destination routing is ``genserialize.dest`` interpreting the descriptor's
routes, and non-content emission is ``genextras.emit_extras``. These pin the invariants that keep
``cli.build_target`` branch-free — the registry and the serializer set agree, and ``cli.py`` carries
no per-ecosystem special-casing.
"""
from __future__ import annotations

import dataclasses
import re
from pathlib import Path

import pytest

from scripts.build import cli, descriptor, serialize
from scripts.build.genextras import ExtrasContext

CLI_SRC = Path(cli.__file__).read_text(encoding="utf-8")


def test_every_build_target_has_a_serializer():
    """The invariant that keeps build_target from KeyError-ing: every ecosystem the descriptors
    declare must have a registered serializer to dispatch to."""
    assert set(descriptor.names()) <= set(serialize.registered_targets())


def test_the_descriptor_set_is_the_single_ecosystem_list():
    """The descriptor files ARE the registry — the CLI target set and the CI smoke matrix both read
    it from ``descriptor.names()``, so there is no second list to drift."""
    assert descriptor.names() == ["claude-code", "copilot-cli", "cursor", "gemini-cli", "grok-build", "opencode"]
    assert tuple(descriptor.names()) == cli.TARGETS


def test_the_ecosystem_list_is_sorted_not_filesystem_order():
    """``descriptor.names()`` sorts, so the target order is stable regardless of directory listing
    order — a `sorted`->`list` regression would leak the OS's readdir order."""
    names = descriptor.names()
    assert names == sorted(names)


def test_extras_context_is_immutable():
    """frozen=True on ExtrasContext is load-bearing: the per-build emit context must not be mutated
    mid-build (also kills the frozen=True->False mutant)."""
    ctx = ExtrasContext(out_root=Path("/tmp"), shared_hooks_src=Path("/tmp"),
                        src_content=Path("/tmp"), tokens={}, version="0.0.0")
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.out_root = Path("/other")


def test_cli_build_target_has_no_per_ecosystem_branches():
    """The whole point of the generic engine: cli.py dispatches through the descriptor, never on the
    target name. (The one literal "claude-code"-free constant that remains is the shared-hooks SOURCE
    path — a build-wide constant, not a dispatch branch — so we assert on branch smells.)"""
    assert "target ==" not in CLI_SRC, "cli.py still branches on the target name"
    assert not re.search(r"\belif\b", CLI_SRC), "cli.py still has an if/elif extras tail"
    assert '"opencode"' not in CLI_SRC and '"cursor"' not in CLI_SRC, \
        "cli.py must not dispatch on a quoted ecosystem name"
