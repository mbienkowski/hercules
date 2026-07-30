import { describe, expect, it } from 'vitest';

import {
  ALLOWED_STATUSES, extractA2aCore, extractUsedStatuses, findCoreEntryLines, matchesA2aEntryFormat,
} from '../../../metrics/a2aGrammar.mjs';
import { countStatusTableRows } from '../../../metrics/markdownMetrics.mjs';
import { readFile } from '../commands/support';
import { readRepoFile } from '../../../commons/support/repo';
import {
  type ConvergenceRow, EXPECTED_CONVERGENCE, EXPECTED_MODEL, parseConvergence, parseScalingModel,
  section, sentences,
} from '../../../metrics/scalingModel.mjs';

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
 * The rules of the debate, pinned as WHOLE SENTENCES rather than as fragments.
 *
 * A fragment survives the one mutation that matters: keep the pinned words, add a qualifier beside
 * them that reverses the rule. Four separate review passes over this delivery each found green
 * assertions sitting on inverted content that way. A whole-sentence pin cannot be hedged — any
 * qualifier added anywhere in the sentence changes it, so the assertion fails.
 *
 * Each entry is `anchor → the sentence that must be exactly this`. The anchor only locates the
 * sentence, so reordering the file is free; the equality is what holds the meaning.
 */
const DEBATE_RULES: Record<string, { anchor: string; sentence: string; why: string }[]> = {
  opening: [{
    anchor: 'a single advisor is a review',
    sentence: 'a single advisor is a review, not a debate, and skips this protocol.',
    why: 'promoting one advisor to a full debate removes the two-advisor floor outright',
  }],
  '## complexity': [{
    anchor: 'ceiling, never an itinerary',
    sentence: 'the high end of the rounds column is a ceiling, never an itinerary — a further round '
      + 'runs only when the one before it left something contested.',
    why: 'without the trigger clause the ceiling becomes a schedule and every round always runs, '
      + 'which is the ritual the requirements forbid',
  }, {
    anchor: 'the low end binds only at',
    sentence: 'the low end binds only at `complexity:critical`, which runs its second round and its '
      + 'fresh-eyes panel whatever the convergence state, because that is the level where a missed '
      + 'problem is least recoverable.',
    why: 'softening "binds" to "is advisory" loses the one place depth is bought unconditionally',
  }, {
    anchor: 'a debate needs two advisors',
    sentence: 'a debate needs two advisors and two rounds.',
    why: 'the floor a success criterion marks automatic; a hedge beside it concedes it away',
  }],
  '## Carrying a position': [{
    anchor: 'a position is what an advisor concluded',
    sentence: 'a position is what an advisor concluded — the verdict it gave and the problems it '
      + 'named — never its speciality.',
    why: 'grouping by speciality miscounts positions, so the next round is sized wrongly',
  }, {
    anchor: 'same conclusion are one position',
    sentence: 'two advisors of different specialities who reached the same conclusion are one '
      + 'position; two of the same speciality who disagreed are two.',
    why: 'the hard case is what the rule exists for; without it the reader guesses',
  }, {
    anchor: 'carries one advisor per position',
    sentence: 'a contested topic carries one advisor per position, including the position that found '
      + 'nothing wrong, so that view is argued rather than dropped.',
    why: 'a threshold added here ("where three or more positions survive") re-invokes the whole board',
  }, {
    anchor: 'more senior voice',
    sentence: 'where several advisors hold one position it is carried by the more senior voice, '
      + 'judged by the standing the role would hold in an engineering organisation — architect over '
      + 'developer, qa engineer over tester — which needs no maintained ranking, so a newly added '
      + 'advisor participates with nothing to update and an ad-hoc expert\'s briefed agenda '
      + 'establishes its standing.',
    why: 'the requirements name seniority as the carrier rule; a substituted criterion silently changes who speaks',
  }],
  '## Fresh-eyes panel': [{
    anchor: 'convenes a panel after its final round',
    sentence: '`complexity:critical` convenes a panel after its final round whatever the convergence '
      + 'state, drawn inside its advisor maximum and carrying no history of the rounds before it.',
    why: '"may convene" makes the one mandatory independent look discretionary',
  }],
  '## Synthesis': [{
    anchor: 'resolves only when every raised topic',
    sentence: 'a debate resolves only when every raised topic is settled.',
    why: 'closure on anything less lets an open finding reach the draft unexamined',
  }, {
    anchor: 'never auto-applied',
    sentence: 'the choices are accept as-is, another angle, or override; a surviving finding is never '
      + 'auto-applied.',
    why: 'an exception added here lets the orchestrator apply its own contested finding',
  }, {
    anchor: 'never resolved by the orchestrator',
    sentence: 'a reservation is carried to the user\'s decision, never resolved by the orchestrator, '
      + 'and any contested finding is presented to the user verbatim as an open question.',
    why: 'the orchestrator closing its own reservation is the self-judgment the gates exist to stop',
  }],
};

/**
 * A whole-sentence pin catches an edit to the sentence it pins. It cannot catch a *new* sentence
 * added beside it that permits the opposite — so each rule that an addition could undo also declares
 * what no sentence in its section may say.
 */
const NO_SENTENCE_MAY: Record<string, { claim: RegExp; why: string }[]> = {
  '## complexity': [{
    claim: /\b(lone|single|one)\b[^.]{0,40}advisor[^.]{0,40}\b(may|can)\b[^.]{0,30}\bdebate\b/,
    why: 'a sentence permitting one advisor to debate reinstates what the floor forbids',
  }, {
    claim: /\ba further round\b[^.]{0,40}\b(always|regardless|whenever the level)\b/,
    why: 'a sentence making a later round unconditional turns the ceiling back into a schedule',
  }],
  '## Carrying a position': [{
    claim: /\b(whole|entire|full)\s+board\b[^.]{0,30}\bre-?invoked\b/,
    why: 're-invoking the whole board undoes one-voice-per-position',
  }],
  '## Fresh-eyes panel': [{
    claim: /\bpanel\b[^.]{0,40}\b(optional|may be skipped|at the orchestrator's discretion)\b/,
    why: 'the panel is the one mandatory independent look at the highest level',
  }],
  '## Synthesis': [{
    claim: /\bthe orchestrator\b[^.]{0,40}\bmay\b[^.]{0,30}\b(apply|resolve|close)\b/,
    why: 'letting the orchestrator resolve its own finding is the self-judgment the gates prevent',
  }],
};

describe('the debate rules, pinned as whole sentences', () => {
  const md = readFile(DEBATE_PROTOCOL);
  const bodyOf = (heading: string): string => (heading === 'opening'
    ? md.slice(0, md.indexOf('## complexity'))
    : section(md, heading, DEBATE_PROTOCOL));

  for (const [heading, rules] of Object.entries(DEBATE_RULES)) {
    const found = sentences(bodyOf(heading));

    for (const { anchor, sentence, why } of rules) {
      it(`${heading} — ${anchor}`, () => {
        const hit = found.filter((s) => s.includes(anchor));
        expect(hit.length, `"${anchor}" appears ${hit.length} times in ${heading} — the rule must be `
          + 'stated once, in the section that owns it').toBe(1);
        expect(hit[0], `${why}\n\nthe sentence must read exactly as the rule, so a qualifier added `
          + 'anywhere in it fails this assertion instead of surviving a fragment match')
          .toBe(sentence);
      });
    }
  }

  for (const [heading, forbidden] of Object.entries(NO_SENTENCE_MAY)) {
    for (const { claim, why } of forbidden) {
      it(`${heading} — no sentence may ${claim.source.slice(0, 34)}…`, () => {
        const offending = sentences(bodyOf(heading)).filter((s) => claim.test(s));
        expect(offending, `${why}\n\noffending sentence(s):\n  ${offending.join('\n  ')}\n`
          + 'a rule can be undone by a sentence added beside it, which no whole-sentence pin sees')
          .toEqual([]);
      });
    }
  }
});

describe('the convergence table, asserted by its own cells', () => {
  const rows = () => parseConvergence(readFile(DEBATE_PROTOCOL), DEBATE_PROTOCOL);

  it('settles a topic only when two or more advisors agree on it', () => {
    const converging = section(readFile(DEBATE_PROTOCOL), '## Converging a round', DEBATE_PROTOCOL);
    const said = sentences(converging);
    expect(said.filter((s) => s.includes('a topic is settled'))[0],
      'one unopposed speaker must not settle a topic — that is the naive rule this model replaced')
      .toBe('a topic is settled — two or more advisors spoke on the topic and state the same position.');
  });

  /**
   * The whole table, not a lookup per row.
   *
   * A `.find()` per case reads the first row whose topic matches and never looks at the rest, so a
   * contradicting row appended below the real one satisfies every assertion — a confirmed survivor of
   * the last review pass. Comparing the row set whole makes an appended row a length failure and a
   * reordered one a positional failure.
   */
  it('states exactly the four outcomes the model requires, in order', () => {
    const actual = rows();
    expect(actual.map((r) => r.topic), 'the convergence table must carry exactly these cases in this '
      + 'order — an added row is how a contradicting outcome hides below a correct one, and a dropped '
      + 'row silently removes a state a topic can reach')
      .toEqual(EXPECTED_CONVERGENCE.map((r) => r.topic));

    EXPECTED_CONVERGENCE.forEach((want, i) => {
      const got = actual[i] as ConvergenceRow;
      expect(got.state, `"${want.topic}" must resolve to "${want.state}" — its state is what decides `
        + 'whether the topic is carried, folded in, or blocks closure').toBe(want.state);
      for (const fragment of want.outcomeIncludes) {
        expect(got.outcome, `"${want.topic}" must say what happens: its outcome is missing `
          + `"${fragment}", so the row states a state without a consequence`).toContain(fragment);
      }
    });
  });

  it('closes on settlement rather than on an exhausted round budget', () => {
    const converging = section(readFile(DEBATE_PROTOCOL), '## Converging a round', DEBATE_PROTOCOL);
    expect(sentences(converging).filter((s) => s.includes('closes when every topic is settled'))[0],
      'closure driven by the round count rather than by settlement is the ritual the requirements forbid')
      .toBe("a debate closes when every topic is settled and the level's floor is met.");
  });
});

describe('the scaling model', () => {
  it('states every tier’s advisor count and round range in the rubric', () => {
    const parsed = parseScalingModel(readFile(DEBATE_PROTOCOL), DEBATE_PROTOCOL);
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
    for (const m of parseScalingModel(readFile(DEBATE_PROTOCOL), DEBATE_PROTOCOL)) {
      if (m.rounds === '0') continue;
      const low = Number(m.advisors.split('–')[0]);
      expect(low, `${m.tier} may convene ${m.advisors} advisors — one advisor is a review, not a debate`)
        .toBeGreaterThanOrEqual(2);
    }
  });

  it('reserves the third round for the most demanding work alone', () => {
    const three = parseScalingModel(readFile(DEBATE_PROTOCOL), DEBATE_PROTOCOL)
      .filter((m) => m.rounds.includes('3'));
    expect(three.map((m) => m.tier), 'a third round anywhere below critical spends depth where it was not earned')
      .toEqual(['critical']);
  });

  /**
   * Every README tier row, as a set — not one lookup per tier.
   *
   * `.find()` stops at the first row for a tier, so a second row promising different numbers sits
   * below it unread. That was a confirmed survivor: the published promise and the shipped behaviour
   * could disagree with the suite green. Collecting all rows and comparing the whole list means a
   * duplicate row fails on length.
   */
  it('keeps the README table stating the same numbers as the rubric, and only once each', () => {
    const rubric = parseScalingModel(readFile(DEBATE_PROTOCOL), DEBATE_PROTOCOL);
    const tiers = new Set<string>(rubric.map((m) => m.tier));
    const rows = readFile('README.md').split('\n')
      .filter((l) => tiers.has((l.split('|')[1] ?? '').trim()))
      .map((l) => {
        const cells = l.split('|').map((x) => x.trim());
        return { tier: cells[1] ?? '', advisors: cells[4] ?? '', rounds: cells[5] ?? '' };
      });
    expect(rows, 'the README table must carry one row per tier and no more — a second row for a tier '
      + 'is how the published promise drifts from the rubric while every per-tier lookup still passes')
      .toEqual(rubric.map((m) => ({ tier: m.tier, advisors: m.advisors, rounds: m.rounds })));
  });

  it('orders the carrier tie-break: standing, then completeness, then role name', () => {
    const carrying = section(readFile(DEBATE_PROTOCOL), '## Carrying a position', DEBATE_PROTOCOL)
      .toLowerCase();
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
