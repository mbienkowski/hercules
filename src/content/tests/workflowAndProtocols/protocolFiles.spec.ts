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

/**
 * A section of the debate protocol, lowercased. Scoping matters: a rule satisfied by prose in a
 * different section proves nothing about the section that governs the behaviour.
 */
function debateSection(heading: string): string {
  const md = readFile(DEBATE_PROTOCOL);
  const start = md.indexOf(heading);
  if (start < 0) throw new Error(`no "${heading}" section in the debate protocol — it was renamed or removed`);
  const rest = md.slice(start + heading.length);
  const end = rest.search(/\n## /);
  return (end < 0 ? rest : rest.slice(0, end)).toLowerCase();
}

/**
 * Every pinned rule below carries a negative pin beside it, declared at the call site so it names the
 * inversion that would defeat *that* rule. A positive substring survives the one mutation that
 * matters — keep the pinned words, add a qualifier that reverses them — which is how three separate
 * review gates each found green assertions sitting on inverted content.
 */
function assertNoInversion(section: string, rule: string, inversions: RegExp[]): void {
  const hit = inversions.find((re) => re.test(section));
  expect(hit, `${rule}: the section hedges with ${hit} — a qualifier here leaves every pinned phrase `
    + 'intact while reversing what the rule requires, which is the drift these pins exist to stop')
    .toBeUndefined();
}

describe('debate resolution', () => {
  it('settles a topic only when two or more advisors agree on it', () => {
    const converging = debateSection('## Converging a round');
    expect(converging, 'a topic settles on two or more speakers agreeing, never on one speaker unopposed')
      .toContain('settled — two or more advisors spoke on the topic and state the same position');
    expect(converging, 'an unraised topic is not agreement').toContain('silence is never agreement');
    assertNoInversion(converging, 'convergence', [
      /settled?[^.]{0,60}\bone speaker\b/, // a lone speaker settling a topic
      /silence[^.]{0,40}\bis agreement\b/, // silence promoted to consent
    ]);
  });

  it('closes on settlement, and escalates whatever survives the ceiling', () => {
    const converging = debateSection('## Converging a round');
    const synthesis = debateSection('## Synthesis');
    expect(converging, 'closure is settlement, not an exhausted round budget')
      .toContain('closes when every topic is settled');
    expect(synthesis, 'synthesis must state the settlement-only resolve rule')
      .toContain('resolves only when every raised topic is settled');
    expect(synthesis, 'a reservation is the user\'s to decide, never the orchestrator\'s to close')
      .toContain("carried to the user's decision, never resolved by the orchestrator");
    for (const choice of ['accept as-is', 'another angle', 'override']) {
      expect(synthesis, `the user's decision must offer "${choice}"`).toContain(choice);
    }
    expect(synthesis, 'a contested finding is never auto-applied').toContain('never auto-applied');
    assertNoInversion(synthesis, 'escalation', [
      /auto-applied\s+(unless|when|if)\b/, // an exception that lets the orchestrator apply it anyway
      /resolved by the orchestrator\s+(unless|when|if)\b/,
      /never resolved by the orchestrator[^.]{0,30}\bexcept\b/,
    ]);
  });

  it('states the round range as a ceiling, not a schedule', () => {
    const complexity = debateSection('## complexity');
    expect(complexity, 'a round runs on contest, not because the level permits one')
      .toContain('ceiling, never an itinerary');
    assertNoInversion(complexity, 'the ceiling', [
      /every round[^.]{0,30}\balways runs\b/, // the ceiling turned back into a quota
      /ceiling, never an itinerary[^.]{0,40}\b(but|though|unless)\b/,
      /a further\s+round\s+runs\s+(always|regardless)/,
    ]);
  });

  it('carries one voice per position, and forms a position from the conclusion', () => {
    const carrying = debateSection('## Carrying a position');
    expect(carrying, 'duplicated voices are not carried forward').toContain('one advisor per position');
    expect(carrying, 'grouping by speciality makes two advisors who agree look like two positions, and '
      + 'two who disagree look like one — the count that sizes the next round would be wrong')
      .toContain('never its speciality');
    expect(carrying, 'both halves of the rule have to ship, or the reader guesses the harder case')
      .toMatch(/same conclusion are one position[^.]*same speciality who disagreed are two/);
    assertNoInversion(carrying, 'position carrying', [
      /\bnever\b[^.]{0,20}one advisor per position/, // the rule negated in place
      /one advisor per position\s+(unless|except)/,
      /carries\s+(every|all)\s+advisors?\b/, // the whole board carried instead of one voice
      /\bby its speciality\b/, // speciality reinstated as the grouping key
    ]);
  });

  it('keeps the two-advisor floor stated in prose, not only in the table', () => {
    const complexity = debateSection('## complexity');
    const opening = readFile(DEBATE_PROTOCOL).slice(0, readFile(DEBATE_PROTOCOL).indexOf('## complexity')).toLowerCase();
    expect(complexity, 'the table is numbers; this sentence is what an orchestrator actually reads')
      .toContain('a debate needs two advisors and two rounds');
    expect(opening, 'a single advisor is a review — saying otherwise licenses a one-advisor debate')
      .toMatch(/a single advisor is a review, not a debate/);
    assertNoInversion(complexity, 'the two-advisor floor', [
      /needs\s+(one|a single)\s+advisor/, // the floor lowered outright
      /two advisors and two rounds[^.]{0,60}\b(though|but|unless)\b/, // the floor conceded away
    ]);
    assertNoInversion(opening, 'the single-advisor rule', [
      /a single advisor is a (full|complete) debate/,
      /a single advisor[^.]{0,30}\bfollows this protocol\b/,
    ]);
  });

  it('makes the most demanding level buy its second round and panel unconditionally', () => {
    const complexity = debateSection('## complexity');
    const panel = debateSection('## Fresh-eyes panel');
    expect(complexity, 'without this the floor is a ceiling and critical can close after one round')
      .toMatch(/`complexity:critical`, which runs its second round and its fresh-eyes panel whatever the convergence\s+state/);
    expect(panel, 'the panel itself must not become discretionary')
      .toContain('convenes a panel after its final round whatever the convergence state');
    assertNoInversion(complexity, "critical's floor", [
      /low end (never binds|does not bind)/,
      /every round after the first is optional/,
    ]);
    assertNoInversion(panel, 'the panel', [
      /\bmay convene a panel\b/, // mandatory turned discretionary
      /panel[^.]{0,40}\b(optional|at the orchestrator's|discretion)\b/,
    ]);
  });

  it('orders the carrier tie-break: standing, then completeness, then role name', () => {
    const carrying = debateSection('## Carrying a position');
    const chain = ['standing the role would hold', 'states the position most completely', 'first by role name'];
    const at = chain.map((t) => carrying.indexOf(t));
    const missing = chain.filter((_, i) => (at[i] ?? -1) < 0);
    expect(missing, `carrier tie-break missing from § Carrying a position: ${missing.join(', ')}`).toEqual([]);
    const ordered = at.every((pos, i) => i === 0 || pos > (at[i - 1] ?? -1));
    expect(ordered,
      'the tie-break order is the rule — seniority decides first, wording completeness second, role name last')
      .toBe(true);
  });
});
