import { createRequire } from 'node:module';
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

import { afterEach, describe, expect, it } from 'vitest';

import { readRepoFile, repoRoot } from '../../support/repo';
import { tempWorkspace } from '../../support/tempWorkspace';

/**
 * `read-file.js` — all that stands between a shipped tree and the agents OpenCode offers a user.
 * Driven from the SOURCE path, since `dist/` holds only a copy the drift gate keeps identical.
 */

const SOURCE = 'src/content/targets/opencode/read-file.js';

interface ReadFileModule {
  readFile(root: string, relPath: string): string;
  frontmatter(text: string): Record<string, string>;
  stripFrontmatter(text: string): string;
  listMarkdown(root: string, dir: string): string[];
}

const { readFile, frontmatter, stripFrontmatter, listMarkdown } =
  createRequire(import.meta.url)(join(repoRoot, SOURCE)) as ReadFileModule;

describe('the opencode runtime file reader', () => {
  it('reaches nothing but node’s own filesystem — no network, no third party', () => {
    // An allowlist, not a denylist — the only form a newly invented channel cannot walk around.
    const source = readRepoFile(...SOURCE.split('/'));
    const required = [...source.matchAll(/require\(\s*["']([^"']+)["']\s*\)/g)].map((m) => m[1]);
    expect(required.length, 'no require() call found — the scan matched nothing and proves nothing')
      .toBeGreaterThan(0);
    expect([...new Set(required)].sort(), 'read-file.js may require only these node builtins')
      .toEqual(['fs', 'path']);
    // `import()` is a second door into the same room, and it is not spelled `require(`.
    expect(source, 'a dynamic import would bypass the require allowlist entirely').not.toMatch(/\bimport\s*\(/);
  });

  it('serves a document’s body as the prompt, with the frontmatter gone and the edges trimmed', () => {
    const doc = '---\nname: challenger\nmode: subagent\n---\n\n# Challenger\n\nBreak the plan.\n\n';
    expect(stripFrontmatter(doc)).toBe('# Challenger\n\nBreak the plan.');
    // A `---` below the head is a horizontal rule; removing one would delete a whole section.
    expect(stripFrontmatter('# Title\n\n---\n\nBody.\n')).toBe('# Title\n\n---\n\nBody.');
  });

  it('reads the frontmatter fields an agent is published under, and nothing else', () => {
    const fields = frontmatter('---\nname: challenger\nmode: subagent\ndescription: Breaks a plan: on purpose.\n---\nBody\n');
    expect(fields['name']).toBe('challenger');
    expect(fields['mode']).toBe('subagent');
    // Only the FIRST ': ' separates key from value — a description containing a colon keeps it.
    expect(fields['description']).toBe('Breaks a plan: on purpose.');
    expect(frontmatter('# No frontmatter here\n'), 'a document with none has no fields').toEqual({});
  });

  describe('listing what is installed', () => {
    const workspace = tempWorkspace();
    afterEach(() => workspace.cleanup());

    it('returns the markdown stems in sorted order, ignoring everything else', () => {
      const root = workspace.make('hercules-read-file-');
      mkdirSync(join(root, 'agents'));
      for (const name of ['ux-ui-designer.md', 'builder.md', 'challenger.md', 'notes.txt']) {
        writeFileSync(join(root, 'agents', name), 'x', 'utf-8');
      }
      // Sorted, because the order agents are registered in is the order a user sees them offered.
      expect(listMarkdown(root, 'agents')).toEqual(['builder', 'challenger', 'ux-ui-designer']);
      expect(readFile(root, join('agents', 'builder.md'))).toBe('x');
    });

    it('reads a missing directory as empty instead of throwing', () => {
      // A throw here lands in OpenCode's start-up and takes the whole plugin, write gate included.
      const root = workspace.make('hercules-read-file-');
      expect(listMarkdown(root, 'commands')).toEqual([]);
    });
  });
});
