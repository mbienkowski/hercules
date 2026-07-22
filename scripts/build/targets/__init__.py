"""Per-ecosystem build descriptors — the single authoritative ecosystem registry.

Importing this package registers every ``Target`` (one module per ecosystem) as a side effect, so
``get`` / ``registered_target_names`` reflect the full set. ``cli`` and the CI smoke matrix both read
the ecosystem list from here, so there is one source of truth.
"""
from __future__ import annotations

from scripts.build.targets.base import (
    ExtrasContext,
    Target,
    get,
    register,
    registered_target_names,
)

# Registration side effects — importing each module calls register(Target(...)). One import per line
# so a new ecosystem adds its own line without colliding with a sibling target's addition.
from scripts.build.targets import claude_code  # noqa: E402,F401
from scripts.build.targets import cursor  # noqa: E402,F401
from scripts.build.targets import gemini_cli  # noqa: E402,F401
from scripts.build.targets import grok_build  # noqa: E402,F401
from scripts.build.targets import opencode  # noqa: E402,F401

__all__ = ["ExtrasContext", "Target", "get", "register", "registered_target_names"]
