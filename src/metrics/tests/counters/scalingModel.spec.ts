import { describe, expect, it } from 'vitest';

import { EXPECTED_MODEL, parseScalingModel, TIER_ORDER } from '../../scalingModel.mjs';

// The extractor behind the scaling-model guard. It fails loudly rather than returning an empty
// parse: a guard that quietly reads nothing is worse than no guard, because it reports success.

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
