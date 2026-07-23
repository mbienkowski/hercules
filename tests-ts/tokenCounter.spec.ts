import { describe, expect, it } from 'vitest';

import { countTokens, encode } from '../scripts-ts/metrics/tokenCounter.mjs';

// Golden token arrays, generated with Python `tiktoken.get_encoding("cl100k_base")` — the engine
// that produced every budget in tests/testdata/thresholds.json. They are the standing regression
// guard behind `make parity-tokens`: that gate proves the two engines agree on this repo's whole
// corpus, but it needs Python present, so these run in the TypeScript suite alone and would catch
// a tokenizer swap or an unpinned upgrade after Python is gone.
const GOLDEN: ReadonlyArray<readonly [string, number[]]> = [
  ['hello world', [15339, 1917]],
  ['', []],
  ['Hercules', [39, 3035, 2482]],
  ['是美國', [21043, 58666, 12554, 233]],
  ['👩‍👦‍👦', [9468, 239, 102, 378, 235, 9468, 239, 99, 378, 235, 9468, 239, 99]],
  ['- item one\n- item two', [12, 1537, 832, 198, 12, 1537, 1403]],
];

describe('counting cl100k_base tokens', () => {
  it.each(GOLDEN)('tokenizes %j exactly as Python tiktoken does', (text, expected) => {
    expect(encode(text)).toEqual(expected);
  });

  it('reports the token count as the length of the encoding', () => {
    expect(countTokens('hello world')).toBe(2);
    expect(countTokens('')).toBe(0);
  });

  it('refuses text carrying a control token instead of silently encoding it', () => {
    // Python tiktoken raises here too. A document that smuggles <|endoftext|> past the counter
    // would understate its own budget, so both engines reject rather than encode it — and the
    // parity harness compares that refusal like any other result.
    expect(() => encode('<|endoftext|>')).toThrow();
  });

  it('counts a longer string without truncating', () => {
    // Guards against a lazily-bound or partially-loaded rank table: a truncated BPE table still
    // encodes short ASCII correctly while silently mis-encoding anything longer.
    const text = 'The quick brown fox jumps over the lazy dog. '.repeat(20);
    expect(countTokens(text)).toBe(201);
  });
});
