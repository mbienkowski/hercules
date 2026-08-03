import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative, sep } from 'node:path';

import { describe, expect, it } from 'vitest';

import { repoRoot } from '../../support/repo';

/**
 * The folder is what a file MEANS — `agents/**` is an agent, `commands/**` a command — and nothing
 * downstream adds a declaration, so a file's own frontmatter has to agree with where it lives.
 */

const CONTENT = join(repoRoot, 'src', 'content');

/** Every markdown source under src/content/, as forward-slash paths relative to it. */
function markdownSources(dir: string = CONTENT): string[] {
  const found: string[] = [];
  for (const name of readdirSync(dir).sort()) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) {
      if (name !== 'tests') found.push(...markdownSources(path));
    } else if (name.endsWith('.md')) {
      found.push(relative(CONTENT, path).split(sep).join('/'));
    }
  }
  return found;
}

/**
 * The keys `relativePath` declares, whichever conditional branch writes them: the FIRST `---`…`---`
 * pair before the first heading, since frontmatter need not open at byte 0 and `---` is also a rule.
 */
function declaredKeys(relativePath: string): Set<string> {
  const lines = readFileSync(join(CONTENT, relativePath), 'utf-8').split('\n');
  const firstHeading = lines.findIndex((line) => line.startsWith('#'));
  const head = firstHeading === -1 ? lines : lines.slice(0, firstHeading);
  const open = head.indexOf('---');
  const close = open === -1 ? -1 : head.indexOf('---', open + 1);
  if (close === -1) return new Set();
  return new Set(
    head.slice(open + 1, close)
      .map((line) => /^([A-Za-z][\w-]*):/.exec(line)?.[1])
      .filter((key): key is string => key !== undefined),
  );
}

const SOURCES = markdownSources();

/** Every source whose declaration satisfies `holds`, paired with whether it lives under `folder`. */
function disagreements(folder: string, holds: (keys: Set<string>) => boolean): string[] {
  return SOURCES.filter((relativePath) => relativePath.startsWith(`${folder}/`) !== holds(declaredKeys(relativePath)));
}

describe('a file’s shape agrees with the folder it lives in', () => {
  it('both sides of the contract have members to check', () => {
    // Guards the guard: "no file disagrees with its folder" is vacuously true of an empty set.
    expect(SOURCES.filter((relativePath) => relativePath.startsWith('agents/')), 'no agents were found').not.toEqual([]);
    expect(SOURCES.filter((relativePath) => relativePath.startsWith('commands/')), 'no commands were found').not.toEqual([]);
    expect(SOURCES.filter((relativePath) => !relativePath.startsWith('agents/') && !relativePath.startsWith('commands/')),
      'nothing outside agents/ and commands/ was found, so neither "nothing outside" check can fail')
      .not.toEqual([]);
  });

  it('a file declares how it should run exactly when it is an agent', () => {
    // `model` or `tools` is an agent's runtime contract, and no build step supplies a default — an
    // agent without one gets no model at all, and one elsewhere renders where it means nothing.
    const wrong = disagreements('agents', (keys) => keys.has('model') || keys.has('tools'));
    expect(wrong, 'these files declare a runtime contract outside agents/, or are agents without one')
      .toEqual([]);
  });

  it('a file forbids being invoked on its own exactly when it is a command', () => {
    // A command runs when a person asks for it BY NAME; without the marker an assistant may run one itself.
    const wrong = disagreements('commands', (keys) => keys.has('disable-model-invocation'));
    expect(wrong, 'these files carry the command marker outside commands/, or are commands without it')
      .toEqual([]);
  });
});
