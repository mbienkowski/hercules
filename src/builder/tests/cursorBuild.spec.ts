import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { afterEach, describe, expect, it } from 'vitest';

import { buildTarget } from '../bin/cli.mjs';
import { filesUnder, srcStems } from '../../commons/support/buildTree';
import { repoRoot } from '../../commons/support/repo';

// Ported from tests/build/test_cursor_build.py's non-YAML-typed assertions (the frontmatter-TYPE
// checks — e.g. alwaysApply being a real boolean, not the string "false" — need a real YAML parser,
// which lands with commit 10's js-yaml dependency; deferred there rather than adding it early).

const SRC_CONTENT = join(repoRoot, 'src', 'content');

const dirs: string[] = [];

function build(): string {
  const root = mkdtempSync(join(tmpdir(), 'hercules-cursor-build-'));
  dirs.push(root);
  const out = join(root, 'cursor');
  buildTarget('cursor', out);
  return out;
}

afterEach(() => {
  while (dirs.length > 0) rmSync(dirs.pop() as string, { recursive: true, force: true });
});

describe('cursor: load-bearing switch branches actually render non-empty', () => {
  it('every command carries its plan-mode instruction', () => {
    const out = build();
    for (const name of srcStems(SRC_CONTENT, 'commands')) {
      const text = readFileSync(join(out, 'commands', `${name}.md`), 'utf-8');
      expect(text.toLowerCase()).toContain('plan mode');
    }
  });

  it("the persona's cursor write-gate note rendered", () => {
    const out = build();
    const persona = readFileSync(join(out, 'rules', 'hercules-persona.mdc'), 'utf-8');
    expect(persona).toContain('ask-before-applying-edits');
  });

  it('the independent-review handshake-or-HALT branch rendered in design and build', () => {
    const out = build();
    for (const cmd of ['design', 'build']) {
      const text = readFileSync(join(out, 'commands', `${cmd}.md`), 'utf-8');
      expect(text).toContain('HALT and tell the user');
    }
  });
});

describe('cursor: protocol citations resolve to shipped files', () => {
  it('every cited protocols/<file> is actually shipped', () => {
    const out = build();
    const files = filesUnder(out);
    const cited = new Set<string>();
    for (const text of Object.values(files)) {
      for (const m of text.matchAll(/protocols\/([A-Za-z0-9-]+\.md)/g)) cited.add(m[1] as string);
    }
    expect(cited.size).toBeGreaterThan(0);
    for (const fname of cited) {
      expect(files[`protocols/${fname}`]).toBeDefined();
    }
  });
});
