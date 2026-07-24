import { mkdtempSync, mkdirSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';

// vi.mock('node:fs') wraps (not replaces) writeFileSync so every test still hits real disk — only
// the CALL ARGUMENTS are additionally observable, for the one test below that needs to pin the
// exact encoding write() passes (content-based verification alone can't distinguish 'utf-8' from ''
// here: Node treats an empty-string encoding identically to 'utf-8' at the byte level for every
// string write() ever writes) — same pattern as tests-ts/build/versionTargets.spec.ts's own
// writeFileSync encoding pin.
vi.mock('node:fs', async (importOriginal) => {
  const actual = await importOriginal<typeof import('node:fs')>();
  return { ...actual, writeFileSync: vi.fn(actual.writeFileSync) };
});

import { EmitError, copyMap, copyVersioned, readSource, write } from '../../scripts-ts/build/emit.mjs';

const dirs: string[] = [];

function workspace(files: Record<string, string> = {}): string {
  const root = mkdtempSync(join(tmpdir(), 'hercules-emit-'));
  dirs.push(root);
  for (const [rel, text] of Object.entries(files)) {
    mkdirSync(dirname(join(root, rel)), { recursive: true });
    writeFileSync(join(root, rel), text, 'utf-8');
  }
  // The setup writes above already called the mocked writeFileSync with 'utf-8' — clearing here
  // means every remaining recorded call in a test belongs to the code under test, not to fixture
  // setup (an unguarded assertion would otherwise trivially match these SETUP calls regardless of
  // what write() itself passes).
  vi.mocked(writeFileSync).mockClear();
  return root;
}

afterEach(() => {
  while (dirs.length > 0) rmSync(dirs.pop() as string, { recursive: true, force: true });
});

const mode = (path: string): string => (statSync(path).mode & 0o777).toString(8);

describe('writing a file into the build output', () => {
  it('creates any missing parent directories', () => {
    const root = workspace();
    write(join(root, 'a/b/c.md'), 'hello\n');
    expect(readFileSync(join(root, 'a/b/c.md'), 'utf-8')).toBe('hello\n');
  });

  it('emits it readable but not executable', () => {
    const root = workspace();
    write(join(root, 'out.md'), 'x');
    expect(mode(join(root, 'out.md'))).toBe('644');
  });

  it('writes with explicit utf-8 encoding, not the platform default', () => {
    const root = workspace();
    write(join(root, 'out.md'), 'x');
    expect(writeFileSync).toHaveBeenCalledWith(join(root, 'out.md'), 'x', 'utf-8');
  });
});

describe('copying files into the build output', () => {
  it('copies each mapped source to its destination and reports what it wrote', () => {
    const root = workspace({ 'in/a.md': 'A', 'in/b.md': 'B' });
    const written = copyMap(
      join(root, 'in'),
      root,
      new Map([
        ['a.md', 'out/a.md'],
        ['b.md', 'out/b.md'],
      ]),
    );
    expect(written).toEqual(['out/a.md', 'out/b.md']);
    expect(readFileSync(join(root, 'out/a.md'), 'utf-8')).toBe('A');
  });

  it('normalises the destination mode instead of inheriting the source’s', () => {
    // Node's copyFileSync propagates the SOURCE's permission bits while Python's shutil.copyfile
    // leaves the destination at the umask. Every file in the committed dist/ tree is 100644, and a
    // byte comparison cannot see a mode — so an executable source would silently emit an
    // executable file and surface later as a spurious permission change.
    const root = workspace({ 'in/tool.md': 'x' });
    // eslint-disable-next-line no-bitwise
    require('node:fs').chmodSync(join(root, 'in/tool.md'), 0o755);
    copyMap(join(root, 'in'), root, new Map([['tool.md', 'out/tool.md']]));
    expect(mode(join(root, 'out/tool.md'))).toBe('644');
  });
});

describe('injecting the version into a manifest', () => {
  it('substitutes the token and leaves every other byte alone', () => {
    // A pure string replace, never a JSON round-trip: re-serialising would reorder keys, change
    // indentation and drop the trailing newline, all of which are dist/ bytes under a drift gate.
    const root = workspace({ 'src.json': '{\n  "version": "${version}",\n  "b": 1\n}\n' });
    copyVersioned(join(root, 'src.json'), join(root, 'out.json'), '1.2.3');
    expect(readFileSync(join(root, 'out.json'), 'utf-8')).toBe('{\n  "version": "1.2.3",\n  "b": 1\n}\n');
  });

  it('refuses a manifest carrying no version token', () => {
    // Failing open here would ship a manifest with no version at all.
    const root = workspace({ 'src.json': '{"b":1}' });
    expect(() => copyVersioned(join(root, 'src.json'), join(root, 'o.json'), '1.2.3')).toThrow(
      EmitError,
    );
    expect(() => copyVersioned(join(root, 'src.json'), join(root, 'o.json'), '1.2.3')).toThrow(
      'found 0',
    );
  });

  it('refuses a manifest carrying more than one version token', () => {
    // Two tokens means the author expected something this function does not do; guessing which one
    // matters would be worse than stopping.
    const root = workspace({ 'src.json': '{"a":"${version}","b":"${version}"}' });
    expect(() => copyVersioned(join(root, 'src.json'), join(root, 'o.json'), '1.2.3')).toThrow(
      'found 2',
    );
  });
});

describe('reading a source file', () => {
  it('reads valid UTF-8 including non-ASCII content', () => {
    const root = workspace({ 'a.md': '是美國 — em dash\n' });
    expect(readSource(join(root, 'a.md'))).toBe('是美國 — em dash\n');
  });

  it('refuses a file that is not valid UTF-8 instead of silently mangling it', () => {
    // Node substitutes U+FFFD for a malformed byte sequence while Python raises. Without this
    // check a corrupted source would build cleanly here and refuse to build there — the two
    // engines disagreeing about whether the repository is even valid.
    const root = workspace();
    writeFileSync(join(root, 'bad.md'), Buffer.from([0x61, 0xff, 0xfe, 0x62]));
    expect(() => readSource(join(root, 'bad.md'))).toThrow(EmitError);
    expect(() => readSource(join(root, 'bad.md'))).toThrow('not valid UTF-8');
  });

  it('accepts a replacement character that genuinely is in the source', () => {
    // U+FFFD is a legitimate character; only a MANUFACTURED one indicates a decode failure.
    const root = workspace({ 'ok.md': 'literal � here\n' });
    expect(readSource(join(root, 'ok.md'))).toBe('literal � here\n');
  });
});

describe('identifying its own failures', () => {
  it('names emit errors as such', () => {
    const root = workspace({ 'src.json': '{}' });
    try {
      copyVersioned(join(root, 'src.json'), join(root, 'o.json'), '1.0.0');
      expect.unreachable('should have thrown');
    } catch (error) {
      expect((error as Error).name).toBe('EmitError');
    }
  });

  it('reads a file with no replacement character at all without re-decoding it', () => {
    // The strict re-decode is only reached when a replacement character is present; ordinary
    // sources must not pay for it. Counts constructions of the global TextDecoder — content alone
    // can't distinguish this from an always-re-decode implementation, since re-decoding
    // already-valid UTF-8 produces an identical result either way; only the CONSTRUCTION COUNT
    // tells them apart (`text.includes('')` is always true, which would make every source
    // re-decode unconditionally). A `class extends TextDecoder`, not `vi.fn(TextDecoder)`: wrapping
    // a native constructor in a plain mock function breaks its `new`-ability (the resulting
    // "instance" loses `.decode`), a class subclass does not.
    let constructions = 0;
    class CountingTextDecoder extends TextDecoder {
      constructor(...args: ConstructorParameters<typeof TextDecoder>) {
        super(...args);
        constructions += 1;
      }
    }
    vi.stubGlobal('TextDecoder', CountingTextDecoder);
    try {
      const root = workspace({ 'plain.md': 'ordinary ascii\n' });
      expect(readSource(join(root, 'plain.md'))).toBe('ordinary ascii\n');
      expect(constructions).toBe(1);
    } finally {
      vi.unstubAllGlobals();
    }
  });
});

describe('preserving a byte-order mark', () => {
  it('keeps a leading BOM rather than silently stripping it', () => {
    // TextDecoder's default strips U+FEFF; Python's read_text preserves it. Stripping it would
    // change the first byte of the emitted file, invisibly, in the very function written to close
    // the UTF-8 decoding divergence.
    const root = workspace({ 'bom.md': '\ufeffcontent\n' });
    expect(readSource(join(root, 'bom.md'))).toBe('\ufeffcontent\n');
  });

  it('carries the BOM through a versioned copy', () => {
    const root = workspace({ 'src.json': '\ufeff{"version": "${version}"}' });
    copyVersioned(join(root, 'src.json'), join(root, 'out.json'), '1.0.0');
    expect(readFileSync(join(root, 'out.json'), 'utf-8')).toBe('\ufeff{"version": "1.0.0"}');
  });
});
