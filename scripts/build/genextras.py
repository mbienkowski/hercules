"""The ONE generic extras emitter — every non-content artifact, driven by the descriptor.

Four descriptor sections map onto four named emission behaviors (a closed set, validated by
``descriptor.py``):

- ``artifacts`` — inline JSON objects dumped canonically (2-space, trailing newline); ``versioned``
  substitutes the single ``${version}`` token from the canonical version, fail-loud on zero/many
  (the same contract as ``emit.copy_versioned``).
- ``assets`` — flat sibling files (``src/ecosystems/<src>``) byte-copied to their dest.
- ``guard`` + ``gate`` — the shared enforcement code (``src/hooks/``: canonical guard modules and
  the ONE generic write-gate adapter) byte-copied into ``hooks/``, with the ecosystem's ``gate``
  parameters emitted as ``hooks/gate.json`` beside it.
- ``generate`` — named Python generators for genuinely generated output (OpenCode's ``plugin.js``
  entrypoint and ``opencode.json``); their inline agent/command entries are computed from the SAME
  descriptor role fields the standalone files use, so the two can never drift by construction.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from scripts.build import emit
from scripts.build.descriptor import ECOSYSTEMS_DIR, EcosystemDescriptor
from scripts.build.genserialize import compute_fields
from scripts.build.manifests import generate_opencode_json, generate_plugin_js
from scripts.build.parse import parse_frontmatter, split_document
from scripts.build.render import render_body

_VERSION_TOKEN = re.compile(r"\$\{version\}")


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


def opencode_entries(descriptor: EcosystemDescriptor, src_content: Path, tokens: dict):
    """Collect ``(name, meta, prompt)`` triples for the plugin.js inline entries — computed from the
    descriptor's OWN agent/command role fields (minus the ``name`` key, which becomes the entry key),
    so the inlined entries and the standalone ``.md`` files share one source of truth."""
    def collect(subdir: str, role: str):
        out = []
        for src in sorted((src_content / subdir).glob("*.md")):
            text = src.read_text(encoding="utf-8")
            meta, _ = parse_frontmatter(text)
            _, body = split_document(text)
            fields = compute_fields(descriptor.roles[role].fields, meta, descriptor.name,
                                    tokens, stem=src.stem)
            fields.pop("name", None)
            out.append((src.stem, fields, render_body(body, descriptor.name, tokens).strip()))
        return out
    return collect("agents", "agent"), collect("commands", "command")


def _run_generator(gen, ctx, descriptor: EcosystemDescriptor) -> list:
    """Dispatch one named ``generate`` step. The registry is closed (descriptor.py rejects unknown
    names); adding a generator means adding a branch HERE, with tests — never code in a descriptor."""
    if gen.name == "opencode_plugin_js":
        agents, commands = opencode_entries(descriptor, ctx.src_content, ctx.tokens)
        emit.write(ctx.out_root / "plugin.js",
                   generate_plugin_js(gen.args["default_agent"], agents, commands))
        return ["plugin.js"]
    # gen.name == "opencode_json" — the only other registered generator
    emit.write(ctx.out_root / "opencode.json", _dump_json(generate_opencode_json()))
    return ["opencode.json"]


def emit_extras(ctx, descriptor: EcosystemDescriptor) -> list:
    """Emit every non-content artifact the descriptor declares; return the written rels."""
    written: list = []
    for artifact in descriptor.artifacts:
        text = _dump_json(artifact.content)
        if artifact.versioned:
            text = _versioned_text(text, ctx.version, artifact.dest)
        emit.write(ctx.out_root / artifact.dest, text)
        written.append(artifact.dest)
    if descriptor.assets:
        written += emit.copy_map(ECOSYSTEMS_DIR, ctx.out_root,
                                 {a.src: a.dest for a in descriptor.assets})
    if descriptor.guard:
        written += emit.copy_map(ctx.shared_hooks_src, ctx.out_root,
                                 {name: f"hooks/{name}" for name in descriptor.guard})
    if descriptor.gate is not None:
        emit.write(ctx.out_root / "hooks" / "gate.json", _dump_json(descriptor.gate))
        written.append("hooks/gate.json")
    for gen in descriptor.generate:
        written += _run_generator(gen, ctx, descriptor)
    return written
