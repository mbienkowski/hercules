import { type SpawnSyncReturns, spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { afterEach, describe, expect, it } from 'vitest';

import { repoRoot } from '../../../commons/support/repo';
import { which } from '../../../commons/support/which';

// Live Claude Code CLI smoke check: the built plugin installs into the real tool and registers its
// skills, agents, and hooks — which checking the shipped markdown/JSON cannot prove. Every `claude`
// subprocess runs in an isolated $HOME with auto-update and telemetry disabled.

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
 * A scratch $HOME so these tests never touch a real developer's ~/.claude config and never block
 * on the auto-updater or telemetry reaching out over the network.
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

// A skill counts only if its directory actually carries a SKILL.md, not merely exists.
function skillDirNames(): string[] {
  return readdirSync(join(PLUGIN, 'skills'), { withFileTypes: true })
    .filter((e) => e.isDirectory() && existsSync(join(PLUGIN, 'skills', e.name, 'SKILL.md')))
    .map((e) => e.name)
    .sort();
}

describe.skipIf(which('claude') === null)('claude code live-CLI smoke', () => {
  it('the built plugin manifest validates without errors', () => {
    // The built plugin must pass Claude Code's own manifest validator, so a malformed plugin.json
    // or frontmatter field is caught before a user ever installs a broken plugin.
    const env = isolatedClaudeHomeEnv();
    const res = run(env, 'plugin', 'validate', PLUGIN);
    expect(res.status, `stdout=${res.stdout}\nstderr=${res.stderr}`).toBe(0);
  }, TIMEOUT_MS + 5_000);

  it('the marketplace manifest validates without errors', () => {
    // The repo's marketplace.json — what `claude plugin marketplace add` reads — must validate on
    // its own; a bad source path would otherwise surface as a confusing install failure.
    const env = isolatedClaudeHomeEnv();
    const res = run(env, 'plugin', 'validate', repoRoot);
    expect(res.status, `stdout=${res.stdout}\nstderr=${res.stderr}`).toBe(0);
  }, TIMEOUT_MS + 5_000);

  it('the plugin installs from a local checkout and shows up enabled', () => {
    // Installing straight from a cloned checkout (CONTRIBUTING.md's flow: marketplace add, then
    // install) must leave the plugin listed and enabled, not silently no-op.
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
    // The installed plugin's inventory must list every skill, command, and agent on disk, counted
    // from the real files rather than a magic number. The CLI's "Skills" line counts SKILL.md files
    // and slash commands together — its own categorization, not a skills/ vs commands/ mismatch.
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
