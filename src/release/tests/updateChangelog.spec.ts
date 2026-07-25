import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// vi.mock('node:child_process') is module-scoped and hoisted (see builder/tests/descriptorSort.spec.ts
// for the fuller rationale on why this must sit at the top of the file rather than inline). Fully
// replaced, not wrapped: getCommitsSince() is the ONLY caller of execFileSync anywhere in this
// suite, and every other test in this file supplies its own `commits` array (bypassing
// getCommitsSince entirely), so nothing else here ever needs a real git process.
vi.mock('node:child_process', async (importOriginal) => {
  const actual = await importOriginal<typeof import('node:child_process')>();
  return { ...actual, execFileSync: vi.fn() };
});

// vi.mock('node:fs') wraps (not replaces) writeFileSync/readFileSync so every test still hits real
// disk — only the CALL ARGUMENTS are additionally observable, for tests that need to pin the exact
// encoding/path updateChangelog() passes, which real-filesystem behavior alone can't always
// distinguish (Node treats an empty-string encoding the same as 'utf-8' for a string payload).
vi.mock('node:fs', async (importOriginal) => {
  const actual = await importOriginal<typeof import('node:fs')>();
  return {
    ...actual,
    writeFileSync: vi.fn(actual.writeFileSync),
    readFileSync: vi.fn(actual.readFileSync),
  };
});

import { formatEntry, getCommitsSince, main, updateChangelog } from '../updateChangelog.mjs';

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

beforeEach(() => {
  vi.clearAllMocks();
});

describe('getCommitsSince', () => {
  it('asks git for the range since the given tag, with the exact log flags updateChangelog relies on', () => {
    vi.mocked(execFileSync).mockReturnValueOnce('feat: one\n');
    getCommitsSince('v1.0.0');
    expect(execFileSync).toHaveBeenCalledWith(
      'git',
      ['log', 'v1.0.0..HEAD', '--pretty=format:%s', '--no-merges'],
      { encoding: 'utf-8' },
    );
  });

  it('asks git for the FULL history to HEAD when there is no previous tag', () => {
    vi.mocked(execFileSync).mockReturnValueOnce('feat: one\n');
    getCommitsSince('');
    expect(execFileSync).toHaveBeenCalledWith(
      'git',
      ['log', 'HEAD', '--pretty=format:%s', '--no-merges'],
      { encoding: 'utf-8' },
    );
  });

  it('trims whitespace, drops blank lines, and drops chore(release) commits from the raw git log output', () => {
    // Exercises every stage of the split/map/filter chain in one pass: a padded normal line (must
    // be trimmed AND kept), a chore(release) line (non-empty, must be dropped despite passing the
    // length check), and blank lines from leading/trailing/doubled newlines (must be dropped despite
    // never matching the chore(release) prefix) — together these distinguish `&&` from `||`, both
    // `> 0` neighbors, the `!`, and startsWith from endsWith.
    vi.mocked(execFileSync).mockReturnValueOnce(
      '  feat: add stuff  \nchore(release): bump version\n\n   \nfix: another change\n',
    );
    expect(getCommitsSince('v1.0.0')).toEqual(['feat: add stuff', 'fix: another change']);
  });
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

  it('a subsequent release actually gets prepended — the file is not left untouched', () => {
    // A companion, positive-presence assertion to the two tests above (CODE_OF_CONDUCT.md's Testing
    // section: "pair every absence check with a positive companion assertion"): both of those pass
    // vacuously if updateChangelog's `else` branch silently did nothing at all, since neither
    // "1.1.0 comes before 1.0.0" nor "contains initial release" requires 1.1.0 to be present.
    const cl = tmpChangelog();
    writeFileSync(cl, '## v1.0.0\n\n* feat: initial release\n\n', 'utf-8');
    updateChangelog('v1.1.0', 'v1.0.0', false, cl, V2_COMMITS);
    expect(readFileSync(cl, 'utf-8')).toContain('v1.1.0');
  });

  it('adding a new release keeps older release notes intact', () => {
    const cl = tmpChangelog();
    writeFileSync(cl, '## v1.0.0\n\n* feat: initial release\n\n', 'utf-8');
    updateChangelog('v1.1.0', 'v1.0.0', false, cl, V2_COMMITS);
    expect(readFileSync(cl, 'utf-8')).toContain('initial release');
  });

  it('a subsequent release for a changelog file that does not exist yet treats it as having no prior content', () => {
    // The `else` branch's `existsSync(path) ? readFileSync(...) : ''` ternary's false side, for a
    // release that isn't the project's first but whose changelog file genuinely isn't on disk yet.
    const dir = mkdtempSync(join(tmpdir(), 'hercules-changelog-'));
    dirs.push(dir);
    const cl = join(dir, 'CHANGELOG.md'); // deliberately never created
    updateChangelog('v1.0.0', 'v0.9.0', false, cl, V2_COMMITS);
    expect(readFileSync(cl, 'utf-8')).toBe(formatEntry('v1.0.0', V2_COMMITS));
  });

  it('a commit message that skips the conventional-commit style still gets recorded', () => {
    const cl = tmpChangelog();
    updateChangelog('v1.0.0', '', true, cl, ['Release improvements and proper versioning']);
    expect(readFileSync(cl, 'utf-8')).toContain('Release improvements and proper versioning');
  });

  it('writes the first-release entry with explicit utf-8 encoding, not the platform default', () => {
    const cl = tmpChangelog();
    updateChangelog('v1.0.0', '', true, cl, V1_COMMITS);
    expect(writeFileSync).toHaveBeenCalledWith(cl, expect.any(String), 'utf-8');
  });

  it('reads prior changelog content with explicit utf-8 encoding, not the platform default', () => {
    const cl = tmpChangelog();
    writeFileSync(cl, '## v1.0.0\n\n* feat: initial release\n\n', 'utf-8');
    updateChangelog('v1.1.0', 'v1.0.0', false, cl, V2_COMMITS);
    expect(readFileSync).toHaveBeenCalledWith(cl, 'utf-8');
  });

  it('writes a prepended (non-first) entry with explicit utf-8 encoding, not the platform default', () => {
    const cl = tmpChangelog();
    writeFileSync(cl, '## v1.0.0\n\n* feat: initial release\n\n', 'utf-8');
    updateChangelog('v1.1.0', 'v1.0.0', false, cl, V2_COMMITS);
    expect(writeFileSync).toHaveBeenLastCalledWith(cl, expect.any(String), 'utf-8');
  });

  it('defaults to CHANGELOG.md in the working directory when no path is given', () => {
    // `path`'s default value is only observable through the ARGUMENT it passes onward — actually
    // letting it write would touch this repo's real CHANGELOG.md, so writeFileSync is stubbed to a
    // no-op for this one call rather than delegating to the real filesystem.
    vi.mocked(writeFileSync).mockImplementationOnce(() => undefined);
    updateChangelog('v1.0.0', '', true, undefined, V1_COMMITS);
    expect(writeFileSync).toHaveBeenCalledWith('CHANGELOG.md', expect.any(String), 'utf-8');
  });
});

describe('formatEntry', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("a release's changelog entry lists every commit under its version number", () => {
    const entry = formatEntry('v1.0.0', ['feat: foo', 'fix: bar', 'just a plain message']);
    expect(entry).toContain('* feat: foo');
    expect(entry).toContain('* fix: bar');
    expect(entry).toContain('* just a plain message');
    expect(entry).toContain('v1.0.0');
  });

  it('separates each commit onto its own line, rather than running them together', () => {
    const entry = formatEntry('v1.0.0', ['feat: foo', 'fix: bar']);
    expect(entry).toContain('* feat: foo\n* fix: bar');
  });

  it('an empty commit list still produces a header-only entry, not a malformed one', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 0, 5)); // January 5th: exercises todayIso's own zero-padding too
    expect(formatEntry('v1.0.0', [])).toBe('## v1.0.0 (2026-01-05)\n\n');
  });

  it("the header date is today's date, zero-padded to two digits for both month and day", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 0, 5)); // month index 0 = January, day 5 — both single digits
    expect(formatEntry('v1.0.0', ['feat: x'])).toContain('(2026-01-05)');
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
