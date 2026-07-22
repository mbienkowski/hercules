"""The ONE generic serializer — descriptor-driven, zero per-ecosystem branches.

``DescriptorSerializer`` renders any source artifact for any ecosystem from its
:class:`~scripts.build.descriptor.EcosystemDescriptor`: a named *dispatch* picks the role
(agent/command/persona/default), the role's named *mode* shapes the output, and named *field
generators* compute frontmatter values. Every behavior here is selected by descriptor data but
implemented as typed, mutation-covered Python — the closed vocabulary ``descriptor.py`` validates.

Byte-fidelity contracts (pinned by ``tests/build/test_generic_serialize.py`` and the dist drift
gate):

- ``preserve`` passes raw frontmatter bytes through untouched, rebuilding ONLY when ``model_tier``
  is present (in-slot swap for the resolved ``model``, omitted when the tier maps to null).
- ``fields``/``wrap`` join ``render_frontmatter(out) + "\\n\\n" + body``; ``preserve`` joins the raw
  block (ending ``---\\n``) directly to the body — the blank-line topologies differ and both are
  load-bearing.
- Frontmatter values render tokens only where a field says ``"render": true``; bodies always render.
- Body trim policies are exact: ``keep`` / ``lstrip_newlines`` / ``strip_newlines`` (newlines only,
  never general whitespace).
"""
from __future__ import annotations

from typing import Optional

from scripts.build.descriptor import EcosystemDescriptor, FieldSpec, RoleSpec
from scripts.build.model_map import resolve as resolve_model
from scripts.build.parse import parse_frontmatter, render_frontmatter, split_document
from scripts.build.render import render_body


class SerializeError(ValueError):
    """Raised when a source artifact is missing frontmatter a target requires."""


def require_field(meta: dict, key: str) -> str:
    """Return ``meta[key]`` or raise :class:`SerializeError` with a scripted, actionable message."""
    if key not in meta:
        name = meta.get("name", "<unnamed>")
        raise SerializeError(  # pragma: no mutate - message text only
            f"source artifact {name!r} is missing required frontmatter field {key!r} "
            f"— add a '{key}:' line to its frontmatter"
        )
    return meta[key]


def toml_basic(s: str) -> str:
    """A TOML basic (double-quoted) single-line string: escape backslash then double-quote."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def toml_multiline(s: str) -> str:
    """Escape a body for a TOML multiline basic (``\"\"\"…\"\"\"``) string. Backslash is TOML's escape
    char (a trailing one would also swallow the closing newline), so it is doubled; and any run of
    three-or-more quotes — which would close the delimiter early — is broken by escaping its third
    quote. Today's command bodies contain neither, so this is a no-op on current output; it guards a
    future token that renders a ``\\`` or ``\"\"\"`` into a body from silently emitting invalid TOML."""
    s = s.replace("\\", "\\\\")
    out: list[str] = []
    run = 0
    for ch in s:
        if ch == '"':
            run += 1
            if run == 3:
                out.append('\\"')
                run = 0
                continue
        else:
            run = 0
        out.append(ch)
    return "".join(out)


def toml_command(description: str, prompt: str) -> str:
    """A TOML custom-command file: a one-line ``description`` + a multiline ``prompt``.

    The ``prompt`` uses a TOML multiline basic string whose opening ``\"\"\"`` is followed by a newline
    (TOML trims that first newline) so the body starts on its own line."""
    return (f"description = {toml_basic(description)}\n\n"
            f'prompt = """\n{toml_multiline(prompt)}\n"""\n')


def dest(descriptor: EcosystemDescriptor, rel: str) -> str:
    """Map a ``src/content`` path through the descriptor's routes (ordered, first match wins,
    identity fallback). Extensions swapped here are load-bearing — a wrong one makes the host
    silently ignore the file — which is why this interpreter lives in a mutation-gated module and
    each ecosystem's route data is pinned by its build tests."""
    for route in descriptor.routes:
        if route.kind == "exact" and rel == route.src:
            return route.dest
        if (route.kind == "suffix_swap" and rel.startswith(route.prefix)
                and rel.endswith(route.from_suffix)):
            return rel[: -len(route.from_suffix)] + route.to_suffix
    return rel


def _apply_body_policy(body: str, policy: str) -> str:
    """The exact trim set the legacy serializers used — newlines only, never all whitespace."""
    if policy == "lstrip_newlines":
        return body.lstrip("\n")
    if policy == "strip_newlines":
        return body.strip("\n")
    return body


def _stem(rel: Optional[str]) -> Optional[str]:
    """The source file stem (``commands/build.md`` → ``build``) for the ``stem`` field generator."""
    if rel is None:
        return None
    base = rel.rsplit("/", 1)[-1]
    return base[: -len(".md")] if base.endswith(".md") else base


def compute_fields(fields: tuple, meta: dict, target: str, tokens: dict,
                   stem: Optional[str] = None) -> dict:
    """Evaluate a role's ordered field specs into the output frontmatter dict.

    Each generator is single-purpose with data operands only (the descriptor vocabulary is closed):
    ``frontmatter`` requires its source key and optionally token-renders the value; ``stem`` emits
    the source file stem; ``literal`` a static; ``primary_mode`` the primary/subagent split;
    ``flag_if_name_in`` emits its value for the named roles and OMITS the key otherwise."""
    out: dict = {}
    for spec in fields:
        if spec.source == "frontmatter":
            value = require_field(meta, spec.field)
            out[spec.key] = render_body(value, target, tokens) if spec.render else value
        elif spec.source == "stem":
            if stem is None:
                raise SerializeError(  # pragma: no mutate - message text only
                    f"field {spec.key!r} needs the source file stem, but none was provided"
                )
            out[spec.key] = stem
        elif spec.source == "literal":
            out[spec.key] = spec.value
        elif spec.source == "primary_mode":
            out[spec.key] = "primary" if meta.get("name") == spec.primary else "subagent"
        elif spec.source == "flag_if_name_in":
            if meta.get("name") in spec.names:
                out[spec.key] = spec.value
    return out


class DescriptorSerializer:
    """One serializer instance per ecosystem, wholly driven by its descriptor."""

    def __init__(self, descriptor: EcosystemDescriptor):
        self.descriptor = descriptor
        self.target = descriptor.name

    # ---- role dispatch (two named dispatchers — the descriptor picks one) ----

    def _role_by_path(self, rel: Optional[str]) -> str:
        if rel == "persona.md":
            return "persona"
        if rel is not None and rel.startswith("agents/"):
            return "agent"
        if rel is not None and rel.startswith("commands/"):
            return "command"
        return "default"

    def _role_by_frontmatter(self, text: str) -> str:
        """OpenCode's shape sniff, verbatim: no frontmatter → persona; ``name`` plus a model/tools
        marker → agent; Claude's slash-command marker → command; anything else → default."""
        fm_block, _ = split_document(text)
        if fm_block is None:
            return "persona"
        meta, _ = parse_frontmatter(fm_block)
        if "name" in meta and ("model_tier" in meta or "tools" in meta):
            return "agent"
        if "disable-model-invocation" in meta:
            return "command"
        return "default"

    def _models(self, models: Optional[dict]) -> dict:
        """An explicitly passed model map wins (the tiering tests inject overrides); otherwise the
        descriptor's own row serves, keyed under this target."""
        if models and self.target in models:
            return models
        return {self.target: self.descriptor.models}

    # ---- the Serializer protocol ----

    def serialize_file(self, text: str, tokens: dict, models: Optional[dict] = None,
                       rel: Optional[str] = None) -> str:
        d = self.descriptor
        role = self._role_by_path(rel) if d.dispatch == "path" else self._role_by_frontmatter(text)
        spec = d.roles[role]
        if spec.mode == "plain":
            return render_body(text, self.target, tokens)
        if spec.mode == "wrap":
            out = compute_fields(spec.fields, {}, self.target, tokens)
            return render_frontmatter(out) + "\n\n" + render_body(text, self.target, tokens)
        fm_block, body = split_document(text)
        if fm_block is None:  # protocols, companion docs, any plain file — every mode passes through
            return render_body(text, self.target, tokens)
        meta, _ = parse_frontmatter(fm_block)
        if spec.mode == "preserve":
            return self._preserve(spec, fm_block, meta, body, tokens, models)
        if spec.mode == "toml_command":
            return self._toml(spec, meta, body, tokens)
        return self._fields(spec, meta, body, tokens, stem=_stem(rel))  # mode == "fields"

    # ---- mode implementations ----

    def _preserve(self, spec: RoleSpec, fm_block: str, meta: dict, body: str,
                  tokens: dict, models: Optional[dict]) -> str:
        """Raw frontmatter bytes pass through; the block is rebuilt ONLY when ``model_tier`` is
        present (in-slot swap — key order preserved, the line vanishing entirely on a null tier).
        Never round-trip frontmatter that needs no change: that would silently normalise it."""
        for key in spec.required:
            require_field(meta, key)
        if spec.resolve_model_tier and "model_tier" in meta:
            out: dict = {}
            for key, value in meta.items():
                if key == "model_tier":
                    model = resolve_model(self._models(models), self.target, value)
                    if model is not None:
                        out["model"] = model
                else:
                    out[key] = value
            fm_block = render_frontmatter(out) + "\n"
        return fm_block + render_body(body, self.target, tokens)

    def _fields(self, spec: RoleSpec, meta: dict, body: str, tokens: dict,
                stem: Optional[str] = None) -> str:
        out = compute_fields(spec.fields, meta, self.target, tokens, stem=stem)
        rendered = _apply_body_policy(render_body(body, self.target, tokens), spec.body)
        return render_frontmatter(out) + "\n\n" + rendered

    def _toml(self, spec: RoleSpec, meta: dict, body: str, tokens: dict) -> str:
        out = compute_fields(spec.fields, meta, self.target, tokens)
        prompt = _apply_body_policy(render_body(body, self.target, tokens), spec.body)
        return toml_command(out["description"], prompt)

    # ---- role-direct sugar (the legacy per-class entry points, kept for tests and generators) ----

    def serialize_agent(self, frontmatter: dict, body: str, tokens: dict,
                        models: Optional[dict] = None) -> str:
        """Serialize *frontmatter*/*body* through the agent role, joined ``fm + "\\n\\n" + body``.

        For a ``preserve`` agent role the frontmatter is rebuilt from the dict (the sugar has no raw
        bytes) — identical output for any in-order source, which the roundtrip gate pins."""
        return self._role_direct("agent", frontmatter, body, tokens, models=models)

    def serialize_command(self, frontmatter: dict, body: str, tokens: dict,
                          stem: Optional[str] = None) -> str:
        return self._role_direct("command", frontmatter, body, tokens, stem=stem)

    def serialize_persona(self, text: str, tokens: dict) -> str:
        spec = self.descriptor.roles["persona"]
        if spec.mode == "wrap":
            out = compute_fields(spec.fields, {}, self.target, tokens)
            return render_frontmatter(out) + "\n\n" + render_body(text, self.target, tokens)
        return render_body(text, self.target, tokens)

    def _role_direct(self, role: str, meta: dict, body: str, tokens: dict,
                     models: Optional[dict] = None, stem: Optional[str] = None) -> str:
        spec = self.descriptor.roles[role]
        if spec.mode == "toml_command":
            return self._toml(spec, meta, body, tokens)
        if spec.mode == "preserve":
            for key in spec.required:
                require_field(meta, key)
            out = {}
            for key, value in meta.items():
                if key == "model_tier" and spec.resolve_model_tier:
                    model = resolve_model(self._models(models), self.target, value)
                    if model is not None:
                        out["model"] = model
                else:
                    out[key] = value
            return render_frontmatter(out) + "\n\n" + render_body(body, self.target, tokens)
        return self._fields(spec, meta, body, tokens, stem=stem)
