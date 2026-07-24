import { describe, expect, it } from 'vitest';

import { countStatusTableRows } from '../../scripts-ts/metrics/markdownMetrics.mjs';

// Ported from tests/metrics/test_markdown_metrics.py. Its countInstructions tests moved to
// instructionCounter.spec.ts alongside commit 11's countAtomicInstructions, which replaced both
// this module's old countInstructions AND the instruction-budget gate's separate block counter —
// see instructionCounter.mts's own top comment.

describe('countStatusTableRows', () => {
  it('counts only the data entries of a status table', () => {
    const md = 'prose\n| STATUS | Meaning | ACTION |\n|---|---|---|\n' +
      '| Blocker | x | y |\n| High | x | y |\n\nafter';
    expect(countStatusTableRows(md)).toBe(2);
  });

  it('reports a document with no status table as such (sentinel -1)', () => {
    expect(countStatusTableRows('no table here')).toBe(-1);
  });

  it('does not mistake a table with different column headers for the status table', () => {
    const md = '| Name | Value | Description |\n|---|---|---|\n| foo | 1 | bar |\n| baz | 2 | qux |\n';
    expect(countStatusTableRows(md)).toBe(-1);
  });

  it('stops counting at the end of the status table even if another one follows', () => {
    const md = '| STATUS | Meaning | ACTION |\n|---|---|---|\n| Blocker | fatal | abort |\n' +
      '| High | serious | fix |\n\nprose after table\n' +
      '| STATUS | Meaning | ACTION |\n|---|---|---|\n| Pass | ok | continue |\n';
    expect(countStatusTableRows(md)).toBe(2); // only 2 rows from the first table
  });
});
