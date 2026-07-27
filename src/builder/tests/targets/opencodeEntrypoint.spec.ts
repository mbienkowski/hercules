import { spawnSync } from 'node:child_process';
import { mkdtempSync, rmSync, unlinkSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { afterEach, describe, expect, it } from 'vitest';

import { buildTarget } from '../../bin/cli.mjs';
import { srcStems } from '../../../commons/support/buildTree';
import { repoRoot } from '../../../commons/support/repo';

// Smoke test for the built OpenCode plugin.js entry point. Expected agent and command counts are
// derived from the roster and config, never magic literals.

const SRC = join(repoRoot, 'src');

const dirs: string[] = [];

function build(): string {
  const root = mkdtempSync(join(tmpdir(), 'hercules-opencode-entrypoint-'));
  dirs.push(root);
  const out = join(root, 'opencode');
  buildTarget('opencode', out);
  return out;
}

afterEach(() => {
  while (dirs.length > 0) rmSync(dirs.pop() as string, { recursive: true, force: true });
});

describe('the OpenCode plugin.js entry point', () => {
  it('starts up and registers every agent and command from the roster, defaulting to hercules', () => {
    // A user installing the plugin must get the complete, correctly wired toolset — every agent
    // and command from the roster — rather than a partial one.
    const out = build();
    const nAgents = srcStems(join(SRC, 'content'), 'agents').length;
    const nCommands = srcStems(join(SRC, 'content'), 'commands').length;

    const probe = `
    const p = require(${JSON.stringify(join(out, 'plugin.js'))});
    p.server().then(r => { const cfg = {}; r.config(cfg);
      console.log(JSON.stringify({
        default_agent: cfg.default_agent,
        instructions: cfg.instructions.length,
        skills: cfg.skills.paths.length,
        agents: Object.keys(cfg.agent).length,
        commands: Object.keys(cfg.command).length,
      }));
    }).catch(e => { console.error(String(e)); process.exit(1); });
    `;
    const res = spawnSync('node', ['-e', probe], { encoding: 'utf-8' });
    expect(res.status, res.stderr).toBe(0);
    const lines = res.stdout.trim().split('\n');
    const emitted = JSON.parse(lines[lines.length - 1] as string) as {
      default_agent: string; instructions: number; skills: number; agents: number; commands: number;
    };
    expect(emitted.default_agent).toBe('hercules');
    expect(emitted.instructions).toBeGreaterThanOrEqual(1);
    expect(emitted.skills).toBeGreaterThanOrEqual(1);
    expect(emitted.agents).toBe(nAgents);
    expect(emitted.commands).toBe(nCommands);
  });

  it('refuses to start if a bundled asset is missing, with a clear error', () => {
    // A broken install must surface immediately: a missing bundled asset aborts startup rather
    // than letting the plugin run quietly on incomplete instructions.
    const out = build();
    unlinkSync(join(out, 'instructions.md'));
    const res = spawnSync('node', ['-e', `require(${JSON.stringify(join(out, 'plugin.js'))}).server()`], {
      encoding: 'utf-8',
    });
    expect(res.status).not.toBe(0);
    expect(res.stderr).toContain('missing asset');
  });
});
