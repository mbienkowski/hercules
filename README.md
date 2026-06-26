# Hercules

In Greek mythology, Hercules was half-man and half-god, with the strength of more than ten men —
and always keen to help anyone on his path. That's the idea here.

**Hercules is a Claude Code plugin that enforces the best known rules of software delivery.**
Discover before you design. Design before you build. No shortcuts.

---

## Quickstart

The fastest way to start is the guided workflow — Hercules walks you through every phase.

After running `hercules` to launch Claude Code, type this command in the chat:

```
/hercules:workflow
```

Or run each phase on its own when you know where you are:

| Command | Phase | What it produces |
|---|---|---|
| `/hercules:discover` | Discover | `YYYY-MM-DD-desc-business-requirements.md` |
| `/hercules:design` | Design | `YYYY-MM-DD-desc-spec-NN-sub.md` (one or more) |
| `/hercules:build` | Build | Working code + tests |

You can also address Hercules directly in Claude: *"Hercules, where do I start?"*

---

## Your first session

After `hercules` launches Claude, type `/hercules:workflow`. Discovery is where the real work happens — bring everything you have: PRDs, ADRs, Figma links, QA scenarios, API contracts, Slack threads. The more context you bring, the better. Hercules asks about the gaps; you answer them. Your first session ends with a requirements document saved to `docs/`.

At each phase, Hercules drafts an artifact and waits for you to say `approved` before saving it. That's the whole loop. Repeat for every feature.

---

## One home for your delivery docs

Hercules keeps every requirement and spec in **a single place** — a command center your whole team
can version, review, and update like any other part of the codebase. Decide on that home once, and
Hercules writes there for every feature:

- **Monorepo** — open Claude in the repo and keep the documents in their own directory, e.g.
  `features/`, `requirements/`, or `docs/`. They live and version right alongside the code.
- **Many repos** — create one dedicated docs repo (the same idea, just its own repository) and open
  Claude there. However many services a feature touches, its documents stay together in that one
  repo — never scattered across services where they drift and get lost.

Name that directory or repo once in your `code-of-conduct.md`; if you skip it, Hercules defaults to
`docs/`. Either way it's plain Markdown under version control, so anyone on the team can read it,
review it in a PR, and keep it current.

**A feature that spans several services?** Tell Hercules the local path to each one — it asks the
first time and remembers them on **your machine only**, in `~/.hercules/hercules-config.json`.
Nothing about where your repos live is ever written into the docs themselves, so there is no
machine-local file to accidentally commit. From there Hercules delivers across all of them in step:
making the changes in each service and branching in each per your team's naming convention.

---

## What Hercules does

Hercules guides you through a three-phase delivery workflow inside Claude:

1. **Discover** — the heaviest phase. Accepts PRDs, ADRs, Figma links, QA scenarios, or a plain
   sentence — whatever you have. Pins the real need, who benefits, what's in and out of scope,
   and what "done" looks like. Output: `*-business-requirements.md` (permanent, committed forever).
2. **Design** — turns requirements into one or more **specs**, each a self-contained build
   blueprint. The depth of a spec comes from whichever specialist agents are engaged — architecture,
   security, QA, and the rest — who challenge the approach before a line of code is written.
   Output: `*-spec-NN-*.md` (temporary, deleted when each feature ships).
3. **Build** — TDD loop: failing tests first, implementation after, reviewed before close-out.
   Executes each spec in order. Branch coverage and mutation testing gate the work before it ships.
   Output: code + tests. The spec files are deleted (`git rm`) the moment a feature ships — code,
   tests, and git history become the record of what was delivered.

**Two kinds of document, two lifecycles.** Business-requirements files are **long-lived**: committed
forever, written in plain business language, and shareable between stakeholders as the durable record
of what a feature is for. They are updated *every time the code changes for an existing feature*, so
they never drift from reality. Specs are **per-development** files — once a feature ships, its specs
are deleted, because the **code, its tests, and git history become the single source of truth for
developers**. Business people keep the documentation they can share; developers read the code.

Artifacts are written to `docs/` in the directory where you launch Hercules (a project's
`code-of-conduct.md` can redirect this; cross-repo work asks where to put them).

Every feature runs all three phases. Complexity scoring determines depth — trivial features get a
single lightweight pass; critical features get multi-round specialist debate. No phase is ever skipped.

Specialist agents — Architect, Security Expert, QA Engineer, Cynical Reviewer, Simplicity
Advocate, and more — are available at every phase. Two things scale with the complexity score:
*which* agents are brought in, and *how many*. A routine fix runs lean; a critical feature
draws a full panel of voices with different agendas — deliberately polarised — because good
decisions come from tension, not consensus. Up to six agents for the most complex work; none
added for the trivial.

---

## Why sub-agents?

A single model in a single pass has predictable failure modes. Specialist advisors counter each one — which is why Hercules recommends them at every phase (and asks before running them).

- **One agent can only follow so many instructions — so split the work across several.** This is
  *the* reason Hercules uses sub-agents. Adherence stays near-perfect at ~50 instructions (~99.6%),
  slips to ~85% at 250, and ~69% at 500
  ([arxiv.org/html/2507.11538v1](https://arxiv.org/html/2507.11538v1)). So one agent carrying ~300
  instructions silently drops roughly one in five; split that same work across three focused agents
  at ~100 instructions each and every agent stays in its ~99% high-adherence zone — far more of the
  total actually gets followed. Smaller scope per agent also means less context drift and tighter
  focus. A single mega-agent cannot do this; more agents with *less* each is the point.
- **Context drifts over long sessions.** Early on, the model invents APIs that do not exist
  (easy to catch); later it reintroduces bugs because decisions from the start fell out of
  working memory. Root cause: no external source of truth. The counter is a spec locked before
  code and TDD that freezes expected behaviour into tests — the session decays, the spec and
  tests do not. Fresh advisors re-read the spec, not the chat history.
- **Models are sycophantic.** Research in 2026 found AI ~49% more likely than a human to affirm
  the user, even when it knows better. The counter: advisors instructed to challenge — to push
  back, name the risks, and offer alternatives before a plan is approved.
- **Agents echo each other.** Propose → validate → confirm is not consensus; it is one opinion
  repeated. Simulations show agents conforming to the majority in up to 83% of cases — agreement
  driven by numbers, not reasoning. The counter: a blind round (independent ideas first), then a
  round that must reach genuine consensus.
- **Output volume feeds the drift.** LLMs restate and pad; the noise pushes the next agent past
  its coherent zone. The counter: an agent-communication protocol that forces concise, structured
  replies.

This is why Hercules recommends advisors at each phase — with deliberately opposing agendas,
scaled to complexity — and asks before running them. You stay in control.

---

## Philosophy

Software built from a clear specification is cheaper to build, easier to review, and harder to
break than software that emerged from a prompt. Hercules applies **spec-driven development**:
the specification is the single source of truth, written before a single line of code is
produced, validated against the requirements that prompted it, and updated whenever the code
diverges from it.

The three-phase flow — Discover, Design, Build — is deliberately front-heavy. Discovering
the real problem (not the first stated one), and designing the technical and visual solution
before implementation, takes real time. That investment pays back in solutions that are
well-reasoned, security-reviewed, and aligned with what stakeholders actually need. Rework is
expensive. Getting it right the first time is cheap.

**Depth scales with complexity.** A trivial fix runs all three phases as a single lightweight
pass. A critical feature runs multi-round specialist debates, solution scoring, fresh-eyes
reviews, and full mutation-tested TDD. The same process, at the right intensity.

**Quality is enforced, not assumed.** Coverage gates, traceability checks, and cynical
peer-review are mandatory steps — not optional best-practices you might skip when under
pressure. Human stakeholder review is built into the Discover and Design phases at medium+
complexity. The AI is a capable collaborator; the standards are yours to set.

---

## A note on quality

Hercules is a tool. Like any tool, it is only as good as the person using it.

AI amplifies intent. If you bring discipline, clear thinking, and high standards to every
interaction, Hercules reflects that back in the output. If you rush, skip the design, or
approve requirements you haven't actually read — Hercules will faithfully build exactly what
you described, which may not be what you needed.

**You are responsible for the quality of what you build.** Hercules makes it easier to do
that well.

---

## Plugin directory

No Python needed. Clone once, add the plugin directory to your Claude CLI config:

```bash
git clone https://github.com/mbienkowski/hercules.git ~/.hercules
claude --add-dir ~/.hercules/plugin
```

Claude Code reads `plugin/commands/`, `plugin/agents/`, and `plugin/skills/` automatically.
To update: `git -C ~/.hercules pull`.

### Claude Code Desktop

Same one-time clone as above — then, instead of the CLI flag, open Claude Code Desktop and go to
**Settings → Plugin directories** and add `~/.hercules/plugin`. No Python or terminal beyond the
initial clone. Update by pulling the repo (`git -C ~/.hercules pull`, or your preferred Git GUI).

---

## CLI auto-sync

The `hercules` CLI wraps `claude` and syncs the plugin on every invocation — so you always
get the latest agents and skills without pulling manually.

### Install

Requires **Python ≥ 3.9** (already shipped on most systems, including macOS 12+ — no install needed).

There is no package index involved — install the `hercules` command directly from the repo.

**From GitHub:**

```bash
pipx install git+https://github.com/mbienkowski/hercules.git
```

**From a local checkout** (e.g. to hack on it):

```bash
git clone https://github.com/mbienkowski/hercules.git
cd hercules
pipx install .          # or, for an editable dev install: pip install -e .
```

Both give you the `hercules` command. (Install only from the repo — do not `pip install hercules`.)

Or via the bootstrap script:

```bash
curl -sSL https://raw.githubusercontent.com/mbienkowski/hercules/main/install.sh | bash
```

### Usage

Use `hercules` everywhere you would use `claude`:

```bash
hercules                        # launch Claude with auto-updated plugin
hercules --sync                 # force an immediate plugin refresh, then exit
hercules "write a test for X"  # pass a prompt directly
```

The plugin syncs automatically every 30 minutes (run `hercules --sync` to refresh immediately).
The first run clones this repo and prompts for setup.

### Multiple config directories (work vs. personal)

```bash
hercules --claude-dir ~/.claude-priv   # fully isolated Claude login + settings
hercules -c ~/.claude-priv             # short form
```

### Track the latest release (default) vs. a branch

By default `hercules` tracks the **latest stable release** (the highest semver tag) — not the
moving `main` branch — so you run a reviewed, tagged version. Until the first release is cut, it
falls back to `main` automatically.

```bash
hercules                          # latest release (recommended)
hercules --branch main            # bleeding edge: follow main
hercules --branch my-feature-x    # test a specific branch before it merges
```

### First-time setup

```bash
hercules --setup
```

### Update hercules itself

```bash
hercules --update   # prints: pipx upgrade hercules
```

### Check install status

```bash
hercules --status   # home, initialized, onboarded, last sync
```

---

## How it works

```
hercules [args]
  │
  ├── First run:    git clone plugin repo → ~/.hercules/ (latest release tag)
  ├── Every 30 min: fetch tags + checkout latest release  (or pull, in --branch mode)
  │
  └── exec claude --add-dir ~/.hercules/plugin [args]
```

The Python source in `hercules/` is the CLI sync wrapper. `plugin/` contains everything
Claude reads: `agents/`, `skills/`, `commands/`, `protocols/`.

---

## Security

`hercules` auto-syncs every 30 minutes. Tracking the **latest release** (the default) means a
push to `main` does not reach users until it is reviewed, merged, and tagged as a release — so the
exposure window for an unreviewed change is a release, not a single push. (`--branch main` opts back
into following every push.) Mitigations:

- All changes go through pull requests and CI before merging, and releases are cut from `main`
- Installs come from the pinned GitHub repo over HTTPS; integrity rests on that repo plus the
  PR/CI gate above
- The git token never touches the shared `~/.hercules/hercules-config.json` (which the plugin and
  GUI read) — it lives only in the `HERCULES_GIT_TOKEN` env var or a 0600 credentials file
- Secret env vars (`HERCULES_GIT_TOKEN`, `HERCULES_REPO_URL`, `GIT_ASKPASS`) are stripped
  before `exec`ing into `claude`

---

## Requirements

- Python ≥ 3.9 (only for the optional auto-sync CLI; the plugin-directory path needs no Python)
- `git` on PATH
- Claude Code ≥ v2.1.128

---

## Contributing

Read [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) first — it defines the rules for extending commands, agents, and skills, plus how to run the tests.

1. Fork and create a branch
2. Add or edit files in `plugin/commands/`, `plugin/agents/`, or `plugin/skills/`
3. Test locally: `hercules --branch your-branch`
4. Run the suite: `pip install -e ".[dev]" && python -m pytest tests/`
5. Open a PR — CI runs the full suite plus mutation testing

All `.md` filenames must be **lowercase** — macOS is case-insensitive but Linux is not.

---

## License

MIT
