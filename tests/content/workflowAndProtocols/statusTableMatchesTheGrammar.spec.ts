import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import { ALLOWED_STATUSES } from '../../budgets/a2aGrammar.mjs';
import { countStatusTableRows } from '../support/statusTable';
import { repoRoot } from '../../support/repo';

/**
 * The statuses an advisor is TOLD it may use and the statuses the grammar ACCEPTS must be the same six.
 * A seventh in the table lands on the advisor, mid-task, as a reply that looks malformed for no reason.
 */

const PROTOCOL = join(repoRoot, 'dist', 'claude-code', 'protocols', 'a2a-communication-protocol.md');

function protocolText(): string {
  return readFileSync(PROTOCOL, 'utf-8');
}

describe('the status table an advisor reads and the grammar that checks it', () => {
  it('there is a table to read and a vocabulary to check against', () => {
    // Guards the guard: a missing table returns -1, which against an empty set lets both be wrong.
    expect(countStatusTableRows(protocolText()),
      'the shipped protocol carries no STATUS | Meaning | ACTION table').toBeGreaterThan(0);
    expect(ALLOWED_STATUSES.size, 'the grammar accepts no statuses at all').toBeGreaterThan(1);
  });

  it('lists exactly the statuses the checker accepts, no more and no fewer', () => {
    const text = protocolText();
    expect(countStatusTableRows(text),
      'the table and the accepted vocabulary disagree on how many statuses exist').toBe(ALLOWED_STATUSES.size);

    const missing = [...ALLOWED_STATUSES].filter((status) => !text.includes(`| \`${status}\` |`));
    expect(missing,
      'the checker accepts these statuses, but the table never tells an advisor they exist').toEqual([]);
  });
});
