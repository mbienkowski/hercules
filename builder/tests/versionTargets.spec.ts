import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';

// vi.mock('node:fs') wraps (not replaces) writeFileSync so every test still hits real disk — only
// the CALL ARGUMENTS are additionally observable, for the one test below that needs to pin the
// exact encoding writeVersion() passes (content-based verification alone can't distinguish 'utf-8'
// from '' here: Node treats an empty-string encoding identically to 'utf-8' at the byte level for
// every string writeVersion() ever writes, verified directly — same pattern as
// release/tests/updateChangelog.spec.ts's own writeFileSync encoding pins).
vi.mock('node:fs', async (importOriginal) => {
  const actual = await importOriginal<typeof import('node:fs')>();
  return { ...actual, writeFileSync: vi.fn(actual.writeFileSync) };
});

import {
  VERSION_TARGETS,
  VersionError,
  checkInSync,
  readCanonicalVersion,
  readVersions,
  writeVersion,
} from '../versionTargets.mjs';

const dirs: string[] = [];

function workspace(pyproject: string, packageJson: string): string {
  const root = mkdtempSync(join(tmpdir(), 'hercules-version-'));
  dirs.push(root);
  writeFileSync(join(root, 'pyproject.toml'), pyproject, 'utf-8');
  writeFileSync(join(root, 'package.json'), packageJson, 'utf-8');
  // The two writes above (workspace setup) already called the mocked writeFileSync with 'utf-8' —
  // clearing here means every remaining recorded call in a test belongs to the code under test,
  // not to fixture setup. Without this, an assertion pinning writeVersion()'s own encoding arg
  // would trivially pass by matching these SETUP calls instead, regardless of what writeVersion()
  // itself actually passes — verified directly: this exact bug was caught live by a manual mutation
  // rehearsal (writeVersion()'s 'utf-8' changed to '' still left the unguarded assertion green).
  vi.mocked(writeFileSync).mockClear();
  return root;
}

afterEach(() => {
  while (dirs.length > 0) rmSync(dirs.pop() as string, { recursive: true, force: true });
});

describe('the canonical list of version-bearing files', () => {
  it('names exactly the two files that must carry a literal version', () => {
    // Everything else derives its version from these at build time. A third entry here without a
    // matching reader is how writer and reader drift apart.
    expect(VERSION_TARGETS.map(([rel]) => rel)).toEqual(['pyproject.toml', 'package.json']);
  });
});

describe('reading the version', () => {
  it('reads it from every canonical file', () => {
    const root = workspace('[project]\nversion = "1.2.3"\n', '{\n  "version": "1.2.3"\n}\n');
    expect(readVersions(root)).toEqual({ 'pyproject.toml': '1.2.3', 'package.json': '1.2.3' });
  });

  it('treats package.json as the single source of truth', () => {
    // Deliberately DIFFERENT values, so this actually proves which file wins rather than passing
    // vacuously because both happen to agree.
    const root = workspace('version = "1.1.1"\n', '{"version": "9.9.9"}');
    expect(readCanonicalVersion(root)).toBe('9.9.9');
  });

  it('matches the version line only at the start of a line', () => {
    // Without a line anchor, a commented-out or nested `version = "..."` elsewhere in the file
    // would be picked up as a second match.
    const root = workspace('[project]\nname = "x"\nversion = "4.5.6"\n', '{"version": "4.5.6"}');
    expect(readCanonicalVersion(root)).toBe('4.5.6');
  });

  it('refuses a file with no version at all', () => {
    const root = workspace('[project]\nname = "x"\n', '{"version": "1.0.0"}');
    expect(() => readVersions(root)).toThrow(VersionError);
    expect(() => readVersions(root)).toThrow('found 0');
  });

  it('refuses a file carrying two versions rather than picking one', () => {
    // A future nested field such as "engines": {"version": …} would otherwise be silently
    // mis-read or mis-written with no signal.
    const root = workspace('version = "1.0.0"\nversion = "1.0.1"\n', '{"version": "1.0.0"}');
    expect(() => readVersions(root)).toThrow('found 2');
  });
});

describe('writing a new version', () => {
  it('rewrites every canonical file in place', () => {
    const root = workspace('[project]\nversion = "1.0.0"\n', '{\n  "version": "1.0.0"\n}\n');
    writeVersion('2.0.0', root);
    expect(readVersions(root)).toEqual({ 'pyproject.toml': '2.0.0', 'package.json': '2.0.0' });
  });

  it('writes with explicit utf-8 encoding, not the platform default', () => {
    const root = workspace('version = "1.0.0"\n', '{"version": "1.0.0"}');
    writeVersion('2.0.0', root);
    expect(writeFileSync).toHaveBeenCalledWith(join(root, 'pyproject.toml'), expect.any(String), 'utf-8');
    expect(writeFileSync).toHaveBeenCalledWith(join(root, 'package.json'), expect.any(String), 'utf-8');
  });

  it('preserves the surrounding formatting exactly', () => {
    // These files are hand-maintained; a rewrite that reflowed them would show up as noise in
    // every release commit.
    const root = workspace('[project]\nname = "x"\nversion = "1.0.0"\ndeps = []\n', '{\n  "a": 1,\n  "version": "1.0.0"\n}\n');
    writeVersion('2.0.0', root);
    expect(readFileSync(join(root, 'pyproject.toml'), 'utf-8')).toBe(
      '[project]\nname = "x"\nversion = "2.0.0"\ndeps = []\n',
    );
    expect(readFileSync(join(root, 'package.json'), 'utf-8')).toBe('{\n  "a": 1,\n  "version": "2.0.0"\n}\n');
  });

  it('refuses to write into a file with no version, rather than adding one', () => {
    const root = workspace('[project]\nname = "x"\n', '{"version": "1.0.0"}');
    expect(() => writeVersion('2.0.0', root)).toThrow('found 0');
  });

  it('the TOML write pattern is anchored to the START of the line, not a substring match anywhere', () => {
    // Without the line anchor, `.replace()` (no global flag) would rewrite the FIRST occurrence of
    // "version = " textually — which is the one inside the comment, not the real field below it.
    const root = workspace(
      '# was version = "0.9.0"\nversion = "1.0.0"\n',
      '{"version": "1.0.0"}',
    );
    writeVersion('2.0.0', root);
    expect(readFileSync(join(root, 'pyproject.toml'), 'utf-8')).toBe(
      '# was version = "0.9.0"\nversion = "2.0.0"\n',
    );
  });

  it.each([
    ['no spaces around the equals', 'version="1.0.0"\n', 'version="2.0.0"\n'],
    ['extra spaces around the equals', 'version   =   "1.0.0"\n', 'version   =   "2.0.0"\n'],
  ])('the TOML write pattern tolerates %s', (_label, before, after) => {
    const root = workspace(before, '{"version": "1.0.0"}');
    writeVersion('2.0.0', root);
    expect(readFileSync(join(root, 'pyproject.toml'), 'utf-8')).toBe(after);
  });

  it.each([
    ['no spaces around the colon', '{"version":"1.0.0"}', '{"version":"2.0.0"}'],
    ['extra spaces around the colon', '{"version"  :  "1.0.0"}', '{"version"  :  "2.0.0"}'],
  ])('the JSON write pattern tolerates %s', (_label, before, after) => {
    const root = workspace('version = "1.0.0"\n', before);
    writeVersion('2.0.0', root);
    expect(readFileSync(join(root, 'package.json'), 'utf-8')).toBe(after);
  });
});

describe('checking the canonical files agree', () => {
  it('passes when every file carries the same version', () => {
    const root = workspace('version = "1.0.0"\n', '{"version": "1.0.0"}');
    expect(() => checkInSync(root)).not.toThrow();
  });

  it('reports every file and its version when they disagree', () => {
    // The message has to show WHICH file is wrong; "versions differ" alone leaves the reader to
    // go and diff them by hand.
    const root = workspace('version = "1.0.0"\n', '{"version": "2.0.0"}');
    expect(() => checkInSync(root)).toThrow(
      "version drift across files: {'pyproject.toml': '1.0.0', 'package.json': '2.0.0'}",
    );
  });

  it('passes when the version matches the one the release expects', () => {
    const root = workspace('version = "1.0.0"\n', '{"version": "1.0.0"}');
    expect(() => checkInSync(root, '1.0.0')).not.toThrow();
  });

  it('fails when the files agree with each other but not with the release tag', () => {
    // This is the check that stops a tag being cut against the wrong version.
    const root = workspace('version = "1.0.0"\n', '{"version": "1.0.0"}');
    expect(() => checkInSync(root, '3.0.0')).toThrow("version '1.0.0' != expected '3.0.0'");
  });
});

describe('tolerating the formatting variations these files really carry', () => {
  it.each([
    ['no spaces around the equals', 'version="1.0.0"\n'],
    ['extra spaces around the equals', 'version   =   "1.0.0"\n'],
    ['a tab before the equals', 'version\t= "1.0.0"\n'],
  ])('reads a TOML version written with %s', (_label, pyproject) => {
    // Reads pyproject.toml directly (not readCanonicalVersion, which now resolves to package.json)
    // — this is exercising TOML-parsing robustness, not canonical-source selection.
    const root = workspace(pyproject, '{"version": "1.0.0"}');
    expect(readVersions(root)['pyproject.toml']).toBe('1.0.0');
  });

  it.each([
    ['no spaces around the colon', '{"version":"1.0.0"}'],
    ['extra spaces around the colon', '{"version"  :  "1.0.0"}'],
    ['a newline between key and value', '{"version"\n: "1.0.0"}'],
  ])('reads a JSON version written with %s', (_label, packageJson) => {
    const root = workspace('version = "1.0.0"\n', packageJson);
    expect(readVersions(root)['package.json']).toBe('1.0.0');
  });

  it('ignores a version-like line that is not at the start of a line', () => {
    // Without the line anchor, `# bumped from version = "0.9.0"` in a comment would count as a
    // second version and the file would be rejected as ambiguous. Reads pyproject.toml directly
    // (not readCanonicalVersion, which now resolves to package.json) — same reasoning as the TOML
    // formatting-variation tests above.
    const root = workspace('# was version = "0.9.0"\nversion = "1.0.0"\n', '{"version": "1.0.0"}');
    expect(readVersions(root)['pyproject.toml']).toBe('1.0.0');
  });

  it('reads the repository’s own files when no root is given', () => {
    // The default argument is what the CI validate job and the release scripts rely on.
    expect(readCanonicalVersion()).toMatch(/^\d+\.\d+\.\d+$/);
    expect(() => checkInSync()).not.toThrow();
    expect(Object.keys(readVersions())).toEqual(['pyproject.toml', 'package.json']);
  });

  it('identifies its failures as version errors', () => {
    const root = workspace('[project]\n', '{"version": "1.0.0"}');
    try {
      readVersions(root);
      expect.unreachable('should have thrown');
    } catch (error) {
      expect((error as Error).name).toBe('VersionError');
    }
  });
});
