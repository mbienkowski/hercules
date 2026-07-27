import { describe, expect, it } from 'vitest';

import { countAtomicInstructions, extractSection } from '../../instructionCounter.mjs';
import { readRepoFile } from '../../../commons/support/repo';

// Hand-labelled fixtures pinning the atomic instruction counter — see instructionCounter.mts's own
// top comment for the unit and separator rules these encode.

describe('countAtomicInstructions: hand-labelled fixtures', () => {
  it('counts one bullet as one directive when it has no separator', () => {
    expect(countAtomicInstructions('- do the thing')).toBe(1);
  });

  it('splits a comma-joined bullet into two directives', () => {
    expect(countAtomicInstructions('- always check the input, never trust it blindly')).toBe(2);
  });

  it('splits on "and" as a whole word, not inside another word', () => {
    // "android" must not false-split on the "and" substring.
    expect(countAtomicInstructions('- support android devices and verify the build')).toBe(2);
  });

  it('splits on "or", "then", and "&"', () => {
    expect(countAtomicInstructions('- fix it or revert the change')).toBe(2);
    expect(countAtomicInstructions('- scaffold then implement the logic')).toBe(2);
    expect(countAtomicInstructions('- lint & format the file')).toBe(2);
  });

  it('drops a fragment under two words as noise', () => {
    // Pins the two-word floor directly: a single-word remainder never earns its own directive.
    expect(countAtomicInstructions('- stop, now')).toBe(1); // "now" alone (1 word) doesn't count
  });

  it('counts a numbered item outside a fence the same way as a bullet', () => {
    expect(countAtomicInstructions('1. read the spec and confirm scope')).toBe(2);
  });

  it('does not count a numbered-looking line outside any list or fence context', () => {
    expect(countAtomicInstructions('See section 2. for details')).toBe(0);
  });

  it('counts a bold-labelled block as its own unit', () => {
    expect(countAtomicInstructions('**Step 1 —** scaffold the class, then write tests')).toBe(2);
  });

  it('counts a numbered rule INSIDE a fence', () => {
    const md = '```\n1. always name the role\n2. never omit the action\n```\n';
    expect(countAtomicInstructions(md)).toBe(2);
  });

  it('ignores a table row (never matches bullet/numbered/bold-label)', () => {
    expect(countAtomicInstructions('| STATUS | Meaning | ACTION |\n|---|---|---|\n| Blocker | x | y |'))
      .toBe(0);
  });

  it('matches a bullet marker followed by more than one space', () => {
    expect(countAtomicInstructions('-   extra spaced bullet')).toBe(1);
  });

  it('matches a numbered marker followed by more than one space', () => {
    expect(countAtomicInstructions('1.   extra spaced number')).toBe(1);
  });

  it('recognizes a bullet indented with leading whitespace', () => {
    expect(countAtomicInstructions('  - indented bullet')).toBe(1);
  });

  it('drops a whitespace-only fragment rather than counting it as a word', () => {
    // The fragment after the comma is pure whitespace — it must contribute zero words, not get
    // miscounted as satisfying the two-word threshold.
    expect(countAtomicInstructions('- word,    ')).toBe(1);
  });

  it('counts two words separated by multiple internal spaces as exactly two', () => {
    expect(countAtomicInstructions('- one   two')).toBe(1); // one unit, no separator, still >=2 words
  });

  it('sums multiple units in one document', () => {
    // String.split consumes the connector, so "two, and three" yields "- two" (2 words, counts) and
    // "three" (1 word, dropped): a short clause beside a connector can fall below the two-word floor.
    const md = '- one\n- two, and three\n1. four';
    expect(countAtomicInstructions(md)).toBe(1 + 1 + 1);
  });
});

describe('extractSection', () => {
  it('returns the slice between start and stop, inclusive of start', () => {
    const text = 'before\n## A\ncontent\n## B\nafter';
    expect(extractSection(text, '## A', '## B')).toBe('## A\ncontent\n');
  });

  it('returns everything from start to the end when stop is omitted', () => {
    const text = 'before\n## A\ncontent';
    expect(extractSection(text, '## A')).toBe('## A\ncontent');
  });

  it('returns everything from start to the end when stop is not found', () => {
    const text = 'before\n## A\ncontent';
    expect(extractSection(text, '## A', '## NEVER')).toBe('## A\ncontent');
  });

  it('returns empty when start is not found', () => {
    expect(extractSection('no headers here', '## A')).toBe('');
  });

  it('returns the full remainder when stop is omitted, even if the text contains the literal word "undefined"', () => {
    // Pins the omitted-stop short-circuit itself: without it, `stop` would flow into
    // `text.indexOf(stop, ...)` as the string "undefined" and truncate the result at that word.
    const text = '## A undefined-marker\nmore content';
    expect(extractSection(text, '## A')).toBe('## A undefined-marker\nmore content');
  });

  it('never searches for stop within the start marker\'s own text', () => {
    // "STOP" appears once, entirely BEFORE the start marker. The search for `stop` must begin only
    // after `start` ends, so this earlier occurrence must never be found.
    const text = 'STOP here ## Section body text';
    expect(extractSection(text, '## Section', 'STOP')).toBe('## Section body text');
  });
});

// The reference measurements this metric is calibrated against, pinned so an edit to the counting
// algorithm or to these exact shipped files fails a test rather than silently drifting what the
// orchestrator waiver (see instructionBudget.spec.ts) measures.
describe('reference chain measurements against real shipped content', () => {
  const claudeMd = readRepoFile('dist', 'claude-code', 'CLAUDE.md');
  const a2a = readRepoFile('dist', 'claude-code', 'protocols', 'a2a-communication-protocol.md');
  const buildMd = readRepoFile('dist', 'claude-code', 'commands', 'build.md');
  const core = extractSection(a2a, '## Agent-Injected Core', '## Orchestrator Section');

  it('CLAUDE.md measures 39', () => {
    expect(countAtomicInstructions(claudeMd)).toBe(39);
  });

  it('the A2A Agent-Injected Core measures 13', () => {
    expect(countAtomicInstructions(core)).toBe(13);
  });

  it('build.md (the heaviest command) measures 83', () => {
    expect(countAtomicInstructions(buildMd)).toBe(83);
  });
});
