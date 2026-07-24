import { type SpawnSyncReturns, spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { afterEach, describe, expect, it } from 'vitest';

import { repoRoot } from '../support/repo';
import { which } from '../support/which';

// Ported from tests/build/test_claude_code_smoke.py (Spec 06) — a live Claude Code CLI smoke
// check: does the built plugin actually install and register with the real tool, not just look
// correct on disk?
//
// Every other test in this suite checks that the shipped markdown/JSON is well-formed and says
// the right things. None of them prove the `claude` binary itself can install this plugin from a
// local checkout and see its skills, agents, and hooks — that's exactly the gap RELEASE.md's
// manual smoke checklist exists to cover today. These tests replace the structural half of that
// checklist (the "does it load and register" half) with a fast, free check: `claude plugin
// validate/marketplace/install/list/details` are documented as local, schema/config-only
// operations that spend no tokens and need no login. The behavioral half (does hercules answer in
// character, does a specialist actually spawn) still needs a live, paid session and stays a
// manual release-time check.
//
// Every `claude` subprocess call runs in an isolated $HOME (never the real developer's
// ~/.claude) with auto-update and telemetry explicitly disabled, so this can't hang on a
// background network call and can't pollute a maintainer's real plugin config when run locally.

const PLUGIN = join(repoRoot, 'dist', 'claude-code');
const MARKETPLACE_NAME = (
  JSON.parse(readFileSync(join(repoRoot, '.claude-plugin', 'marketplace.json'), 'utf-8')) as {
    name: string;
  }
).name;
const PLUGIN_ID = `hercules@${MARKETPLACE_NAME}`;

// No CI runner should ever be waiting more than this for a purely-local, no-network command.
const TIMEOUT_MS = 30_000;

const dirs: string[] = [];
afterEach(() => {
  while (dirs.length > 0) rmSync(dirs.pop() as string, { recursive: true, force: true });
}, 30_000);

/**
 * A scratch $HOME so these tests can never touch a real developer's ~/.claude config, and can
 * never block on the auto-updater or telemetry reaching out over the network.
 */
function isolatedClaudeHomeEnv(): NodeJS.ProcessEnv {
  const root = mkdtempSync(join(tmpdir(), 'hercules-claude-home-'));
  dirs.push(root);
  const home = join(root, 'home');
  mkdirSync(home);
  return {
    ...process.env,
    HOME: home,
    DISABLE_AUTOUPDATER: '1',
    CLAUDE_CODE_ENABLE_TELEMETRY: '0',
  };
}

function run(env: NodeJS.ProcessEnv, ...args: string[]): SpawnSyncReturns<string> {
  return spawnSync('claude', args, { cwd: repoRoot, env, timeout: TIMEOUT_MS, encoding: 'utf-8' });
}

function agentFileNames(): string[] {
  return readdirSync(join(PLUGIN, 'agents')).filter((name) => name.endsWith('.md')).sort();
}

function commandFileNames(): string[] {
  return readdirSync(join(PLUGIN, 'commands')).filter((name) => name.endsWith('.md')).sort();
}

// Mirrors tests/conftest.py's `skill_files` fixture: `(plugin_root / "skills").glob("*/SKILL.md")`
// — a skill counts only if its directory actually carries a SKILL.md, not merely exists.
function skillDirNames(): string[] {
  return readdirSync(join(PLUGIN, 'skills'), { withFileTypes: true })
    .filter((e) => e.isDirectory() && existsSync(join(PLUGIN, 'skills', e.name, 'SKILL.md')))
    .map((e) => e.name)
    .sort();
}

describe.skipIf(which('claude') === null)('claude code live-CLI smoke', () => {
  it('the built plugin manifest validates without errors', () => {
    // The built dist/claude-code plugin must pass Claude Code's own manifest validator — the same
    // check the plugin marketplace review pipeline runs on every submission — so a structural
    // mistake (a malformed plugin.json, a broken agent/command/skill frontmatter field) is caught
    // in seconds, before a user ever tries to install a broken plugin.
    const env = isolatedClaudeHomeEnv();
    const res = run(env, 'plugin', 'validate', PLUGIN);
    expect(res.status, `stdout=${res.stdout}\nstderr=${res.stderr}`).toBe(0);
  }, TIMEOUT_MS + 5_000);

  it('the marketplace manifest validates without errors', () => {
    // The repo's own marketplace.json — the file a user's `claude plugin marketplace add`
    // actually reads — must also pass validation on its own, independent of the plugin manifest
    // check above; a marketplace-level mistake (bad source path, malformed plugin entry) would
    // otherwise only surface as a confusing install failure for a real user.
    const env = isolatedClaudeHomeEnv();
    const res = run(env, 'plugin', 'validate', repoRoot);
    expect(res.status, `stdout=${res.stdout}\nstderr=${res.stderr}`).toBe(0);
  }, TIMEOUT_MS + 5_000);

  it('the plugin installs from a local checkout and shows up enabled', () => {
    // A developer installing straight from a cloned checkout (the exact flow documented in
    // CONTRIBUTING.md: marketplace add, then install) must end up with the plugin actually
    // listed and enabled -- not just a silent no-op -- since this local-install path is how
    // every contributor and CI smoke check exercises the plugin before it ever reaches a real
    // marketplace.
    const env = isolatedClaudeHomeEnv();

    const add = run(env, 'plugin', 'marketplace', 'add', './');
    expect(add.status, `stdout=${add.stdout}\nstderr=${add.stderr}`).toBe(0);

    const install = run(env, 'plugin', 'install', PLUGIN_ID);
    expect(install.status, `stdout=${install.stdout}\nstderr=${install.stderr}`).toBe(0);

    const listed = run(env, 'plugin', 'list', '--json');
    expect(listed.status, `stdout=${listed.stdout}\nstderr=${listed.stderr}`).toBe(0);
    const plugins = JSON.parse(listed.stdout) as Array<{ id: string; enabled: boolean }>;
    const entry = plugins.find((p) => p.id === PLUGIN_ID);
    expect(entry, `${PLUGIN_ID} not found in \`claude plugin list --json\`: ${JSON.stringify(plugins)}`).toBeDefined();
    expect((entry as { enabled: boolean }).enabled).toBe(true);
  }, TIMEOUT_MS * 3 + 5_000);

  it('the installed plugin declares its full component inventory', () => {
    // Once installed, Claude Code's own component inventory for this plugin must list every
    // skill, command, and agent actually shipped on disk -- not a stale or partial subset -- so
    // a user browsing `claude plugin details` sees the real toolset they're about to load into
    // every session, matching exactly what the repo ships (derived from the real file counts,
    // not a magic number that would silently go stale). Claude Code's own "Skills" inventory
    // line counts both SKILL.md files and slash commands together -- a real, confirmed
    // categorization detail of the CLI's own vocabulary, not a bug in this repo's skills/ vs
    // commands/ split.
    const env = isolatedClaudeHomeEnv();
    const skillFiles = skillDirNames();
    const agentFiles = agentFileNames();
    const commandFiles = commandFileNames();

    run(env, 'plugin', 'marketplace', 'add', './');
    run(env, 'plugin', 'install', PLUGIN_ID);

    const details = run(env, 'plugin', 'details', PLUGIN_ID);
    expect(details.status, `stdout=${details.stdout}\nstderr=${details.stderr}`).toBe(0);

    const skillsLine = details.stdout.split('\n').find((ln) => ln.trim().startsWith('Skills'));
    const agentsLine = details.stdout.split('\n').find((ln) => ln.trim().startsWith('Agents'));
    expect(skillsLine, 'no "Skills" line in `claude plugin details` output').toBeDefined();
    expect(agentsLine, 'no "Agents" line in `claude plugin details` output').toBeDefined();
    expect(skillsLine).toContain(`(${skillFiles.length + commandFiles.length})`);
    expect(agentsLine).toContain(`(${agentFiles.length})`);
    expect(agentsLine).toContain('hercules');
  }, TIMEOUT_MS * 4 + 5_000);
});
