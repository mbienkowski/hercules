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
  let contentStart = -1; // stays -1 until the OPENING ``` fence is seen
  for (let i = 0; i < lines.length; i += 1) {
    const isFence = (lines[i] as string).trimStart().startsWith('```');
    if (!isFence) continue;
    if (contentStart === -1) {
      contentStart = i + 1; // opening fence — the block's content begins on the next line
    } else {
      return { text: lines.slice(contentStart, i).join('\n'), found: true }; // closing fence — done
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
  const FIELD_SEPARATOR = ' | ';
  const separatorCount = line.split(FIELD_SEPARATOR).length - 1;
  return separatorCount === 2; // two separators => three fields: [ROLE] STATUS | CONTENT | ACTION
}

/** Return the STATUS value from each A2A entry line found in text. */
export function extractUsedStatuses(text: string): string[] {
  return [...text.matchAll(ENTRY_RE_GLOBAL)].map((m) => m[1] as string);
}
