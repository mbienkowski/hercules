# Releasing Hercules

Hercules is authored once in `src/` and compiled to per-ecosystem trees under `dist/` (`make build`).
CI regenerates and drift-checks `dist/` on every push, so `main` always carries an in-sync build.

## Automated pipeline

On every merge to `main`, `release.yml` runs after CI succeeds:

1. Computes the next version from Conventional Commits (`feat`/`fix`/`perf` bump the CHANGELOG).
2. `scripts/set_version.py` stamps that version into the two files that MUST carry a literal
   (`scripts/build/version_targets.py::VERSION_TARGETS`): `pyproject.toml` (the canonical source, read
   by setuptools) and `package.json` (read by npm/OpenCode). The plugin manifests
   (`dist/{claude-code,cursor}/…/plugin.json`) are **not** stamped — their source carries a
   `${version}` token that the build injects from `pyproject.toml` (step below), so there is one
   version of record and nothing to hand-bump under `src/targets/`.
3. `make build` regenerates `dist/`, injecting the canonical version into each plugin manifest.
4. Commits the bump + rebuilt `dist/` (`chore(release): X.Y.Z [skip ci]`), tags `vX.Y.Z`, pushes.
5. Publishes the GitHub Release.
6. **Publishes the OpenCode plugin to npm** from the tagged tree (requires the `NPM_TOKEN` repo
   secret; the step self-skips if it is absent).

The `validate` CI job re-reads the canonical list (`pyproject.toml` + `package.json`) and fails if
they disagree; a separate test asserts every shipped `dist/…/plugin.json` version equals the canonical
one — so a release can never ship a split or an un-injected (`${version}`) version.

## Manual smoke checklist (release-gating, once per release)

CI proves the artifacts are valid, in-sync, and regression-checked — it **cannot** prove the plugin
loads and behaves inside a live tool (no ecosystem offers a headless load-and-assert harness). Before
announcing a release, run this by hand and record the result (date, version, tester) in the release notes.

### What's automated now

The `smoke` CI job (and `make test-smoke` locally) runs the real `claude` and `opencode` binaries
against a built plugin — no tokens spent, no login required, seconds not minutes — and covers the
first line of each checklist below: does the plugin actually **install and get recognized** by the
real tool. Everything past that first line (does it *behave* correctly once loaded — the agent
answers in character, a slash command drives a real workflow, a hook actually blocks a write) still
needs a live, paid session and stays a manual, release-gating check.

| # | Claude Code item | Status |
|---|---|---|
| 1 | Install from the marketplace | ✅ automated (`test_the_plugin_installs_from_a_local_checkout_and_shows_up_enabled`) |
| 2 | `hercules` is the default agent, answers in character | manual |
| 3 | `/hercules:workflow` drives Discover → Design → Build → Ship | manual |
| 4 | Write-gate hook blocks/allows | manual |
| 5 | A specialist advisor spawns, replies in A2A format | manual |
| 6 | `hercules-reference` skill loads, `§` sections available | manual (component *presence* is automated via `test_the_installed_plugin_declares_its_full_component_inventory`; loading behavior is not) |
| 7 | A fresh `cynical-reviewer` spawns at the coverage gate | manual |
| 8 | A command's `${CLAUDE_PLUGIN_ROOT}/protocols/…` path resolves | manual |

| # | OpenCode item | Status |
|---|---|---|
| 1 | `config` hook fires (agents/commands register) | ⚠️ blocked — [issue #15](https://github.com/mbienkowski/hercules/issues/15): the real OpenCode loader rejects the built `plugin.js` today, so this is encoded as an `xfail(strict=True)` smoke test rather than a pass; it flips to a hard failure (forcing the marker's removal) the moment the loader bug is actually fixed |
| 2 | `plugin.js` loads with no missing-asset throw | ⚠️ blocked — same root cause as #1 |
| 3 | `default_agent` is `hercules`; a subagent spawns | manual |
| 4 | `/hercules:discover` resolves and runs | manual |
| 5 | A skill auto-fires from its description | manual |
| 6 | Command prompts show no leaked YAML frontmatter | manual |
| 7 | "Which version are you?" reports the package version | manual |
| 8 | `CAPABILITIES.md` discloses the write-gate/model-tier gaps | manual |
| 9 | Build phase's Spec-Sync spawns the bare `cynical-reviewer` id | manual |
| 10 | Protocol references resolve into `cfg.instructions` | manual |
| 11 | `hercules-reference` skill is model-invoked | manual |

### Claude Code

- [ ] Install from the marketplace (`.claude-plugin/marketplace.json` → `dist/claude-code`).
- [ ] `hercules` is the default agent — "Hercules, where do I start?" answers in character.
- [ ] `/hercules:workflow` drives Discover → Design → Build → Ship and each phase writes its artifact
      in order (against a throwaway repo).
- [ ] The write-gate hook blocks an unapproved artifact write and allows it after `approved`.
- [ ] A specialist advisor spawns and replies in the A2A line format.
- [ ] The `hercules-reference` skill loads and its `§` sections (e.g. Artifact root resolution) are
      available — the operational reference lives there, not in the (unloaded) plugin `CLAUDE.md`.
- [ ] At Design's coverage gate, a **fresh `cynical-reviewer`** is actually spawned (not the main
      session) and its coverage findings reach you at Plan-approval — the judgment is independent, not
      self-review. (Cannot be proven by the build; this is the live check.)
- [ ] A command that reads `${CLAUDE_PLUGIN_ROOT}/protocols/…` resolves the path (docs say it expands
      in agent/skill content; *command* content is the one case unverified without this run).

### OpenCode

**Install:** The canonical OpenCode install path is the GitHub repo ref — the user adds it to their
`opencode.json`:

```json
{ "plugin": ["github:mbienkowski/hercules"] }
```

OpenCode resolves the package via its `package.json` `main` (`dist/opencode/plugin.js`) and runs its
`config` hook. (The plugin is also published to npm as `hercules` on release when `NPM_TOKEN` is
configured; npm is an opt-in alternative channel, not the primary install path.)

These load-time behaviours are **not** provable by the build (no headless OpenCode harness exists) —
they must be confirmed live before release:

- [ ] With `"plugin": ["hercules"]` set, the `config` hook actually fires (agents/commands register).
      *If it does not, nothing inline registers — the whole plugin is inert.*
- [ ] `plugin.js` loads with no missing-asset throw (`instructions.md` + `skills/` present as siblings).
- [ ] `default_agent` is `hercules` (primary); a subagent (e.g. `challenger`) spawns as a subagent.
- [ ] `/hercules:discover` resolves and runs as the `hercules` agent (confirm the `:` in the command
      name is honoured in the slash menu).
- [ ] A skill auto-fires from its description (skills are reachable via `cfg.skills.paths`).
- [ ] Command prompts contain **no** leaked YAML frontmatter and show a real description in the UI.
- [ ] "Which version are you?" reports the package version (reads `package.json`, not a Claude path).
- [ ] `CAPABILITIES.md` discloses the write-gate and model-tier gaps.
- [ ] The Build phase's Spec-Sync spawns the **bare** `cynical-reviewer` id (not `hercules:cynical-reviewer`).
- [ ] Protocol references resolve — the 3 protocols are injected into `cfg.instructions` (confirm the
      config-hook mutation to `instructions` is applied before the model runs; documented for skills).
- [ ] The `hercules-reference` skill is model-invoked and its `§` sections are reachable.

### Cursor

**Install:** Cursor consumes the built plugin at `dist/cursor/` (`.cursor-plugin/plugin.json` + native
component dirs). Copy `dist/cursor/` into `~/.cursor/plugins/local/hercules/` and restart Cursor (the
documented local-plugin path). Requires Cursor ≥ 2.5
(the version that added plugin packaging). There is **no registry publish step** — like Claude Code,
Cursor is git-consumed.

These load-time behaviours are **not** provable by the build (the `Smoke — cursor` leg runs the real
`cursor-agent` binary + structural checks on every PR and main; the keyed `cursor-agent -p` run is
opt-in — it needs a `CURSOR_API_KEY` secret and skips without it) — confirm live before release:

- [ ] The plugin installs and `rules/hercules-persona.mdc` always-applies (persona is active).
- [ ] `/discover`, `/design`, `/build`, `/ship`, `/workflow` appear and run.
- [ ] A specialist advisor spawns as an **isolated subagent** (own context), not a same-context rule.
- [ ] **The write-gate fires** (`${CURSOR_PLUGIN_ROOT}` resolves and `hercules_gate.py` runs): during a
      build, a `beforeShellExecution`/`beforeMCPExecution` command that writes/commits a frozen test is
      **denied**. If the hook does not run at all, `${CURSOR_PLUGIN_ROOT}` is not resolving — the gate is
      inert (this is the load-bearing check).
- [ ] **The IDE edit path is advisory, not destructive**: a Composer edit to a frozen test raises a
      **user-visible notice** and the working tree is **left untouched** (no silent revert). With
      `HERCULES_RUNTIME_MODE=headless` set, the same edit is instead **restored via `git checkout`** — and
      the message says so only when git actually restored it (an untracked test reports an honest failure).
- [ ] **The acceptance backstop holds**: tamper with a frozen test (no override) and confirm Build
      **HALTs at retire** on the `frozen_baseline` hash mismatch rather than accepting the spec.
- [ ] At the Design coverage / Build traceability gate, the `cynical-reviewer` returns a **handshake**
      (attests it read `*-business-requirements.md` + a coverage/traceability matrix) — or the flow
      **HALTS and asks** (never silently self-reviews).
- [ ] `CAPABILITIES.md` discloses the write-gate, model-tier, and best-effort-independent-review gaps.
- [ ] "Which version are you?" reports the version from `.cursor-plugin/plugin.json`.

| # | Cursor item | Status |
|---|---|---|
| 1 | Real `cursor-agent` binary runs + built plugin is structurally valid | ✅ automated (`test_the_real_cursor_agent_binary_runs_and_the_plugin_is_well_formed`, runs on every PR + main) |
| 2 | Headless `cursor-agent -p` completes a run | ⚙️ keyed (`CURSOR_API_KEY`; skips on forks) |
| 3 | Persona rule always-applies; commands appear | manual |
| 4 | Specialist spawns as an isolated subagent | manual |
| 4b | Write-gate fires (`${CURSOR_PLUGIN_ROOT}` resolves; frozen shell/MCP write denied; IDE edit advisory-not-reverted; headless restores; acceptance backstop HALTs) | manual (load-bearing) |
| 5 | Independent-review handshake returns (or HALTs) | manual |
| 6 | `CAPABILITIES.md` gaps read true | manual |

### Grok Build · Gemini CLI · Copilot CLI

Installable via `@xai-official/grok` (`/marketplace`), `@google/gemini-cli` (`gemini extensions install
./dist/gemini-cli`), and `@github/copilot` (`copilot plugin install hercules@mbienkowski`). The build
proves structure + the in-process guard; these load-time behaviours are verified live before release
(the `test_<target>_smoke` legs run the real CLI on PR + main; each write-gate test never skips):

- [ ] **Write-gate fires on the file-edit tool** (the 100%-tier claim): a frozen-test edit *during a
      build* is denied — Grok `PreToolUse` (exit 2), Gemini `BeforeTool` (`decision:"deny"`), Copilot
      `preToolUse` (`permissionDecision:"deny"`). If a host vetoes only shell, re-file it best-effort in
      its `CAPABILITIES.md` — never a false "blocked".
- [ ] **Fail-open** when `python3` is absent (Copilot's hook wrapper keeps a missing interpreter from
      failing closed); the acceptance-gate `frozen_baseline` re-hash is the backstop.
- [ ] Persona/commands load, `/…workflow` resolves, and each `CAPABILITIES.md`'s disclosed gaps read true.
- [ ] **Rollback:** repo-hosted install — revert the `dist/<target>/` commit and re-tag; the marketplace
      descriptors point at the prior good tag.

### Cross-ecosystem

- [ ] `pyproject.toml` and `package.json` — the two literal version sources
      (`scripts/build/version_targets.py::VERSION_TARGETS`) — both show the release version (matches the
      git tag). The plugin manifests under `src/targets/` carry a `${version}` token (not a literal); the
      build injects the canonical `pyproject.toml` version into every `dist/…/plugin.json`.

Each shipped ecosystem carries its own smoke section above; add one per target
(see [CONTRIBUTING.md](CONTRIBUTING.md) § Adding a new target for the proven extension procedure).
