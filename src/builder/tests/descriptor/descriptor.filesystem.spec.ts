import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';

import { discover, distFiles, load, names } from '../../descriptor.mjs';
import { ECOSYSTEMS, minimal } from '../../../commons/support/descriptorFixtures';

// The filesystem boundary: discover, load, distFiles and their per-process caching, against real
// temp directories. The sort-order proof needs a module-scoped mock, so it lives in a sibling file.

describe('the filesystem boundary: discover, load, distFiles', () => {
  const dirs: string[] = [];

  function workspace(files: Record<string, string>): string {
    const root = mkdtempSync(join(tmpdir(), 'hercules-descriptor-'));
    dirs.push(root);
    for (const [rel, text] of Object.entries(files)) writeFileSync(join(root, rel), text, 'utf-8');
    return root;
  }

  afterEach(() => {
    while (dirs.length > 0) rmSync(dirs.pop() as string, { recursive: true, force: true });
  });

  it('load uses the filename stem as the descriptor name', () => {
    const root = workspace({ 'eco.json': JSON.stringify(minimal()) });
    expect(load(join(root, 'eco.json')).name).toBe('eco');
  });

  it('pins that a bare NaN token crashes load() with a SyntaxError', () => {
    // JSON.parse rejects the non-standard NaN token (RFC 8259 forbids it), so load() throws before
    // parseDescriptor runs. JSON.stringify cannot emit a raw NaN, hence the hand-written text.
    const root = workspace({ 'eco.json': '{"schema": NaN}' });
    expect(() => load(join(root, 'eco.json'))).toThrow(SyntaxError);
  });

  it('a stray sibling file fails discovery loudly', () => {
    // A file that is neither a descriptor nor a '<eco>.dist.<dest>' sibling must fail, never be
    // silently ignored. The exact match keeps the trailing sorted-names clause from going missing.
    const root = workspace({ 'eco.json': JSON.stringify(minimal()), 'notes.md': 'stray' });
    let message = '<did not throw>';
    try {
      discover(root);
    } catch (error) {
      message = (error as Error).message;
    }
    expect(message).toBe(
      "ecosystems/notes.md: every sibling file must be named '<ecosystem>.dist.<dest>' " +
        "or '<ecosystem>.template.<dest>' for a known ecosystem [\"eco\"]",
    );
  });

  it('a marker-less stray file whose name happens to start with a known ecosystem name is still rejected', () => {
    // validateLayout splits on the marker with `indexOf` + slices, guarded by `if (at === -1)`.
    // 'cursorZ' is that guard's adversarial input: a 6-character ecosystem name and the 6-character
    // '.dist.' marker make a not-found match's slices look like a valid dist sibling.
    const root = workspace({ 'cursor.json': JSON.stringify(minimal({ name: 'cursor' })), 'cursorZ': 'x' });
    expect(() => discover(root)).toThrow(/cursorZ/);
  });

  it('a dist file for an unknown ecosystem fails discovery', () => {
    const root = workspace({
      'eco.json': JSON.stringify(minimal()),
      'ghost.dist.CAPABILITIES.md': 'x',
    });
    let message = '<did not throw>';
    try {
      discover(root);
    } catch (error) {
      message = (error as Error).message;
    }
    expect(message).toBe(
      "ecosystems/ghost.dist.CAPABILITIES.md: every sibling file must be named " +
        "'<ecosystem>.dist.<dest>' or '<ecosystem>.template.<dest>' for a known ecosystem [\"eco\"]",
    );
  });

  it('a dist file with an empty dest fails discovery', () => {
    const root = workspace({ 'eco.json': JSON.stringify(minimal()), 'eco.dist.': 'x' });
    let message = '<did not throw>';
    try {
      discover(root);
    } catch (error) {
      message = (error as Error).message;
    }
    expect(message).toBe(
      "ecosystems/eco.dist.: every sibling file must be named '<ecosystem>.dist.<dest>' " +
        "or '<ecosystem>.template.<dest>' for a known ecosystem [\"eco\"]",
    );
  });

  it('a hidden dotfile is tolerated, not treated as a stray sibling', () => {
    const root = workspace({ 'eco.json': JSON.stringify(minimal()), '.DS_Store': 'x' });
    expect(() => discover(root)).not.toThrow();
  });

  it('a directory literally named <eco>.json is silently skipped, not read as a descriptor', () => {
    // discover()'s own statSync(...).isFile() guard: a directory named like a descriptor is skipped
    // rather than read. This is the only test constructing a REAL directory to prove the guard works.
    const root = workspace({ 'real.json': JSON.stringify(minimal({ name: 'real' })) });
    mkdirSync(join(root, 'ghost.json'));
    const found = discover(root);
    expect(Object.keys(found)).toEqual(['real']);
  });

  it("validateLayout's OWN isFile() guard silently skips ANY directory sibling, not just dist/template-shaped ones", () => {
    // validateLayout's OWN isFile() guard, a separate call site from discover's above. A plain,
    // unmatched directory name is the only input depending on it: guarded, it is skipped like any
    // non-candidate entry; unguarded, it falls through and is wrongly rejected as a stray.
    const root = workspace({ 'eco.json': JSON.stringify(minimal()) });
    mkdirSync(join(root, 'a-plain-directory'));
    expect(() => discover(root)).not.toThrow();
  });

  it("distFiles' OWN isFile() guard excludes a directory shaped exactly like a valid dist sibling", () => {
    // distFiles feeds the build real paths to copy, so a directory sneaking through as a shipped
    // file fails later. This is the only test calling distFiles() directly against a directory.
    const root = workspace({ 'eco.json': JSON.stringify(minimal()) });
    mkdirSync(join(root, 'eco.dist.assets'));
    expect(distFiles('eco', root)).toEqual({});
  });

  it('distFiles derives the destination purely from the filename', () => {
    // The input→output contract: '<eco>.dist.<dest>' maps to plugin-root '<dest>', nothing else
    // consulted — a rename IS a re-route, deterministically.
    const root = workspace({
      'eco.json': JSON.stringify(minimal()),
      'eco.dist.CAPABILITIES.md': 'caps',
      'eco.dist.logo.svg': '<svg/>',
    });
    const files = distFiles('eco', root);
    expect(Object.keys(files).sort()).toEqual(['CAPABILITIES.md', 'logo.svg']);
    expect(files['CAPABILITIES.md']).toContain('eco.dist.CAPABILITIES.md');
  });

  it('distFiles returns nothing for an ecosystem with no shipped siblings', () => {
    const root = workspace({ 'eco.json': JSON.stringify(minimal()) });
    expect(distFiles('eco', root)).toEqual({});
  });
});

describe('discover caches per root', () => {
  it('does not re-read the directory on a second call for the same root', () => {
    // A stray file added AFTER the first discover() call must not be seen — proving the per-process
    // cache serves the second call rather than the directory being re-walked.
    const root = mkdtempSync(join(tmpdir(), 'hercules-descriptor-cache-'));
    try {
      writeFileSync(join(root, 'eco.json'), JSON.stringify(minimal()), 'utf-8');
      const first = discover(root);
      writeFileSync(join(root, 'stray.md'), 'x', 'utf-8');
      expect(() => discover(root)).not.toThrow();
      expect(discover(root)).toBe(first);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });
});

describe('load parses the filename stem correctly even with an unusual name', () => {
  const dirs: string[] = [];
  afterEach(() => {
    while (dirs.length > 0) rmSync(dirs.pop() as string, { recursive: true, force: true });
  });

  it('strips only the trailing .json, not the first occurrence of the substring', () => {
    // `/\.json$/` (anchored) vs `/\.json/`: for a name containing ".json" TWICE, the unanchored
    // form strips the FIRST occurrence, mangling the stem into one that still ends in ".json".
    const root = mkdtempSync(join(tmpdir(), 'hercules-descriptor-stem-'));
    dirs.push(root);
    const raw = minimal({ name: 'a.jsonx' });
    writeFileSync(join(root, 'a.jsonx.json'), JSON.stringify(raw), 'utf-8');
    expect(load(join(root, 'a.jsonx.json')).name).toBe('a.jsonx');
  });
});

describe('discover, names and distFiles resolve the real project ecosystems by default', () => {
  it('names() with no argument returns the same six ecosystems as the explicit path', () => {
    // Exercises the REPO_ROOT/ECOSYSTEMS_DIR default parameter, not just the explicit-root path
    // every other test in this file uses.
    expect(names()).toEqual(names(ECOSYSTEMS));
  });

  it('discover() with no argument returns the same registry as the explicit path', () => {
    expect(Object.keys(discover())).toEqual(Object.keys(discover(ECOSYSTEMS)));
  });
});
