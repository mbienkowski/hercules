import { describe, expect, it } from 'vitest';

import {
  EXPECTED_CONVERGENCE, EXPECTED_MODEL, parseConvergence, parseScalingModel, section, sentences,
  TIER_ORDER,
} from '../../scalingModel.mjs';

// The extractor behind the scaling-model guard. It fails loudly rather than returning an empty
// parse: a guard that quietly reads nothing is worse than no guard, because it reports success.
//
// Every function here is tested directly, because `src/metrics/` is excluded from the mutation gate
// (CODE_OF_CONDUCT.md § Testing — you don't mutate your own ruler). Unit tests are the only thing
// standing behind this module, so an untested branch here is an unguarded one.

const WELL_FORMED = `# Debate Consensus Protocol

## complexity

Some prose about scoring.

| complexity | Effort signals | Blast-radius signals | Advisors | Rounds |
|---|---|---|---|---|
| \`complexity:trivial\` | typo | none | 0 | 0 |
| \`complexity:low\` | small | one flow | 2 | 1 |
| \`complexity:medium\` | feature | several flows | 2–3 | 1–2 |
| \`complexity:high\` | architecture | data at risk | 3–5 | 1–2 |
| \`complexity:critical\` | irreversible | user data | 4–6 | 2–3 + fresh eyes |

Trailing prose.

## Round 1 — Blind

More text.
`;

describe('parseScalingModel', () => {
  it('reads every tier row in order', () => {
    const rows = parseScalingModel(WELL_FORMED, 'fixture.md');
    expect(rows.map((r) => r.tier)).toEqual([...TIER_ORDER]);
    expect(rows.find((r) => r.tier === 'medium')).toEqual({ tier: 'medium', advisors: '2–3', rounds: '1–2' });
    expect(rows.find((r) => r.tier === 'critical')?.rounds).toBe('2–3 + fresh eyes');
  });

  it('stops at the next heading rather than swallowing later tables', () => {
    const withLaterTable = `${WELL_FORMED}\n| \`complexity:trivial\` | x | y | 9 | 9 |\n`;
    expect(parseScalingModel(withLaterTable, 'fixture.md')).toHaveLength(TIER_ORDER.length);
  });

  it('reads a rubric that runs to the end of the file, with no heading after it', () => {
    const noTrailingHeading = WELL_FORMED.slice(0, WELL_FORMED.indexOf('Trailing prose.'));
    expect(parseScalingModel(noTrailingHeading, 'tail.md')).toHaveLength(TIER_ORDER.length);
  });

  it('names the file and the missing anchor when the section is gone', () => {
    expect(() => parseScalingModel('# Nothing here\n', 'gone.md'))
      .toThrow(/gone\.md.*## complexity/s);
  });

  it('refuses a table that lost a row instead of reporting the rows it found', () => {
    const short = WELL_FORMED.replace(/^\| `complexity:high`.*\n/m, '');
    expect(() => parseScalingModel(short, 'short.md')).toThrow(/short\.md.*4.*5/s);
  });

  it('refuses a table that GAINED a row', () => {
    // Only an exact row count is safe. Relaxing the check to `<` leaves an extra row parsed and
    // compared positionally, so a duplicate tier row appended inside the section shifts the whole
    // model — and that relaxation survived the full suite while both branch sides read as covered.
    const extra = WELL_FORMED.replace('\nTrailing prose.',
      '\n| `complexity:critical` | any | any | 1 | 1 |\n\nTrailing prose.');
    expect(() => parseScalingModel(extra, 'extra.md'), 'an appended tier row must be refused — a second '
      + 'row for a tier is two answers with nothing saying which one ships')
      .toThrow(/extra\.md.*6.*5/s);
  });

  it('refuses a tier token it does not recognise', () => {
    const typo = WELL_FORMED.replace('complexity:medium', 'complexity:moderate');
    expect(() => parseScalingModel(typo, 'typo.md')).toThrow(/moderate/);
  });

  it('refuses a row missing the advisor or round cell', () => {
    const truncated = WELL_FORMED.replace('| `complexity:low` | small | one flow | 2 | 1 |',
      '| `complexity:low` | small | one flow |');
    expect(() => parseScalingModel(truncated, 'truncated.md')).toThrow(/truncated\.md/);
  });
});

const CONVERGENCE = `## Converging a round

Prose above the table.

| The topic | State | What happens |
|---|---|---|
| positions differ | contested | carried into the next round |
| one speaker, Blocker or High | contested | a further round adds an advisor who has not spoken on it; \
at the ceiling it goes to the casting vote at \`complexity:low\` and to the user elsewhere |
| one speaker, lower severity | folded in | entered with the advisor who raised it named |
| raised by some, unaddressed by others | not settled | silence is never agreement |

Prose below.

## Carrying a position

Later section.
`;

describe('section', () => {
  it('returns the body up to the next heading of the same level', () => {
    const body = section(CONVERGENCE, '## Converging a round', 'fixture.md');
    expect(body).toContain('positions differ');
    expect(body, 'a section that runs past its own heading pulls the next section\'s rules into every '
      + 'assertion made against this one').not.toContain('Later section.');
  });

  it('returns a section that runs to the end of the file', () => {
    const tail = section('## Only section\n\nbody text\n', '## Only section', 'tail.md');
    expect(tail.trim()).toBe('body text');
  });

  it('is not terminated by a deeper sub-heading inside it', () => {
    const nested = '## Outer\n\nfirst\n\n### Inner\n\nsecond\n\n## Next\n\nthird\n';
    const body = section(nested, '## Outer', 'nested.md');
    expect(body, 'a `###` sub-heading belongs to the section it sits in').toContain('second');
    expect(body).not.toContain('third');
  });

  it('names the file and the heading when the section is gone', () => {
    expect(() => section('# nothing\n', '## Converging a round', 'gone.md'))
      .toThrow(/gone\.md.*Converging a round/s);
  });

  it('does not match a heading that merely starts with the same words', () => {
    expect(() => section('## Converging a round quickly\n\nbody\n', '## Converging a round', 'near.md'),
      'an anchored match keeps "## Converging a round quickly" from standing in for the real section')
      .toThrow(/near\.md/);
  });
});

describe('parseConvergence', () => {
  it('reads every row as topic, state and outcome', () => {
    const rows = parseConvergence(CONVERGENCE, 'fixture.md');
    expect(rows.map((r) => r.topic)).toEqual(EXPECTED_CONVERGENCE.map((r) => r.topic));
    expect(rows[1]?.state).toBe('contested');
    expect(rows[1]?.outcome).toContain('casting vote');
  });

  it('keeps a row that was appended, so an added contradiction is visible', () => {
    const extra = CONVERGENCE.replace('\nProse below.',
      '\n| positions differ | settled | folded straight in |\n\nProse below.');
    const rows = parseConvergence(extra, 'extra.md');
    expect(rows, 'an appended row must be returned rather than shadowed by the first match — a caller '
      + 'comparing the whole set is how a contradicting row is caught')
      .toHaveLength(EXPECTED_CONVERGENCE.length + 1);
  });

  it('refuses a table that lost a row', () => {
    const short = CONVERGENCE.replace(/^\| one speaker, lower severity.*\n/m, '');
    expect(() => parseConvergence(short, 'short.md')).toThrow(/short\.md.*3.*4/s);
  });

  it('names the file when the section is gone entirely', () => {
    expect(() => parseConvergence('# nothing\n', 'gone.md')).toThrow(/gone\.md/);
  });

  it('refuses a row that lost its closing pipe rather than reading a partial row', () => {
    // Dropping the trailing `|` leaves the outcome cell absent, so the row would parse as a state
    // with no consequence — silently the most permissive reading of the table there is.
    const truncated = CONVERGENCE.replace(
      '| one speaker, lower severity | folded in | entered with the advisor who raised it named |',
      '| one speaker, lower severity | folded in',
    );
    expect(() => parseConvergence(truncated, 'truncated.md'))
      .toThrow(/truncated\.md: a convergence row is missing a cell/);
  });
});

describe('sentences', () => {
  it('splits on terminators and normalises whitespace and case', () => {
    expect(sentences('One rule holds.\nAnother   RULE follows!'))
      .toEqual(['one rule holds.', 'another rule follows!']);
  });

  it('drops table rows, which carry no terminator', () => {
    const withTable = 'A rule stands.\n| cell | cell |\n| more | more |\nAnother rule stands.';
    expect(sentences(withTable), 'a table row left in glues the whole table onto the sentence beside '
      + 'it, and every pin against that sentence then matches the table instead of the rule')
      .toEqual(['a rule stands.', 'another rule stands.']);
  });

  it('keeps list items and block quotes, which carry rules', () => {
    expect(sentences('- A listed rule.\n> A quoted rule.'))
      .toEqual(['- a listed rule.', '> a quoted rule.']);
  });

  it('keeps an em-dash clause inside its own sentence', () => {
    expect(sentences('The ceiling is a ceiling — never an itinerary.'))
      .toEqual(['the ceiling is a ceiling — never an itinerary.']);
  });

  it('returns nothing for text that is only a table', () => {
    expect(sentences('| a | b |\n|---|---|\n| c | d |')).toEqual([]);
  });
});

describe('EXPECTED_CONVERGENCE', () => {
  it('states an outcome for every row, so no state is left without a consequence', () => {
    for (const row of EXPECTED_CONVERGENCE) {
      expect(row.outcomeIncludes.length, `${row.topic} declares no outcome to check`).toBeGreaterThan(0);
    }
  });

  it('routes a lone serious finding to a person rather than into the draft', () => {
    const lone = EXPECTED_CONVERGENCE.find((r) => r.topic.includes('blocker'));
    expect(lone?.state, 'a lone Blocker folded in is a serious finding nothing checked').toBe('contested');
    expect(lone?.outcomeIncludes).toContain('casting vote');
    expect(lone?.outcomeIncludes).toContain('user');
  });
});

describe('EXPECTED_MODEL', () => {
  it('covers every tier exactly once, in order', () => {
    expect(EXPECTED_MODEL.map((m) => m.tier)).toEqual([...TIER_ORDER]);
  });

  it('never lets a debating tier convene fewer than two advisors', () => {
    for (const m of EXPECTED_MODEL.filter((x) => x.rounds !== '0')) {
      expect(Number(m.advisors.split('–')[0]), `${m.tier} may convene ${m.advisors}`).toBeGreaterThanOrEqual(2);
    }
  });

  it('reserves a third round for the most demanding work alone', () => {
    expect(EXPECTED_MODEL.filter((m) => m.rounds.includes('3')).map((m) => m.tier)).toEqual(['critical']);
  });
});
