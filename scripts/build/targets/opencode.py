"""OpenCode target: the generated ``plugin.js`` entrypoint + inlined agent/command maps."""
from __future__ import annotations

import json
from pathlib import Path

from scripts.build import emit
from scripts.build.manifests import generate_opencode_json, generate_plugin_js
from scripts.build.parse import parse_frontmatter, split_document
from scripts.build.render import render_body
from scripts.build.serialize import require_field
from scripts.build.targets.base import ExtrasContext, Target, register

_CAPABILITIES = """# Hercules on OpenCode — capabilities & disclosed gaps

Hercules ships the full Discover → Design → Build → Ship methodology on OpenCode, with two capability
gaps disclosed here (the "disclose gaps, never hide" principle):

- **Frozen-test write-gate: enforced (needs `python3`).** The plugin's `tool.execute.before` hook
  hard-denies an edit to a frozen test file during an active build — a real pre-write veto, matching
  Claude Code's PreToolUse gate — by invoking the same canonical guard (`hooks/frozen_tests.py`). It
  requires `python3` on PATH; if `python3` is absent the gate **fails open** (the edit is allowed) and
  the approval gate falls back to prompt/permission-mediated discipline. Enable
  `permission: {edit: "ask"}` in your `opencode.json` for an additional backstop. One host limitation to
  be aware of (the plugin cannot pin it for you): on OpenCode versions where `tool.execute.before` does
  **not** also fire for subagent (`task`-tool) edits, a delegated edit bypasses the gate — run a version
  that fires the hook for subagent edits.
- **No per-agent model tier.** Every Hercules agent runs on the model you select in OpenCode (the
  build omits per-agent `model:` on purpose). Claude Code assigns a heavier model to the orchestrator
  and lighter models to routine advisors; on OpenCode that tiering is intentionally not applied.
"""


def _agents_and_commands(src_content: Path, tokens: dict[str, str]):
    """Collect ``(name, meta, opencode-rendered-prompt)`` triples for the plugin.js inline entries."""
    agents = []
    for src in sorted((src_content / "agents").glob("*.md")):
        text = src.read_text(encoding="utf-8")
        meta, _ = parse_frontmatter(text)
        _, body = split_document(text)
        agents.append((
            src.stem,
            {"description": render_body(require_field(meta, "description"), "opencode", tokens),
             "mode": "primary" if src.stem == "hercules" else "subagent"},
            render_body(body, "opencode", tokens).strip(),
        ))
    commands = []
    for src in sorted((src_content / "commands").glob("*.md")):
        text = src.read_text(encoding="utf-8")
        meta, _ = parse_frontmatter(text)
        _, body = split_document(text)
        commands.append((
            src.stem,
            {"description": render_body(require_field(meta, "description"), "opencode", tokens),
             "agent": "hercules"},
            render_body(body, "opencode", tokens).strip(),
        ))
    return agents, commands


def _extras(ctx: ExtrasContext) -> list[str]:
    agents, commands = _agents_and_commands(ctx.src_content, ctx.tokens)
    emit.write(ctx.out_root / "plugin.js", generate_plugin_js("hercules", agents, commands))
    emit.write(ctx.out_root / "opencode.json", json.dumps(generate_opencode_json(), indent=2) + "\n")
    emit.write(ctx.out_root / "CAPABILITIES.md", _CAPABILITIES)
    written = ["plugin.js", "opencode.json", "CAPABILITIES.md"]
    # The write-gate the generated plugin.js invokes: the canonical Python guard + its state reader.
    written += emit.copy_map(ctx.shared_hooks_src, ctx.out_root,
                             {n: f"hooks/{n}" for n in ("frozen_tests.py", "hercules_state.py")})
    return written


register(Target(
    name="opencode",
    renames={"persona.md": "instructions.md"},
    emit_extras_fn=_extras,
))
