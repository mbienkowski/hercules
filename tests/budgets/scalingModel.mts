/**
 * The scaling model — how many advisors are convened and how many rounds they hold — parsed off every
 * surface that states it. Each extractor throws rather than return an empty parse.
 */

export const TIER_ORDER = ['trivial', 'low', 'medium', 'high', 'critical'] as const;

export type Tier = (typeof TIER_ORDER)[number];

interface TierRow {
  readonly tier: Tier;
  /** Advisor count or range as written, e.g. `2` or `2–3`. */
  readonly advisors: string;
  /** Round count or range as written, e.g. `1–2` or `2–3 + fresh eyes`. */
  readonly rounds: string;
}

const SECTION_HEADING = '## complexity';
const ROW_PREFIX = '| `complexity:';

function isTier(value: string): value is Tier {
  return (TIER_ORDER as readonly string[]).includes(value);
}

/**
 * A named section, ending at the next heading of the same or higher level. Throws when the heading is
 * missing or DUPLICATED — a second section is invisible to every assertion made through this function.
 */
export function section(md: string, heading: string, source: string): string {
  const anchored = new RegExp(`^${heading.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*$`, 'gm');
  const hits = [...md.matchAll(anchored)];
  const first = hits[0];
  if (first?.index === undefined) throw new Error(`${source}: no "${heading}" section — it was renamed or removed`);
  if (hits.length > 1) {
    throw new Error(`${source}: "${heading}" appears ${hits.length} times — a rule is read from the `
      + 'first occurrence, so a second section under the same heading changes behaviour while every '
      + 'assertion against it keeps passing. State the section once.');
  }
  const rest = md.slice(first.index + heading.length);
  const end = rest.search(/\n#{1,2} /);
  return end < 0 ? rest : rest.slice(0, end);
}

/** One row of the convergence table: the state a topic reaches, and what follows from it. */
interface ConvergenceRow {
  readonly topic: string;
  readonly state: string;
  readonly outcome: string;
}

/**
 * The convergence outcomes the model requires, compared as a whole ordered set — `.find()` would read
 * the first plausible row and never see a contradicting one added after it.
 */
const EXPECTED_CONVERGENCE: readonly {
  readonly topic: string; readonly state: string; readonly outcomeIncludes: readonly string[];
}[] = [
  { topic: 'positions differ', state: 'contested', outcomeIncludes: ['carried into the next round'] },
  {
    topic: 'one speaker, blocker or high',
    state: 'contested',
    outcomeIncludes: ['has not spoken on it', 'casting vote', 'user'],
  },
  { topic: 'one speaker, lower severity', state: 'folded in', outcomeIncludes: ['named'] },
  {
    topic: 'raised by some, unaddressed by others',
    state: 'not settled',
    outcomeIncludes: ['silence is never agreement'],
  },
];

/**
 * The convergence table, parsed by content rather than matched by phrase: a sentence fragment survives
 * an added qualifier, a parsed cell does not. @throws if the section, its table or a cell is absent.
 */
export function parseConvergence(md: string, source: string): ConvergenceRow[] {
  const body = section(md, '## Converging a round', source);
  const rows = body.split('\n').filter((l) => l.startsWith('|') && !/^\|\s*-+/.test(l));
  const data = rows.slice(1); // the header row is not data
  if (data.length < EXPECTED_CONVERGENCE.length) {
    throw new Error(`${source}: § Converging a round has ${data.length} table rows, expected `
      + `${EXPECTED_CONVERGENCE.length} — a dropped row removes an outcome the model requires`);
  }
  return data.map((line) => {
    const [, topic, state, outcome] = line.split('|').map((c) => c.trim().toLowerCase());
    if (topic === undefined || state === undefined || outcome === undefined) {
      throw new Error(`${source}: a convergence row is missing a cell — row was: ${line.trim()}`);
    }
    return { topic, state, outcome };
  });
}

/**
 * Whole sentences of a section, normalised. A qualifier added anywhere changes the sentence, so an
 * inversion that survives every fragment pin fails here.
 */
export function sentences(sectionText: string): string[] {
  return sectionText
    .split('\n')
    // Table rows carry no terminator, so leaving them in glues the table onto the sentence beside it.
    .filter((line) => !line.trimStart().startsWith('|'))
    .join(' ')
    .replace(/\s+/g, ' ')
    .split(/(?<=[.!?])\s+/)
    .map((s) => s.trim().toLowerCase())
    .filter(Boolean);
}

/**
 * Read the tier rows out of a surface carrying the rubric table. @throws if the section is absent or a
 * row is missing, unparseable or names an unknown tier — each naming `source`, not the guard.
 */
export function parseScalingModel(md: string, source: string): TierRow[] {
  const lines = section(md, SECTION_HEADING, source).split('\n').filter((l) => l.startsWith(ROW_PREFIX));
  if (lines.length !== TIER_ORDER.length) {
    throw new Error(`${source}: parsed ${lines.length} tier rows, expected ${TIER_ORDER.length} — `
      + 'a row was dropped or its shape changed, and a partial model is not a model');
  }
  return lines.map((line) => {
    const cells = line.split('|').map((c) => c.trim());
    const [, rawTier, , , advisors, rounds] = cells;
    if (rawTier === undefined || advisors === undefined || rounds === undefined) {
      throw new Error(`${source}: tier row has ${Math.max(cells.length - 2, 0)} cells, expected the `
        + `advisor and round columns — row was: ${line.trim()}`);
    }
    const tier = rawTier.replace(/`/g, '').replace('complexity:', '');
    if (!isTier(tier)) {
      throw new Error(`${source}: unknown tier token "${tier}" — expected one of ${TIER_ORDER.join(', ')}`);
    }
    return { tier, advisors, rounds };
  });
}
