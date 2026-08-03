import { type SpawnSyncReturns, spawnSync } from 'node:child_process';
import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

import { afterEach, describe, expect, it } from 'vitest';

import { repoRoot } from '../../support/repo';
import { tempWorkspace } from '../../support/tempWorkspace';
import { which } from '../../support/which';
import { scratchHome } from '../smokeHarness';

// Live Claude Code CLI smoke: the built plugin installs into the real tool and registers its skills,
// agents and hooks. Every `claude` subprocess runs in an isolated $HOME, no auto-update, no telemetry.

const PLUGIN = join(repoRoot, 'dist', 'claude-code');
const MARKETPLACE_NAME = (
  JSON.parse(readFileSync(join(repoRoot, '.claude-plugin', 'marketplace.json'), 'utf-8')) as {
    name: string;
  }
).name;
const PLUGIN_ID = `hercules@${MARKETPLACE_NAME}`;

// No CI runner should ever be waiting more than this for a purely-local, no-network command.
const TIMEOUT_MS = 30_000;

const workspace = tempWorkspace();
afterEach(workspace.cleanup, 30_000);

/** A scratch $HOME so these tests never touch a real ~/.claude config and never block on the network. */
function isolatedClaudeHomeEnv(): NodeJS.ProcessEnv {
  const { root, env } = scratchHome(() => ({
    DISABLE_AUTOUPDATER: '1',
    CLAUDE_CODE_ENABLE_TELEMETRY: '0',
  }));
  workspace.track(root);
  return env;
}

function run(env: NodeJS.ProcessEnv, ...args: string[]): SpawnSyncReturns<string> {
  return spawnSync('claude', args, { cwd: repoRoot, env, timeout: TIMEOUT_MS, encoding: 'utf-8' });
}

/** The `.md` files the built plugin ships under `dir` — the inventory, counted from real files. */
function mdFileNames(dir: string): string[] {
  return readdirSync(join(PLUGIN, dir)).filter((name) => name.endsWith('.md')).sort();
}

// A skill counts only if its directory actually carries a SKILL.md, not merely exists.
function skillDirNames(): string[] {
  return readdirSync(join(PLUGIN, 'skills'), { withFileTypes: true })
    .filter((e) => e.isDirectory() && existsSync(join(PLUGIN, 'skills', e.name, 'SKILL.md')))
    .map((e) => e.name)
    .sort();
}

describe.skipIf(which('claude') === null)('claude code live-CLI smoke', () => {
  // Claude Code's own validator is the only thing that rejects a malformed plugin.json before a user
  // installs it, and marketplace.json must validate too — a bad source path there names nothing later.
  it.each([['the built plugin', PLUGIN], ['the marketplace', repoRoot]])(
    '%s manifest validates without errors',
    (_what, path) => {
      const res = run(isolatedClaudeHomeEnv(), 'plugin', 'validate', path);
      expect(res.status, `stdout=${res.stdout}\nstderr=${res.stderr}`).toBe(0);
    },
    TIMEOUT_MS + 5_000,
  );

  it('the plugin installs from a local checkout and shows up enabled', () => {
    // Installing from a cloned checkout (CONTRIBUTING.md's flow) must leave it listed and enabled.
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
    // Counted from the real files, never a magic number. The CLI's "Skills" line counts SKILL.md
    // files and slash commands together — its own categorization, not a mismatch.
    const env = isolatedClaudeHomeEnv();
    const skillFiles = skillDirNames();
    const agentFiles = mdFileNames('agents');
    const commandFiles = mdFileNames('commands');

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
