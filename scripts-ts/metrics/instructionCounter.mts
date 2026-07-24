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
 * The same UNIT identification `_count_instruction_blocks` used: a bullet, a numbered item outside
 * a fence, a bold-labelled block, or a numbered rule INSIDE a fence.
 */
function findUnits(text: string): string[] {
  const units: string[] = [];
  let inFence = false;
  for (const rawLine of text.split('\n')) {
    const line = rawLine.trim();
    if (line.startsWith('```')) {
      inFence = !inFence;
      continue;
    }
    if (BULLET_RE.test(line) || NUMBERED_RE.test(line) || BOLD_LABEL_RE.test(line)) {
      units.push(line);
    } else if (inFence && NUMBERED_RE.test(line)) {
      units.push(line);
    }
  }
  return units;
}

/** Every separator-delimited fragment of `unit` with at least two words counts as one directive. */
function countAtomicDirectives(unit: string): number {
  const fragments = unit
    .split(SEPARATOR_RE)
    .map((f) => f.trim())
    .filter((f) => f.split(/\s+/).filter(Boolean).length >= 2);
  return Math.max(fragments.length, 1); // the unit itself is still one directive, even if too short to split
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
