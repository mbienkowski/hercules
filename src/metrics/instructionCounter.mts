/**
 * Atomic instruction counting across agent loading chains — the V2 metric.
 *
 * Supersedes two counters that used to disagree: `markdown_metrics.count_instructions` (bullets
 * and numbers only, ignoring fenced content) and the budget gate's own `_count_instruction_blocks`
 * (bullets/numbers/bold-labels/fenced-numbered-rules) — both SECTION-level: one counted unit
 * typically bundles 2-4 real directives, which is why the old gate divided its 150-instruction
 * research ceiling by 3 before comparing (a guessed multiplier, not a measurement). V2 counts
 * atomically instead: it finds the same UNITS `_count_instruction_blocks` did (a bullet, a numbered
 * item, a bold-labelled block, or a numbered rule inside a fenced fixture — deliberately including
 * fenced content, unlike `count_instructions`, since a fenced protocol excerpt like the A2A Core's
 * `MODE`/`ROLE`/`STATUS` list still costs the runtime agent reading it real attention), then splits
 * each unit's text on `,` `;` `&` `and` `or` `then` into fragments and counts every fragment of at
 * least two words as its own directive — so a single bulleted sentence carrying three real
 * imperatives ("always X, never Y, and Z") counts as three, not one.
 *
 * Deliberately OVER-counts: a fragment under two words is dropped as noise (a bare "and" or a
 * one-word aside), but nothing beyond that length threshold is filtered — the ceiling this feeds is
 * a safety margin, and undercounting a chain's real cognitive load is the dangerous direction, not
 * overcounting it. Pure regex, no NLP dependency, so a miscount is fixable with a one-line reviewed
 * diff rather than a dependency bump silently moving every budget (`compromise` and peers have
 * shipped count-changing tokenization fixes in non-major releases — exactly the drift this design
 * avoids).
 *
 * A vocabulary-anchored variant was tried first — counting a fragment only when it was the unit's
 * own leading clause OR contained a word from a closed imperative list (`always`/`never`/`ensure`/
 * the RFC 2119 subset `must`/`should`/`shall`/`may`/etc.) — and measured LOW against the project's
 * own reference chains (CLAUDE.md 23 vs. a target of 39; the full orchestrator chain 84 vs. 160).
 * The plain separator-and-length-only version below reproduces every one of those reference numbers
 * EXACTLY (see `instructionCounter.spec.ts`'s golden-corpus test), which is why it shipped instead:
 * simpler, and empirically correct against real content, beats a fancier design that undercounts.
 */

const SEPARATOR_RE = /,|;|&|\band\b|\bor\b|\bthen\b/i;

const BULLET_RE = /^[-*]\s+\S/;
const NUMBERED_RE = /^\d+\.\s+\S/;
const BOLD_LABEL_RE = /^\*\*[A-Z0-9]/;

/**
 * The same UNIT identification `_count_instruction_blocks` used: a bullet, a numbered item, or a
 * bold-labelled block. Matched unconditionally regardless of fence state — a fence delimiter line
 * always starts with three backticks, which can never satisfy any of the three unit patterns above
 * (each requires `-`/`*`/a digit/`**` as its first character), so a numbered rule inside a fenced
 * fixture is already caught by the same unconditional check. No separate fence-tracking is needed:
 * an earlier version both toggled an `inFence` flag AND special-cased skipping the delimiter line
 * itself — neither could ever change this function's output, since a delimiter line can never match
 * any unit pattern with or without being skipped, and a numbered rule INSIDE a fence had already
 * been matched (or not) by the same unconditional check regardless of fence state.
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

/**
 * Every separator-delimited fragment of `unit` with at least two words counts as one directive.
 *
 * Words are counted via `\S+` runs directly — not `split(/\s+/)` — so leading/trailing whitespace
 * on a fragment (from `SEPARATOR_RE` not itself trimming) never needs a separate `.trim()` pass:
 * `\S+` only ever matches non-whitespace runs, so there is nothing left for a boundary-whitespace
 * artifact to slip through as a false "word".
 */
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

/** Atomic instruction count across every unit in `text` — the ONE counter this project uses. */
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
