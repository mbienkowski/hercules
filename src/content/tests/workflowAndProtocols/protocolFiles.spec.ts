import { describe, expect, it } from 'vitest';

import {
  ALLOWED_STATUSES, extractA2aCore, extractUsedStatuses, findCoreEntryLines, matchesA2aEntryFormat,
} from '../../../metrics/a2aGrammar.mjs';
import { countStatusTableRows } from '../../../metrics/markdownMetrics.mjs';
import { readFile } from '../commands/support';
import { readRepoFile } from '../../../commons/support/repo';

// Ported from tests/protocols/test_protocol_files.py — verifies the A2A and debate protocol files
// follow the methodology.

const A2A_PROTOCOL = 'dist/claude-code/protocols/a2a-communication-protocol.md';
const DEBATE_PROTOCOL = 'dist/claude-code/protocols/debate-consensus-protocol.md';
const ALL_PROTOCOLS = [A2A_PROTOCOL, DEBATE_PROTOCOL];

it('every A2A protocol entry line supplies exactly three fields', () => {
  const md = readFile(A2A_PROTOCOL);
  const entryLines = findCoreEntryLines(md);
  const violations = entryLines.filter((ln) => !matchesA2aEntryFormat(ln));
  expect(violations, `Entry lines with wrong field count: ${violations.join(', ')}`).toEqual([]);
});

it('only approved status words appear in the protocol', () => {
  for (const rel of ALL_PROTOCOLS) {
    const md = readFile(rel);
    const violations = extractUsedStatuses(md).filter((s) => !ALLOWED_STATUSES.has(s));
    expect(violations, `${rel}: undefined statuses found: ${violations.join(', ')}`).toEqual([]);
  }
});

it('the status reference table has a row for each approved status', () => {
  const md = readFile(A2A_PROTOCOL);
  const rowCount = countStatusTableRows(md);
  expect(rowCount, `STATUS reference table has ${rowCount} rows, expected 6 (Blocker/High/Medium/Nitpick/Pass/Info)`).toBe(6);
});

it('the shared agent instructions block matches the approved reference copy', () => {
  const md = readRepoFile('dist', 'claude-code', 'protocols', 'a2a-communication-protocol.md');
  const want = readRepoFile('src', 'content', 'tests', 'core.golden');
  const { text: core, found } = extractA2aCore(md);
  expect(found, 'No fenced Core block found in the A2A protocol').toBe(true);
  expect(core, 'Injected Core changed vs golden. If intentional, update content/tests/core.golden.').toBe(want);
});

it('the round-3 reinvoke threshold excludes resolved votes (never ≤4/5)', () => {
  for (const rel of ALL_PROTOCOLS) {
    expect(readFile(rel), `${rel}: R3 re-invoke threshold must stay ≤3/5`).not.toContain('≤4/5');
  }
});

describe('debate resolution', () => {
  it('resolves only at full consensus, else escalates to the user', () => {
    const lower = readFile(DEBATE_PROTOCOL).toLowerCase();
    expect(lower, '5/5 must remain the resolved row').toContain('| 5 | full agreement | resolved');
    expect(lower, '4/5 must be a reservation escalated to the user, not auto-resolved')
      .toContain("reservation — carried to the user's decision, not resolved");
    expect(lower, 'a round must close at full 5/5 (or the tier cap), not ≥4/5').toContain('closes at full 5/5');
    expect(lower, 'Synthesis must state the 5/5-only resolve rule').toContain('resolves only at full 5/5');
    expect(lower.includes('accept as-is') && lower.includes('another angle') && lower.includes('override'),
      "the user's decision must offer accept-as-is / another-angle / override").toBe(true);
    expect(lower, 'a contested or reserved finding is never auto-applied').toContain('never auto-applied');
  });
});
