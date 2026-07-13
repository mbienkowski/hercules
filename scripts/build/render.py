"""Body token + switch rendering (pure, byte-preserving).

Substitutes only a known **allowlist** of Hercules tokens; any other ``${…}`` (notably
``${CLAUDE_PLUGIN_ROOT}`` used in prose and hooks) passes through verbatim. Never normalises
whitespace — only marker spans change — so a Claude render reproduces the source bytes exactly.
"""
from __future__ import annotations

import re

_TOKEN = re.compile(r"\$\{([A-Za-z0-9_.]+)\}")
_DIRECTIVE = re.compile(r"\$\{target:([^}]*)\}")
_TARGET_NAME = re.compile(r"[a-z][a-z0-9-]*\Z")


class RenderError(ValueError):
    """Raised on a malformed or unclosed ``${target:…}`` switch."""


def _resolve_switches(text: str, target: str) -> str:
    lines = text.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        m = _DIRECTIVE.fullmatch(lines[i])
        if not m:
            out.append(lines[i])
            i += 1
            continue
        name = m.group(1)
        if name == "end":
            raise RenderError("`${target:end}` without an opening branch")  # pragma: no mutate
        if not _TARGET_NAME.match(name):
            raise RenderError(f"malformed switch directive: {lines[i]!r}")  # pragma: no mutate
        branches: dict[str, list[str]] = {name: []}
        current = name
        i += 1
        closed = False
        while i < len(lines):
            mm = _DIRECTIVE.fullmatch(lines[i])
            if mm:
                nm = mm.group(1)
                if nm == "end":
                    closed = True
                    i += 1
                    break
                if not _TARGET_NAME.match(nm):
                    raise RenderError(f"malformed switch directive: {lines[i]!r}")  # pragma: no mutate
                current = nm
                branches[nm] = []
                i += 1
                continue
            branches[current].append(lines[i])
            i += 1
        if not closed:
            raise RenderError("unclosed `${target:…}` switch")  # pragma: no mutate
        # Match the full target key, then its short alias (claude-code → claude), then default.
        chosen: list[str] = []
        for key in (target, target.split("-", 1)[0], "default"):
            if key in branches:
                chosen = branches[key]
                break
        out.append("\n".join(chosen))
    return "\n".join(out)


def render_body(text: str, target: str, tokens: dict[str, str]) -> str:
    """Resolve ``${target:…}`` switches then ``${var}`` allowlist tokens for *target*.

    Unknown ``${name}`` (not in *tokens*) passes through verbatim. Raises :class:`RenderError` only on
    a malformed or unclosed switch.
    """
    resolved = _resolve_switches(text, target)
    return _TOKEN.sub(lambda m: tokens.get(m.group(1), m.group(0)), resolved)
