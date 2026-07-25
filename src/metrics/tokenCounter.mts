/**
 * cl100k_base token counting, offline and deterministic.
 *
 * Replaces tests/metrics/token_counter.py (Python `tiktoken`). js-tiktoken is a pure-JS port that
 * bundles its rank tables — no network fetch, no cache-warming step, no WASM binary — and its own
 * CI asserts token-ARRAY equality against the Rust core that Python's tiktoken calls, across ZWJ
 * emoji, CJK, whitespace runs and special tokens. `make parity-tokens` re-proves that claim
 * against this repository's actual corpus rather than trusting it.
 *
 * The version is pinned EXACTLY, not with a caret. The sibling package gpt-tokenizer shipped a
 * split-regex fix in 3.3.0 — a minor bump — that changed token counts; under a range, that would
 * have silently moved every budget in tests/testdata/thresholds.json.
 *
 * ── What this metric is, honestly ────────────────────────────────────────────────────────────
 * cl100k_base is OpenAI's encoding, not Claude's. Anthropic publishes no offline tokenizer for
 * Claude 3+ (@anthropic-ai/tokenizer was last released in 2023 and covers Claude 1/2), and the
 * only accurate alternative is a network count_tokens API call, which a hermetic CI gate must not
 * make. So this is a FROZEN, REPRODUCIBLE PROXY for context consumption: the absolute numbers are
 * not Claude tokens, and divergence grows with non-English text, emoji and unusual code. The
 * budgets are calibrated against this proxy, not against a model's context window — which is what
 * a gate against bloat actually needs.
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
