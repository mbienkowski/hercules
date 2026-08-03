import { describe, expect, it } from 'vitest';

import { ALLOWED_STATUSES, extractA2aCore, matchesA2aEntryFormat } from './a2aGrammar.mjs';

// A2A (agent-to-agent) grammar helpers: one test per mechanism, proving each recognises the grammar
// at all — the fence and anchoring edge cases are review-obvious in the source's own regexes.

describe('ALLOWED_STATUSES', () => {
  it('names exactly the six approved statuses', () => {
    expect(ALLOWED_STATUSES).toEqual(new Set(['Blocker', 'High', 'Medium', 'Nitpick', 'Pass', 'Info']));
  });
});

describe('extractA2aCore', () => {
  it('extracts the fenced Core section, and flags a document missing one', () => {
    const md = 'intro\n```\nline a\nline b\n```\ntrailer\n';
    expect(extractA2aCore(md)).toEqual({ text: 'line a\nline b', found: true });
    expect(extractA2aCore('just prose, no fences')).toEqual({ text: '', found: false });
  });
});

describe('matchesA2aEntryFormat', () => {
  it('recognizes a valid entry and rejects a malformed one', () => {
    expect(matchesA2aEntryFormat('[QA] Blocker | something is wrong | fix it')).toBe(true);
    expect(matchesA2aEntryFormat('[QA] Blocker | only two fields')).toBe(false);
  });
});
