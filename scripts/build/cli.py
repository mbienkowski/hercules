"""``hercules-build`` entry point (thin FS boundary).

``--target {claude-code|opencode|all} [--check]``. Without ``--check`` it writes ``dist/<target>/``;
with ``--check`` it renders to a temp dir and diffs against the committed ``dist/`` (exit non-zero on
drift). One code path for local dev and CI. Spec 02 lands full Claude-Code generation; OpenCode in
Spec 03.
"""
from __future__ import annotations

import argparse
import filecmp
import json
import shutil
import sys
import tempfile
from pathlib import Path

from scripts.build.layout import discover_sources
from scripts.build.manifests import generate_opencode_json, generate_plugin_js
from scripts.build.parse import parse_frontmatter, split_document
from scripts.build.render import render_body
from scripts.build.serialize import cursor_dest, registered_targets, require_field, serialize_file

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"
SRC_CONTENT = SRC / "content"
DIST = REPO_ROOT / "dist"
# Derived from the serializer registry (populated at import) — adding a target needs no edit here.
TARGETS = tuple(registered_targets())

# Per-target source→dest renames + the Claude-only byte-copied files.
_RENAMES = {"claude-code": {"persona.md": "CLAUDE.md"}, "opencode": {"persona.md": "instructions.md"}}

_OPENCODE_CAPABILITIES = """# Hercules on OpenCode — capabilities & disclosed gaps

Hercules ships the full Discover → Design → Build → Ship methodology on OpenCode, with two capability
gaps disclosed here (the "disclose gaps, never hide" principle):

- **No hard write-gate hook.** On Claude Code a PreToolUse hook can deny a premature artifact write;
  OpenCode has no equivalent, so the approval gate is prompt/permission-mediated — the agent presents
  the plan and waits, but it is not a runtime-enforced deny. Enable `permission: {edit: "ask"}` in your
  `opencode.json` for a stronger backstop.
- **No per-agent model tier.** Every Hercules agent runs on the model you select in OpenCode (the
  build omits per-agent `model:` on purpose). Claude Code assigns a heavier model to the orchestrator
  and lighter models to routine advisors; on OpenCode that tiering is intentionally not applied.
"""


def _opencode_agents_and_commands(tokens: dict[str, str]):
    """Collect ``(name, meta, opencode-rendered-prompt)`` triples for the plugin.js inline entries."""
    agents = []
    for src in sorted((SRC_CONTENT / "agents").glob("*.md")):
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
    for src in sorted((SRC_CONTENT / "commands").glob("*.md")):
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


def _emit_opencode_extras(out_root: Path, tokens: dict[str, str]) -> list[str]:
    agents, commands = _opencode_agents_and_commands(tokens)
    _write(out_root / "plugin.js", generate_plugin_js("hercules", agents, commands))
    _write(out_root / "opencode.json", json.dumps(generate_opencode_json(), indent=2) + "\n")
    _write(out_root / "CAPABILITIES.md", _OPENCODE_CAPABILITIES)
    return ["plugin.js", "opencode.json", "CAPABILITIES.md"]


_CURSOR_CAPABILITIES = """# Hercules on Cursor — capabilities & disclosed gaps

Hercules ships the full Discover → Design → Build → Ship methodology on Cursor as an official plugin
(`.cursor-plugin/plugin.json`), with three capability gaps disclosed here (the "disclose gaps, never
hide" principle):

- **No hard write-gate hook.** On Claude Code a PreToolUse hook can deny a premature artifact write;
  Cursor's `afterFileEdit` hook is notification-only and cannot veto an edit, so the approval gate is
  honored by the assistant, not blocked by the tool. Turn on Cursor's *ask-before-applying-edits*
  approval for a stronger backstop.
- **No per-agent model tier.** Every Hercules subagent runs on the model you select in Cursor (the
  build omits per-agent model on purpose). Claude Code assigns a heavier model to the orchestrator and
  lighter models to routine advisors; on Cursor that tiering is intentionally not applied.
- **Independent review is best-effort in the IDE.** The Design coverage and Build traceability gates
  delegate to a fresh, isolated `cynical-reviewer` subagent (Cursor >= 2.4). Cursor exposes **no**
  orchestrator-forced spawn — in-IDE delegation is heuristic or `@`-mention-driven — so Hercules
  requires an explicit reviewer **handshake** (the reviewer attests it read the requirements source and
  returns a coverage/traceability matrix) and **halts and asks you** if that handshake is missing,
  converting a silent self-review into a loud stop. A genuinely forced, isolated reviewer is available
  only when Hercules runs via the headless `cursor-agent --agent cynical-reviewer` CLI.
"""


def _emit_cursor_extras(out_root: Path) -> list[str]:
    _write(out_root / "CAPABILITIES.md", _CURSOR_CAPABILITIES)
    return ["CAPABILITIES.md"]


_CLAUDE_COPIES = {
    "settings.json": "settings.json",
    "hooks/hooks.json": "hooks/hooks.json",
    "hooks/frozen_tests.py": "hooks/frozen_tests.py",
    "hooks/hercules_state.py": "hooks/hercules_state.py",
    "plugin.json": ".claude-plugin/plugin.json",
}

# Byte-copied Cursor sources (non-markdown). The manifest is versioned at its source
# (src/targets/cursor/plugin.json, in VERSION_TARGETS) and copied verbatim, mirroring _CLAUDE_COPIES.
_CURSOR_COPIES = {
    "plugin.json": ".cursor-plugin/plugin.json",
}


def _targets_for(name: str) -> list[str]:
    return list(TARGETS) if name == "all" else [name]


def _load_models() -> dict:
    path = SRC / "models.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _load_tokens(target: str) -> dict[str, str]:
    path = SRC / "targets" / target / "config.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8")).get("vars", {})


def _write(dest: Path, text: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")


def build_target(target: str, out_root: Path) -> list[str]:
    """Render *target* into *out_root*; return the sorted list of written relative paths."""
    models = _load_models()
    tokens = _load_tokens(target)
    renames = _RENAMES.get(target, {})
    written: list[str] = []
    for src in discover_sources(SRC_CONTENT):
        rel = src.relative_to(SRC_CONTENT).as_posix()
        dest_rel = cursor_dest(rel) if target == "cursor" else renames.get(rel, rel)
        _write(out_root / dest_rel, serialize_file(target, src.read_text(encoding="utf-8"), tokens, models, rel))
        written.append(dest_rel)
    if target == "claude-code":
        tdir = SRC / "targets" / target
        for src_rel, dest_rel in _CLAUDE_COPIES.items():
            dest = out_root / dest_rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(tdir / src_rel, dest)
            written.append(dest_rel)
    elif target == "cursor":
        tdir = SRC / "targets" / target
        for src_rel, dest_rel in _CURSOR_COPIES.items():
            dest = out_root / dest_rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(tdir / src_rel, dest)
            written.append(dest_rel)
        written += _emit_cursor_extras(out_root)
    elif target == "opencode":
        # The generic loop above also wrote dist/opencode/{agents,commands}/*.md. OpenCode does NOT
        # load agents/commands from those files — it reads the inlined cfg.agent/cfg.command maps in
        # plugin.js (below). They are kept as a readable, diff-friendly mirror; test_opencode_mirror
        # pins them byte-equal to the inlined entries so the two render paths can't diverge.
        written += _emit_opencode_extras(out_root, tokens)
    return sorted(written)


def _rel_files(root: Path) -> set[str]:
    return {
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and not p.name.endswith(".pyc")
    }


def _dir_diff(a: Path, b: Path) -> list[str]:
    """Relative paths that differ between *a* and *b*, compared by CONTENT.

    Uses ``filecmp.cmp(..., shallow=False)`` so same-size files are always byte-compared. The stdlib
    ``filecmp.dircmp`` compares shallowly (stat signature), which can miss a same-size, same-mtime
    hand-edit to a committed ``dist/`` file — this walk closes that hole.
    """
    a_files, b_files = _rel_files(a), _rel_files(b)
    diffs = sorted(a_files ^ b_files)
    diffs += [rel for rel in sorted(a_files & b_files)
              if not filecmp.cmp(a / rel, b / rel, shallow=False)]
    return diffs


def check_target(target: str) -> int:
    """Render *target* to a temp dir and diff vs committed ``dist/<target>``; 0 == in sync."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / target
        out.mkdir(parents=True, exist_ok=True)
        build_target(target, out)
        committed = DIST / target
        if not committed.exists():
            return 0 if not any(out.rglob("*")) else 1
        return 1 if _dir_diff(committed, out) else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hercules-build")
    parser.add_argument("--target", default="all")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    rc = 0
    for target in _targets_for(args.target):
        if target not in registered_targets():
            continue
        if args.check:
            rc |= check_target(target)
        else:
            build_target(target, DIST / target)
    if args.check and rc != 0:
        print(
            "dist/ is stale — regenerate it with `make build` and commit the result.",
            file=sys.stderr,
        )
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
