/**
 * cl100k_base token counting, offline and deterministic, over js-tiktoken's bundled rank tables.
 *
 * cl100k_base is OpenAI's encoding, not Claude's: Anthropic publishes no offline tokenizer, and the
 * only accurate alternative is a network count_tokens call a hermetic CI gate must not make. So this
 * is a FROZEN, REPRODUCIBLE PROXY for context consumption — the absolute numbers are not Claude
 * tokens, and divergence grows with non-English text, emoji and unusual code. Budgets are calibrated
 * against this proxy rather than a model's context window, which is what a gate against bloat needs.
 *
 * The js-tiktoken version is pinned EXACTLY, not with a caret: a tokenizer minor release can carry a
 * split-regex fix that silently moves every budget in src/metrics/tests/testdata/thresholds.json.
 */

import { Tiktoken } from 'js-tiktoken/lite';
import cl100kBase from 'js-tiktoken/ranks/cl100k_base';

// Module-level singleton: the rank table is ~1 MB and parsing it per call would dominate runtime.
const encoder = new Tiktoken(cl100kBase);

/** Token ids for `text` under cl100k_base. */
export function encode(text: string): number[] {
  return encoder.encode(text);
}

/** Number of cl100k_base tokens in `text`. */
export function countTokens(text: string): number {
  return encoder.encode(text).length;
}
