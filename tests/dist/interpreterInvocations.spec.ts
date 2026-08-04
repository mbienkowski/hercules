import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';

import { describe, expect, it } from 'vitest';

import { repoRoot } from '../support/repo';

// Every shipped instruction that runs one of our own programs must name it by an ABSOLUTE path.
//
// The failure this exists to stop is not cosmetic. An agent runs these commands with the user's
// authority, and its working directory is the repository being worked on. `python3 tools/x.py`
// resolves there — so a repository carrying a file at that path has it executed. A host-resolved
// `${PLUGIN_ROOT}/tools/x.py` cannot be captured that way, and if the variable is ever unset it
// yields `/tools/x.py` and fails loudly rather than running the checkout's copy.

const DIST = join(repoRoot, 'dist');
const ECOSYSTEMS = readdirSync(DIST).filter((name) => statSync(join(DIST, name)).isDirectory());

// An interpreter followed by whatever it is pointed at, up to the first space.
const INVOCATION = /\b(python3?|node|bun|sh|bash)\s+("?)([^\s"']+\.(?:py|js|mjs|cjs|sh))\2/g;

// Only the programs WE ship are our problem: a target repository's own `npm test` is not ours to
// anchor, and neither is a command the user is told to type about their own code.
const OURS = /(?:^|\/)(tools|hooks)\//;

const PROSE = ['.md', '.toml', '.json'];

function proseUnder(root: string): string[] {
  const found: string[] = [];
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir)) {
      const path = join(dir, entry);
      if (statSync(path).isDirectory()) walk(path);
      else if (PROSE.some((suffix) => entry.endsWith(suffix))) found.push(path);
    }
  };
  walk(root);
  return found;
}

/** An invocation is anchored when a host variable or an absolute path precedes our directory. */
function isAnchored(target: string): boolean {
  return target.startsWith('$') || target.startsWith('/') || target.includes('}/');
}

function unanchored(root: string): string[] {
  const found: string[] = [];
  for (const file of proseUnder(root)) {
    const text = readFileSync(file, 'utf-8');
    for (const [, , , target] of text.matchAll(INVOCATION)) {
      if (!target || !OURS.test(target) || isAnchored(target)) continue;
      found.push(`${relative(repoRoot, file)} runs "${target}", resolved against the user's repository`);
    }
  }
  return [...new Set(found)];
}

describe('a shipped instruction never runs one of our programs by a relative path', () => {
  it('at least one ecosystem is built, so the sweep below is never vacuous', () => {
    expect(ECOSYSTEMS.length).toBeGreaterThan(0);
  });

  it.each(ECOSYSTEMS)('%s anchors every invocation of a shipped program', (ecosystem) => {
    expect(unanchored(join(DIST, ecosystem))).toEqual([]);
  });

  it('recognises an unanchored invocation when it sees one', () => {
    // Guard the guard: a matcher that silently stopped matching would pass every ecosystem above.
    const anchored = 'run `python3 ${PLUGIN_ROOT}/tools/state_patch.py apply` to record it';
    const relativeCall = 'run `python3 tools/state_patch.py apply` to record it';
    const matches = (text: string) =>
      [...text.matchAll(INVOCATION)].filter(([, , , t]) => OURS.test(t ?? '') && !isAnchored(t ?? ''));
    expect(matches(relativeCall)).toHaveLength(1);
    expect(matches(anchored)).toHaveLength(0);
  });

  it('leaves a target repository\'s own commands alone', () => {
    // We anchor what we ship. `npm test` in a project's own code-of-conduct is not ours to rewrite.
    const theirs = 'run `python3 scripts/migrate.py` before deploying';
    const matches = [...theirs.matchAll(INVOCATION)].filter(([, , , t]) => OURS.test(t ?? ''));
    expect(matches).toHaveLength(0);
  });
});
