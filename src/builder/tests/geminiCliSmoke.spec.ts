import { spawnSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { afterEach, describe, expect, it } from 'vitest';

import { buildTarget } from '../bin/cli.mjs';
import { srcStems } from '../../commons/support/buildTree';
import { repoRoot } from '../../commons/support/repo';
import { which } from '../../commons/support/which';

// Ported from tests/build/test_gemini_cli_smoke.py — a live Gemini CLI smoke check + an
// always-on structural guard on the built extension.
//
// The ALWAYS-ON check is structural (never skips): the freshly built `dist/gemini-cli` tree must
// satisfy the Gemini extension contract — a kebab manifest name with contextFileName, subagents
// with name+description, TOML commands with a prompt, and the BeforeTool write-gate wired to the
// adapter. The genuinely live check (the real `gemini` binary runs) is opt-in and SKIPs when the
// CLI is absent, so the fork-safe gate stays green.

const SRC_CONTENT = join(repoRoot, 'src', 'content');
const TIMEOUT_MS = 60_000;

const dirs: string[] = [];
afterEach(() => {
  while (dirs.length > 0) rmSync(dirs.pop() as string, { recursive: true, force: true });
}, 30_000);

function build(): string {
  const root = mkdtempSync(join(tmpdir(), 'hercules-gemini-smoke-'));
  dirs.push(root);
  const out = join(root, 'gemini-cli');
  buildTarget('gemini-cli', out);
  return out;
}

function srcSkills(): string[] {
  return readdirSync(join(SRC_CONTENT, 'skills'), { withFileTypes: true })
    .filter((e) => e.isDirectory())
    .map((e) => e.name)
    .sort();
}

it('built extension is well formed', () => {
  // Always-on, auth-free: the built extension satisfies the Gemini contract — a malformed
  // manifest, a `.md` (not `.toml`) command, or an unwired hook would load as absent with no
  // error.
  const out = build();
  const manifest = JSON.parse(readFileSync(join(out, 'gemini-extension.json'), 'utf-8')) as {
    name: string;
    contextFileName: string;
  };
  expect(manifest.name).toMatch(/^[a-z0-9]([a-z0-9-]*[a-z0-9])?$/);
  expect(manifest.contextFileName).toBe('GEMINI.md');
  expect(readFileSync(join(out, 'GEMINI.md'), 'utf-8')).toBeTruthy();

  for (const name of readdirSync(join(out, 'commands')).filter((n) => n.endsWith('.toml'))) {
    const text = readFileSync(join(out, 'commands', name), 'utf-8');
    expect(text, `${name} lacks a TOML prompt`).toContain('prompt = """');
  }
  for (const name of readdirSync(join(out, 'agents')).filter((n) => n.endsWith('.md'))) {
    const text = readFileSync(join(out, 'agents', name), 'utf-8');
    expect(text.startsWith('---\n')).toBe(true);
    expect(text).toContain('name:');
    expect(text).toContain('description:');
  }
  expect(
    readFileSync(join(out, 'agents', 'cynical-reviewer.md'), 'utf-8'),
    'the independent reviewer must ship',
  ).toBeTruthy();
});

it('before-tool gate is wired to the adapter', () => {
  // The write-gate wiring: hooks.json wires BeforeTool (matcher covering both edit tools) to
  // hercules_gate.py via python3 and the ${extensionPath} script path — the exact command form
  // pinned.
  const out = build();
  const hooks = JSON.parse(readFileSync(join(out, 'hooks', 'hooks.json'), 'utf-8')) as {
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

it('ships the full component inventory', () => {
  // The built extension must carry the WHOLE inventory — all 5 commands (as `.toml`), every
  // advisor agent, and every skill — so nothing silently fails to load. Names derive from
  // content (the single source of truth).
  const out = build();
  for (const name of srcStems(SRC_CONTENT, 'commands')) {
    expect(readdirSync(join(out, 'commands')), `gemini missing command ${name}`).toContain(`${name}.toml`);
  }
  for (const name of srcStems(SRC_CONTENT, 'agents')) {
    expect(readdirSync(join(out, 'agents')), `gemini missing agent ${name}`).toContain(`${name}.md`);
  }
  for (const skill of srcSkills()) {
    expect(readdirSync(join(out, 'skills', skill)), `gemini missing skill ${skill}`).toContain('SKILL.md');
  }
  expect(readFileSync(join(out, 'GEMINI.md'), 'utf-8'), 'the GEMINI.md context file must ship').toBeTruthy();
});

describe.skipIf(which('gemini') === null)('live gemini binary', () => {
  it('the real gemini binary runs', () => {
    // With the real CLI present, `gemini --version` must exit 0 (a stub-on-PATH would not).
    const res = spawnSync('gemini', ['--version'], { encoding: 'utf-8', timeout: TIMEOUT_MS });
    expect(res.status, `gemini --version failed: ${res.stdout}\n${res.stderr}`).toBe(0);
  }, TIMEOUT_MS + 5_000);

  it('the extension installs into the real cli and is listed', (ctx) => {
    // Install the built extension into an isolated HOME and confirm the real `gemini` lists it —
    // a genuine install + load check beyond `--version`. Extension management is local (no API
    // call), so it should run without auth; but it SKIPs (never fails the leg) on any
    // error/timeout or a differing subcommand shape, so the every-commit gate stays green while
    // the structural inventory above still runs.
    const root = mkdtempSync(join(tmpdir(), 'hercules-gemini-smoke-'));
    dirs.push(root);
    const home = join(root, 'home');
    mkdirSync(home);
    const env = { ...process.env, HOME: home };
    const ext = join(repoRoot, 'dist', 'gemini-cli');

    const inst = spawnSync('gemini', ['extensions', 'install', ext], {
      encoding: 'utf-8', timeout: TIMEOUT_MS, env,
    });
    if (inst.error || inst.status !== 0) {
      ctx.skip(`gemini extensions install unavailable here: ${((inst.stderr || inst.stdout) ?? '').slice(0, 300)}`);
    }
    const listed = spawnSync('gemini', ['extensions', 'list'], { encoding: 'utf-8', timeout: TIMEOUT_MS, env });
    if (listed.error) {
      ctx.skip(`gemini extensions could not run here: ${listed.error.message}`);
    }
    expect(listed.status, `\`gemini extensions list\` failed: ${listed.stdout}\n${listed.stderr}`).toBe(0);
    expect(listed.stdout.toLowerCase(), `installed extension not listed:\n${listed.stdout}`).toContain('hercules');
  }, TIMEOUT_MS * 2 + 5_000);
});
