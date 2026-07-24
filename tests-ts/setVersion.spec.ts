import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { afterEach, describe, expect, it } from 'vitest';

import { VERSION_TARGETS, readVersions } from '../scripts-ts/build/versionTargets.mjs';
import { setVersion } from '../scripts-ts/setVersion.mjs';

// Ported from test_version_process.py's test_bumping_the_version_updates_every_canonical_file, the
// one test that exercises scripts/set_version.py's own set_version() wrapper directly (as opposed to
// versionTargets.spec.ts's exhaustive coverage of writeVersion() itself, which set_version.py/
// setVersion.mts is a thin, one-line delegation to).

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
