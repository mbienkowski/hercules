/**
 * Token-parity harness, TypeScript side. Reads the corpus Python built and prints canonical JSON
 * in exactly the shape scripts/ci/token_parity.py's `dump` mode prints, so the two are byte-diffed.
 *
 * Deliberately logic-free beyond the tokenize-and-serialise loop: it must not resolve files,
 * extract text, or filter anything. Every such decision belongs to the corpus builder, so that a
 * disagreement between the engines can only ever mean the tokenizers disagree.
 *
 * Usage: node .ts-out/bin/tokenParity.mjs <corpus.json>
 */

import { readFileSync } from 'node:fs';

import { encode } from '../metrics/tokenCounter.mjs';

interface CorpusEntry {
  id: string;
  text: string;
}

const corpusPath = process.argv[2];
if (corpusPath === undefined) {
  process.stderr.write('usage: node .ts-out/bin/tokenParity.mjs <corpus.json>\n');
  process.exit(2);
}

const corpus = JSON.parse(readFileSync(corpusPath, 'utf-8')) as CorpusEntry[];

// A refusal is part of the contract. Both engines reject text containing a special token such as
// `<|endoftext|>` rather than encoding it, so a throwing entry is recorded and compared like any
// other result rather than excluded from the corpus.
const out = corpus.map((entry) => {
  try {
    return { id: entry.id, throws: false, tokens: encode(entry.text) as number[] | null };
  } catch {
    return { id: entry.id, throws: true, tokens: null };
  }
});

// Mirrors Python's json.dumps(..., indent=1, ensure_ascii=False, sort_keys=True) + "\n".
// Object keys are emitted in the sorted order Python produces (id, throws, tokens) and entries are
// pre-sorted by the corpus builder, so a plain stringify reproduces it byte-for-byte.
process.stdout.write(`${JSON.stringify(out, null, 1)}\n`);
