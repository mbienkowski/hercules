import { describe, expect, it } from 'vitest';

import { pyRepr, pyReprMapping, pyReprValue, pySplitlines, pyStrip } from '../pyCompat.mjs';
import { readRepoJson } from '../../commons/support/repo';

// These functions exist to reproduce Python semantics the JavaScript near-equivalents get wrong.
// Every case below is one where `split('\n')`, `trim()` or `JSON.stringify` would give a different
// answer — testing the cases where they agree would prove nothing.

describe('splitting lines the way Python does', () => {
  it('splits on a plain newline', () => {
    expect(pySplitlines('a\nb\nc')).toEqual(['a', 'b', 'c']);
  });

  it('treats a carriage-return/newline pair as one break, not two', () => {
    // `split('\n')` would leave a trailing '\r' on every line of a CRLF file, so the closing
    // frontmatter fence would read as '---\r' and never match.
    expect(pySplitlines('a\r\nb')).toEqual(['a', 'b']);
  });

  it('splits on a lone carriage return', () => {
    expect(pySplitlines('a\rb')).toEqual(['a', 'b']);
  });

  it.each([
    ['form feed', '\u000c'],
    ['line tabulation', '\u000b'],
    ['file separator', '\u001c'],
    ['next line', '\u0085'],
    ['line separator', '\u2028'],
    ['paragraph separator', '\u2029'],
  ])('splits on %s, which split(newline) would miss entirely', (_name, ch) => {
    // A source containing one of these would be split into different lines by the two engines, and
    // frontmatter parsing finds its closing fence by line INDEX.
    expect(pySplitlines(`a${ch}b`)).toEqual(['a', 'b']);
  });

  it('drops the trailing empty segment a final newline would produce', () => {
    // `'a\n'.split('\n')` yields ['a', ''] — the phantom last line.
    expect(pySplitlines('a\n')).toEqual(['a']);
  });

  it('returns nothing at all for an empty string', () => {
    expect(pySplitlines('')).toEqual([]);
  });
});

describe('stripping whitespace the way Python does', () => {
  it('strips ordinary surrounding whitespace', () => {
    expect(pyStrip('  \t hello \n ')).toBe('hello');
  });

  it.each([
    ['unit separator', '\u001f'],
    ['next line', '\u0085'],
    ['file separator', '\u001c'],
  ])('strips %s, which trim() leaves in place', (_name, ch) => {
    expect(pyStrip(`${ch}hello${ch}`)).toBe('hello');
  });

  it('keeps a byte-order mark, which trim() would remove', () => {
    // Python does not treat U+FEFF as whitespace. Trimming it would shift the first line of any
    // UTF-8-BOM source, silently changing where frontmatter starts.
    expect(pyStrip('\ufeffhello')).toBe('\ufeffhello');
  });

  it('leaves an already-tight string untouched', () => {
    expect(pyStrip('hello')).toBe('hello');
  });

  it('reduces an all-whitespace string to nothing', () => {
    expect(pyStrip(' \t\n ')).toBe('');
  });
});

describe('quoting a value into an error message the way Python does', () => {
  it('prefers single quotes', () => {
    // JSON.stringify always double-quotes, so every quoted value in every ported error message
    // would differ from the Python original.
    expect(pyRepr('hello')).toBe("'hello'");
  });

  it('switches to double quotes only to avoid escaping an embedded single quote', () => {
    expect(pyRepr("it's")).toBe('"it\'s"');
  });

  it('keeps single quotes and escapes when the value contains both quote characters', () => {
    expect(pyRepr(`it's "x"`)).toBe(`'it\\'s "x"'`);
  });

  it('escapes a backslash', () => {
    expect(pyRepr('a\\b')).toBe("'a\\\\b'");
  });

  it.each([
    ['newline', '\n', '\\n'],
    ['carriage return', '\r', '\\r'],
    ['tab', '\t', '\\t'],
  ])('escapes a %s', (_name, raw, escaped) => {
    expect(pyRepr(`a${raw}b`)).toBe(`'a${escaped}b'`);
  });

  it('escapes a control character as a two-digit hex escape', () => {
    expect(pyRepr('a\u0001b')).toBe("'a\\x01b'");
  });

  it('escapes a zero-width character that would otherwise be invisible in the message', () => {
    expect(pyRepr('a\u200bb')).toBe("'a\\u200bb'");
  });

  it('passes printable non-ASCII through unescaped', () => {
    // Python 3 keeps printable non-ASCII in repr(); escaping it would make a CJK filename
    // unreadable in a build error.
    expect(pyRepr('是美國')).toBe("'是美國'");
  });
});

describe('rendering a mapping into an error message the way Python does', () => {
  it('uses single quotes and a space after each colon', () => {
    // An f-string interpolating a dict renders this shape; JSON.stringify renders {"a":"1"}.
    expect(pyReprMapping({ a: '1', b: '2' })).toBe("{'a': '1', 'b': '2'}");
  });

  it('renders an empty mapping as empty braces', () => {
    expect(pyReprMapping({})).toBe('{}');
  });

  it('preserves insertion order rather than sorting', () => {
    expect(pyReprMapping({ b: '2', a: '1' })).toBe("{'b': '2', 'a': '1'}");
  });
});

// ── The character tables, asserted against CPython itself ──────────────────────────────────────
// pyCompat reproduces Python's str.isspace(), str.splitlines() and str.isprintable(). Each table is
// a list of characters, and a table entry only earns its place if something exercises it — so these
// walk every entry rather than sampling. The expectations come from tests/testdata/pycompat-golden
// .json, dumped from CPython by builder/pycompat-oracle/gen_pycompat_golden.py, so a typo in the table cannot be
// pinned by a test that shares the typo.

const golden = readRepoJson<{
  whitespace: number[];
  lineBoundaries: number[];
  nonPrintableBelow0x3101: number[];
}>('src', 'builder', 'tests', 'testdata', 'pycompat-golden.json');

describe('the whitespace table matches CPython exactly', () => {
  it.each(golden.whitespace.map((cp) => [`U+${cp.toString(16).padStart(4, '0')}`, cp]))(
    'strips %s',
    (_label, cp) => {
      const ch = String.fromCodePoint(cp as number);
      expect(pyStrip(`${ch}a${ch}`)).toBe('a');
    },
  );

  it('strips nothing CPython would keep', () => {
    // The other direction: over-stripping silently deletes real content. Walks the whole BMP-plus
    // range the golden file covers rather than a sample.
    const shouldStrip = new Set(golden.whitespace);
    const wrong: string[] = [];
    for (let cp = 0; cp <= 0x11000; cp += 1) {
      if (shouldStrip.has(cp)) continue;
      const ch = String.fromCodePoint(cp);
      if (pyStrip(`${ch}a${ch}`) !== `${ch}a${ch}`) wrong.push(`U+${cp.toString(16)}`);
    }
    expect(wrong).toEqual([]);
  });
});

describe('the line-boundary table matches CPython exactly', () => {
  it.each(golden.lineBoundaries.map((cp) => [`U+${cp.toString(16).padStart(4, '0')}`, cp]))(
    'breaks a line at %s',
    (_label, cp) => {
      expect(pySplitlines(`a${String.fromCodePoint(cp as number)}b`)).toEqual(['a', 'b']);
    },
  );

  it('breaks at nothing CPython would leave alone', () => {
    // A spurious break shifts every later line index, which is how frontmatter parsing loses its
    // closing fence.
    const shouldBreak = new Set(golden.lineBoundaries);
    const wrong: string[] = [];
    for (let cp = 0; cp <= 0x11000; cp += 1) {
      if (shouldBreak.has(cp)) continue;
      const ch = String.fromCodePoint(cp);
      if (pySplitlines(`a${ch}b`).length !== 1) wrong.push(`U+${cp.toString(16)}`);
    }
    expect(wrong).toEqual([]);
  });
});

describe('the non-printable table escapes what CPython escapes', () => {
  it('escapes every character CPython considers non-printable in the documented range', () => {
    // pyRepr covers characters up to U+3100 — the realistic domain for a markdown line quoted into
    // an error message. Within it, agreement with CPython must be total.
    const unescaped: string[] = [];
    for (const cp of golden.nonPrintableBelow0x3101) {
      const ch = String.fromCodePoint(cp);
      const repr = pyRepr(`a${ch}b`);
      if (repr.includes(ch)) unescaped.push(`U+${cp.toString(16)}`);
    }
    expect(unescaped).toEqual([]);
  });

  it('leaves printable characters unescaped in the documented range', () => {
    // Escaping a printable character would make a perfectly readable filename unreadable in a
    // build failure.
    const shouldEscape = new Set(golden.nonPrintableBelow0x3101);
    const wrong: string[] = [];
    for (let cp = 0x21; cp <= 0x3100; cp += 1) {
      if (shouldEscape.has(cp)) continue;
      const ch = String.fromCodePoint(cp);
      if (ch === "'" || ch === '\\') continue; // quoting, not printability
      if (!pyRepr(`a${ch}b`).includes(ch)) wrong.push(`U+${cp.toString(16)}`);
    }
    expect(wrong).toEqual([]);
  });
});

describe('quoting an arbitrary not-yet-validated JSON value the way Python does', () => {
  it('renders null as None and booleans as True/False', () => {
    expect(pyReprValue(null)).toBe('None');
    expect(pyReprValue(true)).toBe('True');
    expect(pyReprValue(false)).toBe('False');
  });

  it('renders a number without quotes', () => {
    expect(pyReprValue(42)).toBe('42');
  });

  it('quotes a string the same way pyRepr does', () => {
    expect(pyReprValue('hi')).toBe("'hi'");
  });

  it('renders a list recursively, matching Python’s repr of a list', () => {
    expect(pyReprValue([1, 'a', null, true, { x: 1 }])).toBe("[1, 'a', None, True, {'x': 1}]");
  });

  it('renders a nested object with quoted keys and recursively-reprd values', () => {
    expect(pyReprValue({ a: 'b', c: 1 })).toBe("{'a': 'b', 'c': 1}");
  });

  it('renders an empty list and an empty object', () => {
    expect(pyReprValue([])).toBe('[]');
    expect(pyReprValue({})).toBe('{}');
  });
});
