import { writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';

// vi.mock('node:fs') wraps rather than replaces writeFileSync, so tests hit real disk while the CALL
// ARGUMENTS stay observable — Node treats an empty-string encoding as 'utf-8' for a string payload.
vi.mock('node:fs', async (importOriginal) => {
  const actual = await importOriginal<typeof import('node:fs')>();
  return { ...actual, writeFileSync: vi.fn(actual.writeFileSync) };
});

import { checkInSync, readCanonicalVersion, readVersions, writeVersion } from '../../../internal/release/version-files.mjs';
import { tempWorkspace } from '../../support/tempWorkspace';

const scratch = tempWorkspace();

function workspace(pyproject: string, packageJson: string): string {
  const root = scratch.make('hercules-version-');
  writeFileSync(join(root, 'pyproject.toml'), pyproject, 'utf-8');
  writeFileSync(join(root, 'package.json'), packageJson, 'utf-8');
  vi.mocked(writeFileSync).mockClear();
  return root;
}

afterEach(scratch.cleanup);

// The three an operator relies on: read, write, and the package.json-wins tiebreak.
describe('reading and writing the canonical version files', () => {
  it('reads it from every canonical file', () => {
    const root = workspace('[project]\nversion = "1.2.3"\n', '{\n  "version": "1.2.3"\n}\n');
    expect(readVersions(root)).toEqual({ 'pyproject.toml': '1.2.3', 'package.json': '1.2.3' });
  });

  it('treats package.json as the single source of truth', () => {
    // Deliberately DIFFERENT values, so this proves which file wins rather than passing vacuously.
    const root = workspace('version = "1.1.1"\n', '{"version": "9.9.9"}');
    expect(readCanonicalVersion(root)).toBe('9.9.9');
  });

  it('rewrites every canonical file in place, with explicit utf-8 encoding', () => {
    const root = workspace('[project]\nversion = "1.0.0"\n', '{\n  "version": "1.0.0"\n}\n');
    writeVersion('2.0.0', root);
    expect(readVersions(root)).toEqual({ 'pyproject.toml': '2.0.0', 'package.json': '2.0.0' });
    expect(writeFileSync).toHaveBeenCalledWith(join(root, 'pyproject.toml'), expect.any(String), 'utf-8');
    expect(writeFileSync).toHaveBeenCalledWith(join(root, 'package.json'), expect.any(String), 'utf-8');
  });

  it('refuses a file with no version at all, or one carrying two, rather than reading past it', () => {
    // Guards a missing version line AND a duplicate: a nested `"engines": {"version": …}` misreads silently.
    expect(() => readVersions(workspace('[project]\nname = "x"\n', '{"version": "1.0.0"}'))).toThrow('found 0');
    expect(() => readVersions(workspace('version = "1.0.0"\nversion = "1.0.1"\n', '{"version": "1.0.0"}'))).toThrow('found 2');
  });
});

describe('checking the canonical files agree', () => {
  it('reports every file and its version when they disagree, and when they agree but not with the release tag', () => {
    const drift = workspace('version = "1.0.0"\n', '{"version": "2.0.0"}');
    expect(() => checkInSync(drift)).toThrow(
      "version drift across files: {\"pyproject.toml\":\"1.0.0\",\"package.json\":\"2.0.0\"}",
    );
    const inSync = workspace('version = "1.0.0"\n', '{"version": "1.0.0"}');
    expect(() => checkInSync(inSync, '3.0.0')).toThrow("version \"1.0.0\" != expected \"3.0.0\"");
  });
});
