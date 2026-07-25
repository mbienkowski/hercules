/** A2A protocol entry structure validation and vocabulary checks. */

export const ALLOWED_STATUSES: ReadonlySet<string> = new Set([
  'Blocker', 'High', 'Medium', 'Nitpick', 'Pass', 'Info',
]);

const CORE_ENTRY_RE = /^\d+\./;
const ENTRY_RE = /\[[A-Z][A-Z0-9_-]*\] (Blocker|High|Medium|Nitpick|Pass|Info) \|/;
const ENTRY_RE_GLOBAL = new RegExp(ENTRY_RE.source, 'g');

/** Extract the content of the first fenced ``` block — the injected A2A Core. */
export function extractA2aCore(md: string): { text: string; found: boolean } {
  const lines = md.split('\n');
  let start = -1;
  for (let i = 0; i < lines.length; i += 1) {
    if ((lines[i] as string).trimStart().startsWith('```')) {
      if (start === -1) {
        start = i + 1;
      } else {
        return { text: lines.slice(start, i).join('\n'), found: true };
      }
    }
  }
  return { text: '', found: false };
}

/**
 * Count top-level numbered entries (`^\d+\.`) inside a Core block.
 *
 * Continuation lines are indented and do not match.
 */
export function countCoreEntries(text: string): number {
  return text.split('\n').filter((line) => CORE_ENTRY_RE.test(line)).length;
}

/** Return all `[ROLE] STATUS | CONTENT | ACTION` lines found in text. */
export function findCoreEntryLines(text: string): string[] {
  const out: string[] = [];
  for (const line of text.split('\n')) {
    const m = ENTRY_RE.exec(line);
    if (m !== null) out.push(line.slice(m.index));
  }
  return out;
}

/**
 * Return true if a line matches the `[ROLE] STATUS | CONTENT | ACTION` structure.
 *
 * The entry must contain exactly two `' | '` field separators (three fields total). A bare `|`
 * inside the CONTENT field is permitted — only `' | '` with spaces counts.
 */
export function matchesA2aEntryFormat(line: string): boolean {
  return line.split(' | ').length - 1 === 2;
}

/** Return the STATUS value from each A2A entry line found in text. */
export function extractUsedStatuses(text: string): string[] {
  return [...text.matchAll(ENTRY_RE_GLOBAL)].map((m) => m[1] as string);
}
