import { describe, expect, it } from 'vitest';

import {
  ALLOWED_STATUSES, extractA2aCore, extractUsedStatuses, findCoreEntryLines, matchesA2aEntryFormat,
} from '../../../metrics/a2aGrammar.mjs';
import { countStatusTableRows } from '../../../metrics/markdownMetrics.mjs';
import { readFile } from '../commands/support';
import { readRepoFile } from '../../../commons/support/repo';

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

const RETIRED_NOTATION = ['agreement: n/5', '≤3/5', '5/5', 'round 1 + 2 + 3', 'fresh-eyes(mandatory)'];

// The scaling model, stated once. Every surface that repeats it is asserted against this.
const EXPECTED_MODEL = [
  { tier: 'trivial', advisors: '0', rounds: '0' },
  { tier: 'low', advisors: '2', rounds: '1' },
  { tier: 'medium', advisors: '2–3', rounds: '1–2' },
  { tier: 'high', advisors: '3–5', rounds: '1–2' },
  { tier: 'critical', advisors: '4–6', rounds: '2–3 + fresh eyes' },
] as const;

/** Parse § complexity's rows into {tier, advisors, rounds}; throws rather than returning empty. */
function parseRubric(md: string): { tier: string; advisors: string; rounds: string }[] {
  const start = md.indexOf('## complexity');
  if (start < 0) throw new Error('no "## complexity" section — the rubric heading was renamed or removed');
  const section = md.slice(start, md.indexOf('\n## ', start + 1));
  const rows = section.split('\n').filter((l) => l.startsWith('| `complexity:'));
  if (rows.length !== EXPECTED_MODEL.length) {
    throw new Error(`§ complexity has ${rows.length} tier rows, expected ${EXPECTED_MODEL.length} — a row was dropped or its shape changed`);
  }
  return rows.map((line) => {
    const c = line.split('|').map((x) => x.trim());
    const tier = c[1].replace(/`/g, '').replace('complexity:', '');
    if (!EXPECTED_MODEL.some((m) => m.tier === tier)) throw new Error(`unknown tier token "${tier}"`);
    return { tier, advisors: c[4], rounds: c[5] };
  });
}

describe('the scaling model', () => {
  it('states every tier’s advisor count and round range in the rubric', () => {
    const parsed = parseRubric(readFile(DEBATE_PROTOCOL));
    expect(parsed, 'the rubric is the one place the tier is scored from — a wrong cell '
      + 'silently changes how much review every future feature gets').toEqual([...EXPECTED_MODEL]);
  });

  it('scores the tier on both axes, so max(effort, blast radius) is computable', () => {
    const md = readFile(DEBATE_PROTOCOL);
    expect(md, 'without the effort column an agent cannot score the axis it is told to take the higher of')
      .toContain('Effort signals');
    expect(md, 'without the blast-radius column the floor is the only risk signal an agent has')
      .toContain('Blast-radius signals');
  });

  it('never lets a debating tier run on fewer than two advisors', () => {
    for (const m of parseRubric(readFile(DEBATE_PROTOCOL))) {
      if (m.rounds === '0') continue;
      const low = Number(m.advisors.split('–')[0]);
      expect(low, `${m.tier} may convene ${m.advisors} advisors — one advisor is a review, not a debate`)
        .toBeGreaterThanOrEqual(2);
    }
  });

  it('reserves the third round for the most demanding work alone', () => {
    const three = parseRubric(readFile(DEBATE_PROTOCOL)).filter((m) => m.rounds.includes('3'));
    expect(three.map((m) => m.tier), 'a third round anywhere below critical spends depth where it was not earned')
      .toEqual(['critical']);
  });

  it('keeps the README table stating the same numbers as the rubric', () => {
    const readme = readFile('README.md');
    for (const m of parseRubric(readFile(DEBATE_PROTOCOL))) {
      const row = readme.split('\n').find((l) => l.startsWith(`| ${m.tier} |`));
      expect(row, `README has no tier row for ${m.tier} — a user reads the promise from this table`).toBeTruthy();
      const cells = (row as string).split('|').map((x) => x.trim());
      expect(`${cells[4]}|${cells[5]}`, `README promises ${m.tier} = ${cells[4]} advisors / ${cells[5]} rounds `
        + `while the rubric runs ${m.advisors} / ${m.rounds} — the shipped behaviour and the published promise disagree`)
        .toBe(`${m.advisors}|${m.rounds}`);
    }
  });
});

it('the retired agreement notation appears nowhere in the protocols', () => {
  for (const rel of ALL_PROTOCOLS) {
    const lower = readFile(rel).toLowerCase();
    const found = RETIRED_NOTATION.filter((n) => lower.includes(n));
    expect(found, `${rel} still states the retired ${found.join(', ')} notation — a debate is `
      + 'converged by topic, so a numeric agreement vote has no consumer and would be dead text')
      .toEqual([]);
  }
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
    expect(at.filter((i) => i < 0), `carrier tie-break missing: ${chain.filter((_, i) => at[i] < 0).join(', ')}`).toEqual([]);
    expect(at[0] < at[1] && at[1] < at[2],
      'the tie-break order is the rule — seniority decides first, wording completeness second, role name last')
      .toBe(true);
  });
});
