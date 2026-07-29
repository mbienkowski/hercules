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

/** The `## complexity` section, ending at the next heading of the same or higher level. */
function section(md: string, source: string): string {
  const start = md.search(new RegExp(`^${SECTION_HEADING}\\s*$`, 'm'));
  if (start < 0) {
    throw new Error(`${source}: no "${SECTION_HEADING}" section — the rubric heading was renamed or removed, `
      + 'so nothing states how a tier is scored');
  }
  const rest = md.slice(start + SECTION_HEADING.length);
  const end = rest.search(/\n#{1,2} /);
  return end < 0 ? rest : rest.slice(0, end);
}

/**
 * Read the tier rows out of a surface carrying the rubric table.
 *
 * @throws if the section is absent, a row is missing or unparseable, or a tier token is unknown —
 * each names `source` so a failure points at the file rather than at the guard.
 */
export function parseScalingModel(md: string, source: string): TierRow[] {
  const lines = section(md, source).split('\n').filter((l) => l.startsWith(ROW_PREFIX));
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
