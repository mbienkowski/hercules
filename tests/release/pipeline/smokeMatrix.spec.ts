import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { afterEach, describe, expect, it, vi } from 'vitest';

// Wraps (not replaces) appendFileSync so main()'s $GITHUB_OUTPUT write still hits real disk.
vi.mock('node:fs', async (importOriginal) => {
  const actual = await importOriginal<typeof import('node:fs')>();
  return { ...actual, appendFileSync: vi.fn(actual.appendFileSync) };
});

import { SmokeMatrixError, buildMatrix, main } from '../../../internal/release/smokeMatrix.mjs';
import { tempWorkspace } from '../../support/tempWorkspace';

import { smokeTargets } from '../../../internal/release/smoke-targets.mjs';
import { listRecipeNames } from '../../../internal/builder/recipe-loader.mjs';
import { expectRefusal } from '../../support/refusal';

// A hole here lets a broken ecosystem skip its smoke leg while CI reports green — GitHub counts a
// skipped leg as success — so the recipes and smoke-targets.json are pinned against each other.
describe('the smoke matrix fails closed', () => {
  it.each<[string, () => unknown, RegExp]>([
    ['a distribution with no entry in smoke-targets.json fails closed',
      () => buildMatrix(['claude-code', 'opencode', 'cursor', 'ghost-ecosystem']),
      /no entry in internal\/release\/smoke-targets\.json/],
    ['a smoke entry naming no distribution fails closed',
      () => buildMatrix(['claude-code', 'opencode']), /phantom smoke legs/],
  ])('%s', (_name, invoke, pattern) => {
    expect(invoke).toThrowError(SmokeMatrixError);
    expect(invoke).toThrow(pattern);
  });

  it('an empty registry with no smoke targets resolves to zero legs and fails closed', () => {
    expect(() => buildMatrix([], {})).toThrowError(SmokeMatrixError);
    expect(() => buildMatrix([], {})).toThrow(/zero legs/);
  });

  it('includes every registered ecosystem from the real registry, including the script-installed one', () => {
    const legs = Object.fromEntries(buildMatrix().include.map((leg) => [leg.target, leg]));
    expect(Object.keys(legs)).toEqual(expect.arrayContaining(['claude-code', 'opencode', 'cursor']));
    expect(legs['cursor']?.install_method).toBe('script');
    expect(legs['claude-code']?.install_method).toBe('package');
  });
});

describe('main', () => {
  const originalWrite = process.stdout.write.bind(process.stdout);
  const originalGithubOutput = process.env['GITHUB_OUTPUT'];
  const workspace = tempWorkspace();

  afterEach(() => {
    process.stdout.write = originalWrite;
    if (originalGithubOutput === undefined) delete process.env['GITHUB_OUTPUT'];
    else process.env['GITHUB_OUTPUT'] = originalGithubOutput;
    workspace.cleanup();
  });

  function captureStdout(): { text: () => string } {
    let out = '';
    process.stdout.write = ((chunk: string) => {
      out += chunk;
      return true;
    }) as typeof process.stdout.write;
    return { text: () => out };
  }

  it('appends the exact matrix= line to $GITHUB_OUTPUT when the env var is set', () => {
    const dir = workspace.make('hercules-smoke-matrix-');
    const outFile = join(dir, 'output');
    writeFileSync(outFile, '', 'utf-8');
    process.env['GITHUB_OUTPUT'] = outFile;
    captureStdout();
    main();
    const matrix = buildMatrix();
    expect(readFileSync(outFile, 'utf-8')).toBe('matrix=' + JSON.stringify(matrix) + '\n');
  });
});

describe('the smoke declarations are validated, not merely read', () => {
  // A mistyped `cli` produces a smoke leg that installs the wrong binary and reports green, because
  // nothing it names is there to disagree — hence a schema over the declarations.
  it('refuses a declaration the schema does not describe, naming the file', () => {
    const scratch = mkdtempSync(join(tmpdir(), 'hercules-smoke-'));
    try {
      const path = join(scratch, 'smoke-targets.json');
      writeFileSync(path, JSON.stringify({ targets: { cursor: { cli: 'cursor-agent', tset: 'x' } } }), 'utf-8');
      expectRefusal(() => smokeTargets(path), [path, 'smoke-targets.schema.json', 'tset']);
    } finally {
      rmSync(scratch, { recursive: true, force: true });
    }
  });

  it('reads the real declarations, one per distribution the build registers', () => {
    expect(Object.keys(smokeTargets()).sort()).toEqual(listRecipeNames());
  });
});
