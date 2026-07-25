import { globSync } from 'node:fs';

import { describe, expect, it } from 'vitest';

import { parseFrontmatter, renderFrontmatter, splitDocument } from '../parse.mjs';
import { readRepoFile, repoRoot } from '../../tests/support/repo';

// Ported from tests/build/test_frontmatter_roundtrip.py — the KEYSTONE GATE for dist/claude-code
// byte-identity. That byte-identity (proven elsewhere by cli.spec.ts's checkTarget()===0 assertions
// against the whole build pipeline) rests entirely on these two properties holding for EVERY
// current dist/claude-code file, checked here directly at the pure-module level rather than only
// implied through the full pipeline:
//   1. splitDocument is lossless: (block ?? '') + body === original.
//   2. renderFrontmatter(parseFrontmatter(block).metadata) reproduces the frontmatter block
//      byte-for-byte.
//
// The Python original's "a value containing a triple dash isn't mistaken for the fence" synthetic
// case is already covered, with the same assertion, by parse.spec.ts's "does not mistake a value
// containing three dashes for the closing fence" — not duplicated here.

const CORPUS = globSync('dist/claude-code/**/*.md', { cwd: repoRoot }).sort();

describe('the real dist/claude-code corpus the byte-identity gate depends on', () => {
  it('is not accidentally empty', () => {
    // The two round-trip checks below only prove anything if they run against a real, populated
    // corpus — an empty glob would let both pass while testing nothing at all.
    expect(CORPUS.length).toBeGreaterThanOrEqual(25);
  });

  it.each(CORPUS)('splitting %s into metadata and content loses no bytes', (rel) => {
    const raw = readRepoFile(rel);
    const { block, body } = splitDocument(raw);
    expect((block ?? '') + body).toBe(raw);
  });

  it.each(CORPUS)('rewriting %s’s metadata header reproduces it exactly', (rel) => {
    const raw = readRepoFile(rel);
    const { block } = splitDocument(raw);
    if (block === null) return; // no frontmatter in this file — nothing to round-trip
    const { metadata } = parseFrontmatter(block);
    // renderFrontmatter yields the fenced block without a trailing newline; the block carries one.
    expect(`${renderFrontmatter(metadata)}\n`).toBe(block);
  });
});
