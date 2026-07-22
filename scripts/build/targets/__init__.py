"""The build's target registry — populated from the ecosystem descriptors, zero per-ecosystem code.

Importing this package registers one :class:`~scripts.build.targets.base.Target` per
``src/ecosystems/<name>.json``: destination routing via the generic route interpreter
(``genserialize.dest``) and non-content artifacts via the generic extras emitter
(``genextras.emit_extras``), both driven wholly by the descriptor. A new ecosystem is one new JSON
file — it appears here, in ``cli.TARGETS``, and in the CI smoke matrix automatically (and the
enforcement-gate test then fails until its hand-authored gate expectation exists).
"""
from __future__ import annotations

from functools import partial

from scripts.build import genextras, genserialize
from scripts.build.descriptor import discover
from scripts.build.targets.base import (
    ExtrasContext,
    Target,
    get,
    register,
    registered_target_names,
)

for _descriptor in discover().values():
    register(Target(
        name=_descriptor.name,
        dest_fn=partial(genserialize.dest, _descriptor),
        emit_extras_fn=partial(genextras.emit_extras, descriptor=_descriptor),
    ))

__all__ = ["ExtrasContext", "Target", "get", "register", "registered_target_names"]
