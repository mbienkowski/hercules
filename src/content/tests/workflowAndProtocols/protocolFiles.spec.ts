import { describe, expect, it } from 'vitest';

import {
  ALLOWED_STATUSES, extractA2aCore, extractUsedStatuses, findCoreEntryLines, matchesA2aEntryFormat,
} from '../../../metrics/a2aGrammar.mjs';
import { countStatusTableRows } from '../../../metrics/markdownMetrics.mjs';
import { readFile } from '../commands/support';
import { readRepoFile } from '../../../commons/support/repo';
import { EXPECTED_MODEL, parseScalingModel } from '../../../metrics/scalingModel.mjs';

// The A2A (agent-to-agent) and debate protocol files follow the methodology.

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

describe('debate resolution', () => {
  it('settles a topic only when two or more advisors agree on it', () => {
    const lower = readFile(DEBATE_PROTOCOL).toLowerCase();
    expect(lower, 'a topic settles on two or more speakers agreeing, never on one speaker unopposed')
      .toContain('settled — two or more advisors spoke on the topic and state the same position');
    expect(lower, 'an unraised topic is not agreement').toContain('silence is never agreement');
  });

  it('closes on settlement, and escalates whatever survives the ceiling', () => {
    const lower = readFile(DEBATE_PROTOCOL).toLowerCase();
    expect(lower, 'closure is settlement, not an exhausted round budget').toContain('closes when every topic is settled');
    expect(lower, 'synthesis must state the settlement-only resolve rule')
      .toContain('resolves only when every raised topic is settled');
    expect(lower, 'a reservation is the user\'s to decide, never the orchestrator\'s to close')
      .toContain("carried to the user's decision, never resolved by the orchestrator");
    expect(lower.includes('accept as-is') && lower.includes('another angle') && lower.includes('override'),
      "the user's decision must offer accept-as-is / another-angle / override").toBe(true);
    expect(lower, 'a contested finding is never auto-applied').toContain('never auto-applied');
  });

  it('states the round range as a ceiling and carries one voice per position', () => {
    const lower = readFile(DEBATE_PROTOCOL).toLowerCase();
    expect(lower, 'a round runs on contest, not because the level permits one').toContain('ceiling, never an itinerary');
    expect(lower, 'duplicated voices are not carried forward').toContain('one advisor per position');
  });

  it('orders the carrier tie-break: standing, then completeness, then role name', () => {
    const lower = readFile(DEBATE_PROTOCOL).toLowerCase();
    const chain = ['standing the role would hold', 'states the position most completely', 'first by role name'];
    const at = chain.map((t) => lower.indexOf(t));
    const missing = chain.filter((_, i) => (at[i] ?? -1) < 0);
    expect(missing, `carrier tie-break missing: ${missing.join(', ')}`).toEqual([]);
    const ordered = at.every((pos, i) => i === 0 || pos > (at[i - 1] ?? -1));
    expect(ordered,
      'the tie-break order is the rule — seniority decides first, wording completeness second, role name last')
      .toBe(true);
  });
});
