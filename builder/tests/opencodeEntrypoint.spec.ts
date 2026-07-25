import { spawnSync } from 'node:child_process';
import { mkdtempSync, rmSync, unlinkSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { afterEach, describe, expect, it } from 'vitest';

import { buildTarget } from '../bin/cli.mjs';
import { srcStems } from '../../tests/support/buildTree';
import { repoRoot } from '../../tests/support/repo';

// Ported from tests/build/test_opencode_entrypoint.py (Spec 03 — the OpenCode plugin.js
// entry-point smoke, adapted from PR #11's node probe). Counts are derived from the roster/config,
// not magic literals. Frozen for spec-03-opencode-target.

const SRC = repoRoot;

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
    // After building the OpenCode target, the generated plugin loads in OpenCode and registers
    // every agent and command from the roster, with the default agent set to hercules — so a
    // user installing the OpenCode plugin gets the complete, correctly wired toolset, not a
    // partial or stale one.
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
    // If a file that must ship alongside the built OpenCode plugin (like the instructions file)
    // is missing, the plugin fails to start with a clear error instead of silently running with
    // incomplete instructions — this holds no matter how deep the plugin is installed on disk,
    // so a broken install is caught immediately rather than misbehaving quietly for the user.
    const out = build();
    unlinkSync(join(out, 'instructions.md'));
    const res = spawnSync('node', ['-e', `require(${JSON.stringify(join(out, 'plugin.js'))}).server()`], {
      encoding: 'utf-8',
    });
    expect(res.status).not.toBe(0);
    expect(res.stderr).toContain('missing asset');
  });
});
