import { describe, expect, it } from 'vitest';

import { countAtomicInstructions, extractSection } from './instructionCounter.mjs';

// One test per counting mechanism, proving each counts at all. The thresholds themselves are enforced
// by tests/content/promptBudgets.spec.ts, over every shipped command, agent and skill.

describe('countAtomicInstructions', () => {
  it('splits a comma/and-joined bullet into its separate directives', () => {
    expect(countAtomicInstructions('- always check the input, never trust it blindly')).toBe(2);
    expect(countAtomicInstructions('- support android devices and verify the build')).toBe(2);
  });

  it('drops a fragment under two words as noise, and ignores a table row entirely', () => {
    expect(countAtomicInstructions('- stop, now')).toBe(1); // "now" alone (1 word) doesn't count
    expect(countAtomicInstructions('| STATUS | Meaning | ACTION |\n|---|---|---|\n| Blocker | x | y |'))
      .toBe(0);
  });
});

describe('extractSection', () => {
  it('returns the slice between start and stop, inclusive of start', () => {
    const text = 'before\n## A\ncontent\n## B\nafter';
    expect(extractSection(text, '## A', '## B')).toBe('## A\ncontent\n');
  });
});
