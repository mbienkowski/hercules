import { describe, expect, it } from 'vitest';

import {
  parseFrontmatter,
  renderFrontmatter,
  splitDocument,
} from '../../parse.mjs';

describe('reading a document’s frontmatter', () => {
  it('reads each key and value, and hands back the body separately', () => {
    const { metadata, body } = parseFrontmatter('---\nname: alpha\nmodel: fast\n---\n\nBody.\n');
    expect([...metadata]).toEqual([
      ['name', 'alpha'],
      ['model', 'fast'],
    ]);
    expect(body).toBe('Body.');
  });

  it('treats a document with no fence as all body', () => {
    expect(parseFrontmatter('Just prose.\n').metadata.size).toBe(0);
    expect(parseFrontmatter('Just prose.\n').body).toBe('Just prose.');
  });

  it('does not mistake a value containing three dashes for the closing fence', () => {
    // Splitting on the bare substring would end frontmatter mid-value, truncating it and silently
    // dropping every key after it.
    const { metadata } = parseFrontmatter('---\ndescription: pros --- cons\nname: beta\n---\nBody\n');
    expect(metadata.get('description')).toBe('pros --- cons');
    expect(metadata.get('name')).toBe('beta');
  });

  it('keeps everything after the first colon as the value', () => {
    expect(parseFrontmatter('---\nd: a: b: c\n---\n').metadata.get('d')).toBe('a: b: c');
  });

  it('ignores a frontmatter line with no colon rather than failing', () => {
    const { metadata } = parseFrontmatter('---\nname: x\nnocolon\nother: y\n---\n');
    expect([...metadata.keys()]).toEqual(['name', 'other']);
  });

  it('treats an unclosed fence as no frontmatter at all', () => {
    // Guessing at where the block ends would invent keys from body prose.
    expect(parseFrontmatter('---\nname: x\nbody text\n').metadata.size).toBe(0);
  });

  it('preserves the order keys were written in, even when they look like numbers', () => {
    // A plain object would hoist "1" and "2" ahead of "name", reordering the emitted frontmatter
    // and changing dist/ bytes. This is why the parser returns a Map.
    const { metadata } = parseFrontmatter('---\n2: two\n1: one\nname: after\n---\n');
    expect([...metadata.keys()]).toEqual(['2', '1', 'name']);
  });
});

describe('writing frontmatter back out', () => {
  it('fences the block and writes one key per line', () => {
    expect(renderFrontmatter(new Map([['name', 'alpha']]))).toBe('---\nname: alpha\n---');
  });

  it('round-trips a parsed block unchanged', () => {
    // The keystone property: parse then render must reproduce the original block, or every
    // rebuild would rewrite files it did not mean to change.
    const source = '---\nname: alpha\nmodel: fast\n---';
    expect(renderFrontmatter(parseFrontmatter(`${source}\nbody`).metadata)).toBe(source);
  });

  it('emits just the two fences when there are no keys', () => {
    expect(renderFrontmatter(new Map())).toBe('---\n---');
  });
});

describe('splitting a document without touching its bytes', () => {
  it('reassembles to exactly the original text', () => {
    // The lossless property the Claude renderer depends on: it edits the body and re-joins, so any
    // byte this drops is a byte that vanishes from dist/.
    const source = '---\nname: a\n---\n\n\nBody  with   spacing\n';
    const { block, body } = splitDocument(source);
    expect((block ?? '') + body).toBe(source);
  });

  it('includes both fences and the newline after the closing one in the block', () => {
    expect(splitDocument('---\nname: a\n---\nBody\n').block).toBe('---\nname: a\n---\n');
  });

  it('reports no block when the document does not open with a fence', () => {
    expect(splitDocument('Body only\n').block).toBeNull();
  });

  it('reports no block when the fence is never closed', () => {
    expect(splitDocument('---\nname: a\nno close\n').block).toBeNull();
  });

  it('returns the entire original text as the body when the fence is never closed', () => {
    // Weaker than it looks: block being null alone doesn't prove the body is the FULL untouched
    // original — a bug could still have truncated or reordered it. Only comparing body against the
    // exact source text catches that.
    const source = '---\nname: x\nnever closes';
    expect(splitDocument(source)).toEqual({ block: null, body: source });
  });

  it('handles a closing fence with no trailing newline', () => {
    const { block, body } = splitDocument('---\nname: a\n---');
    expect(block).toBe('---\nname: a\n---');
    expect(body).toBe('');
  });
});

describe('locating the frontmatter fence precisely', () => {
  it('does not treat the opening fence as its own closing fence', () => {
    // Searching from position zero would match the opening `---` and produce an empty block.
    const { metadata } = parseFrontmatter('---\nname: a\n---\nBody\n');
    expect(metadata.get('name')).toBe('a');
  });

  it('reads only the lines between the fences as keys', () => {
    // Scanning the whole document instead would turn body prose containing a colon into keys.
    const { metadata } = parseFrontmatter('---\nname: a\n---\nintro: not a key\n');
    expect([...metadata.keys()]).toEqual(['name']);
  });

  it('keeps body content that itself contains a fence line', () => {
    const { body } = parseFrontmatter('---\nname: a\n---\nbefore\n---\nafter\n');
    expect(body).toBe('before\n---\nafter');
  });

  it('splits a document whose body starts immediately after the closing fence', () => {
    const { block, body } = splitDocument('---\na: 1\n---\nBody');
    expect(block).toBe('---\na: 1\n---\n');
    expect(body).toBe('Body');
  });

  it('does not consume a character beyond the closing fence when the document ends there', () => {
    // Reading one past the end would append undefined to the block and lose the round-trip.
    const source = '---\na: 1\n---';
    const { block, body } = splitDocument(source);
    expect((block ?? '') + body).toBe(source);
  });

  it('treats a document that is only an opening fence as having no frontmatter', () => {
    expect(splitDocument('---\n').block).toBeNull();
  });
});

describe('the no-fence guard actually prevents misreading later dashes as frontmatter', () => {
  it('does not scan for a closing fence when the document never opens with one', () => {
    // A document that starts with prose but happens to contain two '---' lines LATER must not be
    // misread as if those were a frontmatter block — the guard must stop that before the scan ever
    // starts, not merely happen to produce the right answer some other way.
    const source = 'Body\n---\nkey: val\n---\nMore';
    const { metadata, body } = parseFrontmatter(source);
    expect(metadata.size).toBe(0);
    expect(body).toBe(source);
  });
});

describe('an unclosed fence falls back to the FULL original text as body', () => {
  it('is not merely "no metadata" but the untouched original, dashes included', () => {
    // The weaker assertion (metadata is empty) cannot tell "correctly fell back to the whole
    // document" apart from "incorrectly treated line 1 as a phantom closing fence and dropped
    // everything before it" — both leave metadata empty, only the BODY reveals which happened.
    const source = '---\nname: x\nbody text\n';
    const { metadata, body } = parseFrontmatter(source);
    expect(metadata.size).toBe(0);
    expect(body).toBe(source.trim());
  });
});

describe('splitDocument’s closing-fence search skips past the opening fence itself', () => {
  it('does not recognise two fences on adjacent lines as an empty frontmatter block', () => {
    // Mirrors the Python original's `text.find("\n" + FENCE, len(FENCE) + 1)`: the search starts
    // just past the OPENING fence's own text, not at its second character. Starting one character
    // too early would let the opening fence's own trailing dash be mistaken for a closing one.
    const { block, body } = splitDocument('---\n---\n');
    expect(block).toBeNull();
    expect(body).toBe('---\n---\n');
  });
  // The "still finds a real closing fence one full line later" contrast case is deliberately not
  // repeated here — it would be structurally identical to the pre-existing "splits a document whose
  // body starts immediately after the closing fence" test above, adding no incremental coverage.
});
