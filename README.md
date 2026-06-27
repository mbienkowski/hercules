# Hercules

In Greek mythology, Hercules was half-man and half-god, with the strength of more than ten men —
and always keen to help anyone on his path. That's the idea here.

**Hercules is a Claude Code plugin that enforces the best known rules of software delivery.**
Discover before you design. Design before you build. No shortcuts.

---

## Install

Hercules is a Claude Code plugin, installed from its marketplace — **no Python required.** In Claude
Code, run:

```
/plugin marketplace add mbienkowski/hercules
/plugin install hercules@hercules
```

The agents, commands, and skills load automatically, and Claude Code keeps the plugin updated. You
can also add the marketplace from a local checkout — handy for trying a branch before it merges:

```
/plugin marketplace add /path/to/your/hercules/checkout
/plugin install hercules@hercules
```

### Optional: the branded `hercules` launcher

If you like typing `hercules` to start Claude — and want to run fully isolated configurations side by
side (work vs. personal) — install the thin launcher. It only execs `claude`; the plugin itself comes
from the marketplace. Requires **Python ≥ 3.9** (already on most systems, incl. macOS 12+):

```bash
pipx install git+https://github.com/mbienkowski/hercules.git
hercules                               # launch claude
hercules --claude-dir ~/.claude-work   # use an isolated config directory
```

Or via the bootstrap script — handy if you don't have `pipx`; it finds a suitable Python and falls
back to `pip --user`, then prints the marketplace commands for the plugin:

```bash
curl -sSL https://raw.githubusercontent.com/mbienkowski/hercules/main/install.sh | bash
```

Upgrade the launcher later with `pipx upgrade hercules` (or re-run the script with `--upgrade`).

| Your situation | Use |
|---|---|
| Just want the plugin (most people) | **Marketplace** (`/plugin install`) |
| Want a branded `hercules` command + isolated config dirs | **Launcher** (`pipx` → `hercules`) |
| On Claude Code Desktop | **Marketplace** (Settings → Plugins) |

---

## Quickstart

The fastest way to start is the guided workflow — Hercules walks you through every phase. In Claude
Code, type:

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

Type `/hercules:workflow`. Discovery is where the real work happens — bring everything you have:
PRDs, ADRs, Figma links, QA scenarios, API contracts, Slack threads. The more context you bring, the
better. Hercules asks about the gaps; you answer them. Your first session ends with a requirements
document saved to `docs/`.

At each phase, Hercules drafts an artifact and waits for you to say `approved` before saving it.
That's the whole loop. Repeat for every feature.

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
machine-local file to accidentally commit. From there Hercules delivers across all of them in step.

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
of what a feature is for. Specs are **per-development** files — once a feature ships, its specs are
deleted, because the **code, its tests, and git history become the single source of truth for
developers**. Business people keep the documentation they can share; developers read the code.

Every feature runs all three phases. Complexity scoring determines depth — trivial features get a
single lightweight pass; critical features get multi-round specialist debate. No phase is ever skipped.

Specialist agents — Architect, Security Expert, QA Engineer, Cynical Reviewer, Simplicity
Advocate, and more — are available at every phase. Two things scale with the complexity score:
*which* agents are brought in, and *how many*. A routine fix runs lean; a critical feature draws a
full panel of voices with different agendas — deliberately polarised — because good decisions come
from tension, not consensus. Up to six agents for the most complex work; none added for the trivial.

---

## Why sub-agents?

A single model in a single pass has predictable failure modes. Specialist advisors counter each one —
which is why Hercules recommends them at every phase (and asks before running them).

- **One agent can only follow so many instructions — so split the work across several.** Adherence
  stays near-perfect at ~50 instructions (~99.6%), slips to ~85% at 250, and ~69% at 500
  ([arxiv.org/html/2507.11538v1](https://arxiv.org/html/2507.11538v1)). Split work across focused
  agents and each stays in its high-adherence zone — far more of the total actually gets followed.
- **Context drifts over long sessions.** The counter is a spec locked before code and TDD that
  freezes expected behaviour into tests — the session decays, the spec and tests do not. Fresh
  advisors re-read the spec, not the chat history.
- **Models are sycophantic.** The counter: advisors instructed to challenge — to push back, name the
  risks, and offer alternatives before a plan is approved.
- **Agents echo each other.** The counter: a blind round (independent ideas first), then a round that
  must reach genuine consensus.
- **Output volume feeds the drift.** The counter: an agent-communication protocol that forces
  concise, structured replies.

This is why Hercules recommends advisors at each phase — with deliberately opposing agendas, scaled to
complexity — and asks before running them. You stay in control.

---

## Philosophy

Software built from a clear specification is cheaper to build, easier to review, and harder to break
than software that emerged from a prompt. Hercules applies **spec-driven development**: the
specification is the single source of truth, written before a single line of code is produced,
validated against the requirements that prompted it, and updated whenever the code diverges from it.

The three-phase flow — Discover, Design, Build — is deliberately front-heavy. Discovering the real
problem (not the first stated one), and designing the technical and visual solution before
implementation, takes real time. That investment pays back in solutions that are well-reasoned,
security-reviewed, and aligned with what stakeholders actually need. Rework is expensive. Getting it
right the first time is cheap.

**Depth scales with complexity.** A trivial fix runs all three phases as a single lightweight pass. A
critical feature runs multi-round specialist debates, solution scoring, fresh-eyes reviews, and full
mutation-tested TDD. The same process, at the right intensity.

**Quality is enforced, not assumed.** Coverage gates, traceability checks, and cynical peer-review are
mandatory steps — not optional best-practices you might skip when under pressure. The AI is a capable
collaborator; the standards are yours to set.

---

## A note on quality

Hercules is a tool. Like any tool, it is only as good as the person using it.

AI amplifies intent. If you bring discipline, clear thinking, and high standards to every interaction,
Hercules reflects that back in the output. If you rush, skip the design, or approve requirements you
haven't actually read — Hercules will faithfully build exactly what you described, which may not be
what you needed.

**You are responsible for the quality of what you build.** Hercules makes it easier to do that well.

---

## Updating

Claude Code manages plugin updates from the marketplace. To pull the latest:

```
/plugin marketplace update hercules
```

If you use the optional launcher, upgrade it separately with `pipx upgrade hercules`.

Because distribution is the marketplace's job, there is no background process and no tokens to
manage: you update when you choose, and you can pin or roll back through Claude Code's plugin manager.

---

## Requirements

- **Claude Code** — the plugin runs entirely inside it.
- **Python ≥ 3.9** — only for the optional `hercules` launcher and for contributing (running the
  tests). The plugin itself needs no Python.

---

## Contributing

Read [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) first — it defines the rules for extending commands,
agents, and skills, plus how to run the tests.

1. Fork and create a branch (use hyphens, no slashes)
2. Add or edit files in `plugin/commands/`, `plugin/agents/`, or `plugin/skills/`
3. Test the plugin locally: add your checkout as a local marketplace —
   `/plugin marketplace add /path/to/your/checkout` — then `/plugin install hercules@hercules`, and
   `git checkout` the branch you want to try.
4. Run the suite: `pip install -e ".[dev]" && make test`
5. Open a PR — CI runs the full suite plus mutation testing and validates the plugin package.

For a local dev clone:

```bash
git clone https://github.com/mbienkowski/hercules.git
cd hercules
pip install -e ".[dev]"
```

All `.md` filenames must be **lowercase** — macOS is case-insensitive but Linux is not.

---

## License

MIT
