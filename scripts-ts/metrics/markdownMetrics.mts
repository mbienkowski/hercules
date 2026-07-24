/** Instruction and status-table row counting in markdown files. */

const NUMBERED_RE = /^\s*\d+\.\s/;
const BULLET_RE = /^\s*[-*]\s/;

/**
 * Count numbered and bulleted list items, excluding any inside fenced code blocks.
 *
 * Table rows start with `|` and never match a list-item pattern, so they are excluded
 * automatically — no explicit table check is needed here.
 */
export function countInstructions(text: string): number {
  let n = 0;
  let inFence = false;
  for (const line of text.split('\n')) {
    const stripped = line.trimStart();
    if (stripped.startsWith('```')) {
      inFence = !inFence;
      continue;
    }
    if (inFence) continue;
    if (NUMBERED_RE.test(line) || BULLET_RE.test(line)) n += 1;
  }
  return n;
}

/**
 * Count data rows in the STATUS reference table (header: `STATUS | Meaning | ACTION`).
 *
 * Returns -1 when no matching header row is found.
 */
export function countStatusTableRows(text: string): number {
  const lines = text.split('\n');
  let headerIndex = -1;
  for (let i = 0; i < lines.length; i += 1) {
    const stripped = (lines[i] as string).trim();
    if (stripped.startsWith('|') && stripped.includes('STATUS') && stripped.includes('Meaning') && stripped.includes('ACTION')) {
      headerIndex = i;
      break;
    }
  }
  if (headerIndex === -1) return -1;

  let n = 0;
  for (const line of lines.slice(headerIndex + 2)) { // skip header row + separator row
    if (!line.trim().startsWith('|')) break;
    n += 1;
  }
  return n;
}
