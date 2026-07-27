import { describe, expect, it } from 'vitest';

import {
  ALLOWED_STATUSES, countCoreEntries, extractA2aCore, extractUsedStatuses, findCoreEntryLines,
  matchesA2aEntryFormat,
} from '../../a2aGrammar.mjs';

// A2A (agent-to-agent) grammar helpers, each function covered independently.

describe('ALLOWED_STATUSES', () => {
  it('names exactly the six approved statuses', () => {
    expect(ALLOWED_STATUSES).toEqual(new Set(['Blocker', 'High', 'Medium', 'Nitpick', 'Pass', 'Info']));
  });
});

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

  it('recognizes a fence line even when it carries a language tag after the backticks', () => {
    const md = 'intro\n  ```text\nline a\nline b\n```\ntrailer\n';
    const { text, found } = extractA2aCore(md);
    expect(found).toBe(true);
    expect(text).toBe('line a\nline b');
  });

  it('recognizes a fence line indented with leading whitespace', () => {
    const md = 'intro\n   ```\nline a\n   ```\ntrailer\n';
    const { text, found } = extractA2aCore(md);
    expect(found).toBe(true);
    expect(text).toBe('line a');
  });
});

describe('countCoreEntries', () => {
  it('counts only top-level numbered entries, not their continuation lines', () => {
    const core = '0. zero\n   continuation (indented, not counted)\n1. one\n2. two\nExample: not an entry';
    expect(countCoreEntries(core)).toBe(3);
  });

  it('counts a multi-digit entry number', () => {
    expect(countCoreEntries('9. nine\n10. ten\n11. eleven')).toBe(3);
  });

  it('does not count a digit-dot pattern that is not anchored at the start of the line', () => {
    expect(countCoreEntries('prefix 5. embedded, not an entry\n0. real entry')).toBe(1);
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

  it('trims any leading prose before the entry marker on the same line', () => {
    const lines = findCoreEntryLines('note: [QA] Blocker | something wrong | fix it');
    expect(lines).toEqual(['[QA] Blocker | something wrong | fix it']);
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
