import { describe, expect, it } from 'vitest';

import { countTokens, encode } from './tokenCounter.mjs';

// Golden pin on the cl100k_base encoding every budget is measured against: a tokenizer swap or an
// unpinned upgrade changes these ids and fails here rather than silently moving every budget.
const GOLDEN: ReadonlyArray<readonly [string, number[]]> = [
  ['hello world', [15339, 1917]],
  ['是美國', [21043, 58666, 12554, 233]],
];

describe('counting cl100k_base tokens', () => {
  it.each(GOLDEN)('tokenizes %j exactly as Python tiktoken does', (text, expected) => {
    expect(encode(text)).toEqual(expected);
  });

  it('reports the token count as the length of the encoding', () => {
    expect(countTokens('hello world')).toBe(2);
  });
});
