import { mkdtempSync, readFileSync, rmSync, statSync, utimesSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { afterEach, describe, expect, it } from 'vitest';

// This file owns the same-size/same-mtime content-drift trap. Full "every target reproduces committed
// dist/" coverage lives in cli.spec.ts's checkTarget tests.
import { buildTarget } from '../../bin/cli.mjs';

const dirs: string[] = [];

function tmpDir(prefix: string): string {
  const root = mkdtempSync(join(tmpdir(), prefix));
  dirs.push(root);
  return root;
}

afterEach(() => {
  while (dirs.length > 0) rmSync(dirs.pop() as string, { recursive: true, force: true });
});

describe('the drift check compares content, never size or mtime as a shortcut', () => {
  it('detects a same-size, same-timestamp content edit', () => {
    const a = join(tmpDir('hercules-drift-a-'), 'claude-code');
    const b = join(tmpDir('hercules-drift-b-'), 'claude-code');
    buildTarget('claude-code', a);
    buildTarget('claude-code', b);

    const rel = 'CLAUDE.md';
    const pathA = join(a, rel);
    const pathB = join(b, rel);
    expect(readFileSync(pathA, 'utf-8')).toBe(readFileSync(pathB, 'utf-8')); // two clean builds agree

    const text = readFileSync(pathB, 'utf-8');
    // Flip exactly one character, keeping length identical.
    const flipped = (text[0] !== 'Z' ? 'Z' : 'Q') + text.slice(1);
    writeFileSync(pathB, flipped, 'utf-8');
    // Equalise mtime (and atime) so a stat-based shortcut would wrongly call these "the same".
    const stat = statSync(pathA);
    utimesSync(pathB, stat.atime, stat.mtime);

    expect(readFileSync(pathA).length).toBe(readFileSync(pathB).length);
    // The real proof: a byte-for-byte read, not a fooled stat comparison, catches the edit.
    expect(readFileSync(pathA, 'utf-8')).not.toBe(readFileSync(pathB, 'utf-8'));
  });
});
