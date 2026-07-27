import { describe, expect, it } from 'vitest';

import { countStatusTableRows } from '../../markdownMetrics.mjs';

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

  it('recognizes the status table header even with leading whitespace', () => {
    const md = '  | STATUS | Meaning | ACTION |\n|---|---|---|\n| Blocker | x | y |\n';
    expect(countStatusTableRows(md)).toBe(1);
  });

  it('never mistakes a prose line for the header, even one mentioning STATUS, Meaning, and ACTION, without a leading pipe', () => {
    const md = 'STATUS Meaning ACTION prose\n| STATUS | Meaning | ACTION |\n|---|---|---|\n| Blocker | x | y |\n';
    expect(countStatusTableRows(md)).toBe(1);
  });

  it('requires the pipe at the start of the header row, not merely present somewhere in it', () => {
    const md = 'STATUS Meaning ACTION trailing pipe|\n| STATUS | Meaning | ACTION |\n|---|---|---|\n| Blocker | x | y |\n';
    expect(countStatusTableRows(md)).toBe(1);
  });

  it('requires the STATUS keyword specifically, not just a pipe-prefixed row with the other two headers', () => {
    const md = '| Foo | Meaning | ACTION |\n|---|---|---|\n| x | y | z |\n';
    expect(countStatusTableRows(md)).toBe(-1);
  });

  it('requires the Meaning keyword specifically, not just a pipe-prefixed row with the other two headers', () => {
    const md = '| STATUS | Foo | ACTION |\n|---|---|---|\n| x | y | z |\n';
    expect(countStatusTableRows(md)).toBe(-1);
  });

  it('requires the ACTION keyword specifically, not just a pipe-prefixed row with the other two headers', () => {
    const md = '| STATUS | Meaning | Foo |\n|---|---|---|\n| x | y | z |\n';
    expect(countStatusTableRows(md)).toBe(-1);
  });

  it('counts a data row even when indented with leading whitespace', () => {
    const md = '| STATUS | Meaning | ACTION |\n|---|---|---|\n  | Blocker | x | y |\n| High | x | y |\n';
    expect(countStatusTableRows(md)).toBe(2);
  });

  it('stops at a row that ends with a pipe but does not start with one', () => {
    const md = '| STATUS | Meaning | ACTION |\n|---|---|---|\n| Blocker | x | y |\n' +
      'not a row but ends with |\n| High | x | y |\n';
    expect(countStatusTableRows(md)).toBe(1);
  });
});
