"""Per-target serializers (pure) + a target registry.

A ``Serializer`` turns a parsed source artifact into the exact bytes a target expects. Adding a
target later = one new ``Serializer`` registered here + one config file — ``parse``/``render``/
``model_map``/``cli`` need no change (proven by ``tests/build/test_serialize.py``).

Spec 01 lands the protocol, the registry, and a ``ClaudeCodeSerializer`` agent path (frontmatter emit
+ byte-preserving body). OpenCode is added in Spec 03.
"""
from __future__ import annotations

from typing import Protocol

from scripts.build.model_map import resolve as resolve_model
from scripts.build.parse import parse_frontmatter, render_frontmatter, split_document
from scripts.build.render import render_body


class Serializer(Protocol):
    """Turns a source ``(frontmatter, body)`` into one target's output text."""

    target: str

    def serialize_agent(self, frontmatter: dict[str, str], body: str, tokens: dict[str, str], models: dict) -> str:
        ...

    def serialize_file(self, text: str, tokens: dict[str, str], models: dict) -> str:
        ...


_REGISTRY: dict[str, "Serializer"] = {}


def register(serializer: "Serializer") -> "Serializer":
    """Register *serializer* under its ``.target`` key; return it (usable as a decorator)."""
    _REGISTRY[serializer.target] = serializer
    return serializer


def get(target: str) -> "Serializer":
    """Return the registered serializer for *target*; raise ``KeyError`` if absent."""
    return _REGISTRY[target]


def registered_targets() -> list[str]:
    """Return the sorted list of registered target keys."""
    return sorted(_REGISTRY)


class ClaudeCodeSerializer:
    """Emit Claude-Code agent files: ``model_tier`` → ``model:`` alias in the ``model`` slot, key
    order ``name, description, model, tools`` preserved, ``tools`` kept only when present; body via
    byte-preserving token substitution."""

    target = "claude-code"

    def serialize_agent(self, frontmatter: dict[str, str], body: str, tokens: dict[str, str], models: dict) -> str:
        tier = frontmatter.get("model_tier")
        out: dict[str, str] = {"name": frontmatter["name"], "description": frontmatter["description"]}
        if tier is not None:
            model = resolve_model(models, self.target, tier)
            if model is not None:
                out["model"] = model
        if "tools" in frontmatter:
            out["tools"] = frontmatter["tools"]
        return render_frontmatter(out) + "\n\n" + render_body(body, self.target, tokens)

    def serialize_file(self, text: str, tokens: dict[str, str], models: dict) -> str:
        """Render a whole source file byte-preservingly for Claude Code.

        Frontmatter with ``model_tier`` is rebuilt with the resolved ``model:`` alias in the same
        slot (all other keys and their order kept); frontmatter without ``model_tier`` — and files
        with none — are left untouched. The body is substituted in place with no normalisation.
        """
        fm_block, body = split_document(text)
        if fm_block is None:
            return render_body(text, self.target, tokens)
        meta, _ = parse_frontmatter(fm_block)
        if "model_tier" in meta:
            out: dict[str, str] = {}
            for key, value in meta.items():
                if key == "model_tier":
                    model = resolve_model(models, self.target, value)
                    if model is not None:
                        out["model"] = model
                else:
                    out[key] = value
            fm_block = render_frontmatter(out) + "\n"
        return fm_block + render_body(body, self.target, tokens)


class OpenCodeSerializer:
    """Emit OpenCode agent files: frontmatter ``name, description, mode`` (``primary`` for the
    orchestrator, ``subagent`` otherwise); ``model``/``model_tier``/``tools`` dropped (OpenCode uses
    the user's selected model — ``models.json[opencode]`` is all-``null``). Body via token/switch
    substitution (the ``${target:opencode}`` branch selected)."""

    target = "opencode"
    primary_agent = "hercules"

    def serialize_agent(self, frontmatter: dict[str, str], body: str, tokens: dict[str, str], models: dict) -> str:
        name = frontmatter["name"]
        out = {
            "name": name,
            "description": frontmatter["description"],
            "mode": "primary" if name == self.primary_agent else "subagent",
        }
        return render_frontmatter(out) + "\n\n" + render_body(body, self.target, tokens)

    def serialize_file(self, text: str, tokens: dict[str, str], models: dict) -> str:
        fm_block, body = split_document(text)
        if fm_block is None:
            return render_body(text, self.target, tokens)
        meta, _ = parse_frontmatter(fm_block)
        if "name" in meta and ("model_tier" in meta or "tools" in meta):  # an agent file
            return self.serialize_agent(meta, body, tokens, models)
        return fm_block + render_body(body, self.target, tokens)


def serialize_file(target: str, text: str, tokens: dict[str, str], models: dict) -> str:
    """Serialize *text* for *target* using its registered serializer."""
    return get(target).serialize_file(text, tokens, models)


register(ClaudeCodeSerializer())
register(OpenCodeSerializer())
