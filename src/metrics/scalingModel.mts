/**
 * The scaling model, stated once, and the extractor that reads it back off a shipped surface.
 *
 * Complexity sizes two things together: how many advisors are convened, and how many rounds they may
 * hold. That pair is written on several surfaces — the rubric, the README table, the injected core —
 * and they have to agree, so each is parsed and compared against `EXPECTED_MODEL` rather than being
 * spot-checked for a substring.
 *
 * The extractor throws instead of returning an empty parse. A guard that silently reads nothing
 * reports success while the surface it was meant to police drifts freely.
 */

export const TIER_ORDER = ['trivial', 'low', 'medium', 'high', 'critical'] as const;

export type Tier = (typeof TIER_ORDER)[number];

export interface TierRow {
  readonly tier: Tier;
  /** Advisor count or range as written, e.g. `2` or `2–3`. */
  readonly advisors: string;
  /** Round count or range as written, e.g. `1–2` or `2–3 + fresh eyes`. */
  readonly rounds: string;
}

export const EXPECTED_MODEL: readonly TierRow[] = [
  { tier: 'trivial', advisors: '0', rounds: '0' },
  { tier: 'low', advisors: '2', rounds: '1' },
  { tier: 'medium', advisors: '2–3', rounds: '1–2' },
  { tier: 'high', advisors: '3–5', rounds: '1–2' },
  { tier: 'critical', advisors: '4–6', rounds: '2–3 + fresh eyes' },
];

const SECTION_HEADING = '## complexity';
const ROW_PREFIX = '| `complexity:';

function isTier(value: string): value is Tier {
  return (TIER_ORDER as readonly string[]).includes(value);
}

/**
 * A named section, ending at the next heading of the same or higher level.
 *
 * Throws when the heading is missing — a guard that silently reads nothing reports success while the
 * surface it polices drifts — and throws when it appears more than once. Returning the first match is
 * not a harmless simplification: a second section under the same heading, carrying a contradicting
 * rule or a rubric row of its own, is invisible to every assertion made through this function, and a
 * mutation doing exactly that survived a full suite. The duplicate is the defect, so it is reported.
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
export interface ConvergenceRow {
  readonly topic: string;
  readonly state: string;
  readonly outcome: string;
}

/**
 * The convergence outcomes the model requires, as an exact set.
 *
 * Matching a row by `.find()` reads the first row whose topic looks right and ignores the rest, so a
 * contradicting row *added after* the real one is never seen. The row set is therefore compared whole:
 * an added row is a length mismatch, and a reordered one is a positional mismatch.
 *
 * `outcome` is matched by the substrings that carry the consequence rather than by the full cell,
 * because the cell also carries wording the golden pin already fixes.
 */
export const EXPECTED_CONVERGENCE: readonly {
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
 * The convergence table, parsed by content rather than matched by phrase. Asserting a row's own
 * cells is what makes an inversion fail: a sentence fragment survives an added qualifier, a parsed
 * cell does not.
 *
 * @throws if the section or its table is absent, or a row is missing a cell.
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
 * Whole sentences of a section, normalised. Pinning a whole sentence is what defeats the inversion
 * that beat every fragment pin in this repo's history: a qualifier added anywhere in the sentence
 * changes it, so the assertion fails, where a fragment of it would still have matched.
 */
export function sentences(sectionText: string): string[] {
  return sectionText
    .split('\n')
    // Table rows carry no terminator, so leaving them in glues the whole table onto the sentence
    // beside it and every pin against that sentence matches the table instead of the rule.
    .filter((line) => !line.trimStart().startsWith('|'))
    .join(' ')
    .replace(/\s+/g, ' ')
    .split(/(?<=[.!?])\s+/)
    .map((s) => s.trim().toLowerCase())
    .filter(Boolean);
}

/**
 * Read the tier rows out of a surface carrying the rubric table.
 *
 * @throws if the section is absent, a row is missing or unparseable, or a tier token is unknown —
 * each names `source` so a failure points at the file rather than at the guard.
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
