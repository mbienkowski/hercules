import { describe, expect, it } from 'vitest';

import { countInstructions, countStatusTableRows } from '../../scripts-ts/metrics/markdownMetrics.mjs';

// Ported from tests/metrics/test_markdown_metrics.py.

describe('countInstructions', () => {
  it('does not count instructions shown only as a fenced code example', () => {
    const md = '1. real instruction\n- a bullet\n| table | row |\n```\n1. fenced not counted\n' +
      '- fenced bullet\n```\nplain prose\n2. another instruction';
    expect(countInstructions(md)).toBe(3); // "1.", "- a bullet", "2." — table + fenced excluded
  });

  it('does not mistake table rows for instructions', () => {
    const md = '| col1 | col2 |\n|---|---|\n| val1 | val2 |\n- bullet after table';
    expect(countInstructions(md)).toBe(1); // only the bullet
  });
});

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
