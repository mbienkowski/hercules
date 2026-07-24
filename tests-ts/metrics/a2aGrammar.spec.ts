import { describe, expect, it } from 'vitest';

import {
  countCoreEntries, extractA2aCore, extractUsedStatuses, findCoreEntryLines, matchesA2aEntryFormat,
} from '../../scripts-ts/metrics/a2aGrammar.mjs';

// Ported from tests/metrics/test_a2a_grammar.py — each function tested independently.

describe('extractA2aCore', () => {
  it('extracts only the first Core section when multiple fenced blocks exist', () => {
    const md = 'intro\n```\nline a\nline b\n```\ntrailer\n```\nsecond\n```\n';
    const { text, found } = extractA2aCore(md);
    expect(found).toBe(true);
    expect(text).toBe('line a\nline b');
  });

  it('clearly flags a document missing its Core section', () => {
    const { text, found } = extractA2aCore('just prose, no fences');
    expect(found).toBe(false);
    expect(text).toBe('');
  });
});

describe('countCoreEntries', () => {
  it('counts only top-level numbered entries, not their continuation lines', () => {
    const core = '0. zero\n   continuation (indented, not counted)\n1. one\n2. two\nExample: not an entry';
    expect(countCoreEntries(core)).toBe(3);
  });
});

describe('findCoreEntryLines', () => {
  it('finds every [ROLE] STATUS | CONTENT | ACTION line, ignoring prose in between', () => {
    const text = '[QA] Blocker | something is broken | fix it\n' +
      'prose line (ignored)\n' +
      '[ARCH] Pass | reviewed | none\n';
    const lines = findCoreEntryLines(text);
    expect(lines).toHaveLength(2);
    expect(lines[0]?.startsWith('[QA] Blocker')).toBe(true);
    expect(lines[1]?.startsWith('[ARCH] Pass')).toBe(true);
  });
});

describe('matchesA2aEntryFormat', () => {
  it('recognizes a valid entry even with a bare pipe inside its content', () => {
    const validEntries = [
      '[QA] Blocker | something is wrong | fix it',
      '[QA] Pass | reviewed scope x | none',
      '[QA] Medium | content with a|pipe inside | fix it',
    ];
    for (const line of validEntries) expect(matchesA2aEntryFormat(line), line).toBe(true);
  });

  it('rejects an entry with the wrong number of fields', () => {
    const invalidEntries = [
      '[QA] Blocker | only two fields', // one separator
      '[QA] Blocker | a | b | c', // three separators
    ];
    for (const line of invalidEntries) expect(matchesA2aEntryFormat(line), line).toBe(false);
  });
});

describe('extractUsedStatuses', () => {
  it('collects statuses only from correctly formatted entries', () => {
    const md = '[QA] Blocker | x | y\n[ARCH] Info | z | none\n[OLD] Bogus | a | b';
    expect(extractUsedStatuses(md)).toEqual(['Blocker', 'Info']);
  });
});
