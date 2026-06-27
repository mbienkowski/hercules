# Hercules — Code of Conduct

Hercules enforces spec-driven discipline for its users. It holds itself to the same standard.
This document is for **contributors** — the rules for extending or contributing to Hercules
itself. How a user *runs* Hercules (the workflow, phases, and artifact conventions) lives in
[`plugin/CLAUDE.md`](plugin/CLAUDE.md).

---

## Development

### Adding a command

- File: `plugin/commands/{name}.md` — **lowercase only** (macOS is case-insensitive, Linux is not)
- Must contain the `/hercules:{name}` trigger phrase in the body
- Must open with `**Plan mode — required.**`
- Must use `YYYY-MM-DD` date format in all artifact paths
- Must point forward to the next phase at close-out
- Must update the delivery workflow table in `plugin/CLAUDE.md`
- Add a token budget entry to `tests/testdata/thresholds.json`
- Step numbering uses integers only — no letter suffixes (no `4a` / `1b`)

### Adding an agent

- File: `plugin/agents/{name}.md` — lowercase
- Carries **no hardcoded stack or personal preferences** — project variance lives in each project's `code-of-conduct.md`
- Replies follow the A2A `§ Agent-Injected Core` format (see `plugin/protocols/a2a-communication-protocol.md`)
- Update the agent list in `plugin/CLAUDE.md` after adding
- The list is pinned by `tests/methodology/` — run the suite to confirm no drift

### Adding a skill

- Directory: `plugin/skills/{name}/SKILL.md`
- Must declare: phase-anchored trigger, precondition-then-stop guard, atomic/idempotent writes
- Falls back gracefully when `code-of-conduct.md` is absent in the target project

### Branching

- **Branch names must not contain slashes.** A `/` makes git create nested directories under
  `.git/refs/heads/` (e.g. `claude/feature-x` becomes `refs/heads/claude/feature-x`), which clutters
  the ref namespace and blocks a later branch from reusing that name as a leaf.
- Use **hyphens** instead: `claude-feature-x`, not `claude/feature-x`.

---

## Testing

One language, one runner: **Python**. Everything is a pytest test under `python -m pytest tests/` —
the wrapper's logic, the plugin-content lint, and the A2A protocol/metric budgets.

```bash
# Set up once
pip install -e ".[dev]"

# Run everything — CI gates on >= 90% branch coverage (make test)
make test

# Branch coverage, same gate as CI
python -m pytest tests/ --cov=hercules --cov-branch --cov-report=term-missing --cov-fail-under=90
```

Hercules holds itself to the bar it enforces on its users: **>= 90% branch coverage** (gated by
`make test`) and a **>= 90% mutation kill rate** (gated by `make test-mutation`). Both run in CI on
every PR — practice what we preach.

### What's covered

| Area | Where | Kind |
|------|-------|------|
| CLI flag parsing and orchestration | `tests/plugin_sync/test_cli.py` | unit |
| Config read/write and migration shim | `tests/plugin_sync/test_config.py`, `test_wizard.py` | unit |
| Git clone/pull, URL validation, TTL | `tests/plugin_sync/test_git_sync.py`, `test_git_sync_subprocess.py` | unit |
| Directory-based PID lock | `tests/plugin_sync/test_lock.py` | unit + subprocess |
| claude exec and secret stripping | `tests/plugin_sync/test_claude_runner.py` | unit |
| A2A protocol grammar and status vocabulary | `tests/methodology/test_a2a_grammar.py`, `test_protocol_files.py` | unit + policy |
| Instruction and token budget checks | `tests/methodology/test_threshold_runner.py`, `test_plugin_integrity.py` | unit + data-driven |
| Agent and skill file hygiene | `tests/methodology/test_agents.py`, `test_skills.py` | policy |
| Command file structure       | `tests/methodology/test_commands.py`                | policy |

### Adding a check

**A threshold/budget check → add a row to `tests/testdata/thresholds.json`** (no Python change):

```json
{
  "name": "my-file-token-budget",
  "target": "plugin/commands/discover.md",
  "metric": "token_count",
  "op": "<=", "limit": 400, "warn_at": 320,
  "severity": "warn"
}
```

- `target` — a path, or a comma-separated list of paths/globs. For a glob/list the metric is
  **summed** across all matched files.
- `metric` — one of: `instruction_count`, `token_count`, `core_entry_count`, `core_token_count`.
  Add new ones in `hercules/methodology/threshold_runner.py` (`METRIC_REGISTRY`).
- `op` — `==`, `<=`, `>=`, `<`, `>`.
- `severity` — `gate` (fails the build) or `warn` (prints a warning, non-failing).
- `warn_at` (optional) — emit a warning when the value crosses this soft line while still under
  the hard `limit`.

**A new metric → add a function to `hercules/methodology/` and register it** in `METRIC_REGISTRY`.

**A behavioral/CLI check → add a pytest test** in `tests/plugin_sync/test_cli.py` using the
`fake_bin` and `isolated_home` fixtures from `tests/conftest.py`.

### Budgets are fixed — stop and ask before you bump or cut

Token and instruction budgets in `tests/testdata/thresholds.json` are quality gates, not
obstacles: every token a command/agent/skill carries is consumed at startup and on every run,
eating context the model needs for good output. More tokens → less room to think → lower quality.

When a change would breach a budget, the assistant is the **guardian of the gate**. It must
**not** silently raise the threshold, and must **not** silently cut content to make room. Instead:

1. **Stop and surface it.** State plainly which budget would be exceeded and by how much, e.g.
   *"The token budget for the Discover phase (`discover.md`) would be exceeded — ~1390 / limit 1350."*
2. **Propose at least three options** and recommend one, for example:
   - **Tighten verbose prose** elsewhere in the file to absorb the addition (usually the best fit).
   - **Move content out** — extract detail into a separate file/reference the phase links to.
   - **Drop a lower-value instruction** to make room for the higher-value one.
   - **Raise the threshold** — only if the maintainer explicitly chooses this.
3. **Let the maintainer decide.** Apply only the chosen option.

Raise a threshold **only** when the maintainer explicitly instructs it in their own words. Absent
that explicit instruction, treat every threshold as immovable.

### Tokens

Token counts are computed offline with `tiktoken` (cl100k_base, no network call).

### Golden files

The injected A2A Core is pinned byte-for-byte in `tests/testdata/core.golden`. After an
intentional edit to the Core block, re-bless it:

```bash
cp plugin/protocols/a2a-communication-protocol.md /tmp/a2a.md  # then extract and overwrite core.golden
```

Or let the failing test tell you the expected value and paste it in.

All methodology checks are gates, not warnings. A failing gate means the change violates a
contract — fix the contract or the gate, not the test.
