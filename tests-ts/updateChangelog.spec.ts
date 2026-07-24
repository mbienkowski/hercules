import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { afterEach, describe, expect, it, vi } from 'vitest';

import { formatEntry, main, updateChangelog } from '../scripts-ts/updateChangelog.mjs';

// Ported from tests/release/test_update_changelog.py.

const V1_COMMITS = ['feat: initial release', 'chore: add CI'];
const V2_COMMITS = ['feat: add new thing', 'fix: correct bug'];

const dirs: string[] = [];

function tmpChangelog(): string {
  const dir = mkdtempSync(join(tmpdir(), 'hercules-changelog-'));
  dirs.push(dir);
  return join(dir, 'CHANGELOG.md');
}

afterEach(() => {
  while (dirs.length > 0) rmSync(dirs.pop() as string, { recursive: true, force: true });
});

describe('updateChangelog', () => {
  it("a project's first release replaces any leftover changelog content", () => {
    const cl = tmpChangelog();
    writeFileSync(cl, '## v0.1.0\n\nstale content from a previous run\n\n', 'utf-8');
    updateChangelog('v1.0.0', '', true, cl, V1_COMMITS);
    const content = readFileSync(cl, 'utf-8');
    expect(content).not.toContain('stale content');
    expect(content).toContain('v1.0.0');
  });

  it('the newest release notes appear above older ones', () => {
    const cl = tmpChangelog();
    writeFileSync(cl, '## v1.0.0\n\n* feat: initial release\n\n', 'utf-8');
    updateChangelog('v1.1.0', 'v1.0.0', false, cl, V2_COMMITS);
    const content = readFileSync(cl, 'utf-8');
    expect(content.indexOf('1.1.0')).toBeLessThan(content.indexOf('1.0.0'));
  });

  it('adding a new release keeps older release notes intact', () => {
    const cl = tmpChangelog();
    writeFileSync(cl, '## v1.0.0\n\n* feat: initial release\n\n', 'utf-8');
    updateChangelog('v1.1.0', 'v1.0.0', false, cl, V2_COMMITS);
    expect(readFileSync(cl, 'utf-8')).toContain('initial release');
  });

  it('a commit message that skips the conventional-commit style still gets recorded', () => {
    const cl = tmpChangelog();
    updateChangelog('v1.0.0', '', true, cl, ['Release improvements and proper versioning']);
    expect(readFileSync(cl, 'utf-8')).toContain('Release improvements and proper versioning');
  });

  it("a release's changelog entry lists every commit under its version number", () => {
    const entry = formatEntry('v1.0.0', ['feat: foo', 'fix: bar', 'just a plain message']);
    expect(entry).toContain('* feat: foo');
    expect(entry).toContain('* fix: bar');
    expect(entry).toContain('* just a plain message');
    expect(entry).toContain('v1.0.0');
  });
});

// main(env) is the environment-variable handling split out of bin/updateChangelog.mts (an
// entry-point guard cannot be covered directly — see that file's own comment). The injectable
// `updateChangelogFn` param (purely for test benefit) verifies main()'s env parsing in isolation,
// without touching real git/filesystem state — updateChangelog()'s own real behavior is already
// covered directly by the describe block above. Avoids process.chdir(), which Stryker's
// worker-thread test runner rejects ("process.chdir() is not supported in workers").
describe('main', () => {
  it('throws when NEW_TAG is not set, rather than writing a changelog with an empty header', () => {
    expect(() => main({})).toThrow("environment variable 'NEW_TAG' is required");
  });

  it('forwards NEW_TAG, PREV_TAG, and IS_FIRST=true to updateChangelog', () => {
    const fn = vi.fn();
    main({ NEW_TAG: 'v1.0.0', PREV_TAG: 'v0.9.0', IS_FIRST: 'true' }, fn);
    expect(fn).toHaveBeenCalledWith('v1.0.0', 'v0.9.0', true);
  });

  it('PREV_TAG defaults to the empty string when unset', () => {
    const fn = vi.fn();
    main({ NEW_TAG: 'v1.0.0' }, fn);
    expect(fn).toHaveBeenCalledWith('v1.0.0', '', false);
  });

  it('IS_FIRST defaults to false when unset', () => {
    const fn = vi.fn();
    main({ NEW_TAG: 'v1.0.0', PREV_TAG: 'v0.9.0' }, fn);
    expect(fn).toHaveBeenCalledWith('v1.0.0', 'v0.9.0', false);
  });

  it('IS_FIRST is case-insensitive and only "true" means true', () => {
    const fn = vi.fn();
    main({ NEW_TAG: 'v1.0.0', IS_FIRST: 'TRUE' }, fn);
    expect(fn).toHaveBeenCalledWith('v1.0.0', '', true);
    fn.mockClear();
    main({ NEW_TAG: 'v1.0.0', IS_FIRST: 'yes' }, fn);
    expect(fn).toHaveBeenCalledWith('v1.0.0', '', false);
  });
});
