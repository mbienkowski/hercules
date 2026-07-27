import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { afterEach, describe, expect, it } from 'vitest';

import { VERSION_TARGETS, readVersions } from '../../../builder/versionTargets.mjs';
import { main, setVersion } from '../../setVersion.mjs';

// Covers setVersion()'s own thin wrapper directly; versionTargets.spec.ts covers the writeVersion()
// it delegates to, exhaustively.

const dirs: string[] = [];

function seed(version = '0.1.0'): string {
  const root = mkdtempSync(join(tmpdir(), 'hercules-set-version-'));
  dirs.push(root);
  for (const [rel, fmt] of VERSION_TARGETS) {
    const path = join(root, rel);
    writeFileSync(
      path,
      fmt === 'toml'
        ? `[project]\nname = "hercules"\nversion = "${version}"\n`
        : `{\n  "name": "hercules",\n  "version": "${version}"\n}\n`,
      'utf-8',
    );
  }
  return root;
}

afterEach(() => {
  while (dirs.length > 0) rmSync(dirs.pop() as string, { recursive: true, force: true });
});

describe('setVersion', () => {
  it('writes the new version into every canonical file, not just some of them', () => {
    const root = seed();
    setVersion('9.9.9', root);
    const expected = Object.fromEntries(VERSION_TARGETS.map(([rel]) => [rel, '9.9.9']));
    expect(readVersions(root)).toEqual(expected);
  });
});

// main(argv) is the CLI argument handling split out of bin/setVersion.mts (an entry-point guard
// cannot be covered directly — see that file's own comment): argv is already sliced. The optional
// `root` param avoids process.chdir(), which Stryker's worker-thread runner rejects.
describe('main', () => {
  const originalWrite = process.stderr.write.bind(process.stderr);

  afterEach(() => {
    process.stderr.write = originalWrite;
  });

  it('writes the version and returns 0 when exactly one argument is given', () => {
    const root = seed();
    expect(main(['9.9.9'], root)).toBe(0);
    const expected = Object.fromEntries(VERSION_TARGETS.map(([rel]) => [rel, '9.9.9']));
    expect(readVersions(root)).toEqual(expected);
  });

  it('reports a usage error and returns 1 when no argument is given', () => {
    let stderr = '';
    process.stderr.write = ((chunk: string) => {
      stderr += chunk;
      return true;
    }) as typeof process.stderr.write;
    expect(main([])).toBe(1);
    expect(stderr).toContain('usage: setVersion.mjs X.Y.Z');
  });

  it('reports a usage error and returns 1 when more than one argument is given', () => {
    let stderr = '';
    process.stderr.write = ((chunk: string) => {
      stderr += chunk;
      return true;
    }) as typeof process.stderr.write;
    expect(main(['9.9.9', 'extra'])).toBe(1);
    expect(stderr).toContain('usage: setVersion.mjs X.Y.Z');
  });

  it('reports a usage error and returns 1 when the single argument is undefined, not just when argv.length is wrong', () => {
    // A length-1 argv whose sole element is undefined must still be rejected by the
    // `version === undefined` half of the guard, independent of the `argv.length !== 1` half.
    let stderr = '';
    process.stderr.write = ((chunk: string) => {
      stderr += chunk;
      return true;
    }) as typeof process.stderr.write;
    expect(main([undefined as unknown as string])).toBe(1);
    expect(stderr).toContain('usage: setVersion.mjs X.Y.Z');
  });
});
