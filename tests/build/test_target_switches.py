"""Guard: every ``${target:NAME}`` switch names a real target (or ``default``/``end``).

``render._resolve_switches`` silently renders an empty branch when a switch matches no target and
has no ``default``. That is deliberate for single-target blocks (e.g. an opencode-only note that is
empty on Claude). The failure mode this guards is a *typo'd* target name — ``${target:opencde}`` —
which would silently drop content on every target with no error. Coverage is intentionally NOT
required (single-target blocks are a supported pattern); only name validity is.
"""
from __future__ import annotations

import re
from pathlib import Path

from scripts.build.serialize import registered_targets

SRC_CONTENT = Path(__file__).resolve().parents[2] / "src" / "content"
_DIRECTIVE = re.compile(r"^\$\{target:([^}]*)\}$")


def _valid_names() -> set[str]:
    names = {"default", "end"}
    for target in registered_targets():
        names.add(target)
        names.add(target.split("-", 1)[0])  # short alias, e.g. claude-code → claude
    return names


def test_every_target_switch_names_a_known_target():
    valid = _valid_names()
    offenders: list[str] = []
    for md in sorted(SRC_CONTENT.rglob("*.md")):
        for lineno, line in enumerate(md.read_text(encoding="utf-8").splitlines(), start=1):
            m = _DIRECTIVE.match(line.strip())
            if m and m.group(1) not in valid:
                rel = md.relative_to(SRC_CONTENT).as_posix()
                offenders.append(f"{rel}:{lineno} → ${{target:{m.group(1)}}}")
    assert not offenders, (
        "unknown ${target:…} switch name(s) — a typo renders empty on every target:\n"
        + "\n".join(offenders)
        + f"\nvalid names: {sorted(valid)}"
    )
