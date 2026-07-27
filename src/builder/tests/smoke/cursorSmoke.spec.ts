import { spawnSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { afterEach, describe, expect, it } from 'vitest';

import { buildTarget } from '../../bin/cli.mjs';
import { which } from '../../../commons/support/which';

// Live Cursor CLI smoke check. Cursor has no auth-free introspection beyond `--version`, so the
// always-on check is structural: the real `cursor-agent` binary executes and the built
// `dist/cursor` tree satisfies the component contract. The headless run needs `CURSOR_API_KEY`.

const TIMEOUT_MS = 60_000;

const dirs: string[] = [];
afterEach(() => {
  while (dirs.length > 0) rmSync(dirs.pop() as string, { recursive: true, force: true });
}, 30_000);

function isolatedHomeEnv(): NodeJS.ProcessEnv {
  const root = mkdtempSync(join(tmpdir(), 'hercules-cursor-home-'));
  dirs.push(root);
  const home = join(root, 'home');
  mkdirSync(home);
  return {
    ...process.env,
    HOME: home,
    XDG_CONFIG_HOME: join(home, '.config'),
    XDG_CACHE_HOME: join(home, '.cache'),
  };
}

function tmpDir(): string {
  const root = mkdtempSync(join(tmpdir(), 'hercules-cursor-smoke-'));
  dirs.push(root);
  return root;
}

describe.skipIf(which('cursor-agent') === null)('cursor live-CLI smoke', () => {
  it('the real cursor-agent binary runs and the plugin is well formed', () => {
    // `cursor-agent --version` must exit 0 (a stub-on-PATH would not), and the built plugin must
    // satisfy the component contract — a malformed rule or agent loads as absent, with no error.
    const env = isolatedHomeEnv();
    const res = spawnSync('cursor-agent', ['--version'], { encoding: 'utf-8', timeout: TIMEOUT_MS, env });
    expect(res.status, `cursor-agent --version failed: ${res.stdout}\n${res.stderr}`).toBe(0);

    const out = join(tmpDir(), 'cursor');
    buildTarget('cursor', out);

    const manifest = JSON.parse(
      readFileSync(join(out, '.cursor-plugin', 'plugin.json'), 'utf-8'),
    ) as { name: string };
    expect(manifest.name).toMatch(/^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$/);

    const fm = (path: string): string => {
      const text = readFileSync(path, 'utf-8');
      expect(text.startsWith('---\n'), `${path} lacks frontmatter`).toBe(true);
      return text;
    };

    for (const name of readdirSync(join(out, 'agents')).filter((n) => n.endsWith('.md'))) {
      const text = fm(join(out, 'agents', name));
      expect(text).toContain('name:');
      expect(text).toContain('description:');
    }
    for (const name of readdirSync(join(out, 'commands')).filter((n) => n.endsWith('.md'))) {
      const text = fm(join(out, 'commands', name));
      expect(text).toContain('name:');
      expect(text).toContain('description:');
    }
    const persona = fm(join(out, 'rules', 'hercules-persona.mdc'));
    expect(persona).toContain('alwaysApply: true');
    expect(
      readFileSync(join(out, 'agents', 'cynical-reviewer.md'), 'utf-8'),
      'the independent reviewer must ship',
    ).toBeTruthy();
  }, TIMEOUT_MS + 5_000);

  it.skipIf(!process.env['CURSOR_API_KEY'])(
    'the real cursor-agent runs a headless prompt',
    () => {
      // With a key present, the real binary must complete one trivial headless prompt end-to-end —
      // the same `cursor-agent -p` mode the deterministic-independent-review path uses.
      const env = isolatedHomeEnv();
      const res = spawnSync(
        'cursor-agent',
        ['-p', 'Reply with the single word OK.', '--output-format', 'text'],
        { encoding: 'utf-8', timeout: TIMEOUT_MS, env },
      );
      expect(res.status, `headless cursor-agent run failed: ${res.stdout}\n${res.stderr}`).toBe(0);
    },
    TIMEOUT_MS + 5_000,
  );
});
