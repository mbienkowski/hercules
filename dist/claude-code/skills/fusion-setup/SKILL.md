---
name: fusion-setup
description: Configure per-role models for the Build delegation split — an expensive primary that plans and reviews, a cheaper builder that executes. Use to set which model each role runs on where the host supports per-agent routing; on hosts without it, reports that per-role routing is unavailable and one model serves the whole flow.
---

# Fusion setup

Hercules splits Build into two roles: the **primary** (you, `hercules`) plans the delivery and reviews each diff, and the **builder** subagent applies the mechanical edits and runs verification. Routing them onto different models is what makes the split worth the overhead — the expensive model spends its tokens on judgment, the cheap one on mechanics.

This skill configures that routing. It writes nothing to the repository; it only adjusts the host's own agent configuration.

## Claude Code — tiers are baked in

On Claude Code per-role models ship with the plugin: the primary (`hercules`) runs on the high tier and the builder on the low tier, resolved from the plugin's `models` map. No setup step is needed for the routing to take effect — the split and the edit denial on the primary are already enforced.

If the user wants a different model for a role, the override paths are: copy the agent file from the plugin's `agents/` into `~/.claude/agents/` (or `.claude/agents/`) and set its `model:` frontmatter to the alias or full id (`opus`, `sonnet`, `haiku`, `fable`, or a full model id) — a user- or project-scoped agent overrides the plugin's for the same name. The builder runs the project's verification command (declared in its code-of-conduct), so the model choice is independent of the stack.
