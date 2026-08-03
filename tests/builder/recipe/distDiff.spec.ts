import { chmodSync, mkdirSync, utimesSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';

import { describeDifferences, findDifferences, readPermissionBits, listFilesUnder } from '../../../internal/builder/dist-diff.mjs';
import { tempWorkspace } from '../../support/tempWorkspace';

/**
 * Users install the COMMITTED `dist/` tree, so this compares it against a fresh render by BYTES —
 * never size or mtime — and by MODE, since a recipe may ask for its own permission bits.
 */
describe('comparing a fresh render with the committed dist/', () => {
  const scratch = tempWorkspace();
  afterEach(scratch.cleanup);

  function tree(files: Record<string, string>, mode = 0o644): string {
    const root = scratch.make('hercules-diff-');
    for (const [relativePath, text] of Object.entries(files)) {
      const full = join(root, relativePath);
      mkdirSync(join(full, '..'), { recursive: true });
      writeFileSync(full, text, 'utf-8');
      chmodSync(full, mode);
    }
    return root;
  }

  it('sees no difference between two identical trees', () => {
    expect(findDifferences(tree({ 'a.md': 'x\n' }), tree({ 'a.md': 'x\n' }))).toEqual([]);
  });

  it('catches a same-size, same-mtime hand edit to a committed file', () => {
    const committed = tree({ 'a.md': 'aaaa\n' });
    const rendered = tree({ 'a.md': 'bbbb\n' });
    const when = new Date(1_700_000_000_000);
    utimesSync(join(committed, 'a.md'), when, when);
    utimesSync(join(rendered, 'a.md'), when, when);
    expect(findDifferences(committed, rendered)).toEqual([{ relativePath: 'a.md', kind: 'content' }]);
  });

  it('catches a permission change on a file whose bytes are IDENTICAL', () => {
    const committed = tree({ 'hooks/gate.py': 'print(1)\n' }, 0o644);
    const rendered = tree({ 'hooks/gate.py': 'print(1)\n' }, 0o755);
    expect(findDifferences(committed, rendered)).toEqual([{ relativePath: 'hooks/gate.py', kind: 'mode' }]);
  });

  it('says which mode is where, so the fix is obvious from the message alone', () => {
    const committed = tree({ 'hooks/gate.py': 'print(1)\n' }, 0o644);
    const rendered = tree({ 'hooks/gate.py': 'print(1)\n' }, 0o755);
    const [line] = describeDifferences(committed, rendered, findDifferences(committed, rendered));
    expect(line).toContain('MODE 644 in dist/, 755 rendered');
    expect(line).toContain('permissions');
  });

  it('reads a mode as the three-digit octal a recipe would write', () => {
    const root = tree({ 'a.md': 'x\n' }, 0o600);
    expect(readPermissionBits(join(root, 'a.md'))).toBe('600');
  });

  describe('naming the remedy, because stale and stray need different ones', () => {
    it('calls a file nothing declares STRAY, and says to delete it', () => {
      const committed = tree({ 'gone.md': 'x\n' });
      const rendered = tree({});
      expect(describeDifferences(committed, rendered, findDifferences(committed, rendered))[0])
        .toBe('gone.md — STRAY: present in dist/ but declared by no target; delete it');
    });

    it('calls a file the build writes but dist/ lacks MISSING', () => {
      const committed = tree({});
      const rendered = tree({ 'new.md': 'x\n' });
      expect(describeDifferences(committed, rendered, findDifferences(committed, rendered))[0])
        .toContain('new.md — MISSING from dist/');
    });

    it('calls a file present on both sides with different bytes STALE', () => {
      const committed = tree({ 'a.md': 'old\n' });
      const rendered = tree({ 'a.md': 'new\n' });
      expect(describeDifferences(committed, rendered, findDifferences(committed, rendered))[0])
        .toContain('a.md — STALE content');
    });

    it('reports every differing path, sorted, so one run lists the whole job', () => {
      const committed = tree({ 'b.md': 'old\n', 'stray.md': 'x\n' });
      const rendered = tree({ 'a.md': 'new\n', 'b.md': 'new\n' });
      expect(findDifferences(committed, rendered).map((d) => d.relativePath)).toEqual(['a.md', 'b.md', 'stray.md']);
    });
  });

  describe('what counts as a file', () => {
    it('reads a missing root as empty rather than throwing', () => {
      expect(listFilesUnder(join(scratch.make('hercules-diff-'), 'nope')).size).toBe(0);
    });

    it('ignores everything __pycache__ holds, not merely the .pyc files in it', () => {
      // Two rules, not one: the directory is skipped AND `.pyc` is filtered. A planted `.pyc` alone
      // proves only the second, and CPython writes non-`.pyc` entries there too.
      const root = tree({
        'hooks/gate.py': 'x\n',
        'hooks/__pycache__/gate.pyc': 'binary\n',
        'hooks/__pycache__/gate.pyc.140abc': 'a partial write CPython left behind\n',
      });
      expect([...listFilesUnder(root)]).toEqual(['hooks/gate.py']);
    });
  });
});
