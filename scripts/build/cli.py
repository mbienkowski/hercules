"""``hercules-build`` entry point (thin FS boundary).

``--target {claude-code|opencode|cursor|all} [--check]``. Without ``--check`` it writes
``dist/<target>/``; with ``--check`` it renders to a temp dir and diffs against the committed ``dist/``
(exit non-zero on drift). One code path for local dev and CI. The target list is derived from the
serializer registry, so ``all`` and the accepted values extend automatically as serializers are added.
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


# The canonical frozen-test guard lives with the Claude hooks; OpenCode and Cursor ship COPIES of the
# same files so the write-gate logic has one source of truth across every ecosystem.
_SHARED_HOOKS_SRC = SRC / "targets" / "claude-code" / "hooks"


def _copy_map(tdir: Path, out_root: Path, mapping: dict[str, str]) -> list[str]:
    """Byte-copy each ``tdir/<src>`` to ``out_root/<dest>``; return the written dest rels."""
    written = []
    for src_rel, dest_rel in mapping.items():
        dest = out_root / dest_rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(tdir / src_rel, dest)
        written.append(dest_rel)
    return written


def _copy_shared_hooks(out_root: Path, names: tuple[str, ...]) -> list[str]:
    """Copy the canonical guard files (authored once under claude-code/hooks) into a target's hooks/.

    ``_SHARED_HOOKS_SRC`` already IS the hooks dir, so the source key is the bare filename."""
    return _copy_map(_SHARED_HOOKS_SRC, out_root, {n: f"hooks/{n}" for n in names})


def _emit_opencode_extras(out_root: Path, tokens: dict[str, str]) -> list[str]:
    agents, commands = _opencode_agents_and_commands(tokens)
    _write(out_root / "plugin.js", generate_plugin_js("hercules", agents, commands))
    _write(out_root / "opencode.json", json.dumps(generate_opencode_json(), indent=2) + "\n")
    _write(out_root / "CAPABILITIES.md", _OPENCODE_CAPABILITIES)
    # The write-gate the generated plugin.js invokes: the canonical Python guard + its state reader.
    written = ["plugin.js", "opencode.json", "CAPABILITIES.md"]
    written += _copy_shared_hooks(out_root, ("frozen_tests.py", "hercules_state.py"))
    return written


_CURSOR_CAPABILITIES = """# Hercules on Cursor — capabilities & disclosed gaps

Hercules ships the full Discover → Design → Build → Ship methodology on Cursor as an official plugin
(`.cursor-plugin/plugin.json`), with three capability gaps disclosed here (the "disclose gaps, never
hide" principle):

- **Frozen-test write-gate: partially enforced (needs `python3`).** Cursor has no pre-file-edit veto
  (`afterFileEdit` is notification-only), so a Composer edit to a frozen test **cannot be prevented** —
  but the plugin's hooks (`hooks/hooks.json` → `hooks/hercules_gate.py`, reusing the same canonical
  guard state AND the same `frozen_override` policy) add real teeth: `beforeShellExecution`
  **hard-denies** a shell command that writes to or commits a frozen test during a build, and
  `afterFileEdit` **reverts** a frozen edit after the fact (a backstop, since it cannot block). A
  user-granted `frozen_override` ("change test X") lifts the gate for that file this round, exactly as
  on Claude Code and OpenCode. The hooks need `python3` on PATH and fail **open** if it is absent. Turn
  on Cursor's *ask-before-applying-edits* approval for an additional backstop. This is stronger than
  advisory but weaker than Claude Code's hard pre-write veto — the Composer-edit path is revert-only, and
  the shell check is a coarse guardrail against honest/accidental writes (it catches the common
  write/delete/redirect forms, but not `python -c`, heredocs, or cross-pipe data flow).
- **No per-agent model tier.** Every Hercules subagent **inherits the model you select in Cursor** — the
  build omits a per-agent `model:` on purpose (Cursor's `inherit` default), because forcing advisors onto
  a cheap `fast` tier would degrade the reasoning-heavy reviewers, and Cursor's `model: inherit` is itself
  unreliable in nested cases. Claude Code assigns a heavier model to the orchestrator and lighter models
  to routine advisors; on Cursor that tiering is intentionally not applied — your one selected model
  drives everything.
- **Independent review is best-effort in the IDE.** The Design coverage and Build traceability gates
  delegate to a fresh, isolated `cynical-reviewer` subagent (Cursor >= 2.4). Cursor exposes **no**
  orchestrator-forced spawn — in-IDE delegation is heuristic or `@`-mention-driven — so Hercules
  requires an explicit reviewer **handshake** (the reviewer attests it read the requirements source and
  returns a coverage/traceability matrix) and **halts and asks you** if that handshake is missing,
  converting a silent self-review into a loud stop. The closest to a forced, isolated reviewer is to run
  the review packet through the headless `cursor-agent -p` CLI — a fresh agent process with its own
  context; Cursor's CLI has no flag to select a named subagent, so the packet carries the reviewer mandate.
"""


def _emit_cursor_extras(out_root: Path, tdir: Path) -> list[str]:
    """All non-content Cursor artifacts (mirrors _emit_opencode_extras): the versioned manifest copy, the
    write-gate hooks (cursor adapter + the shared canonical guard files, from which the adapter reuses the
    SAME frozen_override policy Claude/OpenCode apply — not a re-port), and CAPABILITIES.md."""
    written = _copy_map(tdir, out_root, _CURSOR_COPIES)
    written += _copy_map(tdir, out_root, {f"hooks/{n}": f"hooks/{n}" for n in ("hooks.json", "hercules_gate.py")})
    written += _copy_shared_hooks(out_root, ("hercules_state.py", "frozen_tests.py"))
    _write(out_root / "CAPABILITIES.md", _CURSOR_CAPABILITIES)
    written.append("CAPABILITIES.md")
    return written


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
        written += _copy_map(SRC / "targets" / target, out_root, _CLAUDE_COPIES)
    elif target == "cursor":
        written += _emit_cursor_extras(out_root, SRC / "targets" / target)
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
