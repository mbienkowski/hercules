import { writeFileSync } from 'node:fs';
import { join } from 'node:path';

import { afterEach, describe, expect, it } from 'vitest';

import { VERSION_TARGETS, readVersions } from '../../../internal/release/version-files.mjs';
import { main } from '../../../internal/release/setVersion.mjs';
import { tempWorkspace } from '../../support/tempWorkspace';

// setVersion() is a one-line wrapper over writeVersion(), which versionFiles.spec.ts covers; this
// file owns only main()'s CLI (command-line interface) argument parsing.

const workspace = tempWorkspace();

function seed(version = '0.1.0'): string {
  const root = workspace.make('hercules-set-version-');
  for (const [relativePath, fmt] of VERSION_TARGETS) {
    const path = join(root, relativePath);
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

afterEach(workspace.cleanup);

// main(argv) is the argument handling split out of bin/setVersion.mts, with argv already sliced. The
// optional `root` avoids process.chdir(), which Stryker's worker-thread runner rejects.
describe('main', () => {
  const originalWrite = process.stderr.write.bind(process.stderr);

  afterEach(() => {
    process.stderr.write = originalWrite;
  });

  it('writes the version and returns 0 when exactly one argument is given', () => {
    const root = seed();
    expect(main(['9.9.9'], root)).toBe(0);
    const expected = Object.fromEntries(VERSION_TARGETS.map(([relativePath]) => [relativePath, '9.9.9']));
    expect(readVersions(root)).toEqual(expected);
  });

  it('reports a usage error and returns 1 when argument count is wrong (zero or more than one)', () => {
    let stderr = '';
    process.stderr.write = ((chunk: string) => {
      stderr += chunk;
      return true;
    }) as typeof process.stderr.write;
    expect(main([])).toBe(1);
    expect(main(['9.9.9', 'extra'])).toBe(1);
    expect(stderr).toContain('usage: setVersion.mjs X.Y.Z');
  });
});
