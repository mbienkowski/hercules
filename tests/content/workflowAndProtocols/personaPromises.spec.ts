import { describe, expect, it } from 'vitest';

import { distFile, PERSONA_PER_TREE, TREES } from './editions';

/**
 * The persona's communication-style promise: plain, example-backed, professional-level language, never
 * slang or an insult. Pinned across every edition so a future rewrite can't silently drop it.
 */
const COMMUNICATION_STYLE_PROMISE = 'Never use slang, profanity, or anything that could read as an insult.';

describe('the persona\'s communication-style promise ships on every edition', () => {
  it.each(TREES)('%s carries the plain-language, no-insult commitment', (tree) => {
    expect(distFile(tree, PERSONA_PER_TREE[tree]), `dist/${tree}/${PERSONA_PER_TREE[tree]} is missing `
      + 'the communication-style paragraph — a rewrite here would silently reintroduce jargon-heavy, '
      + 'unexplained phrasing toward the user').toContain(COMMUNICATION_STYLE_PROMISE);
  });
});
