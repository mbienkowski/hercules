/**
 * Atomic instruction counting: how many distinct directives a stretch of markdown asks an agent to
 * follow. Feeds the loading-chain ceilings in `loadingChains.mts`.
 *
 * A UNIT is a bullet, a numbered item, or a bold-labelled block, fenced content included — a fenced
 * protocol excerpt still costs the agent reading it real attention. Each unit splits on `,` `;` `&`
 * `and` `or` `then`, and every fragment of at least two words is one directive, so "always X, never
 * Y, and Z" counts as three. The metric deliberately OVER-counts: undercounting a chain's cognitive
 * load is the dangerous direction, and pure regex keeps a miscount a one-line reviewed diff.
 */

const SEPARATOR_RE = /,|;|&|\band\b|\bor\b|\bthen\b/i;

const BULLET_RE = /^[-*]\s+\S/;
const NUMBERED_RE = /^\d+\.\s+\S/;
const BOLD_LABEL_RE = /^\*\*[A-Z0-9]/;

/**
 * Every unit line in `text`: a bullet, a numbered item, or a bold-labelled block, matched regardless
 * of fence state. No fence tracking is needed — a fence delimiter starts with three backticks and so
 * can never satisfy a unit pattern, while a numbered rule inside a fence counts like any other unit.
 */
function findUnits(text: string): string[] {
  const units: string[] = [];
  for (const rawLine of text.split('\n')) {
    const line = rawLine.trim();
    if (BULLET_RE.test(line) || NUMBERED_RE.test(line) || BOLD_LABEL_RE.test(line)) {
      units.push(line);
    }
  }
  return units;
}

/** The number of whitespace-separated words in `s` (`\S+` runs, so boundary whitespace never counts). */
function wordCount(s: string): number {
  return s.match(/\S+/g)?.length ?? 0;
}

const MIN_WORDS_PER_DIRECTIVE = 2; // a shorter fragment (a bare "and", a one-word aside) is dropped as noise

function countAtomicDirectives(unit: string): number {
  const directives = unit
    .split(SEPARATOR_RE)
    .filter((fragment) => wordCount(fragment) >= MIN_WORDS_PER_DIRECTIVE);
  // Even a unit too short to split into any qualifying fragment still counts as one directive itself.
  return Math.max(directives.length, 1);
}

/** Atomic instruction count across every unit in `text`. */
export function countAtomicInstructions(text: string): number {
  return findUnits(text).reduce((sum, unit) => sum + countAtomicDirectives(unit), 0);
}

/** Extract the slice of `text` between `start` and an optional `stop` header, inclusive of `start`. */
export function extractSection(text: string, start: string, stop?: string): string {
  const idx = text.indexOf(start);
  if (idx === -1) return '';
  if (stop === undefined) return text.slice(idx);
  const end = text.indexOf(stop, idx + start.length);
  return end === -1 ? text.slice(idx) : text.slice(idx, end);
}
