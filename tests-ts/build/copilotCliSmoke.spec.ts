import { spawnSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { afterEach, describe, expect, it } from 'vitest';

import { buildTarget } from '../../scripts-ts/bin/cli.mjs';
import { srcStems } from '../support/buildTree';
import { repoRoot } from '../support/repo';
import { which } from '../support/which';

// Ported from tests/build/test_copilot_cli_smoke.py — a live Copilot CLI smoke check: does the
// real `copilot` binary run, and is the built plugin tree structurally loadable?
//
// The ALWAYS-ON checks are structural (never skip): re-validate the built `dist/copilot-cli`
// plugin against the plugin contract (kebab manifest name, per-type frontmatter, `.agent.md`
// agents, `.prompt.md` commands, the `preToolUse` write-gate, the reviewer subagent). The
// genuinely live check (the real `copilot` binary executes) is opt-in — it SKIPs (never fails)
// when the CLI is not installed, so the fork-safe gate stays green.

const SRC_CONTENT = join(repoRoot, 'src', 'content');
const TIMEOUT_MS = 60_000;

function srcSkills(): string[] {
  return readdirSync(join(SRC_CONTENT, 'skills'), { withFileTypes: true })
    .filter((e) => e.isDirectory())
    .map((e) => e.name)
    .sort();
}

function frontmatterText(path: string): string {
  const text = readFileSync(path, 'utf-8');
  expect(text.startsWith('---\n'), `${path} lacks frontmatter`).toBe(true);
  return text;
}

const dirs: string[] = [];
afterEach(() => {
  while (dirs.length > 0) rmSync(dirs.pop() as string, { recursive: true, force: true });
}, 30_000);

function tmpDir(): string {
  const root = mkdtempSync(join(tmpdir(), 'hercules-copilot-smoke-'));
  dirs.push(root);
  return root;
}

it('the built plugin is well formed', () => {
  // The freshly built plugin must satisfy the Copilot plugin contract — this is the load-bearing,
  // auth-free, never-skipping guard (a malformed agent/command loads as absent with no error).
  const out = join(tmpDir(), 'copilot-cli');
  buildTarget('copilot-cli', out);

  const manifest = JSON.parse(readFileSync(join(out, 'plugin.json'), 'utf-8')) as { name: string };
  expect(manifest.name).toMatch(/^[a-z0-9]([a-z0-9-]*[a-z0-9])?$/);

  for (const name of readdirSync(join(out, 'agents')).filter((n) => n.endsWith('.agent.md'))) {
    const text = frontmatterText(join(out, 'agents', name));
    expect(text).toContain('name:');
    expect(text).toContain('description:');
  }
  for (const name of readdirSync(join(out, 'commands')).filter((n) => n.endsWith('.prompt.md'))) {
    expect(frontmatterText(join(out, 'commands', name))).toContain('description:');
  }
  expect(readFileSync(join(out, 'AGENTS.md'), 'utf-8'), 'the persona instructions must ship').toBeTruthy();
  expect(
    readFileSync(join(out, 'agents', 'cynical-reviewer.agent.md'), 'utf-8'),
    'the independent reviewer must ship',
  ).toBeTruthy();
  const hooks = JSON.parse(readFileSync(join(out, 'hooks', 'hooks.json'), 'utf-8')) as {
    hooks: { preToolUse: unknown };
  };
  expect(hooks.hooks.preToolUse, 'the preToolUse write-gate must be wired').toBeTruthy();
});

it('ships the full component inventory', () => {
  // The built plugin must carry the WHOLE inventory — all 5 commands (as `.prompt.md`), every
  // advisor agent (as `.agent.md`), and every skill — so nothing silently fails to load. Names
  // derive from src/content (the single source of truth).
  const out = join(tmpDir(), 'copilot-cli');
  buildTarget('copilot-cli', out);
  for (const name of srcStems(SRC_CONTENT, 'commands')) {
    expect(readdirSync(join(out, 'commands')), `copilot missing command ${name}`).toContain(`${name}.prompt.md`);
  }
  for (const name of srcStems(SRC_CONTENT, 'agents')) {
    expect(readdirSync(join(out, 'agents')), `copilot missing agent ${name}`).toContain(`${name}.agent.md`);
  }
  for (const skill of srcSkills()) {
    expect(readdirSync(join(out, 'skills', skill)), `copilot missing skill ${skill}`).toContain('SKILL.md');
  }
  expect(readFileSync(join(out, 'AGENTS.md'), 'utf-8'), 'the AGENTS.md persona instructions must ship').toBeTruthy();
});

describe.skipIf(which('copilot') === null)('live copilot binary', () => {
  it('the real copilot binary runs', () => {
    // With the CLI installed, the real `copilot --version` must exit 0 (a stub-on-PATH would not).
    const res = spawnSync('copilot', ['--version'], { encoding: 'utf-8', timeout: TIMEOUT_MS });
    expect(res.status, `copilot --version failed: ${res.stdout}\n${res.stderr}`).toBe(0);
  }, TIMEOUT_MS + 5_000);

  it('the plugin installs into the real cli and is listed', (ctx) => {
    // Add the repo's local marketplace, install the plugin, then confirm the real `copilot` lists
    // it — a genuine install + load check beyond `--version`. Copilot plugin management may
    // require a login, so it SKIPs (never fails the leg) on any error/timeout; the structural
    // inventory above runs every commit regardless. If install+list DO succeed, the plugin MUST
    // be listed (a real bug otherwise).
    const home = join(tmpDir(), 'home');
    mkdirSync(home);
    const env = { ...process.env, HOME: home };

    const add = spawnSync('copilot', ['plugin', 'marketplace', 'add', repoRoot], {
      encoding: 'utf-8', timeout: TIMEOUT_MS, env,
    });
    if (add.error || add.status !== 0) {
      ctx.skip(`copilot marketplace add unavailable here: ${((add.stderr || add.stdout) ?? '').slice(0, 300)}`);
    }
    const inst = spawnSync('copilot', ['plugin', 'install', 'hercules@hercules'], {
      encoding: 'utf-8', timeout: TIMEOUT_MS, env,
    });
    if (inst.error || inst.status !== 0) {
      ctx.skip(`copilot plugin install unavailable here: ${((inst.stderr || inst.stdout) ?? '').slice(0, 300)}`);
    }
    const listed = spawnSync('copilot', ['plugin', 'list'], { encoding: 'utf-8', timeout: TIMEOUT_MS, env });
    if (listed.error) {
      ctx.skip(`copilot plugin management could not run here: ${listed.error.message}`);
    }
    expect(listed.status, `\`copilot plugin list\` failed: ${listed.stdout}\n${listed.stderr}`).toBe(0);
    expect(listed.stdout.toLowerCase(), `installed plugin not listed:\n${listed.stdout}`).toContain('hercules');
  }, TIMEOUT_MS * 3 + 5_000);
});
