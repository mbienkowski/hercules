---
name: fusion-setup
description: Configure per-role models for the Build delegation split — an expensive primary that plans and reviews, a cheaper builder that executes. Use to set which model each role runs on where the host supports per-agent routing; on hosts without it, reports that per-role routing is unavailable and one model serves the whole flow.
---

# Fusion setup

Hercules splits Build into two roles: the **primary** (you, `hercules`) plans the delivery and reviews each diff, and the **builder** subagent applies the mechanical edits and runs verification. Routing them onto different models is what makes the split worth the overhead — the expensive model spends its tokens on judgment, the cheap one on mechanics.

This skill configures that routing. It writes nothing to the repository; it only adjusts the host's own agent configuration.

${target:opencode}
## OpenCode — set a model per role

On ${product} each agent's model is `provider/model-id` in the user `opencode.json` under `agent.<name>.model`. The plugin preserves a model you set here: its `config` hook deep-merges per agent, so your `agent.hercules.model` and `agent.builder.model` win while the plugin's `description`, `mode`, `prompt`, and `permission` still apply.

Interview the user for two models, then write them:

1. **Primary (`agent.hercules.model`)** — the judgment model. Ask which provider and model the user wants for planning and review (the expensive one). Confirm it is one their OpenCode install is authenticated for (`opencode auth login` / `/connect`).
2. **Builder (`agent.builder.model`)** — the execution model. Ask for a cheaper, faster model from any provider. Cross-vendor (a different family than the primary) gives you an independent second read on every diff for free.

Write both into the `opencode.json` the user points you at (project `.opencode/opencode.json`, or global `~/.config/opencode/opencode.json` if they prefer it follow them across repos). Merge into the existing `agent` block; never overwrite the file. Tell the user to restart OpenCode (config loads once at startup), then verify with `/models`.

The builder should stay cheaper and faster than the primary. If the user has one subscription (OpenCode Go/Zen, ChatGPT, or GitHub Copilot), pick the primary and builder from the models that subscription covers — there is no key to paste, the provider is already connected. The verification command the builder runs comes from the project's code-of-conduct, so whatever stack the repo uses, builder runs that stack's test command — the model choice is independent of the stack.
${target:claude}
## Claude Code — tiers are baked in

On ${product} per-role models ship with the plugin: the primary (`hercules`) runs on the high tier and the builder on the low tier, resolved from the plugin's `models` map. No setup step is needed for the routing to take effect — the split and the edit denial on the primary are already enforced.

If the user wants a different model for a role, the override paths are: copy the agent file from the plugin's `agents/` into `~/.claude/agents/` (or `.claude/agents/`) and set its `model:` frontmatter to the alias or full id (`opus`, `sonnet`, `haiku`, `fable`, or a full model id) — a user- or project-scoped agent overrides the plugin's for the same name. The builder runs the project's verification command (declared in its code-of-conduct), so the model choice is independent of the stack.
${target:default}
## ${product} — per-role routing is not available here

On ${product} the host does not support assigning a different model per agent, so the fusion setup step does not apply. One model serves the whole delivery flow: the primary and the builder run on the same model, and the edit denial is not enforced — the primary may edit directly, delegating to builder only when it keeps the context clean. No configuration is written. Tell the user the cost optimization is unavailable on this host and stop.
${target:end}
