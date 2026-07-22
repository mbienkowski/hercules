"""The ONE generic extras emitter — every non-content artifact, driven by the descriptor.

Four descriptor sections map onto four named emission behaviors (a closed set, validated by
``descriptor.py``):

- ``artifacts`` — inline JSON objects dumped canonically (2-space, trailing newline); ``versioned``
  substitutes the single ``${version}`` token from the canonical version, fail-loud on zero/many
  (the same contract as the version-injection invariant).
- shipped siblings — every ``src/ecosystems/<name>.dist.<dest>`` file byte-copied to plugin-root
  ``<dest>``: the filename IS the routing (``descriptor.dist_files``), no separate mapping to drift.
- ``guard`` + ``gate`` — the shared enforcement code (``src/hooks/``: canonical guard modules and
  the ONE generic write-gate adapter) byte-copied into ``hooks/``, with the ecosystem's ``gate``
  parameters emitted as ``hooks/gate.json`` beside it.
- ``templates`` — ``<name>.template.<dest>`` sibling text rendered by single-pass placeholder
  substitution with values from a closed computed-value vocabulary (``js_string``,
  ``js_string_list``, ``js_root_joins``, ``role_entries_js``). Role entries are computed from the
  SAME descriptor role fields the standalone files use, so an inlined entry (e.g. OpenCode's
  ``plugin.js`` agent map) and its standalone mirror can never drift by construction.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from scripts.build import emit
from scripts.build.descriptor import ECOSYSTEMS_DIR, EcosystemDescriptor, dist_files
from scripts.build.genserialize import compute_fields
from scripts.build.parse import parse_frontmatter, split_document
from scripts.build.render import render_body

_VERSION_TOKEN = re.compile(r"\$\{version\}")
_PLACEHOLDER = re.compile(r"__[A-Z_]+__")


def _dump_json(content: dict) -> str:
    """The one canonical JSON byte-format every emitted artifact uses."""
    return json.dumps(content, indent=2, ensure_ascii=False) + "\n"


def _versioned_text(text: str, version: str, dest: str) -> str:
    """Substitute the single ``${version}`` token; fail LOUD on zero or many — a release manifest
    must never ship the literal token or a stray extra substitution."""
    new, n = _VERSION_TOKEN.subn(version, text)
    if n != 1:
        raise SystemExit(  # pragma: no mutate - message text only
            f"genextras: expected exactly one ${{version}} token in artifact {dest!r}, found {n}"
        )
    return new


# ---- JavaScript-literal serialization (generic; used by the js_* template value kinds) ----

def js_string(value: str) -> str:
    """Return a JSON-stringified JavaScript string literal (non-ASCII kept literal)."""
    return json.dumps(value, ensure_ascii=False)


def js_object_literal(obj, indent: int = 8) -> str:
    """Render a JSON-serialisable object as a JS object literal (keys bare when identifier-safe)."""
    spaces = " " * indent
    if isinstance(obj, dict):
        if not obj:
            return "{}"
        items = []
        for k, v in obj.items():
            key = k if re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", k) else js_string(k)
            items.append(f"{spaces}  {key}: {js_object_literal(v, indent + 2)},")
        return "{\n" + "\n".join(items) + f"\n{spaces}}}"
    if isinstance(obj, list):
        if not obj:
            return "[]"
        return "[" + ", ".join(js_object_literal(v, indent + 2) for v in obj) + "]"
    if isinstance(obj, bool):
        return "true" if obj else "false"
    if isinstance(obj, str):
        return js_string(obj)
    if obj is None:
        return "null"
    return str(obj)


# ---- role entries (generic; the shared source for inlined entry maps and their mirrors) ----

_ROLE_SUBDIRS = {"agent": "agents", "command": "commands"}


def role_entries(descriptor: EcosystemDescriptor, src_content: Path, tokens: dict, role: str):
    """Collect ``(stem, fields, body)`` triples for *role* — fields computed from the descriptor's
    OWN role field specs (minus ``name``, which becomes the entry key), body rendered and fully
    stripped. One source of truth for template entry maps and the standalone-file mirror tests."""
    out = []
    for src in sorted((src_content / _ROLE_SUBDIRS[role]).glob("*.md")):
        text = src.read_text(encoding="utf-8")
        meta, _ = parse_frontmatter(text)
        _, body = split_document(text)
        fields = compute_fields(descriptor.roles[role].fields, meta, descriptor.name,
                                tokens, stem=src.stem)
        fields.pop("name", None)
        out.append((src.stem, fields, render_body(body, descriptor.name, tokens).strip()))
    return out


def _template_value(spec, descriptor: EcosystemDescriptor, ctx) -> str:
    """Evaluate one closed-vocabulary template value to its substitution text."""
    if spec.kind == "js_string":
        return js_string(spec.value)
    if spec.kind == "js_string_list":
        return ", ".join(js_string(v) for v in spec.values)
    if spec.kind == "js_root_joins":
        return ",\n        ".join(f"path.join(PLUGIN_ROOT, {js_string(p)})" for p in spec.paths)
    # spec.kind == "role_entries_js" — the only other validated kind
    entries = {}
    for stem, fields, body in role_entries(descriptor, ctx.src_content, ctx.tokens, spec.role):
        kept = {k: v for k, v in fields.items() if k not in spec.drop}
        kept[spec.body_key] = body
        entries[spec.key_prefix + stem] = kept
    return js_object_literal(entries)


def _render_template(descriptor: EcosystemDescriptor, template, ctx) -> str:
    """Single-pass placeholder substitution: every ``__X__`` is filled from values computed up
    front, so an inserted value can never be re-scanned and have a LATER placeholder rewritten
    inside it; an unknown placeholder passes through unchanged."""
    text = (ECOSYSTEMS_DIR / template.src).read_text(encoding="utf-8")
    values = {p: _template_value(v, descriptor, ctx) for p, v in template.values.items()}
    return _PLACEHOLDER.sub(lambda m: values.get(m.group(0), m.group(0)), text)


def emit_extras(ctx, descriptor: EcosystemDescriptor) -> list:
    """Emit every non-content artifact the descriptor declares; return the written rels."""
    written: list = []
    for artifact in descriptor.artifacts:
        text = _dump_json(artifact.content)
        if artifact.versioned:
            text = _versioned_text(text, ctx.version, artifact.dest)
        emit.write(ctx.out_root / artifact.dest, text)
        written.append(artifact.dest)
    siblings = dist_files(descriptor.name)
    if siblings:
        written += emit.copy_map(ECOSYSTEMS_DIR, ctx.out_root,
                                 {path.name: dest for dest, path in siblings.items()})
    if descriptor.guard:
        written += emit.copy_map(ctx.shared_hooks_src, ctx.out_root,
                                 {name: f"hooks/{name}" for name in descriptor.guard})
    if descriptor.gate is not None:
        emit.write(ctx.out_root / "hooks" / "gate.json", _dump_json(descriptor.gate))
        written.append("hooks/gate.json")
    for template in descriptor.templates:
        emit.write(ctx.out_root / template.dest, _render_template(descriptor, template, ctx))
        written.append(template.dest)
    return written
