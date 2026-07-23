"""Frontmatter + document parsing (pure).

``parse_frontmatter`` / ``render_frontmatter`` are lifted from ``pr-11:scripts/generate_opencode.py``
— they round-trip today's clean ``key: value`` frontmatter byte-for-byte (proven by the keystone gate
in ``tests/build/test_frontmatter_roundtrip.py``). ``split_document`` is the byte-preserving splitter
Claude-target rendering relies on.
"""
from __future__ import annotations

_FENCE = "---"


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Return ``(frontmatter_dict, body)`` for a markdown document.

    A document with no ``---`` fence yields ``({}, text.strip())``. Values are ``strip``-ed, so this
    is *not* byte-preserving — use :func:`split_document` when exact bytes matter.
    """
    text = text.strip()
    if not text.startswith(_FENCE):
        return {}, text
    # Split on FENCE *lines*, not the bare substring: a frontmatter VALUE containing "---" (e.g.
    # ``description: pros --- cons``) must not be mistaken for the closing fence, which would
    # truncate the value and silently drop every key after it.
    lines = text.splitlines()
    close = next((i for i in range(1, len(lines)) if lines[i].strip() == _FENCE), None)
    if close is None:
        return {}, text
    metadata: dict[str, str] = {}
    for line in lines[1:close]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip()
    return metadata, "\n".join(lines[close + 1:]).strip()


def render_frontmatter(metadata: dict[str, str]) -> str:
    """Render an ordered ``metadata`` dict to a ``---``-fenced YAML block (no trailing newline)."""
    lines = [_FENCE]
    for key, value in metadata.items():
        lines.append(f"{key}: {value}")
    lines.append(_FENCE)
    return "\n".join(lines)


def split_document(text: str) -> tuple[str | None, str]:
    """Split into ``(raw_frontmatter_block_or_None, body)`` losslessly: ``(block or "") + body == text``.

    A frontmatter block is present only when *text* opens with ``---\\n`` and a later line is exactly
    ``---``. The returned block includes both fences and the single newline after the closing fence;
    the body is returned verbatim (no ``strip``).
    """
    if not text.startswith(_FENCE + "\n"):
        return None, text
    close = text.find("\n" + _FENCE, len(_FENCE) + 1)
    if close == -1:
        return None, text
    end = close + 1 + len(_FENCE)  # position just past the closing "---"
    if end < len(text) and text[end] == "\n":
        end += 1
    return text[:end], text[end:]
