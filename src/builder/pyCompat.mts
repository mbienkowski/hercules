/**
 * Faithful ports of the two Python string primitives whose JavaScript near-equivalents differ.
 *
 * These exist because the compiler must reproduce `dist/` BYTE-for-byte, and both differences are
 * silent: they give a plausible result on ordinary input and a different one on input nobody
 * thought to test.
 *
 * Not hypothetical dogma - `parse.parseFrontmatter` calls both on every markdown source under
 * `content/`, so a file carrying one of these characters would compile differently under the
 * two engines while every ASCII fixture kept agreeing.
 *
 * Every character is written as a \uXXXX escape, never a literal: these are invisible bytes, and a
 * table of them is unreviewable and un-greppable in raw form. Both tables are generated from
 * CPython and pinned by builder/tests/pyCompat.spec.ts.
 */

/**
 * The boundaries Python's `str.splitlines()` recognises.
 *
 * JavaScript's `split('\n')` recognises exactly one; Python recognises these ten, and treats CRLF
 * as a single break. `parse.parseFrontmatter` locates the closing `---` fence by line INDEX, so one
 * spurious extra line silently shifts where frontmatter ends and the body begins.
 */
const LINE_BOUNDARIES = new Set([
  '\u000a', // LINE FEED
  '\u000d', // CARRIAGE RETURN - CRLF is collapsed to one boundary below
  '\u000b', // LINE TABULATION
  '\u000c', // FORM FEED
  '\u001c', // FILE SEPARATOR
  '\u001d', // GROUP SEPARATOR
  '\u001e', // RECORD SEPARATOR
  '\u0085', // NEXT LINE
  '\u2028', // LINE SEPARATOR
  '\u2029', // PARAGRAPH SEPARATOR
]);

/** Python's `str.splitlines()`. */
export function pySplitlines(text: string): string[] {
  if (text === '') return [];
  const lines: string[] = [];
  let current = '';
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i] as string;
    if (!LINE_BOUNDARIES.has(ch)) {
      current += ch;
      continue;
    }
    if (ch === '\u000d' && text[i + 1] === '\u000a') i += 1;
    lines.push(current);
    current = '';
  }
  if (current !== '') lines.push(current);
  return lines;
}

/**
 * The characters Python's `str.strip()` removes - every one for which `str.isspace()` is true.
 *
 * The set differs from `String.prototype.trim()` at BOTH ends: Python strips the C0/C1 separators
 * and NEXT LINE, which JavaScript leaves; JavaScript strips U+FEFF (BOM), which Python leaves.
 * Trimming a BOM that Python keeps would silently shift the first line of a UTF-8-BOM source.
 */
const PY_WHITESPACE = new Set([
  '\u0009', // CHARACTER TABULATION
  '\u000a', // LINE FEED
  '\u000b', // LINE TABULATION
  '\u000c', // FORM FEED
  '\u000d', // CARRIAGE RETURN
  '\u0020', // SPACE
  '\u001c', // FILE SEPARATOR
  '\u001d', // GROUP SEPARATOR
  '\u001e', // RECORD SEPARATOR
  '\u001f', // UNIT SEPARATOR
  '\u0085', // NEXT LINE
  '\u00a0', // NO-BREAK SPACE
  '\u1680', // OGHAM SPACE MARK
  '\u2000', // EN QUAD
  '\u2001', // EM QUAD
  '\u2002', // EN SPACE
  '\u2003', // EM SPACE
  '\u2004', // THREE-PER-EM SPACE
  '\u2005', // FOUR-PER-EM SPACE
  '\u2006', // SIX-PER-EM SPACE
  '\u2007', // FIGURE SPACE
  '\u2008', // PUNCTUATION SPACE
  '\u2009', // THIN SPACE
  '\u200a', // HAIR SPACE
  '\u2028', // LINE SEPARATOR
  '\u2029', // PARAGRAPH SEPARATOR
  '\u202f', // NARROW NO-BREAK SPACE
  '\u205f', // MEDIUM MATHEMATICAL SPACE
  '\u3000', // IDEOGRAPHIC SPACE
]);

/** Python's `str.strip()` with no argument. */
export function pyStrip(text: string): string {
  let start = 0;
  let end = text.length;
  while (start < end && PY_WHITESPACE.has(text[start] as string)) start += 1;
  while (end > start && PY_WHITESPACE.has(text[end - 1] as string)) end -= 1;
  return text.slice(start, end);
}


/**
 * The characters `pyRepr` escapes rather than emitting literally: every code point below U+3101 for
 * which CPython's `str.isprintable()` is false.
 *
 * Generated from builder/tests/testdata/pycompat-golden.json by builder/pycompat-oracle/gen_pycompat_golden.py
 * and asserted against it in builder/tests/pyCompat.spec.ts, so a hand-edit cannot drift from the
 * semantics it claims to reproduce. A range table of NUMBERS rather than a list of characters on
 * purpose: the same data spelled as string literals produced one surviving mutant per entry, since
 * no test exercises an individual unassigned code point.
 *
 * The table is Unicode-version specific — it encodes the database CI's pinned CPython ships, which
 * `make pycompat-golden-check` verifies. Below U+3101 agreement with that CPython is TOTAL. At and
 * above it, characters are emitted literally, which matches CPython for assigned printable
 * characters but NOT for the unassigned and format code points up there; a `!r`-quoted string
 * containing one would render differently. That is an accepted approximation, not full fidelity:
 * the domain is a markdown line quoted into a build error, and the build fails either way.
 */
const NON_PRINTABLE: ReadonlyArray<readonly [number, number]> = [
  [0x0000, 0x001f],
  [0x007f, 0x00a0],
  [0x00ad, 0x00ad],
  [0x0378, 0x0379],
  [0x0380, 0x0383],
  [0x038b, 0x038b],
  [0x038d, 0x038d],
  [0x03a2, 0x03a2],
  [0x0530, 0x0530],
  [0x0557, 0x0558],
  [0x058b, 0x058c],
  [0x0590, 0x0590],
  [0x05c8, 0x05cf],
  [0x05eb, 0x05ee],
  [0x05f5, 0x0605],
  [0x061c, 0x061d],
  [0x06dd, 0x06dd],
  [0x070e, 0x070f],
  [0x074b, 0x074c],
  [0x07b2, 0x07bf],
  [0x07fb, 0x07fc],
  [0x082e, 0x082f],
  [0x083f, 0x083f],
  [0x085c, 0x085d],
  [0x085f, 0x085f],
  [0x086b, 0x089f],
  [0x08b5, 0x08b5],
  [0x08c8, 0x08d2],
  [0x08e2, 0x08e2],
  [0x0984, 0x0984],
  [0x098d, 0x098e],
  [0x0991, 0x0992],
  [0x09a9, 0x09a9],
  [0x09b1, 0x09b1],
  [0x09b3, 0x09b5],
  [0x09ba, 0x09bb],
  [0x09c5, 0x09c6],
  [0x09c9, 0x09ca],
  [0x09cf, 0x09d6],
  [0x09d8, 0x09db],
  [0x09de, 0x09de],
  [0x09e4, 0x09e5],
  [0x09ff, 0x0a00],
  [0x0a04, 0x0a04],
  [0x0a0b, 0x0a0e],
  [0x0a11, 0x0a12],
  [0x0a29, 0x0a29],
  [0x0a31, 0x0a31],
  [0x0a34, 0x0a34],
  [0x0a37, 0x0a37],
  [0x0a3a, 0x0a3b],
  [0x0a3d, 0x0a3d],
  [0x0a43, 0x0a46],
  [0x0a49, 0x0a4a],
  [0x0a4e, 0x0a50],
  [0x0a52, 0x0a58],
  [0x0a5d, 0x0a5d],
  [0x0a5f, 0x0a65],
  [0x0a77, 0x0a80],
  [0x0a84, 0x0a84],
  [0x0a8e, 0x0a8e],
  [0x0a92, 0x0a92],
  [0x0aa9, 0x0aa9],
  [0x0ab1, 0x0ab1],
  [0x0ab4, 0x0ab4],
  [0x0aba, 0x0abb],
  [0x0ac6, 0x0ac6],
  [0x0aca, 0x0aca],
  [0x0ace, 0x0acf],
  [0x0ad1, 0x0adf],
  [0x0ae4, 0x0ae5],
  [0x0af2, 0x0af8],
  [0x0b00, 0x0b00],
  [0x0b04, 0x0b04],
  [0x0b0d, 0x0b0e],
  [0x0b11, 0x0b12],
  [0x0b29, 0x0b29],
  [0x0b31, 0x0b31],
  [0x0b34, 0x0b34],
  [0x0b3a, 0x0b3b],
  [0x0b45, 0x0b46],
  [0x0b49, 0x0b4a],
  [0x0b4e, 0x0b54],
  [0x0b58, 0x0b5b],
  [0x0b5e, 0x0b5e],
  [0x0b64, 0x0b65],
  [0x0b78, 0x0b81],
  [0x0b84, 0x0b84],
  [0x0b8b, 0x0b8d],
  [0x0b91, 0x0b91],
  [0x0b96, 0x0b98],
  [0x0b9b, 0x0b9b],
  [0x0b9d, 0x0b9d],
  [0x0ba0, 0x0ba2],
  [0x0ba5, 0x0ba7],
  [0x0bab, 0x0bad],
  [0x0bba, 0x0bbd],
  [0x0bc3, 0x0bc5],
  [0x0bc9, 0x0bc9],
  [0x0bce, 0x0bcf],
  [0x0bd1, 0x0bd6],
  [0x0bd8, 0x0be5],
  [0x0bfb, 0x0bff],
  [0x0c0d, 0x0c0d],
  [0x0c11, 0x0c11],
  [0x0c29, 0x0c29],
  [0x0c3a, 0x0c3c],
  [0x0c45, 0x0c45],
  [0x0c49, 0x0c49],
  [0x0c4e, 0x0c54],
  [0x0c57, 0x0c57],
  [0x0c5b, 0x0c5f],
  [0x0c64, 0x0c65],
  [0x0c70, 0x0c76],
  [0x0c8d, 0x0c8d],
  [0x0c91, 0x0c91],
  [0x0ca9, 0x0ca9],
  [0x0cb4, 0x0cb4],
  [0x0cba, 0x0cbb],
  [0x0cc5, 0x0cc5],
  [0x0cc9, 0x0cc9],
  [0x0cce, 0x0cd4],
  [0x0cd7, 0x0cdd],
  [0x0cdf, 0x0cdf],
  [0x0ce4, 0x0ce5],
  [0x0cf0, 0x0cf0],
  [0x0cf3, 0x0cff],
  [0x0d0d, 0x0d0d],
  [0x0d11, 0x0d11],
  [0x0d45, 0x0d45],
  [0x0d49, 0x0d49],
  [0x0d50, 0x0d53],
  [0x0d64, 0x0d65],
  [0x0d80, 0x0d80],
  [0x0d84, 0x0d84],
  [0x0d97, 0x0d99],
  [0x0db2, 0x0db2],
  [0x0dbc, 0x0dbc],
  [0x0dbe, 0x0dbf],
  [0x0dc7, 0x0dc9],
  [0x0dcb, 0x0dce],
  [0x0dd5, 0x0dd5],
  [0x0dd7, 0x0dd7],
  [0x0de0, 0x0de5],
  [0x0df0, 0x0df1],
  [0x0df5, 0x0e00],
  [0x0e3b, 0x0e3e],
  [0x0e5c, 0x0e80],
  [0x0e83, 0x0e83],
  [0x0e85, 0x0e85],
  [0x0e8b, 0x0e8b],
  [0x0ea4, 0x0ea4],
  [0x0ea6, 0x0ea6],
  [0x0ebe, 0x0ebf],
  [0x0ec5, 0x0ec5],
  [0x0ec7, 0x0ec7],
  [0x0ece, 0x0ecf],
  [0x0eda, 0x0edb],
  [0x0ee0, 0x0eff],
  [0x0f48, 0x0f48],
  [0x0f6d, 0x0f70],
  [0x0f98, 0x0f98],
  [0x0fbd, 0x0fbd],
  [0x0fcd, 0x0fcd],
  [0x0fdb, 0x0fff],
  [0x10c6, 0x10c6],
  [0x10c8, 0x10cc],
  [0x10ce, 0x10cf],
  [0x1249, 0x1249],
  [0x124e, 0x124f],
  [0x1257, 0x1257],
  [0x1259, 0x1259],
  [0x125e, 0x125f],
  [0x1289, 0x1289],
  [0x128e, 0x128f],
  [0x12b1, 0x12b1],
  [0x12b6, 0x12b7],
  [0x12bf, 0x12bf],
  [0x12c1, 0x12c1],
  [0x12c6, 0x12c7],
  [0x12d7, 0x12d7],
  [0x1311, 0x1311],
  [0x1316, 0x1317],
  [0x135b, 0x135c],
  [0x137d, 0x137f],
  [0x139a, 0x139f],
  [0x13f6, 0x13f7],
  [0x13fe, 0x13ff],
  [0x1680, 0x1680],
  [0x169d, 0x169f],
  [0x16f9, 0x16ff],
  [0x170d, 0x170d],
  [0x1715, 0x171f],
  [0x1737, 0x173f],
  [0x1754, 0x175f],
  [0x176d, 0x176d],
  [0x1771, 0x1771],
  [0x1774, 0x177f],
  [0x17de, 0x17df],
  [0x17ea, 0x17ef],
  [0x17fa, 0x17ff],
  [0x180e, 0x180f],
  [0x181a, 0x181f],
  [0x1879, 0x187f],
  [0x18ab, 0x18af],
  [0x18f6, 0x18ff],
  [0x191f, 0x191f],
  [0x192c, 0x192f],
  [0x193c, 0x193f],
  [0x1941, 0x1943],
  [0x196e, 0x196f],
  [0x1975, 0x197f],
  [0x19ac, 0x19af],
  [0x19ca, 0x19cf],
  [0x19db, 0x19dd],
  [0x1a1c, 0x1a1d],
  [0x1a5f, 0x1a5f],
  [0x1a7d, 0x1a7e],
  [0x1a8a, 0x1a8f],
  [0x1a9a, 0x1a9f],
  [0x1aae, 0x1aaf],
  [0x1ac1, 0x1aff],
  [0x1b4c, 0x1b4f],
  [0x1b7d, 0x1b7f],
  [0x1bf4, 0x1bfb],
  [0x1c38, 0x1c3a],
  [0x1c4a, 0x1c4c],
  [0x1c89, 0x1c8f],
  [0x1cbb, 0x1cbc],
  [0x1cc8, 0x1ccf],
  [0x1cfb, 0x1cff],
  [0x1dfa, 0x1dfa],
  [0x1f16, 0x1f17],
  [0x1f1e, 0x1f1f],
  [0x1f46, 0x1f47],
  [0x1f4e, 0x1f4f],
  [0x1f58, 0x1f58],
  [0x1f5a, 0x1f5a],
  [0x1f5c, 0x1f5c],
  [0x1f5e, 0x1f5e],
  [0x1f7e, 0x1f7f],
  [0x1fb5, 0x1fb5],
  [0x1fc5, 0x1fc5],
  [0x1fd4, 0x1fd5],
  [0x1fdc, 0x1fdc],
  [0x1ff0, 0x1ff1],
  [0x1ff5, 0x1ff5],
  [0x1fff, 0x200f],
  [0x2028, 0x202f],
  [0x205f, 0x206f],
  [0x2072, 0x2073],
  [0x208f, 0x208f],
  [0x209d, 0x209f],
  [0x20c0, 0x20cf],
  [0x20f1, 0x20ff],
  [0x218c, 0x218f],
  [0x2427, 0x243f],
  [0x244b, 0x245f],
  [0x2b74, 0x2b75],
  [0x2b96, 0x2b96],
  [0x2c2f, 0x2c2f],
  [0x2c5f, 0x2c5f],
  [0x2cf4, 0x2cf8],
  [0x2d26, 0x2d26],
  [0x2d28, 0x2d2c],
  [0x2d2e, 0x2d2f],
  [0x2d68, 0x2d6e],
  [0x2d71, 0x2d7e],
  [0x2d97, 0x2d9f],
  [0x2da7, 0x2da7],
  [0x2daf, 0x2daf],
  [0x2db7, 0x2db7],
  [0x2dbf, 0x2dbf],
  [0x2dc7, 0x2dc7],
  [0x2dcf, 0x2dcf],
  [0x2dd7, 0x2dd7],
  [0x2ddf, 0x2ddf],
  [0x2e53, 0x2e7f],
  [0x2e9a, 0x2e9a],
  [0x2ef4, 0x2eff],
  [0x2fd6, 0x2fef],
  [0x2ffc, 0x3000],
  [0x3040, 0x3040],
  [0x3097, 0x3098],
  [0x3100, 0x3100],
];

/**
 * Is `cp` printable per Python's `str.isprintable()`?
 *
 * Relies on NON_PRINTABLE being sorted ascending with non-overlapping `[lo, hi]` ranges: scan once
 * and the FIRST range whose `lo` is already past `cp` proves `cp` sits in a gap between ranges
 * (printable). A range that contains `cp` makes it non-printable. Reaching the end means `cp` is
 * above every range — printable too.
 */
function isPyPrintable(cp: number): boolean {
  for (const [lo, hi] of NON_PRINTABLE) {
    if (cp < lo) return true; // before this range and all later ones => in a gap => printable
    if (cp <= hi) return false; // inside [lo, hi] => non-printable
  }
  return true; // above every non-printable range => printable
}

/**
 * Python's `repr()` for a string.
 *
 * The ported modules quote offending input with `!r`, and those messages are contractual: the
 * parity harness diffs them byte-for-byte, and the code-of-conduct requires a failure to name what
 * went wrong. `JSON.stringify` is NOT a substitute — it always double-quotes, while Python prefers
 * a single quote and switches to double only when the value contains a single quote and no double.
 */
export function pyRepr(value: string): string {
  const quote = value.includes("'") && !value.includes('"') ? '"' : "'";
  let out = quote;
  for (const ch of value) {
    const cp = ch.codePointAt(0) as number;
    if (ch === '\\' || ch === quote) {
      out += '\\' + ch;
    } else if (cp === 0x0a) {
      out += '\\n';
    } else if (cp === 0x0d) {
      out += '\\r';
    } else if (cp === 0x09) {
      out += '\\t';
    } else if (isPyPrintable(cp)) {
      out += ch;
    } else if (cp <= 0xff) {
      out += '\\x' + cp.toString(16).padStart(2, '0');
    } else {
      // Two-digit and four-digit escapes only. A `\\U` eight-digit branch would be unreachable:
      // NON_PRINTABLE stops at U+3100, so every code point above it is treated as printable and
      // emitted literally, exactly as Python emits printable non-ASCII. Dead defensive code here
      // would sit in the mutation report forever as an unkillable survivor.
      out += '\\u' + cp.toString(16).padStart(4, '0');
    }
  }
  return out + quote;
}

/**
 * Python's `repr()` for a `dict[str, str]`.
 *
 * An f-string interpolating a dict (`f"drift: {versions}"`) renders `{'a': '1', 'b': '2'}` — single
 * quotes, a space after each colon. `JSON.stringify` renders `{"a":"1","b":"2"}`. Both are
 * plausible; only one matches the message the Python original emits, and the parity harness diffs
 * these byte-for-byte.
 */
export function pyReprMapping(mapping: Readonly<Record<string, string>>): string {
  const body = Object.entries(mapping)
    .map(([key, value]) => `${pyRepr(key)}: ${pyRepr(value)}`)
    .join(', ');
  return `{${body}}`;
}

/**
 * Python's `repr()` for an arbitrary JSON value: string, number, boolean, null, array, or a plain
 * object with string keys — the full range of what a descriptor field can hold before it is
 * validated. Every ported error message that interpolates raw, not-yet-validated input needs this
 * rather than `pyRepr`, which only handles strings.
 *
 * Numbers are the one incomplete case: JSON has a single number type, but Python's `json.loads`
 * distinguishes `2` (int, repr `'2'`) from `2.0` (float, repr `'2.0'`) by whether the source
 * literal had a decimal point, and JavaScript's `number` cannot recover that distinction after
 * parsing. This affects only an integer-valued float appearing where a non-string value is being
 * rejected — never a legitimate field, since no descriptor field is numeric. Accepted as a
 * documented gap rather than ported: fixtures avoid the case rather than papering over it.
 */
export function pyReprValue(value: unknown): string {
  if (value === null || value === undefined) return 'None';
  if (value === true) return 'True';
  if (value === false) return 'False';
  if (typeof value === 'number') return String(value);
  if (typeof value === 'string') return pyRepr(value);
  if (Array.isArray(value)) return `[${value.map(pyReprValue).join(', ')}]`;
  if (typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>);
    return `{${entries.map(([k, v]) => `${pyRepr(k)}: ${pyReprValue(v)}`).join(', ')}}`;
  }
  return String(value);
}
