import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';

import { discover, distFiles, load, names } from '../../scripts-ts/build/descriptor.mjs';
import { ECOSYSTEMS, minimal } from '../support/descriptorFixtures';

// Split out of descriptor.spec.ts (CODE_OF_CONDUCT.md's 500-line test-file cap) — see that file's
// header comment for the full split rationale. This file owns the filesystem boundary: discover,
// load, distFiles and their per-process caching, all against real temp directories. See the
// SEPARATE descriptorSort.spec.ts for the vi.mock('node:fs')-based sort-order proof — module-scoped
// mocks must live in their own file, so that proof cannot live here.

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

  it('pins that a bare NaN token crashes load() with a SyntaxError (documented TS/Python divergence)', () => {
    // JSON.parse rejects the non-standard NaN/Infinity/-Infinity tokens that Python's json.loads
    // accepts by default (RFC 8259 forbids them; Python's acceptance is a Python-specific
    // extension). Python would parse this into float('nan') and reject it later through the normal
    // DescriptorError path; this port crashes at JSON.parse, before parseDescriptor ever runs. See
    // the divergence documented at the top of descriptor.mts. A raw NaN token can't be produced via
    // JSON.stringify, so this writes the file's text directly rather than through `minimal()`.
    const root = workspace({ 'eco.json': '{"schema": NaN}' });
    expect(() => load(join(root, 'eco.json'))).toThrow(SyntaxError);
  });

  it('a stray sibling file fails discovery loudly', () => {
    // The directory has a definitive schema: a file that is neither a descriptor nor a
    // '<eco>.dist.<dest>' shipped file must fail — nothing here is ever silently ignored. Exact
    // message (not a substring): a loose `.toThrow('dist')` would not notice the trailing
    // '${pyReprValue([...names].sort())}' clause going missing or malformed.
    const root = workspace({ 'eco.json': JSON.stringify(minimal()), 'notes.md': 'stray' });
    let message = '<did not throw>';
    try {
      discover(root);
    } catch (error) {
      message = (error as Error).message;
    }
    expect(message).toBe(
      "src/ecosystems/notes.md: every sibling file must be named '<ecosystem>.dist.<dest>' " +
        "or '<ecosystem>.template.<dest>' for a known ecosystem ['eco']",
    );
  });

  it('a marker-less stray file whose name happens to start with a known ecosystem name is still rejected', () => {
    // validateLayout reimplements Python's `path.name.partition(marker)` as
    // `entryName.indexOf(marker)` + manual `.slice(0, at)`/`.slice(at + marker.length)`, relying on
    // `if (at === -1) continue` to emulate partition()'s not-found behavior. For a KNOWN ecosystem
    // name of length >= marker.length - 1 (DIST_MARKER '.dist.' is 6 chars; 'cursor' is 6), a stray
    // file named exactly `<name>` + one extra character with NO marker at all (e.g. 'cursorZ') is a
    // genuine adversarial case for that guard: `'cursorZ'.slice(0, -1)` coincidentally equals
    // 'cursor' and `'cursorZ'.slice(-1 + 6)` is coincidentally non-empty ('rZ') — so if the `at ===
    // -1` guard were ever dropped, this file would be WRONGLY accepted as a valid dist sibling
    // instead of rejected as a stray one. It has no '.' anywhere, so it plainly should be rejected.
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
      "src/ecosystems/ghost.dist.CAPABILITIES.md: every sibling file must be named " +
        "'<ecosystem>.dist.<dest>' or '<ecosystem>.template.<dest>' for a known ecosystem ['eco']",
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
      "src/ecosystems/eco.dist.: every sibling file must be named '<ecosystem>.dist.<dest>' " +
        "or '<ecosystem>.template.<dest>' for a known ecosystem ['eco']",
    );
  });

  it('a hidden dotfile is tolerated, not treated as a stray sibling', () => {
    const root = workspace({ 'eco.json': JSON.stringify(minimal()), '.DS_Store': 'x' });
    expect(() => discover(root)).not.toThrow();
  });

  it('a directory literally named <eco>.json is silently skipped, not read as a descriptor', () => {
    // The documented third divergence from Python (see descriptor.mts's top-of-file comment):
    // Python's Path.read_text()/glob("*.json") would crash on this with an unhandled
    // IsADirectoryError; this port's statSync(...).isFile() guard skips it instead. No existing
    // test constructed a REAL directory to prove that guard does anything at all.
    const root = workspace({ 'real.json': JSON.stringify(minimal({ name: 'real' })) });
    mkdirSync(join(root, 'ghost.json'));
    const found = discover(root);
    expect(Object.keys(found)).toEqual(['real']);
  });

  it("validateLayout's OWN isFile() guard silently skips ANY directory sibling, not just dist/template-shaped ones", () => {
    // validateLayout has its OWN statSync(...).isFile() guard (a SEPARATE call site from discover's,
    // tested above) — but it is NOT a Python divergence: descriptor.py's _validate_layout carries
    // the identical `not path.is_file()` guard (line 450), so this is faithful parity, not TS-only
    // defensiveness. A directory NAMED like a valid dist sibling (e.g. 'eco.dist.assets') can't
    // distinguish this guard from no guard at all, because the dist-marker match itself doesn't
    // care whether the entry is a file or a directory — a plain, unmatched directory name is the
    // only input that actually depends on the isFile() check: WITH the guard it's silently skipped
    // (matches every OTHER "not a candidate at all" entry, like a hidden dotfile); WITHOUT it, it
    // would incorrectly fall through to the marker check and get rejected as a stray sibling.
    const root = workspace({ 'eco.json': JSON.stringify(minimal()) });
    mkdirSync(join(root, 'a-plain-directory'));
    expect(() => discover(root)).not.toThrow();
  });

  it("distFiles' OWN isFile() guard excludes a directory shaped exactly like a valid dist sibling", () => {
    // distFiles (unlike validateLayout) is called directly by the build to get actual file paths to
    // copy — a directory sneaking through as if it were a shipped file would later fail when the
    // build tries to read it as one. Python's own dist_files carries the identical `p.is_file()`
    // filter (descriptor.py line 470), so this is parity, not a TS-only safety net. No prior test
    // called distFiles() directly against a directory input; the sibling test above only exercises
    // validateLayout's OWN, separate isFile() call site (reached via discover(), never distFiles()).
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
    // A stray file added AFTER the first discover() call must not be seen — proving the result is
    // cached rather than re-walked, matching the Python original's per-process _CACHE dict.
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
    // `/\.json$/` (anchored) vs `/\.json/` (unanchored, non-global): for a name containing ".json"
    // TWICE, the unanchored form removes the FIRST occurrence and leaves the trailing one intact —
    // mangling the stem into something that still ends in ".json".
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
