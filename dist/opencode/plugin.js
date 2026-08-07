// The OpenCode entry point (the name is fixed — OpenCode loads `plugin.js` from the package root).
// Hand-written and static: agent/command bodies are READ from their shipped files at run time, so
// editing one changes what this plugin serves. Generic file handling lives in `read-file.js`.

const path = require("path");
const fs = require("fs");
const { spawnSync } = require("child_process");
const { readFile, frontmatter, stripFrontmatter, listMarkdown } = require("./read-file.js");

// This file lives at the root of dist/opencode/; assets are its siblings.
const PLUGIN_ROOT = path.resolve(__dirname);
for (const asset of ["instructions.md", "protocols/a2a-communication-protocol.md", "protocols/debate-consensus-protocol.md", "protocols/workflow-protocol.md", "skills"]) {
  if (!fs.existsSync(path.join(PLUGIN_ROOT, asset))) {
    throw new Error("hercules opencode plugin: missing asset " + asset);
  }
}

// Every other host names its own plugin directory in an environment variable, and shipped prose
// invokes a tool through that variable. OpenCode names none, so this plugin publishes one — the
// shell an agent runs is a child of this process and inherits it.
//
// Why it matters more than tidiness: without an absolute prefix the invocation resolves against
// the working directory, which IS the repository being worked on.
// Any repository shipping a file at that path would have it executed with the user's authority. The
// prose now carries the HERCULES_PLUGIN_ROOT expansion, so an unset variable yields the absolute
// `/tools/…` and fails loudly instead of silently running whatever the checkout contains.
process.env.HERCULES_PLUGIN_ROOT = PLUGIN_ROOT;

const LEAD = "hercules";
const COMMAND_PREFIX = "hercules:";

/** `{name: {description, mode, prompt}}` for every agent shipped beside this file. */
function agents() {
  const out = {};
  for (const stem of listMarkdown(PLUGIN_ROOT, "agents")) {
    const text = readFile(PLUGIN_ROOT, path.join("agents", stem + ".md"));
    const fields = frontmatter(text);
    out[stem] = {
      description: fields.description,
      mode: fields.mode || "subagent",
      prompt: stripFrontmatter(text),
    };
  }
  return out;
}

/** `{"hercules:<stem>": {description, agent, template}}` for every shipped command. */
function commands() {
  const out = {};
  for (const stem of listMarkdown(PLUGIN_ROOT, "commands")) {
    const text = readFile(PLUGIN_ROOT, path.join("commands", stem + ".md"));
    const fields = frontmatter(text);
    out[COMMAND_PREFIX + stem] = {
      description: fields.description,
      agent: fields.agent || LEAD,
      template: stripFrontmatter(text),
    };
  }
  return out;
}

// Hard write-gate (G1). Reuses the CANONICAL Python guard shipped at hooks/frozen_tests.py — the
// same code Claude Code runs as a PreToolUse hook — so all three ecosystems share one source of
// truth. `tool.execute.before` runs before the real Write/Edit executes; THROWING aborts it, a true
// pre-write veto matching Claude's exit-2 gate. Fails OPEN (allow) if python3 is absent, the guard
// file is missing, or anything errors — so it is a progressive enhancement that never bricks an edit.
// OpenCode tool ids map onto the Claude tool names the guard expects.
const WRITE_TOOLS = { edit: "Edit", write: "Write", apply_patch: "MultiEdit", patch: "MultiEdit" };
function makeWriteGate(projectDir) {
  const guard = path.join(PLUGIN_ROOT, "hooks", "frozen_tests.py");
  return (input, output) => {
    let reason = null;
    try {
      const claudeTool = WRITE_TOOLS[input && input.tool];
      if (!claudeTool) return;
      const args = (output && output.args) || {};
      const paths = [];
      const direct = args.filePath || args.file_path;
      if (direct) paths.push(direct);
      if (typeof args.patchText === "string") {
        // apply_patch is multi-file: EVERY "*** ... File: <path>" hunk header is a write target, so
        // check them all — a frozen file in a later hunk must still block (checking only the first
        // let an innocuous-first, frozen-second patch slip the veto).
        for (const line of args.patchText.split("\n")) {
          const idx = line.indexOf(" File: ");
          if (idx !== -1 && line.indexOf("*** ") === 0) paths.push(line.slice(idx + 7).trim());
        }
      }
      if (!paths.length || !fs.existsSync(guard)) return;
      for (const filePath of paths) {
        const payload = JSON.stringify({ tool_name: claudeTool, tool_input: { file_path: filePath }, cwd: projectDir });
        const r = spawnSync("python3", [guard], { input: payload, encoding: "utf8", timeout: 10000 });
        if (r && r.status === 2) { reason = (r.stderr || "").trim() || "edit to a frozen test file denied during build"; break; }
      }
    } catch (e) {
      return; // fail open: python3 missing / spawn error must never brick an unrelated edit
    }
    if (reason) throw new Error("hercules write-gate — " + reason);
  };
}

// A bare `module.exports = <function>` breaks Bun's real loader (it spreads the function's own
// properties into the namespace and throws on the first non-export value), so this exports the
// documented `PluginModule` shape instead; `id` is required in practice. Diagnosis: issue #15.
module.exports = {
  id: "hercules",
  server: async (input) => {
    const projectDir = (input && input.directory) || process.cwd();
    return {
      config: (cfg) => {
        cfg.default_agent = LEAD;
        // Fusion delegation needs the primary to spawn builder, and builder to spawn a read-only
        // helper (explore) for lookups — a depth-2 chain. Preserve a user's larger value; only raise
        // the floor. OpenCode 1.18.2+ defaults to 1, which would block that nested helper call.
        cfg.subagent_depth = Math.max(cfg.subagent_depth ?? 1, 2);
        // Persona + protocols are always-loaded so their `§`/path references resolve
        // (OpenCode has no ${CLAUDE_PLUGIN_ROOT}; the plugin injects absolute paths here).
        cfg.instructions = [
          ...(cfg.instructions || []),
          path.join(PLUGIN_ROOT, "instructions.md"),
          path.join(PLUGIN_ROOT, "protocols/a2a-communication-protocol.md"),
          path.join(PLUGIN_ROOT, "protocols/debate-consensus-protocol.md"),
          path.join(PLUGIN_ROOT, "protocols/workflow-protocol.md"),
        ];
        cfg.skills = cfg.skills || {};
        cfg.skills.paths = [...(cfg.skills.paths || []), path.join(PLUGIN_ROOT, "skills")];
        // Per-agent merge: the plugin's description/mode/prompt win, and the Fusion `permission`
        // (edit denial + verification-only bash + bounded task graph on the primary; edit/bash allow
        // on the builder) is injected by name. A user-set per-agent `model` (written by the
        // fusion-setup skill) survives because the plugin entry carries no `model` key — the spread
        // keeps the existing `model` while the plugin's other fields override it.
        cfg.agent = cfg.agent || {};
        const shipped = agents();
        const taskAllow = { "*": "deny" };
        for (const name of Object.keys(shipped)) {
          if (name !== LEAD) taskAllow[name] = "allow";
        }
        const FUSION_PERMISSIONS = {
          // Primary plans and reviews; edits are denied so delegation to builder is the only path to
          // a changed file. Bash stays, narrowed to read-only verification (last-match-wins, so the
          // catch-all `ask` prompts for anything unlisted — a non-JS stack's `pytest` prompts rather
          // than bricks, while JS verification commands run automatically).
          [LEAD]: {
            edit: "deny",
            bash: {
              "*": "ask",
              "git diff*": "allow", "git status*": "allow", "git log*": "allow", "git show*": "allow",
              "npm test*": "allow", "npm run lint*": "allow", "npm run build*": "allow",
              "npx vitest run*": "allow", "npx tsc --noEmit*": "allow",
            },
            task: taskAllow,
          },
          // Builder executes edits and commands; it may spawn only the read-only explore helper.
          builder: { edit: "allow", bash: "allow", task: { "*": "deny", explore: "allow" } },
        };
        for (const [name, entry] of Object.entries(shipped)) {
          const existing = cfg.agent[name] || {};
          const permission = FUSION_PERMISSIONS[name];
          cfg.agent[name] = { ...existing, ...entry, ...(permission ? { permission } : {}) };
        }
        cfg.command = { ...(cfg.command || {}), ...commands() };
      },
      "tool.execute.before": makeWriteGate(projectDir),
    };
  },
};
