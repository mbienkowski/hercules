import { describe, expect, it } from 'vitest';

import { parseConvergence, parseScalingModel, TIER_ORDER } from './scalingModel.mjs';

// One test per parser, proving each reads a well-formed table at all.

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
  });

  it('refuses a table that lost a row instead of reporting the rows it found, naming the file', () => {
    expect(() => parseScalingModel(WELL_FORMED.replace(/^\| `complexity:high`.*\n/m, ''), 'short.md'))
      .toThrow(/short\.md.*4.*5/s);
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

describe('parseConvergence', () => {
  it('reads every row as topic, state and outcome, and the body it reads stops at the next heading', () => {
    const rows = parseConvergence(CONVERGENCE, 'fixture.md');
    expect(rows[1]?.state).toBe('contested');
    expect(rows[1]?.outcome).toContain('casting vote');
    expect(rows.some((r) => r.outcome.includes('later section'))).toBe(false);
  });
});
