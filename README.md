# Hercules

**Hercules is a Claude Code plugin that brings spec-driven discipline to AI-assisted delivery.**
Discover before you design. Design before you build. No shortcuts.

**Who it's for:** engineers who want their AI to follow a disciplined process — *and* non-developers
(QA, product) who want to turn messy notes into clear, reviewable requirements.

> New to the terms? *Plugin* = an add-on you install into Claude Code. *Marketplace* = a source (here,
> a GitHub repo) you add plugins from. *Agent* = a specialist persona Claude can consult. *Business
> requirements* = the permanent, plain-language "what & why" doc. *Spec* = the temporary technical
> blueprint, deleted once it's built.

---

## Install

**Prerequisite:** Hercules runs *inside* [Claude Code](https://code.claude.com) — install Claude Code
first. The plugin itself needs **no Python**.

Then, three steps:

**1 — Add the marketplace and install the plugin.** In Claude Code (CLI or Desktop), type:

```
/plugin marketplace add mbienkowski/hercules
/plugin install hercules@mbienkowski
```

`hercules@mbienkowski` is `plugin@marketplace` (the plugin named `hercules`, from `mbienkowski`'s
marketplace). The `/plugin` and `/hercules:*` commands are typed **inside Claude Code**, not in a terminal.

**2 — Verify.** Run `/help` (or `/plugin`) and confirm the `/hercules:` commands appear. If they don't,
the plugin is installed-but-disabled — enable it from the `/plugin` screen.

**3 — Start.** There's nothing to configure — just run:

```
/hercules:workflow
```

When enabled, Hercules becomes your **default agent** — that's why you can also just say
*"Hercules, where do I start?"*. This means Hercules is active for every Claude Code session where
this plugin is enabled — it does not add instructions to Claude sessions where the plugin is off.
The `/hercules:*` commands run the phases.

### Claude Code Desktop
Same flow: type the `/plugin` commands in the chat, **or** use the in-app plugin browser (the `+` near
the prompt → **Plugins** → add marketplace / install). It is *not* a "Settings → Plugins" page.

### For a team (or CI) — no typing
Declare it once in `settings.json` (user `~/.claude/settings.json`, project `.claude/settings.json`, or
local) so everyone gets Hercules on clone:

```json
{
  "extraKnownMarketplaces": {
    "hercules": { "source": { "source": "github", "repo": "mbienkowski/hercules" } }
  },
  "enabledPlugins": ["hercules@mbienkowski"]
}
```

Use the **project** scope to standardize a whole repo; consider an org fork + a pinned version for
governance. This file merges with any existing Claude Code settings — it does not replace them.

| Your situation | Use |
|---|---|
| Just want the plugin (most people) | **Marketplace** — the steps above |
| A whole team / CI | **`settings.json`** (`extraKnownMarketplaces` + `enabledPlugins`) |

---

## Quickstart

The fastest way to start is the guided workflow — Hercules walks you through every phase:

```
/hercules:workflow
```

Or run each phase on its own. Outputs are dated Markdown files (`YYYY-MM-DD` = today's date; `desc` = a
short slug; `NN` = the spec number):

| Command | Phase | WHAT / HOW / SHIP | What it produces |
|---|---|---|---|
| `/hercules:discover` | Discover — **WHAT** | Pin the real need | a `*-business-requirements.md` (the permanent "what & why") |
| `/hercules:design` | Design — **HOW** | Turn it into a spec | one or more `*-spec-NN-*.md` build blueprints |
| `/hercules:build` | Build — **SHIP** | Write and verify code | working code + tests (specs deleted on merge to main) |

Each feature is its own workflow run — start a new one any time with `/hercules:workflow` and a feature
description. Your `docs/` folder accumulates business-requirements files over time; specs are temporary
and deleted on merge to main (when the feature is accepted into the main codebase). Multiple features
can be in-flight simultaneously — each gets its own spec files with unique sequential numbers.

---

## Your first session

**One-time setup per repo:** before your first feature, run the onboarding skill once. It scans your
repo, infers your stack and quality bar, and writes a `code-of-conduct.md` that all Hercules agents
read. Without it, Hercules falls back to generic defaults. Just say:

*"Hercules, set up this project"* — or explicitly: `code-of-conduct-generator`

It asks ≤5 questions when it can't infer something; otherwise it's silent. Once it exists, you don't
run it again unless your standards change.

Then type `/hercules:workflow`. Discovery is where the real work happens — bring everything you have:
PRDs, ADRs, Figma links, QA scenarios, API contracts, Slack threads. The more context you bring, the
better. Hercules will always paraphrase what it understood before writing — correct it if anything's
off. Your first session ends with a requirements document saved to `docs/`.

At each phase, Hercules drafts the document and waits for you to say `approved` before saving it.
Saying `approved` tells Hercules to write the draft to `docs/` and advance to the next phase — it
does not lock the document; you can revisit it any time. That's the whole loop. Repeat for every
feature.

### What that looks like

```
You:       /hercules:workflow — we need password reset for the web app.
Hercules:  A few gaps before I write this up:
           • who can trigger a reset — any user, or only verified emails?
           • token lifetime?
           • is email delivery in scope, or assumed?
You:       Any user with a registered email; 30-minute token; email delivery is out of scope.
Hercules:  Here's the draft (business language, no code). Review it, then say `approved`:
```
```markdown
# Business Requirements: password-reset
## Goal
Let a user who forgot their password regain access without contacting support.
## Users
Registered users with a verified email address.
## Scope
In: request a reset, receive a one-time link, set a new password.
Out: the email-delivery service itself (already exists).
## Success criteria
A reset link works once, expires after 30 minutes, and never reveals whether an email is registered.
```

---

## Where your delivery docs live

Hercules keeps every requirement and spec in **one place** your team can version and review like code.
By default that's `docs/` in the directory where you launch Claude. To change it, name the directory (or
a dedicated docs repo) once in your project's **`code-of-conduct.md`** — a *per-project, lowercase*
config file Hercules reads at runtime. (Not to be confused with this repo's `CODE_OF_CONDUCT.md`, which
is the contributor guide.)

A feature that spans several services? Tell Hercules the local path to each — it asks once and remembers
them on **your machine only**, in `~/.hercules/hercules-config.json` (auto-written; it stores only
local filesystem paths — no credentials, tokens, or telemetry). Nothing about where your repos live
is written into the docs themselves.

---

## How it works

Every feature runs all three phases — the *process* is constant; only the *depth* scales.

1. **Discover — WHAT** (the heaviest phase) — pins the real need, who benefits, what's in/out of
   scope, and what "done" means. Output: a permanent `*-business-requirements.md`, in plain business
   language. On a large feature, Discover may span multiple sessions; the draft is saved and picked up
   where you left off.
2. **Design — HOW** — turns requirements into one or more self-contained **specs**, challenged by
   specialist advisors before any code. Output: `*-spec-NN-*.md` (temporary).
3. **Build — SHIP** — TDD (write the failing test first), then the implementation, then review.
   Output: code + tests. The specs are deleted on merge to main (`git rm`).

**Two documents, two lifecycles.** Business-requirements are **long-lived** — committed forever, in
business language, the shareable record of what a feature is *for*. Specs are **per-development** — once
merged to main, they're deleted, because the code, its tests, and git history become the source of truth.

**Complexity scoring (so depth isn't guesswork).** In Discover, Hercules scores the feature on
*effort* and *blast-radius* (how many users or systems a bug could harm) and takes the higher of the two.

| Tier | Effort signals | Blast-radius signals | Advisors |
|---|---|---|---|
| trivial | typo, config tweak | no user-visible change | 0 |
| low | single-service change | one bounded flow affected | 0–2 |
| medium | cross-service or new API | multiple flows affected | 1–3 |
| high | auth, payments, migration | data at risk, deletion, prod config | 2–4 |
| critical | multi-service migration | user data, security primitives, money | 3–6 |

You see the score and can override it. A single substantiated dissent escalates the tier.

**Quality has numbers, not adjectives.** Build gates on **≥90% branch coverage** and a **≥90%
mutation kill-rate** (mutation testing checks that your tests actually catch bugs), and a requirement
ships only when a **named test** asserts it. These are mandatory steps, not best-practices you skip
under pressure.

---

## Philosophy

AI removed the safety net. Without a clear requirement, quality doesn't degrade gracefully — it
collapses. Hercules is front-heavy on purpose: the time invested in Discover and Design pays back in
less rework, fewer misbuilt features, and code that does what was actually needed.

Bring discipline and it amplifies it. Rush the process and it will faithfully build what you described
— which may not be what you needed. **You own the quality of what you build;** Hercules makes it
easier to do that well.

---

## Updating

Updates are **manual and in your control** — there's no background process and nothing to manage. Pull
the latest from the marketplace:

```
/plugin marketplace update mbienkowski
```

You can pin or roll back through Claude Code's plugin manager.

---

## Uninstalling

To remove the plugin and its marketplace entry:

```
/plugin uninstall hercules@mbienkowski
/plugin marketplace remove mbienkowski
```

---

## Requirements

- **Claude Code** — the plugin runs entirely inside it.
- **Python ≥ 3.9** — only for contributing (running the tests). The plugin itself needs no Python.

---

## Contributing

Read [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) first — it defines the rules for extending commands,
agents, and skills, plus how to run the tests.

1. Fork and create a branch (use hyphens, no slashes)
2. Add or edit files in `plugin/commands/`, `plugin/agents/`, or `plugin/skills/`
3. Test the plugin locally: add **your local checkout** as a marketplace first —
   `/plugin marketplace add /path/to/your/checkout` — then `/plugin install hercules@mbienkowski`, and
   `git checkout` the branch you want to test. (Don't install from the public marketplace first — you'd
   test the released version, not your changes.)
4. Run the suite: `pip install -e ".[dev]" && make test`
5. Open a PR — CI runs the full suite plus mutation testing and validates the plugin package. Commit
   messages follow Conventional Commits (`feat:`/`fix:`/`feat!:`), which drive the version on release.

For a local dev clone:

```bash
git clone https://github.com/mbienkowski/hercules.git
cd hercules
pip install -e ".[dev]"
```

All `.md` filenames must be **lowercase** — macOS is case-insensitive but Linux is not.

---

## Plugin permissions

Hercules is a set of Markdown files — commands, agents, and skills — interpreted by Claude Code.
It has no executable code of its own. What it can do is exactly what Claude Code can do in your session:

- **Project files** — reads your project files to understand context; writes to `docs/` (or wherever
  `code-of-conduct.md` points). Nothing is written outside directories Claude Code already has access to.
- **`~/.hercules/`** — full read/write/create access to this directory. `hercules-config.json` is the
  only file stored here: local filesystem paths only (no credentials, no tokens, no telemetry, no code
  snippets).
- **Shell** — only during Build, when tests need to run. Claude Code executes the command; Hercules
  issues no shell commands independently.
- **Network** — none. All model calls go through your existing Claude Code session and API key.
  Hercules makes no direct API calls and opens no separate network channel.

You can audit the full plugin source in the `plugin/` directory of this repository.

---

## Why sub-agents?

A single model in a single pass has predictable failure modes. Specialist advisors counter each — and
Hercules always **asks before running them** (they cost tokens and time, so it scales them to
complexity and adds none for trivial work).

- **Agents echo each other, and models are sycophantic.** Research shows AI is 49% more likely than
  humans to affirm users even when it knows the right answer, and agrees with wrong answers 51% of the
  time ([Science 2026](https://www.science.org/doi/10.1126/science.adp9289)). The *structural* counter
  is a **blind round**: each advisor forms its position independently, before seeing the others — then a
  consensus round, so agreement has to be earned, not echoed. Advisors are briefed with deliberately
  opposing agendas (e.g. a Cynical Reviewer vs. a Simplicity Advocate), because good decisions come
  from tension.
- **Multi-agent systems can still echo each other.** In 2,500+ simulations, agents conformed to the
  majority in up to 83% of cases — driven by numbers, not reasoning. Opposing agendas are the
  structural fix, not just a nice-to-have.
- **One agent can only follow so many instructions.** At 150 instructions the best model followed ~96%;
  at 500, ~68.9% — the drop is non-linear and invisible (no error, no warning)
  ([arxiv.org/html/2507.11538v1](https://arxiv.org/html/2507.11538v1)). Splitting work across focused
  advisors keeps each one in its high-adherence range.
- **Context drifts over long sessions.** The counter: a spec locked before code, and TDD that freezes
  expected behaviour into tests. Fresh advisors re-read the spec, not the chat history.
- **Output volume feeds the drift.** The counter: a terse agent-communication protocol — structured,
  low-noise replies.

You stay in control: advisors are a recommendation you approve, never automatic.

---

## License

MIT
