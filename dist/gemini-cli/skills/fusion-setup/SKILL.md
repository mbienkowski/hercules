---
name: fusion-setup
description: Configure per-role models for the Build delegation split — an expensive primary that plans and reviews, a cheaper builder that executes. Use to set which model each role runs on where the host supports per-agent routing; on hosts without it, reports that per-role routing is unavailable and one model serves the whole flow.
---

# Fusion setup

Hercules splits Build into two roles: the **primary** (you, `hercules`) plans the delivery and reviews each diff, and the **builder** subagent applies the mechanical edits and runs verification. Routing them onto different models is what makes the split worth the overhead — the expensive model spends its tokens on judgment, the cheap one on mechanics.

This skill configures that routing. It writes nothing to the repository; it only adjusts the host's own agent configuration.

## Gemini CLI — per-role routing is not available here

On Gemini CLI the host does not support assigning a different model per agent, so the fusion setup step does not apply. One model serves the whole delivery flow: the primary and the builder run on the same model, and the edit denial is not enforced — the primary may edit directly, delegating to builder only when it keeps the context clean. No configuration is written. Tell the user the cost optimization is unavailable on this host and stop.
