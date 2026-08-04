import { describe, expect, it } from 'vitest';

import { distFile, PERSONA_PER_TREE, TREES } from './editions';

/**
 * The persona's communication-style promise: plain, example-backed, professional-level language, never
 * slang or an insult. Pinned across every edition so a future rewrite can't silently drop it.
 */
const COMMUNICATION_STYLE_PROMISE = 'Never use slang, profanity, or anything that could read as an insult.';

/** The reading-level target — pinned so a rewrite can't silently drop the B2/C1 commitment. */
const READING_LEVEL_PROMISE = 'CEFR (Common European Framework of Reference for Languages) B2/C1';

/**
 * How the persona judges abbreviation familiarity — by the user's own usage and the current domain,
 * not a fixed word list. Pinned after this exact bullet was rewritten three times in one session.
 */
const ABBREVIATION_JUDGEMENT_PROMISE = 'Skip an abbreviation already familiar — user-used/universal/domain-common';

describe('the persona\'s communication-style promise ships on every edition', () => {
  it.each(TREES)('%s carries the plain-language, no-insult commitment', (tree) => {
    expect(distFile(tree, PERSONA_PER_TREE[tree]), `dist/${tree}/${PERSONA_PER_TREE[tree]} is missing `
      + 'the communication-style paragraph — a rewrite here would silently reintroduce jargon-heavy, '
      + 'unexplained phrasing toward the user').toContain(COMMUNICATION_STYLE_PROMISE);
  });

  it.each(TREES)('%s carries the CEFR B2/C1 reading-level target', (tree) => {
    expect(distFile(tree, PERSONA_PER_TREE[tree]), `dist/${tree}/${PERSONA_PER_TREE[tree]} is missing `
      + 'the reading-level target — a rewrite here would silently drop the plain-language bar').toContain(READING_LEVEL_PROMISE);
  });

  it.each(TREES)('%s judges abbreviation familiarity by usage and domain, not a fixed list', (tree) => {
    expect(distFile(tree, PERSONA_PER_TREE[tree]), `dist/${tree}/${PERSONA_PER_TREE[tree]} is missing `
      + 'the abbreviation-judgement rule — a rewrite here would silently reintroduce a fixed word list '
      + 'or over-explain common terms').toContain(ABBREVIATION_JUDGEMENT_PROMISE);
  });
});
