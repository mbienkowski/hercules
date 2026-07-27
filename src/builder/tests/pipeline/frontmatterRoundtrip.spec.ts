import { globSync } from 'node:fs';

import { describe, expect, it } from 'vitest';

import { parseFrontmatter, renderFrontmatter, splitDocument } from '../../parse.mjs';
import { readRepoFile, repoRoot } from '../../../commons/support/repo';

// The KEYSTONE GATE for dist/claude-code byte-identity, checked at the pure-module level: for EVERY
// current dist/claude-code file, splitDocument is lossless ((block ?? '') + body === original) and
// renderFrontmatter(parseFrontmatter(block).metadata) reproduces the block byte-for-byte.

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
