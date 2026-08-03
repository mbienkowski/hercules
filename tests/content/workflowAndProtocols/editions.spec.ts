import { describe, expect, it } from 'vitest';

import {
  commandPath, distFile, editionsOnDisk, PERSONA_PER_TREE, REFERENCE, RUBRIC, shippedFiles, TREES,
} from './editions';

/**
 * The guard over the guards: `TREES` is reconciled against what the builder ships, and every path
 * helper is proved to resolve on every edition. A guard whose target moved must fail, never skip.
 */
describe('the edition list matches what ships', () => {
  it('names every directory under dist/, and no others', () => {
    expect([...TREES].sort(), 'TREES has drifted from dist/. An edition present on disk but missing '
      + 'here is an edition no guard in this repo reads — its content ships unchecked. An edition here '
      + 'but not on disk means every guard for it silently opens nothing.')
      .toEqual(editionsOnDisk());
  });

  it('resolves a persona for every edition', () => {
    expect(Object.keys(PERSONA_PER_TREE).sort(), 'an edition with no persona path mapped would be '
      + 'skipped by the persona guards, which are the ones covering the always-loaded instructions')
      .toEqual([...TREES].sort());
    for (const tree of TREES) {
      expect(distFile(tree, PERSONA_PER_TREE[tree]).length, `dist/${tree} persona is empty`)
        .toBeGreaterThan(0);
    }
  });

  it.each(TREES)('resolves every command path on %s', (tree) => {
    for (const name of ['discover', 'design', 'build', 'ship', 'workflow']) {
      expect(distFile(tree, commandPath(tree, name)).length,
        `dist/${tree}/${commandPath(tree, name)} is empty — a command that resolves to nothing makes `
        + 'every assertion against it vacuous').toBeGreaterThan(0);
    }
  });

  it.each(TREES)('resolves the rubric and the reference skill on %s', (tree) => {
    for (const relativePath of [RUBRIC, REFERENCE]) {
      expect(distFile(tree, relativePath).length, `dist/${tree}/${relativePath} is empty`).toBeGreaterThan(0);
    }
  });

  it.each(TREES)('finds a real file set on %s', (tree) => {
    const files = shippedFiles(tree);
    expect(files.length, `dist/${tree} yielded ${files.length} files — every sweep in this directory `
      + 'iterates this, so a short list is a sweep that reports success over nothing').toBeGreaterThan(10);
  });
});
