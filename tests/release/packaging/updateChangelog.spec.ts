import { readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

import { afterEach, describe, expect, it, vi } from 'vitest';

// vi.mock('node:fs') wraps rather than replaces, so every test still hits real disk and only the CALL
// ARGUMENTS become observable — Node treats an empty-string encoding as 'utf-8' for a string payload.
vi.mock('node:fs', async (importOriginal) => {
  const actual = await importOriginal<typeof import('node:fs')>();
  return {
    ...actual,
    writeFileSync: vi.fn(actual.writeFileSync),
    readFileSync: vi.fn(actual.readFileSync),
  };
});

import { main, updateChangelog } from '../../../internal/release/updateChangelog.mjs';
import { tempWorkspace } from '../../support/tempWorkspace';

const V1_COMMITS = ['feat: initial release', 'chore: add CI'];
const V2_COMMITS = ['feat: add new thing', 'fix: correct bug'];

const workspace = tempWorkspace();

function tmpChangelog(): string {
  return join(workspace.make('hercules-changelog-'), 'CHANGELOG.md');
}

afterEach(workspace.cleanup);

// The two cases an operator hits — first release and subsequent release — driving updateChangelog()
// end to end, which exercises the git-log parsing and entry formatting as a byproduct.
describe('updateChangelog', () => {
  it("a project's first release replaces any leftover content, writing explicit utf-8", () => {
    const cl = tmpChangelog();
    writeFileSync(cl, '## v0.1.0\n\nstale content from a previous run\n\n', 'utf-8');
    updateChangelog('v1.0.0', '', true, cl, V1_COMMITS);
    const content = readFileSync(cl, 'utf-8');
    expect(content).not.toContain('stale content');
    expect(content).toContain('v1.0.0');
    expect(writeFileSync).toHaveBeenCalledWith(cl, expect.any(String), 'utf-8');
  });

  it('a subsequent release is prepended above older notes, which stay intact', () => {
    const cl = tmpChangelog();
    writeFileSync(cl, '## v1.0.0\n\n* feat: initial release\n\n', 'utf-8');
    updateChangelog('v1.1.0', 'v1.0.0', false, cl, V2_COMMITS);
    const content = readFileSync(cl, 'utf-8');
    expect(content).toContain('v1.1.0');
    expect(content).toContain('initial release');
    expect(content.indexOf('1.1.0')).toBeLessThan(content.indexOf('1.0.0'));
  });

  it('a subsequent release for a changelog file that does not exist yet treats it as having no prior content', () => {
    // A release that is not the project's first but whose changelog file is not on disk yet.
    const cl = tmpChangelog();
    updateChangelog('v1.0.0', 'v0.9.0', false, cl, V2_COMMITS);
    expect(readFileSync(cl, 'utf-8')).toContain('v1.0.0');
  });
});

// main(env) is the environment-variable handling split out of bin/updateChangelog.mts.
describe('main', () => {
  it('throws when NEW_TAG is not set, rather than writing a changelog with an empty header', () => {
    expect(() => main({})).toThrow("environment variable 'NEW_TAG' is required");
  });
});
