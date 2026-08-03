import { spawnSync } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

import { afterEach, describe, expect, it } from 'vitest';

import { repoRoot } from '../../support/repo';
import { tempWorkspace } from '../../support/tempWorkspace';

// The two per-commit CI gates, exercised against REAL throwaway git repositories, never mocked diffs.
// A push is judged one commit at a time: an early compliant commit never excuses a later violating one.

const TRIPWIRE = join(repoRoot, 'internal', 'release', 'ci', 'tripwire.sh');
const NORMATIVE_GATE = join(repoRoot, 'internal', 'release', 'ci', 'normative_gate.sh');

interface GateResult {
  readonly status: number | null;
  readonly stdout: string;
  readonly stderr: string;
}

const workspace = tempWorkspace();
afterEach(workspace.cleanup);

/** A throwaway git repo with one base commit; returns its path and the base SHA. */
function fixtureRepo(): { repo: string; base: string } {
  const repo = workspace.make('hercules-gate-');
  const git = (...args: string[]) => {
    const r = spawnSync('git', args, { cwd: repo, encoding: 'utf-8' });
    if (r.status !== 0) throw new Error(`git ${args.join(' ')} failed: ${r.stderr}`);
    return r.stdout.trim();
  };
  git('init', '-q');
  git('config', 'user.email', 'gate-test@example.invalid');
  git('config', 'user.name', 'Gate Test');
  writeFileSync(join(repo, 'README.md'), 'base\n');
  git('add', '.');
  git('commit', '-q', '-m', 'base');
  return { repo, base: git('rev-parse', 'HEAD') };
}

/** Add one commit touching `files` (path -> content) with `message`; returns its SHA. */
function commit(repo: string, files: Record<string, string>, message: string): string {
  for (const [relativePath, content] of Object.entries(files)) {
    const abs = join(repo, relativePath);
    mkdirSync(join(abs, '..'), { recursive: true });
    writeFileSync(abs, content);
  }
  const git = (...args: string[]) => {
    const r = spawnSync('git', args, { cwd: repo, encoding: 'utf-8' });
    if (r.status !== 0) throw new Error(`git ${args.join(' ')} failed: ${r.stderr}`);
    return r.stdout.trim();
  };
  git('add', '.');
  git('commit', '-q', '-m', message);
  return git('rev-parse', 'HEAD');
}

function runGate(script: string, repo: string, base: string, head?: string): GateResult {
  const r = spawnSync('bash', [script], {
    cwd: repo,
    encoding: 'utf-8',
    env: { ...process.env, BASE: base, HEAD_SHA: head ?? 'HEAD' },
  });
  return { status: r.status, stdout: r.stdout ?? '', stderr: r.stderr ?? '' };
}

describe('tripwire: a commit that changes production code must carry a test change', () => {
  it('a commit changing prod code with no test change is rejected, and the rejection names that commit', () => {
    const { repo, base } = fixtureRepo();
    const sha = commit(repo, { 'internal/core/thing.mts': 'export const x = 1;\n' }, 'add prod logic');
    const r = runGate(TRIPWIRE, repo, base);
    expect(r.status).toBe(1);
    expect(r.stdout + r.stderr).toContain(sha);
  });

  it('a commit touching only tests passes', () => {
    const { repo, base } = fixtureRepo();
    commit(repo, { 'internal/core/tests/thing.spec.ts': 'it.todo("x");\n' }, 'add a test');
    expect(runGate(TRIPWIRE, repo, base).status).toBe(0);
  });

  it('a commit pairing prod code with a test passes', () => {
    const { repo, base } = fixtureRepo();
    commit(
      repo,
      { 'internal/core/thing.mts': 'export const x = 1;\n', 'internal/core/tests/thing.spec.ts': 'it.todo("x");\n' },
      'prod with its test',
    );
    expect(runGate(TRIPWIRE, repo, base).status).toBe(0);
  });

  it('a pure rename marked [rename-only] passes without a test change', () => {
    const { repo, base } = fixtureRepo();
    commit(repo, { 'internal/core/renamed.mts': 'export const x = 1;\n' }, 'move module [rename-only]');
    expect(runGate(TRIPWIRE, repo, base).status).toBe(0);
  });

  it('in a push of three commits, a violating middle commit fails the gate even though its neighbours comply', () => {
    const { repo, base } = fixtureRepo();
    commit(repo, { 'internal/a/tests/a.spec.ts': 'it.todo("a");\n' }, 'compliant: tests only');
    const offender = commit(repo, { 'internal/a/logic.mts': 'export const a = 1;\n' }, 'violates: prod, no test');
    commit(
      repo,
      { 'internal/b/logic.mts': 'export const b = 1;\n', 'internal/b/tests/b.spec.ts': 'it.todo("b");\n' },
      'compliant: prod with test',
    );
    const r = runGate(TRIPWIRE, repo, base);
    expect(r.status).toBe(1);
    expect(r.stdout + r.stderr).toContain(offender);
  });

  it('an unresolvable base ref fails loudly with the fetch-depth remedy, never as a silent pass', () => {
    const { repo } = fixtureRepo();
    commit(repo, { 'internal/core/thing.mts': 'export const x = 1;\n' }, 'prod, no test');
    const r = runGate(TRIPWIRE, repo, 'no-such-ref-anywhere');
    expect(r.status).not.toBe(0);
    expect(r.stdout + r.stderr).toContain('fetch-depth');
  });

  it('a test living under a nested tests/ directory counts as a test change', () => {
    const { repo, base } = fixtureRepo();
    commit(
      repo,
      { 'internal/builder/logic.mts': 'export const x = 1;\n', 'internal/builder/tests/deep/logic.spec.ts': 'it.todo("x");\n' },
      'prod with nested test',
    );
    expect(runGate(TRIPWIRE, repo, base).status).toBe(0);
  });
});

describe('normative gate: a commit that changes shipped content must declare its normative impact', () => {
  it('a commit touching shipped content without a declaration is rejected', () => {
    const { repo, base } = fixtureRepo();
    const sha = commit(repo, { 'src/content/commands/build.md': '# changed\n' }, 'tweak a command');
    const r = runGate(NORMATIVE_GATE, repo, base);
    expect(r.status).toBe(1);
    expect(r.stdout + r.stderr).toContain(sha);
  });

  it('a content commit carrying its own Normative-change line passes, and the diff is surfaced beside the declaration', () => {
    const { repo, base } = fixtureRepo();
    commit(
      repo,
      { 'src/content/commands/build.md': '# changed\n' },
      'tweak a command\n\nNormative-change: none — wording only',
    );
    const r = runGate(NORMATIVE_GATE, repo, base);
    expect(r.status).toBe(0);
    expect(r.stdout).toContain('src/content/commands/build.md');
  });

  it('a commit that never touches shipped content needs no declaration', () => {
    const { repo, base } = fixtureRepo();
    commit(repo, { 'internal/builder/logic.mts': 'export const x = 1;\n' }, 'builder-only change');
    expect(runGate(NORMATIVE_GATE, repo, base).status).toBe(0);
  });

  it('an early declared commit never excuses a later undeclared content commit in the same push', () => {
    const { repo, base } = fixtureRepo();
    commit(
      repo,
      { 'src/content/persona.md': '# v2\n' },
      'declared edit\n\nNormative-change: sharpened the delivery gate wording',
    );
    const offender = commit(repo, { 'src/content/persona.md': '# v3\n' }, 'sneaky follow-up, no declaration');
    const r = runGate(NORMATIVE_GATE, repo, base);
    expect(r.status).toBe(1);
    expect(r.stdout + r.stderr).toContain(offender);
  });

  it("a file only one tool ships is guarded exactly like content everyone gets", () => {
    // Ecosystem-specific content lives under `src/content/targets/<ecosystem>/`, which the gate covers
    // by being scoped to `src/content` — nothing new can land outside a scope somebody forgot to widen.
    const { repo, base } = fixtureRepo();
    commit(repo, { 'src/content/targets/cursor/README.md': '# shipped readme\n' }, 'edit a tool-specific file');
    expect(runGate(NORMATIVE_GATE, repo, base).status).toBe(1);
  });
});
