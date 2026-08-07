import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';

import { describe, expect, it } from 'vitest';

import { repoRoot } from '../support/repo';

// A cross-artifact contract derived, never listed: the tools an ecosystem's prose tells an agent to
// run, against the tools that ecosystem actually ships. Renaming a tool without its callers, or
// shipping one nothing invokes, fails by name here rather than at a user's first run.

const DIST = join(repoRoot, 'dist');
const ECOSYSTEMS = readdirSync(DIST).filter((name) => statSync(join(DIST, name)).isDirectory());

// `tools/<name>.py` wherever it appears in prose, however the host spells its plugin root.
const REFERENCE = /tools\/((?:[a-z0-9_]+\/)*[a-z0-9_]+\.py)/g;

// Prose, in whatever a host spells it: markdown for most, TOML command files for gemini-cli. The
// `tools/` directory is excluded so a tool mentioning its own name never counts as a caller.
const PROSE = ['.md', '.toml'];

function proseUnder(root: string): string[] {
  const found: string[] = [];
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir)) {
      const path = join(dir, entry);
      if (statSync(path).isDirectory()) {
        if (entry !== 'tools') walk(path);
      } else if (PROSE.some((suffix) => entry.endsWith(suffix))) found.push(path);
    }
  };
  walk(root);
  return found;
}

function referencedTools(root: string): Map<string, string> {
  const cited = new Map<string, string>();
  for (const file of proseUnder(root)) {
    const text = readFileSync(file, 'utf-8');
    for (const match of text.matchAll(REFERENCE)) {
      // The capture group is what names the tool; a match without one means the pattern changed.
      const name = match[1];
      if (name && !cited.has(name)) cited.set(name, relative(repoRoot, file));
    }
  }
  return cited;
}

function shippedTools(root: string): string[] {
  // Recursive: tools are grouped by the feature they serve, so a flat listing would report every
  // grouped tool as unshipped and every reference to one as dangling.
  const found: string[] = [];
  const walk = (dir: string, prefix: string) => {
    for (const entry of readdirSync(dir)) {
      const path = join(dir, entry);
      if (statSync(path).isDirectory()) walk(path, `${prefix}${entry}/`);
      else if (entry.endsWith('.py')) found.push(`${prefix}${entry}`);
    }
  };
  try {
    walk(join(root, 'tools'), '');
  } catch {
    return [];
  }
  return found;
}

describe('every ecosystem ships the tools its own prose invokes', () => {
  it('at least one ecosystem is built, so the sweep below is never vacuous', () => {
    expect(ECOSYSTEMS.length).toBeGreaterThan(0);
  });

  describe.each(ECOSYSTEMS)('%s', (ecosystem) => {
    const root = join(DIST, ecosystem);

    it('names no tool it does not ship', () => {
      const shipped = new Set(shippedTools(root));
      const missing = [...referencedTools(root)].filter(([name]) => !shipped.has(name));
      expect(missing.map(([name, file]) => `${file} runs tools/${name}, which ${ecosystem} does not ship`))
        .toEqual([]);
    });

    it('ships no tool nothing invokes', () => {
      const cited = referencedTools(root);
      const orphans = shippedTools(root).filter((name) => !cited.has(name));
      expect(orphans.map((name) => `${ecosystem} ships tools/${name}, which no prose invokes`))
        .toEqual([]);
    });
  });
});
