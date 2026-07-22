"""Per-target serializers (pure) + a target registry.

A ``Serializer`` turns a parsed source artifact into the exact bytes a target expects. Adding a
target later = one new ``Serializer`` registered here + one config file — ``parse``/``render``/
``model_map``/``cli`` need no change (proven by ``tests/build/test_serialize.py``).

Three serializers are registered: ``ClaudeCodeSerializer`` (native ``.claude-plugin`` tree, per-agent
model tiers, hooks), ``OpenCodeSerializer`` (generated ``plugin.js`` + inlined agent/command maps), and
``CursorSerializer`` (an official Cursor plugin — subagents, commands, an always-applied persona rule).
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

    def serialize_file(self, text: str, tokens: dict[str, str], models: dict, rel: str | None = None) -> str:
        ...


class SerializeError(ValueError):
    """Raised when a source artifact is missing frontmatter a target requires."""


def require_field(meta: dict[str, str], key: str) -> str:
    """Return ``meta[key]`` or raise :class:`SerializeError` with a scripted, actionable message."""
    if key not in meta:
        name = meta.get("name", "<unnamed>")
        raise SerializeError(  # pragma: no mutate - message text only
            f"source artifact {name!r} is missing required frontmatter field {key!r} "
            f"— add a '{key}:' line to its frontmatter"
        )
    return meta[key]


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
        out: dict[str, str] = {"name": require_field(frontmatter, "name"),
                               "description": require_field(frontmatter, "description")}
        if tier is not None:
            model = resolve_model(models, self.target, tier)
            if model is not None:
                out["model"] = model
        if "tools" in frontmatter:
            out["tools"] = frontmatter["tools"]
        return render_frontmatter(out) + "\n\n" + render_body(body, self.target, tokens)

    def serialize_file(self, text: str, tokens: dict[str, str], models: dict, rel: str | None = None) -> str:
        """Render a whole source file byte-preservingly for Claude Code.

        Frontmatter with ``model_tier`` is rebuilt with the resolved ``model:`` alias in the same
        slot (all other keys and their order kept); frontmatter without ``model_tier`` — and files
        with none — are left untouched. The body is substituted in place with no normalisation.

        ``rel`` (the source path under ``src/content``) is accepted for signature parity with
        path-aware serializers (Cursor); Claude Code dispatches by frontmatter shape and ignores it.
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
        name = require_field(frontmatter, "name")
        out = {
            "name": name,
            # Render the description like serialize_command does, so the standalone agent file and the
            # plugin.js-inlined entry (cli._opencode_agents_and_commands) stay byte-for-byte in step.
            "description": render_body(require_field(frontmatter, "description"), self.target, tokens),
            "mode": "primary" if name == self.primary_agent else "subagent",
        }
        return render_frontmatter(out) + "\n\n" + render_body(body, self.target, tokens)

    def serialize_command(self, frontmatter: dict[str, str], body: str, tokens: dict[str, str]) -> str:
        """Emit an OpenCode command file: frontmatter ``description, agent``; the Claude-only
        ``disable-model-invocation`` key is dropped and the command is bound to the primary agent."""
        out = {
            "description": render_body(require_field(frontmatter, "description"), self.target, tokens),
            "agent": self.primary_agent,
        }
        return render_frontmatter(out) + "\n\n" + render_body(body, self.target, tokens).lstrip("\n")

    def serialize_file(self, text: str, tokens: dict[str, str], models: dict, rel: str | None = None) -> str:
        fm_block, body = split_document(text)
        if fm_block is None:
            return render_body(text, self.target, tokens)
        meta, _ = parse_frontmatter(fm_block)
        if "name" in meta and ("model_tier" in meta or "tools" in meta):  # an agent file
            return self.serialize_agent(meta, body, tokens, models)
        if "disable-model-invocation" in meta:  # a command file (Claude's slash-command marker)
            return self.serialize_command(meta, body, tokens)
        return fm_block + render_body(body, self.target, tokens)


# The one source file Cursor relocates: the frontmatter-less persona becomes an always-applied rule.
# Shared by CursorSerializer.serialize_file (which wraps it) and cursor_dest (which routes it) so the
# two never disagree.
_PERSONA_SRC = "persona.md"
_PERSONA_RULE_DEST = "rules/hercules-persona.mdc"


class CursorSerializer:
    """Emit an official Cursor plugin (``.cursor-plugin/plugin.json`` + native component dirs).

    Cursor's component directories match ``src/content``'s (``agents/``, ``commands/``, ``skills/``),
    so only ``persona.md`` is relocated — to ``rules/hercules-persona.mdc`` (an always-applied rule).
    Dispatch is by source ``rel`` (path-aware), not frontmatter-sniffing, because the frontmatter-less
    persona and the protocols are otherwise indistinguishable. Field shapes are the officially
    documented minimal set (confirmed against real ``cursor/plugins`` files):

    - agent → ``agents/<name>.md`` subagent: ``name, description`` (+ ``readonly: true`` for the
      review/audit roles); ``model_tier``/``tools`` dropped (subagents inherit the user's model, as
      OpenCode does — ``models.json[cursor]`` is all-``null``).
    - command → ``commands/<name>.md``: ``name`` (from the file stem) + ``description`` — the official
      plugin validator requires both; Claude's ``disable-model-invocation`` marker is dropped.
    - skill → ``skills/<name>/SKILL.md`` (native skill): frontmatter kept, body token-rendered.
    - persona → ``rules/hercules-persona.mdc``: ``description`` + ``alwaysApply: true``.
    - protocol / companion / plain → passthrough with token/switch rendering.
    """

    target = "cursor"
    # Roles that render a GATE VERDICT on other agents' work ship read-locked, so an isolated reviewer
    # can never become an author — this is what keeps the independent-review gates independent
    # (``cynical-reviewer`` above all; the audit roles alongside it). Generative advisors are not
    # listed: they never write files either, but read-locking is scoped to the verdict-givers.
    readonly_agents = frozenset({
        "cynical-reviewer", "security-expert", "source-checker", "senior-qa-engineer", "maintainer",
    })
    persona_description = (
        "Hercules — the spec-first delivery methodology (Discover → Design → Build → Ship). "
        "Always-on persona and project instructions."
    )

    def serialize_agent(self, frontmatter: dict[str, str], body: str, tokens: dict[str, str]) -> str:
        name = require_field(frontmatter, "name")
        out: dict[str, str] = {
            "name": name,
            "description": render_body(require_field(frontmatter, "description"), self.target, tokens),
        }
        if name in self.readonly_agents:
            out["readonly"] = "true"
        return render_frontmatter(out) + "\n\n" + render_body(body, self.target, tokens)

    def serialize_command(self, name: str, frontmatter: dict[str, str], body: str, tokens: dict[str, str]) -> str:
        """Emit a Cursor command: ``name`` (the file stem) + ``description`` frontmatter, then the
        prompt body. Claude's ``disable-model-invocation`` key is dropped."""
        out = {
            "name": name,
            "description": render_body(require_field(frontmatter, "description"), self.target, tokens),
        }
        return render_frontmatter(out) + "\n\n" + render_body(body, self.target, tokens).lstrip("\n")

    def serialize_persona(self, text: str, tokens: dict[str, str]) -> str:
        """Wrap the frontmatter-less ``persona.md`` as an always-applied Cursor rule."""
        out = {"description": self.persona_description, "alwaysApply": "true"}
        return render_frontmatter(out) + "\n\n" + render_body(text, self.target, tokens)

    def serialize_file(self, text: str, tokens: dict[str, str], models: dict, rel: str | None = None) -> str:
        if rel == _PERSONA_SRC:
            return self.serialize_persona(text, tokens)
        fm_block, body = split_document(text)
        if fm_block is None:  # protocols, skill companion docs, any plain file
            return render_body(text, self.target, tokens)
        meta, _ = parse_frontmatter(fm_block)
        if rel is not None and rel.startswith("agents/"):
            return self.serialize_agent(meta, body, tokens)
        if rel is not None and rel.startswith("commands/"):
            return self.serialize_command(rel.rsplit("/", 1)[-1][: -len(".md")], meta, body, tokens)
        # skills/<name>/SKILL.md and any other frontmatter'd file: keep frontmatter (already
        # name+description for skills), render the body.
        return fm_block + render_body(body, self.target, tokens)


def _gemini_toml_basic(s: str) -> str:
    """A TOML basic (double-quoted) single-line string: escape backslash then double-quote."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _gemini_toml_multiline(s: str) -> str:
    """Escape a body for a TOML multiline basic (``\"\"\"…\"\"\"``) string. Backslash is TOML's escape char
    (a trailing one would also swallow the closing newline), so it is doubled; and any run of three-or-
    more quotes — which would close the delimiter early — is broken by escaping its third quote. Today's
    command bodies contain neither, so this is a no-op on current output; it guards a future token that
    renders a ``\\`` or ``\"\"\"`` into a body from silently emitting invalid TOML."""
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


def _gemini_toml_command(description: str, prompt: str) -> str:
    """A Gemini custom-command TOML file: a one-line ``description`` + a multiline ``prompt``.

    The ``prompt`` uses a TOML multiline basic string whose opening ``\"\"\"`` is followed by a newline
    (TOML trims that first newline) so the body starts on its own line; the body is escaped for that
    context by ``_gemini_toml_multiline``."""
    return (f"description = {_gemini_toml_basic(description)}\n\n"
            f'prompt = """\n{_gemini_toml_multiline(prompt)}\n"""\n')


class GeminiCliSerializer:
    """Emit a Gemini CLI extension's components (subagents, TOML commands, the GEMINI.md context).

    Gemini reads Markdown-with-frontmatter subagents (``agents/<name>.md``: ``name`` + ``description``,
    body = system prompt), TOML custom commands (``commands/<name>.toml`` with a required ``prompt`` and
    optional ``description``), and a plain ``GEMINI.md`` context file. Per-agent ``model``/``model_tier``/
    ``tools`` are dropped — subagents inherit the user's selected model (``models.json[gemini-cli]`` is
    all-``null``), as OpenCode and Cursor do. Dispatch is by source ``rel`` (path-aware): the persona is
    frontmatter-less (relocated to ``GEMINI.md`` by ``gemini_dest``) and falls through the no-frontmatter
    branch; ``agents/`` and ``commands/`` take their shapes; every other frontmatter'd file (skills)
    keeps its frontmatter and renders its body.
    """

    target = "gemini-cli"

    def serialize_agent(self, frontmatter: dict[str, str], body: str, tokens: dict[str, str]) -> str:
        out = {
            "name": require_field(frontmatter, "name"),
            "description": render_body(require_field(frontmatter, "description"), self.target, tokens),
        }
        return render_frontmatter(out) + "\n\n" + render_body(body, self.target, tokens)

    def serialize_command(self, frontmatter: dict[str, str], body: str, tokens: dict[str, str]) -> str:
        """Emit a Gemini TOML command: ``description`` + the rendered prompt body. Claude's
        ``disable-model-invocation`` marker is dropped (Gemini has no such field)."""
        description = render_body(require_field(frontmatter, "description"), self.target, tokens)
        prompt = render_body(body, self.target, tokens).strip("\n")
        return _gemini_toml_command(description, prompt)

    def serialize_file(self, text: str, tokens: dict[str, str], models: dict, rel: str | None = None) -> str:
        fm_block, body = split_document(text)
        if fm_block is None:  # the frontmatter-less persona (→ GEMINI.md), protocols, any plain file
            return render_body(text, self.target, tokens)
        meta, _ = parse_frontmatter(fm_block)
        if rel is not None and rel.startswith("agents/"):
            return self.serialize_agent(meta, body, tokens)
        if rel is not None and rel.startswith("commands/"):
            return self.serialize_command(meta, body, tokens)
        return fm_block + render_body(body, self.target, tokens)


# Gemini relocations that are load-bearing (a wrong extension loads as absent): the frontmatter-less
# persona → GEMINI.md context, and a command's .md → .toml (Gemini parses commands as TOML).
_GEMINI_PERSONA_DEST = "GEMINI.md"


def gemini_dest(rel: str) -> str:
    """Map a ``src/content`` path into the Gemini extension tree.

    ``persona.md`` becomes the ``GEMINI.md`` context file; a ``commands/<name>.md`` source becomes
    ``commands/<name>.toml`` (Gemini reads commands as TOML — a ``.md`` command is ignored). Both are
    load-bearing, so — like ``cursor_dest``'s ``.mdc`` mapping — they live in this mutation-covered
    module and are wired into the Gemini ``Target`` via ``dest_fn``."""
    if rel == _PERSONA_SRC:
        return _GEMINI_PERSONA_DEST
    if rel.startswith("commands/") and rel.endswith(".md"):
        return rel[: -len(".md")] + ".toml"
    return rel


class CopilotCliSerializer:
    """Emit a GitHub Copilot CLI plugin (``plugin.json`` manifest + native component dirs).

    Copilot CLI's plugin components live in conventional dirs the manifest points at; only two
    sources are relocated by extension (``copilot_cli_dest``): agents become ``agents/<name>.agent.md``
    (Copilot derives the agent id from the ``<name>`` stem) and commands become Copilot prompt files
    ``commands/<name>.prompt.md``. The frontmatter-less ``persona.md`` becomes the plugin's ``AGENTS.md``
    custom-instructions file. Dispatch is by source ``rel`` (path-aware), like Cursor, because the
    frontmatter-less persona and the protocols are otherwise indistinguishable. Field shapes are the
    documented minimal set:

    - agent → ``agents/<name>.agent.md``: ``name, description``; ``model_tier``/``tools`` dropped
      (Copilot agents inherit the user's model — ``models.json[copilot-cli]`` is all-``null``).
    - command → ``commands/<name>.prompt.md``: ``description`` (Copilot keys the command off the file
      stem); Claude's ``disable-model-invocation`` marker is dropped.
    - persona → ``AGENTS.md``: plain custom instructions (no frontmatter), body token-rendered.
    - skill → ``skills/<name>/SKILL.md``: frontmatter kept, body token-rendered.
    - protocol / companion / plain → passthrough with token/switch rendering.
    """

    target = "copilot-cli"

    def serialize_agent(self, frontmatter: dict[str, str], body: str, tokens: dict[str, str]) -> str:
        out = {
            "name": require_field(frontmatter, "name"),
            "description": render_body(require_field(frontmatter, "description"), self.target, tokens),
        }
        return render_frontmatter(out) + "\n\n" + render_body(body, self.target, tokens)

    def serialize_command(self, frontmatter: dict[str, str], body: str, tokens: dict[str, str]) -> str:
        """Emit a Copilot prompt file: a ``description`` frontmatter, then the prompt body. Copilot keys
        the command off the file stem, so no ``name`` is emitted; Claude's ``disable-model-invocation``
        marker is dropped."""
        out = {"description": render_body(require_field(frontmatter, "description"), self.target, tokens)}
        return render_frontmatter(out) + "\n\n" + render_body(body, self.target, tokens).lstrip("\n")

    def serialize_file(self, text: str, tokens: dict[str, str], models: dict, rel: str | None = None) -> str:
        if rel == _PERSONA_SRC:  # persona.md → AGENTS.md custom instructions (no frontmatter)
            return render_body(text, self.target, tokens)
        fm_block, body = split_document(text)
        if fm_block is None:  # protocols, skill companion docs, any plain file
            return render_body(text, self.target, tokens)
        meta, _ = parse_frontmatter(fm_block)
        if rel is not None and rel.startswith("agents/"):
            return self.serialize_agent(meta, body, tokens)
        if rel is not None and rel.startswith("commands/"):
            return self.serialize_command(meta, body, tokens)
        # skills/<name>/SKILL.md and any other frontmatter'd file: keep frontmatter, render the body.
        return fm_block + render_body(body, self.target, tokens)


# Copilot relocates the persona to AGENTS.md, agents to <name>.agent.md, commands to <name>.prompt.md.
_COPILOT_AGENT_SUFFIX = ".agent.md"
_COPILOT_COMMAND_SUFFIX = ".prompt.md"


def copilot_cli_dest(rel: str) -> str:
    """Map a ``src/content`` source path to its destination inside the Copilot CLI plugin tree.

    Two extensions are load-bearing: Copilot derives an agent's id from ``<name>.agent.md`` (a plain
    ``agents/<name>.md`` is not loaded as a plugin agent), and a plugin command is a ``.prompt.md``
    prompt file. The frontmatter-less ``persona.md`` becomes the plugin's ``AGENTS.md`` custom
    instructions. Lives here (a mutation-covered module), wired via ``dest_fn``, so a mutant flipping an
    extension is killed by ``test_copilot_cli_serialize``/``test_copilot_cli_build``."""
    if rel == _PERSONA_SRC:
        return "AGENTS.md"
    if rel.startswith("agents/") and rel.endswith(".md"):
        return rel[: -len(".md")] + _COPILOT_AGENT_SUFFIX
    if rel.startswith("commands/") and rel.endswith(".md"):
        return rel[: -len(".md")] + _COPILOT_COMMAND_SUFFIX
    return rel


def cursor_dest(rel: str) -> str:
    """Map a ``src/content`` source path to its destination inside the Cursor plugin tree.

    Cursor's ``agents/``/``commands/``/``skills/`` dirs match the source layout, so only the
    frontmatter-less ``persona.md`` is relocated — to an always-applied rule. This lives here (a
    mutation-covered module), wired into the Cursor ``Target`` via ``dest_fn``, rather than as plain
    ``renames`` data on the target descriptor: the ``.mdc`` extension is load-bearing (a ``.md`` rule is
    silently ignored by Cursor in agent mode), so a mutant flipping it must be killed by
    ``test_cursor_serialize`` — the per-ecosystem ``targets/*`` data modules are outside the mutation gate."""
    if rel == _PERSONA_SRC:
        return _PERSONA_RULE_DEST
    return rel


class GrokBuildSerializer(ClaudeCodeSerializer):
    """Grok Build reads Claude-format plugins natively, so it reuses Claude-Code serialization
    verbatim — with per-agent ``model:`` dropped. ``models.json[grok-build]`` is all-``null``, so
    ``resolve_model`` returns ``None`` and no ``model`` key is emitted (Grok's model line-up does not
    map onto Hercules' opus/sonnet/haiku tiers; every agent runs on the user's selected Grok model).
    Body ``${target:…}`` switches take the ``grok-build`` → ``grok`` → ``default`` fallthrough."""

    target = "grok-build"


def serialize_file(target: str, text: str, tokens: dict[str, str], models: dict, rel: str | None = None) -> str:
    """Serialize *text* for *target* using its registered serializer."""
    return get(target).serialize_file(text, tokens, models, rel)


register(ClaudeCodeSerializer())
register(OpenCodeSerializer())
register(CursorSerializer())
register(GrokBuildSerializer())
register(GeminiCliSerializer())
register(CopilotCliSerializer())
