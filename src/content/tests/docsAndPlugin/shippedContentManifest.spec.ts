import { createHash } from 'node:crypto';
import { readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs';
import { join, relative, sep } from 'node:path';

import { describe, expect, it } from 'vitest';

import { repoRoot } from '../../../commons/support/repo';

/**
 * Every shipped file, pinned by content hash.
 *
 * Almost everything this plugin ships is prompt text an agent reads and obeys, which makes the whole
 * of `dist/` a normative surface. Three review passes proved that guarding it by sampling does not
 * work: mutation campaigns against the shipped rules found 11, then 29 of 32, then 8 of 10 and 16 of
 * 21 semantic mutations surviving a fully green suite. Not one survivor edited a pinned sentence —
 * each was written on a surface that owned no pin. Selective pinning always loses, because the person
 * writing the contradiction chooses where to write it.
 *
 * This closes that by covering everything. A content change fails here until it is re-blessed, which
 * turns "a rule was quietly reworded" into "someone deliberately re-baselined the shipped content and
 * said why in the commit". That is the whole point: these files decide how every future delivery
 * behaves, so changing them should cost one explicit step.
 *
 * It also makes two separate defects impossible. A `${target:...}` split that keeps one edition
 * correct and changes the other five now fails, because all six editions are hashed independently.
 * And an edition dropped from a test's own list of editions no longer goes unnoticed — the manifest
 * enumerates what ships, so a missing tree is a missing key, not a silently smaller test run.
 *
 * What this does NOT do is check that the content is *right*. It only proves nothing changed
 * unnoticed. The semantic guards are the layer that makes a wrong re-bless fail — the rubric parsers,
 * the whole-sentence rule pins, and the cross-surface sweeps. Neither layer is sufficient alone.
 *
 * Re-bless with `make bless-content` after an intentional edit, in the same commit as the edit.
 */

const MANIFEST = 'src/content/tests/shipped-content.manifest';

/** Compiled Python bytecode is gitignored, machine-specific, and does not ship. */
function isShipped(relPath: string): boolean {
  return !relPath.includes('__pycache__');
}

/** Every shipped file under `dist/`, as `posix/relative/path` → sha256, sorted by path. */
function shippedHashes(): Map<string, string> {
  const root = join(repoRoot, 'dist');
  const out = new Map<string, string>();
  const walk = (dir: string): void => {
    for (const name of readdirSync(dir).sort()) {
      const abs = join(dir, name);
      if (statSync(abs).isDirectory()) walk(abs);
      else {
        const rel = relative(root, abs).split(sep).join('/');
        if (isShipped(rel)) out.set(rel, createHash('sha256').update(readFileSync(abs)).digest('hex'));
      }
    }
  };
  walk(root);
  return new Map([...out].sort(([a], [b]) => (a < b ? -1 : 1)));
}

function formatManifest(hashes: Map<string, string>): string {
  return `${[...hashes].map(([path, sha]) => `${sha}  ${path}`).join('\n')}\n`;
}

function parseManifest(text: string): Map<string, string> {
  const out = new Map<string, string>();
  for (const line of text.split('\n')) {
    if (line.trim() === '' || line.startsWith('#')) continue;
    const [sha, path] = line.split('  ');
    if (sha === undefined || path === undefined) throw new Error(`malformed manifest line: ${line}`);
    out.set(path, sha);
  }
  return out;
}

describe('shipped content is pinned by hash', () => {
  const actual = shippedHashes();

  it('covers a whole plugin rather than a handful of files', () => {
    expect(actual.size, 'the walk found almost nothing — a sweep that opens nothing reports success, '
      + 'and that is the failure mode this pin exists to remove').toBeGreaterThan(150);
    const trees = new Set([...actual.keys()].map((p) => p.split('/')[0]));
    expect([...trees].sort(), 'all six editions must be hashed; an edition absent here is an edition '
      + 'no guard in this repo is reading')
      .toEqual(['claude-code', 'copilot-cli', 'cursor', 'gemini-cli', 'grok-build', 'opencode']);
  });

  it('matches the manifest, file for file', () => {
    if (process.env['BLESS_CONTENT'] === '1') {
      writeFileSync(join(repoRoot, MANIFEST), formatManifest(actual));
      return;
    }
    const expected = parseManifest(readFileSync(join(repoRoot, MANIFEST), 'utf-8'));

    const added = [...actual.keys()].filter((p) => !expected.has(p));
    const removed = [...expected.keys()].filter((p) => !actual.has(p));
    const changed = [...actual].filter(([p, sha]) => expected.has(p) && expected.get(p) !== sha)
      .map(([p]) => p);

    const report = [
      added.length > 0 ? `NEW (${added.length}):\n    ${added.join('\n    ')}` : '',
      removed.length > 0 ? `GONE (${removed.length}):\n    ${removed.join('\n    ')}` : '',
      changed.length > 0 ? `CHANGED (${changed.length}):\n    ${changed.join('\n    ')}` : '',
    ].filter(Boolean).join('\n  ');

    expect(report, `shipped content differs from the manifest.\n\n  ${report}\n\n`
      + 'Every one of these files is read by an agent and acted on, so a change here changes how '
      + 'future deliveries behave. If the change is intended, run `make bless-content` and commit the '
      + 'manifest alongside it, saying in the message what behaviour changed. If it is not intended, '
      + 'this is the regression the pin exists to catch — a reworded rule, a contradicting sentence '
      + 'added beside a correct one, a rule deleted, or a change that reached one edition and not the '
      + 'other five.').toBe('');
  });
});
