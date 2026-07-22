"""Every shipped distribution MUST carry the frozen-test write-gate (G1) — the *presence* invariant.

The per-ecosystem write-gate tests (``test_opencode_write_gate.py``, ``test_cursor_write_gate.py``, and
the Claude ``frozen_tests`` tests) prove each gate *works*. They do NOT fail if a distribution ships
*without* its gate: a dropped ``hooks/`` copy, a refactor that stops emitting the wiring, or a brand-new
4th ecosystem added with no enforcement would all pass silently.

This module closes that hole. It iterates **every registered target** (``cli.TARGETS``, derived from the
serializer registry) and asserts each ships its required gate wiring. The load-bearing check is
``test_every_registered_target_declares_a_gate``: a target with no declared expectation FAILS, so a new
ecosystem cannot ship without either wiring a gate or recording an explicit, reasoned waiver.

Builds into a temp dir rather than reading committed ``dist/``; the drift gate (``--check``) already
guarantees committed ``dist/`` is byte-identical to a fresh build, so this equivalently guards what ships.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.build import cli
from scripts.build.cli import build_target

REPO_ROOT = Path(__file__).resolve().parents[2]

# The frozen-guard state reader every gate reuses — one source of truth across ecosystems.
_STATE = "hooks/hercules_state.py"

# What each distribution MUST ship for the write-gate to exist. A target present in cli.TARGETS but
# absent here fails test_every_registered_target_declares_a_gate — that is the "fail if a required gate
# is missing" guarantee, now and for any future ecosystem. An entry may instead be
# ``{"waiver": "<reason>"}`` for a runtime with no hook surface at all; the entry must still EXIST.
GATE_EXPECTATIONS: dict[str, dict] = {
    # Claude Code: a PreToolUse hook denies a premature/ frozen write before it lands.
    "claude-code": {
        "files": ["hooks/hooks.json", "hooks/frozen_tests.py", _STATE],
        "hooks_json": {
            "path": "hooks/hooks.json",
            "event": "PreToolUse",
            "matcher_tokens": ["Edit", "Write", "MultiEdit"],
            "guard": "frozen_tests.py",
        },
    },
    # OpenCode: a generated tool.execute.before hook throws to abort a frozen edit before disk.
    "opencode": {
        "files": ["plugin.js", "hooks/frozen_tests.py", _STATE],
        "plugin_js": ["\"tool.execute.before\"", "makeWriteGate", "spawnSync(\"python3\"",
                      "frozen_tests.py"],
    },
    # Cursor: shell/read deny + after-edit revert, keyed off the same frozen state.
    "cursor": {
        "files": [".cursor-plugin/plugin.json", "hooks/hooks.json", "hooks/hercules_gate.py",
                  "hooks/frozen_tests.py", _STATE],
        "manifest_hooks_pointer": ".cursor-plugin/plugin.json",
        "cursor_hooks": {
            "path": "hooks/hooks.json",
            "modes": ["beforeShellExecution", "beforeMCPExecution", "afterFileEdit"],
            "guard": "hercules_gate.py",
        },
    },
    # Grok Build: reads Claude-format hooks, so it reuses the PreToolUse wiring (rooted at
    # ${GROK_PLUGIN_ROOT}) and the byte-identical canonical guard to deny a frozen write before it lands.
    "grok-build": {
        "files": ["hooks/hooks.json", "hooks/frozen_tests.py", _STATE],
        "hooks_json": {
            "path": "hooks/hooks.json",
            "event": "PreToolUse",
            "matcher_tokens": ["Edit", "Write", "MultiEdit"],
            "guard": "frozen_tests.py",
        },
    },
    # Gemini CLI: a BeforeTool hook denies a frozen write_file/replace before it lands (Claude-shape veto).
    "gemini-cli": {
        "files": ["hooks/hooks.json", "hooks/hercules_gate.py", "hooks/frozen_tests.py", _STATE],
        "hooks_json": {
            "path": "hooks/hooks.json",
            "event": "BeforeTool",
            "matcher_tokens": ["write_file", "replace"],
            "guard": "hercules_gate.py",
        },
    },
    # Copilot CLI: a preToolUse hook denies an edit to a frozen test before it lands.
    "copilot-cli": {
        "files": ["plugin.json", ".github/plugin/marketplace.json", "hooks/hooks.json",
                  "hooks/hercules_gate.py", "hooks/frozen_tests.py", _STATE],
        "copilot_hooks": {
            "path": "hooks/hooks.json",
            "event": "preToolUse",
            "matcher_tokens": ["create", "edit"],
            "guard": "hercules_gate.py",
        },
    },
}


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """Build every registered target once; return ``{target: dist_root}``."""
    roots = {}
    for target in cli.TARGETS:
        out = tmp_path_factory.mktemp(target)
        build_target(target, out)
        roots[target] = out
    return roots


# ── The load-bearing invariant: no ecosystem ships without a declared gate ───────────────────
def test_every_registered_target_declares_a_gate():
    """A target registered in the build but missing from GATE_EXPECTATIONS FAILS here — you cannot add
    a distribution (now or a future 4th ecosystem) without wiring its write-gate or recording a waiver.
    This is the 'fail if we won't have the gates required' guarantee."""
    registered = set(cli.TARGETS)
    declared = set(GATE_EXPECTATIONS)
    missing = registered - declared
    assert not missing, (
        f"registered target(s) with NO declared write-gate: {sorted(missing)} — wire the gate and add a "
        f"GATE_EXPECTATIONS entry (or an explicit {{'waiver': reason}}); a distribution must not ship "
        f"without frozen-test enforcement")
    stale = declared - registered
    assert not stale, f"GATE_EXPECTATIONS names unregistered target(s): {sorted(stale)}"
    # A waiver is the only sanctioned way to declare "no gate" — it must carry a real, non-empty reason,
    # so nobody disables enforcement for a target with an empty ``{"waiver": ""}`` rubber stamp.
    for target, spec in GATE_EXPECTATIONS.items():
        if "waiver" in spec:
            assert isinstance(spec["waiver"], str) and spec["waiver"].strip(), \
                f"{target}: a gate waiver must state a non-empty reason"


# ── Per-target: the declared gate is actually shipped and wired ──────────────────────────────
@pytest.mark.parametrize("target", list(GATE_EXPECTATIONS))
def test_target_ships_its_write_gate(target, built):
    spec = GATE_EXPECTATIONS[target]
    if "waiver" in spec:
        pytest.skip(f"{target}: gate waived — {spec['waiver']}")
    out = built[target]

    for rel in spec["files"]:
        assert (out / rel).is_file(), f"{target}: required gate file {rel} not shipped"

    # Claude Code: PreToolUse matcher covers the write tools and points at the guard.
    if "hooks_json" in spec:
        hj = spec["hooks_json"]
        data = json.loads((out / hj["path"]).read_text(encoding="utf-8"))
        entries = data.get("hooks", {}).get(hj["event"], [])
        assert entries, f"{target}: no {hj['event']} hook wired"
        matchers = " ".join(e.get("matcher", "") for e in entries)
        for tok in hj["matcher_tokens"]:
            assert tok in matchers, f"{target}: {hj['event']} matcher must cover {tok}"
        wired = json.dumps(entries)
        assert hj["guard"] in wired, f"{target}: {hj['event']} must invoke {hj['guard']}"

    # OpenCode: the generated plugin.js carries the real pre-write veto.
    if "plugin_js" in spec:
        js = (out / "plugin.js").read_text(encoding="utf-8")
        for token in spec["plugin_js"]:
            assert token in js, f"{target}: plugin.js missing write-gate token {token!r}"

    # Copilot CLI: the preToolUse hook matches the edit tools and invokes the guard adapter.
    if "copilot_hooks" in spec:
        ch = spec["copilot_hooks"]
        data = json.loads((out / ch["path"]).read_text(encoding="utf-8"))
        entries = data.get("hooks", {}).get(ch["event"], [])
        assert entries, f"{target}: no {ch['event']} hook wired"
        matchers = " ".join(e.get("matcher", "") for e in entries)
        for tok in ch["matcher_tokens"]:
            assert tok in matchers, f"{target}: {ch['event']} matcher must cover {tok}"
        wired = json.dumps(entries)
        assert ch["guard"] in wired, f"{target}: {ch['event']} must invoke {ch['guard']}"

    # Cursor: manifest points at the hooks file, which wires all three gate modes to the guard.
    if "manifest_hooks_pointer" in spec:
        manifest = json.loads((out / spec["manifest_hooks_pointer"]).read_text(encoding="utf-8"))
        assert manifest.get("hooks"), f"{target}: manifest must declare a hooks pointer"
    if "cursor_hooks" in spec:
        ch = spec["cursor_hooks"]
        data = json.loads((out / ch["path"]).read_text(encoding="utf-8"))
        hooks = data.get("hooks", {})
        for mode in ch["modes"]:
            wired = json.dumps(hooks.get(mode, []))
            assert hooks.get(mode), f"{target}: {mode} not wired"
            assert ch["guard"] in wired, f"{target}: {mode} must invoke {ch['guard']}"


# ── One source of truth: the state reader never diverges across ecosystems ───────────────────
def test_frozen_state_reader_is_byte_identical_across_all_gated_targets(built):
    """Every distribution that ships hercules_state.py must ship the SAME bytes — the gates share one
    state reader, so a Claude/OpenCode/Cursor build can never enforce a different frozen set."""
    shipped = {}
    for target, spec in GATE_EXPECTATIONS.items():
        if "waiver" in spec or _STATE not in spec.get("files", []):
            continue
        shipped[target] = (built[target] / _STATE).read_bytes()
    assert len(shipped) >= 2, "expected at least two gated targets to ship the shared state reader"
    reference = REPO_ROOT / "src" / "targets" / "claude-code" / "hooks" / "hercules_state.py"
    ref_bytes = reference.read_bytes()
    for target, data in shipped.items():
        assert data == ref_bytes, f"{target}: hercules_state.py diverged from the canonical source"
