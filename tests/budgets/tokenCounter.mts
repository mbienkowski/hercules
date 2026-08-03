/**
 * cl100k_base token counting, offline and deterministic, over js-tiktoken's bundled rank tables.
 * cl100k_base is OpenAI's encoding, not Claude's, so this is a FROZEN, REPRODUCIBLE PROXY for context
 * consumption rather than a Claude token count. js-tiktoken is pinned EXACTLY: a split-regex fix in a
 * minor release would silently move every budget in tests/content/promptBudgets.spec.ts.
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
