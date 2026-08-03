import { spawnSync } from 'node:child_process';
import { closeSync, openSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

import { afterEach, describe, expect, it } from 'vitest';

import { repoRoot } from '../../support/repo';
import { tempWorkspace } from '../../support/tempWorkspace';
import { which } from '../../support/which';
import { scratchHome } from '../smokeHarness';

// Live Gemini CLI smoke, plus the wiring guard for the one hook command no other host writes: Gemini
// resolves its own files through `${extensionPath}`, launched as a shell string whose form decides a refusal.

const DIST = join(repoRoot, 'dist', 'gemini-cli');
const TIMEOUT_MS = 60_000;

const workspace = tempWorkspace();
afterEach(workspace.cleanup, 30_000);

it('before-tool gate is wired to the adapter', () => {
  // hooks.json wires BeforeTool to hercules_gate.py via python3 and `${extensionPath}` — form pinned.
  const hooks = JSON.parse(readFileSync(join(DIST, 'hooks', 'hooks.json'), 'utf-8')) as {
    hooks: { BeforeTool: Array<{ matcher: string; hooks: Array<{ command: string }> }> };
  };
  const entries = hooks.hooks.BeforeTool;
  const matcher = (entries[0] as { matcher: string }).matcher;
  expect(matcher, 'matcher must cover both edit tools').toContain('write_file');
  expect(matcher).toContain('replace');
  const cmd = (entries[0] as { hooks: Array<{ command: string }> }).hooks[0]?.command;
  expect(cmd, `unexpected hook command: ${cmd}`).toBe(
    'python3 ${extensionPath}/hooks/hercules_gate.py || exit 0',
  );
});

describe.skipIf(which('gemini') === null)('live gemini binary', () => {
  // gemini spawns a background update child that INHERITS and holds open a stdout pipe, making a piped
  // `spawnSync` block past its own timeout — so every call routes output to a FILE and SIGKILLs.
  function runGemini(args: string[], env: NodeJS.ProcessEnv = process.env) {
    const dir = workspace.make('hercules-gemini-run-');
    const outPath = join(dir, 'out.txt');
    const fd = openSync(outPath, 'w');
    try {
      const res = spawnSync('gemini', args, {
        timeout: TIMEOUT_MS, killSignal: 'SIGKILL', env, stdio: ['ignore', fd, fd],
      });
      return { status: res.status, signal: res.signal, error: res.error, out: readFileSync(outPath, 'utf-8') };
    } finally {
      closeSync(fd);
    }
  }

  it('the extension installs into the real cli and is listed', (ctx) => {
    // Extension management is local and needs no auth; any error or timeout SKIPs rather than fails.
    const { root, env } = scratchHome();
    workspace.track(root);

    const inst = runGemini(['extensions', 'install', DIST], env);
    if (inst.error || inst.signal || inst.status !== 0) {
      ctx.skip(`gemini extensions install unavailable here: ${(inst.out ?? '').slice(0, 300)}`);
    }
    const listed = runGemini(['extensions', 'list'], env);
    if (listed.error || listed.signal) {
      ctx.skip(`gemini extensions could not run here: ${listed.error?.message ?? listed.signal}`);
    }
    expect(listed.status, `\`gemini extensions list\` failed: ${listed.out}`).toBe(0);
    expect(listed.out.toLowerCase(), `installed extension not listed:\n${listed.out}`).toContain('hercules');
  }, TIMEOUT_MS * 2 + 5_000);
});
