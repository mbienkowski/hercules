/**
 * Status-table row counting in markdown files.
 *
 * Instruction counting used to live here too (`countInstructions`, bullets/numbers only, no
 * fenced content), alongside a SECOND, deliberately-different counter in the instruction-budget
 * gate (`_count_instruction_blocks`, bullets/numbers/bold-labels/fenced-numbered-rules, then
 * scaled ÷3 against a guessed multiplier). Commit 11 collapsed both into the ONE atomic counter —
 * see `instructionCounter.mts`'s `countAtomicInstructions` — so this module now owns only the
 * status-table concern.
 */

/**
 * Count data rows in the STATUS reference table (header: `STATUS | Meaning | ACTION`).
 *
 * Returns -1 when no matching header row is found.
 */
export function countStatusTableRows(text: string): number {
  const lines = text.split('\n');
  let headerIndex = -1;
  for (let lineIndex = 0; lineIndex < lines.length; lineIndex += 1) {
    const stripped = (lines[lineIndex] as string).trim();
    if (stripped.startsWith('|') && stripped.includes('STATUS') && stripped.includes('Meaning') && stripped.includes('ACTION')) {
      headerIndex = lineIndex;
      break;
    }
  }
  if (headerIndex === -1) return -1;

  let rowCount = 0;
  for (const line of lines.slice(headerIndex + 2)) { // skip header row + separator row
    if (!line.trim().startsWith('|')) break;
    rowCount += 1;
  }
  return rowCount;
}
