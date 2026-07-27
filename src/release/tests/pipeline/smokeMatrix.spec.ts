import { appendFileSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { afterEach, describe, expect, it, vi } from 'vitest';

// Wraps (not replaces) appendFileSync so main()'s $GITHUB_OUTPUT write still hits real disk — every
// other test in this file reads the real appended file back — while letting one test assert the
// exact encoding argument main() passes, which real-filesystem behavior alone can't distinguish
// (Node treats an empty-string encoding the same as 'utf-8' for a string payload).
vi.mock('node:fs', async (importOriginal) => {
  const actual = await importOriginal<typeof import('node:fs')>();
  return { ...actual, appendFileSync: vi.fn(actual.appendFileSync) };
});

import {
  type EcosystemDescriptor,
  names as registeredTargetNames,
  parseDescriptor,
} from '../../../builder/descriptor.mjs';
import { SmokeMatrixError, buildMatrix, main } from '../../smokeMatrix.mjs';
import { minimal } from '../../../commons/support/descriptorFixtures';

// Ported from tests/build/test_ci_smoke_matrix.py's unit-level (build_matrix()) assertions. The
// CI-job-graph assertions (smoke/mutation `needs`/`if` wiring) live in release/tests/pipeline/releasePipeline.spec.ts
// instead — they parse the workflow YAML directly and never call buildMatrix().
//
// The Python original monkeypatched GITHUB_REF and asserted the matrix was the same either way — but
// buildMatrix() (like build_matrix() before it) never reads that env var at all; the matrix is a pure
// function of the descriptor registry. That assertion is preserved here as "every ecosystem is present
// regardless of context" without actually touching the environment, since there is nothing to fake.

function legsByTarget(): Record<string, ReturnType<typeof buildMatrix>['include'][number]> {
  const legs = buildMatrix().include;
  return Object.fromEntries(legs.map((leg) => [leg.target, leg]));
}

/**
 * A minimal-but-valid fabricated descriptor, for tests that need to inject an unsorted/fabricated
 * `descriptors` record into `buildMatrix`'s (test-only) second parameter — the real registry's own
 * `discover()` result is always already alphabetically ordered (proven by descriptorSort.spec.ts),
 * so only a fabricated set can prove `buildMatrix`'s own `.sort()` calls are load-bearing rather
 * than riding that upstream guarantee.
 */
function fakeDescriptor(name: string): EcosystemDescriptor {
  return parseDescriptor(name, minimal({ name, smoke: { cli: name, test: 'builder/tests/x.spec.ts' } }));
}

describe('the smoke matrix', () => {
  it('includes every registered ecosystem, including the script-installed one', () => {
    const legs = legsByTarget();
    expect(Object.keys(legs)).toEqual(expect.arrayContaining(['claude-code', 'opencode', 'cursor']));
    expect(legs['cursor']?.install_method).toBe('script');
    expect(legs['claude-code']?.install_method).toBe('npm');
  });

  it('every leg carries the fields the install and run scripts read', () => {
    const legs = legsByTarget();
    for (const leg of Object.values(legs)) {
      expect(leg).toHaveProperty('target');
      expect(leg).toHaveProperty('cli');
      expect(leg).toHaveProperty('test');
      expect(leg).toHaveProperty('install_method');
    }
  });

  it('the matrix targets come from the build registry, not an independently maintained list', () => {
    const legs = legsByTarget();
    expect(new Set(Object.keys(legs))).toEqual(new Set(registeredTargetNames()));
  });

  it('a registered ecosystem missing its smoke.json fails closed', () => {
    // A ghost ecosystem the real descriptor registry does not know about — not undiscoverable, just
    // fabricated for this test via the injectable `registered` param.
    expect(() =>
      buildMatrix(['claude-code', 'opencode', 'cursor', 'ghost-ecosystem']),
    ).toThrowError(SmokeMatrixError);
    expect(() => buildMatrix(['claude-code', 'opencode', 'cursor', 'ghost-ecosystem'])).toThrow(
      /no smoke\.json/,
    );
  });

  it('a smoke.json for an unregistered ecosystem fails closed', () => {
    // cursor's descriptor (with its smoke.json config) exists on disk but is deliberately left out
    // of this fabricated registry — a phantom leg the real build never produces.
    expect(() => buildMatrix(['claude-code', 'opencode'])).toThrowError(SmokeMatrixError);
    expect(() => buildMatrix(['claude-code', 'opencode'])).toThrow(/unregistered ecosystems/);
  });

  it("SmokeMatrixError instances carry the class's own name, not the generic 'Error'", () => {
    // CI tooling (and any operator grepping a failed-job log) filters on `error.name`, not on the
    // message text alone.
    expect(new SmokeMatrixError('boom').name).toBe('SmokeMatrixError');
  });

  it('a multi-ecosystem drift report lists the missing names in sorted order, not registration order', () => {
    expect(() => buildMatrix(['claude-code', 'zzz-ghost', 'aaa-ghost'])).toThrow(
      /no smoke\.json config.*\["aaa-ghost","zzz-ghost"\]/,
    );
  });

  it('a multi-ecosystem phantom-leg report lists the orphan names in sorted order, not descriptor order', () => {
    // The real registry's own discover() result is already alphabetical (descriptorSort.spec.ts),
    // so only a fabricated `descriptors` record (via the test-only second param) can exercise this:
    // these two keys are inserted in DELIBERATELY reverse-of-sorted order.
    const descriptors: Readonly<Record<string, EcosystemDescriptor>> = {
      'zzz-phantom': fakeDescriptor('zzz-phantom'),
      'aaa-phantom': fakeDescriptor('aaa-phantom'),
      'claude-code': fakeDescriptor('claude-code'),
    };
    expect(() => buildMatrix(['claude-code'], descriptors)).toThrow(
      /unregistered ecosystems.*\["aaa-phantom","zzz-phantom"\]/,
    );
  });

  it('an empty registry with no descriptors resolves to zero legs and fails closed', () => {
    // Both the missing- and orphan-ecosystem checks need SOMETHING registered/discovered to ever
    // fire, so this is the one scenario that reaches the third fail-closed guard: legs.length === 0.
    expect(() => buildMatrix([], {})).toThrowError(SmokeMatrixError);
    expect(() => buildMatrix([], {})).toThrow(/zero legs/);
  });

  it('extracts every npm/install field the real descriptors carry, not just install_method', () => {
    // claude-code carries npm_package/npm_version but no `install` section; cursor carries
    // `install.url`/`install.flags` but no npm fields — between the two, every `?? ''` fallback in
    // buildMatrix's leg-building is exercised on BOTH its present (real value) and absent (default)
    // side, pinned exactly (not just presence) so a fallback silently returning '' instead of the
    // real value, or vice versa, cannot pass unnoticed.
    const legs = legsByTarget();
    expect(legs['claude-code']).toMatchObject({
      install_method: 'npm',
      npm_package: '@anthropic-ai/claude-code',
      npm_version: '2.1.214',
      install_url: '',
      install_flags: '',
    });
    expect(legs['cursor']).toMatchObject({
      install_method: 'script',
      npm_package: '',
      npm_version: '',
      install_url: 'https://cursor.com/install',
      install_flags: '-fsSL',
    });
  });
});

describe('main', () => {
  const originalWrite = process.stdout.write.bind(process.stdout);
  const originalGithubOutput = process.env['GITHUB_OUTPUT'];
  const dirs: string[] = [];

  afterEach(() => {
    process.stdout.write = originalWrite;
    if (originalGithubOutput === undefined) delete process.env['GITHUB_OUTPUT'];
    else process.env['GITHUB_OUTPUT'] = originalGithubOutput;
    while (dirs.length > 0) rmSync(dirs.pop() as string, { recursive: true, force: true });
  });

  function captureStdout(): { text: () => string } {
    let out = '';
    process.stdout.write = ((chunk: string) => {
      out += chunk;
      return true;
    }) as typeof process.stdout.write;
    return { text: () => out };
  }

  it('prints the exact resolved-matrix summary and matrix= JSON line to stdout', () => {
    delete process.env['GITHUB_OUTPUT'];
    const matrix = buildMatrix();
    const legs = matrix.include.map((leg) => leg.target);
    const capture = captureStdout();
    main();
    expect(capture.text()).toBe(
      `smoke matrix (${legs.length} legs): ${legs.join(', ')}\n` + 'matrix=' + JSON.stringify(matrix) + '\n',
    );
  });

  it('appends the exact matrix= line to $GITHUB_OUTPUT when the env var is set', () => {
    const dir = mkdtempSync(join(tmpdir(), 'hercules-smoke-matrix-'));
    dirs.push(dir);
    const outFile = join(dir, 'output');
    writeFileSync(outFile, '', 'utf-8');
    process.env['GITHUB_OUTPUT'] = outFile;
    captureStdout(); // silence stdout for this test; asserted separately above
    main();
    const matrix = buildMatrix();
    expect(readFileSync(outFile, 'utf-8')).toBe('matrix=' + JSON.stringify(matrix) + '\n');
  });

  it('does not throw when $GITHUB_OUTPUT is unset — it only prints, never writes a file', () => {
    delete process.env['GITHUB_OUTPUT'];
    captureStdout();
    expect(() => main()).not.toThrow();
  });

  it('appends to $GITHUB_OUTPUT with explicit utf-8 encoding, not the platform default', () => {
    const dir = mkdtempSync(join(tmpdir(), 'hercules-smoke-matrix-'));
    dirs.push(dir);
    const outFile = join(dir, 'output');
    writeFileSync(outFile, '', 'utf-8');
    process.env['GITHUB_OUTPUT'] = outFile;
    captureStdout();
    main();
    expect(appendFileSync).toHaveBeenCalledWith(outFile, expect.any(String), 'utf-8');
  });
});
