"""Every shipped distribution carries the frozen-test write-gate — the PRESENCE invariant no gate
suite covers, since a gate that works proves nothing about a distribution shipping without one.
READS ``dist/`` on purpose: marketplaces install straight from that committed tree, so the
supply-chain fact worth asserting is that the copy a user installs carries the guard, wires it to a
real host event, and has not drifted from its source. ``test_every_registered_target_declares_a_gate``
is load-bearing: nothing ships without either a wired gate or an explicit, reasoned waiver."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
_DIST = REPO_ROOT / "dist"
# The registered target list is the sorted set of ecosystem directories committed under dist/.
TARGETS = sorted(p.name for p in _DIST.iterdir() if p.is_dir())

# The two canonical guards every gate reuses: the state reader, and the frozen-test policy above it.
_STATE = "hooks/hercules_state.py"
_GUARD = "hooks/frozen_tests.py"

# What each distribution MUST ship; a hook-less runtime may say ``{"waiver": "<reason>"}`` instead.
# ecosystem-tax:start — one entry per host; measured and capped by tests/budgets/ecosystemTax.spec.ts.
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
    # Grok Build: reads Claude-format hooks, so it reuses the PreToolUse wiring and the same guard.
    "grok-build": {
        "files": ["hooks/hooks.json", "hooks/frozen_tests.py", _STATE],
        "hooks_json": {
            "path": "hooks/hooks.json",
            "event": "PreToolUse",
            "matcher_tokens": ["Edit", "Write", "MultiEdit"],
            "guard": "frozen_tests.py",
        },
    },
    # Gemini CLI: a BeforeTool hook denies a frozen write_file/replace before it lands.
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
    # Codex: native PreToolUse hook with the hookSpecificOutput decision envelope.
    "codex": {
        "files": [".codex-plugin/plugin.json", "hooks/hooks.json", "hooks/hercules_gate.py",
                  "hooks/frozen_tests.py", _STATE],
        "codex_hooks": {
            "path": "hooks/hooks.json",
            "event": "PreToolUse",
            "matcher_tokens": ["apply_patch", "Bash"],
            "guard": "hercules_gate.py",
        },
    },
}
# ecosystem-tax:end


@pytest.fixture(scope="module")
def built():
    """The committed dist/ root for every registered target — return ``{target: dist_root}``."""
    return {target: _DIST / target for target in TARGETS}


# ── The load-bearing invariant: no ecosystem ships without a declared gate ───────────────────
def test_every_registered_target_declares_a_gate():
    """A distribution cannot be added without wiring its write-gate or recording a reasoned waiver."""
    registered = set(TARGETS)
    declared = set(GATE_EXPECTATIONS)
    missing = registered - declared
    assert not missing, (
        f"registered target(s) with NO declared write-gate: {sorted(missing)} — wire the gate and add a "
        f"GATE_EXPECTATIONS entry (or an explicit {{'waiver': reason}}); a distribution must not ship "
        f"without frozen-test enforcement")
    stale = declared - registered
    assert not stale, f"GATE_EXPECTATIONS names unregistered target(s): {sorted(stale)}"
    # A waiver carries a real reason, so an empty rubber stamp cannot disable enforcement.
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

    # Codex: PreToolUse hook invokes the adapter with Codex's nested decision envelope.
    if "codex_hooks" in spec:
        ch = spec["codex_hooks"]
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


# ── One source of truth: the canonical guards never diverge across ecosystems ────────────────
@pytest.mark.parametrize("guard", [_STATE, _GUARD])
def test_the_canonical_guard_files_are_byte_identical_across_all_gated_targets(guard, built):
    """One state reader and one frozen-test policy across every distribution, so no build can enforce
    a different frozen set or override rule — and what the fixture suites prove is what users install."""
    shipped = {}
    for target, spec in GATE_EXPECTATIONS.items():
        if "waiver" in spec or guard not in spec.get("files", []):
            continue
        shipped[target] = (built[target] / guard).read_bytes()
    assert len(shipped) >= 2, f"expected at least two gated targets to ship {guard}"
    ref_bytes = (REPO_ROOT / "src" / "scripts" / "hooks" / Path(guard).name).read_bytes()
    for target, data in shipped.items():
        assert data == ref_bytes, f"{target}: {Path(guard).name} diverged from the canonical source"


# ── Cursor: claims about the shipped package, not about the gate ─────────────────────────────
def test_cursor_ships_the_manifest_referenced_marketplace_assets():
    """A dangling ``logo`` path in the manifest is what a Cursor submission validator rejects."""
    out = _DIST / "cursor"
    assert (out / "README.md").is_file(), "a README must ship with the plugin"
    manifest = json.loads((out / ".cursor-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert manifest.get("logo") == "./logo.svg", "manifest must declare the logo"
    assert (out / manifest["logo"].lstrip("./")).is_file(), "the manifest-referenced logo must ship"


def test_cursor_hook_commands_invoke_the_gate_by_exact_plugin_root_path():
    """A plugin hook runs with cwd = the PROJECT root, so only ``${CURSOR_PLUGIN_ROOT}`` finds its own
    bundled script. Confirmed by Cursor staff (forum thread 153236) but absent from the env-var docs,
    so whether the gate really FIRES stays a manual RELEASE.md item (4b)."""
    hooks = json.loads((_DIST / "cursor" / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    expected = {
        "beforeShellExecution": "python3 ${CURSOR_PLUGIN_ROOT}/hooks/hercules_gate.py shell",
        "beforeMCPExecution": "python3 ${CURSOR_PLUGIN_ROOT}/hooks/hercules_gate.py mcp",
        "afterFileEdit": "python3 ${CURSOR_PLUGIN_ROOT}/hooks/hercules_gate.py after_edit",
    }
    for event, want in expected.items():
        got = [h["command"] for h in hooks["hooks"][event]]
        assert got == [want], f"{event}: hook command must be exactly {want!r}, got {got!r}"
