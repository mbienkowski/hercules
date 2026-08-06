import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import { repoRoot } from '../support/repo';
import { LEAD, agentNames } from '../support/roster';
import { countCoreEntries, extractA2aCore } from '../budgets/a2aGrammar.mjs';
import { CHAIN_TEMPLATES, HARD_GATE, resolveChains, WAIVERS } from '../budgets/loadingChains.mjs';
import { countTokens } from '../budgets/tokenCounter.mjs';

/**
 * How much a tool has to read before it can act. Every ceiling is measured off a real file with a real
 * tokenizer and lives in one list, so raising one shows in a diff as a change to a limit.
 */

/** Tokens in a shipped file, as the model reading it would count them. */
function tokens(relativePath: string): number {
  return countTokens(readFileSync(join(repoRoot, relativePath), 'utf-8'));
}

// Every agent but the lead, read from src/content/agents/ rather than listed, so a deleted agent
// cannot silently stop being checked. The lead carries its own, larger ceiling in BUDGETS below.
const AGENTS = agentNames().filter((name) => name !== LEAD);

/** Every budget, as `[what it is, the file, its ceiling in tokens]`. */
const BUDGETS: ReadonlyArray<readonly [string, string, number]> = [
  ['the debate protocol', 'protocols/debate-consensus-protocol.md', 1700],
  ['the workflow protocol', 'protocols/workflow-protocol.md', 1250],
  ['the discover command', 'commands/discover.md', 2020],
  ['the design command', 'commands/design.md', 2200],
  ['the build command', 'commands/build.md', 3260],
  ['the ship command', 'commands/ship.md', 1800],
  ['the guided workflow command', 'commands/workflow.md', 2000],
  ['the project-reset command', 'commands/project-reset.md', 1620],
  ['the lead persona', 'agents/hercules.md', 1150],
  ['the learnings skill', 'skills/learnings/SKILL.md', 1050],
  ['the test-scenarios skill', 'skills/write-test-scenarios/SKILL.md', 1050],
  ['the reference skill', 'skills/hercules-reference/SKILL.md', 3900],
  ['the code-of-conduct generator', 'skills/code-of-conduct-generator/SKILL.md', 3000],
  // 6600 → 6700 at the owner's request. What the rise bought: five gates the map has to teach
  // because a blind review found each one being broken in real output — a `Check:` must name
  // something runnable, a universal claim must be verified or scoped, every scanned family must be
  // covered or declined, a heading may not exceed eight directives, and code blocks are invited.
  // The shape spec itself was deduplicated into SKILL.md § Step 5 first, which paid back ~200
  // tokens; this is the remainder. Re-measure DOWN when the catalogue next shrinks.
  ['its coverage map', 'skills/code-of-conduct-generator/coverage-map.md', 6700],
  ['the fusion-setup skill', 'skills/fusion-setup/SKILL.md', 1100],
];

// One distribution is measured: the content is the same everywhere, only the file names differ.
const SHIPPED = 'dist/claude-code';

describe('nothing we ship costs more to read than it earns back', () => {
  it('there are budgets to enforce', () => {
    // Guards the guard: an empty list would make every ceiling below vanish without a failure.
    expect(BUDGETS.length).toBeGreaterThan(10);
    expect(AGENTS.length).toBeGreaterThan(10);
  });

  for (const [what, relativePath, ceiling] of BUDGETS) {
    it(`${what} stays inside its ceiling`, () => {
      const used = tokens(`${SHIPPED}/${relativePath}`);
      expect(used, `${relativePath} is ${used} tokens, over its ${ceiling} ceiling`).toBeLessThanOrEqual(ceiling);
    });
  }

  it('no single advisor costs more than a thousand tokens to load', () => {
    // The ceiling is per advisor, not for the set: they are spawned one at a time, mid-task.
    const over = AGENTS
      .map((name) => [name, tokens(`${SHIPPED}/agents/${name}.md`)] as const)
      .filter(([, used]) => used > 1000);
    expect(over, 'these advisors are over their 1000-token ceiling').toEqual([]);
  });
});

describe('the agent-to-agent protocol stays teachable', () => {
  // A shape limit, not a size one: too few examples teach nothing, too many are never read to the end.
  const core = (): string => {
    const { text, found } = extractA2aCore(readFileSync(
      join(repoRoot, SHIPPED, 'protocols/a2a-communication-protocol.md'), 'utf-8'));
    expect(found, 'the protocol must carry a fenced Core block — it is what an agent reads first').toBe(true);
    return text;
  };

  it('shows enough examples to learn the format from', () => {
    expect(countCoreEntries(core())).toBeGreaterThanOrEqual(8);
  });

  it('and few enough that they are all read', () => {
    expect(countCoreEntries(core())).toBeLessThanOrEqual(20);
  });

  it('and the block an agent reads first stays inside its own ceiling', () => {
    // Measured on the Core block alone — what every agent-to-agent exchange actually carries.
    const used = countTokens(core());
    expect(used, `the Core block is ${used} tokens, over its 1050 ceiling`).toBeLessThanOrEqual(1050);
  });
});

describe('no single thing a model is asked to do buries it in instructions', () => {
  /**
   * A whole reading path rather than one file: an advisor is handed the shared protocol and the
   * project instructions with its own description, and that sum is what competes with the work.
   */
  const chains = resolveChains(join(repoRoot, SHIPPED), CHAIN_TEMPLATES);
  const waived = new Map(WAIVERS.map((waiver) => [waiver.chain, waiver]));

  it('there are reading paths to measure', () => {
    expect(chains.length, 'no loading chain resolved — the measurement found nothing').toBeGreaterThan(0);
  });

  it('every reading path is under the ceiling, or carries a recorded exception', () => {
    const unexplained = chains
      .filter((chain) => chain.value > HARD_GATE && !waived.has(chain.name))
      .map((chain) => `${chain.name}: ${chain.value} instructions (ceiling ${HARD_GATE})`);
    expect(unexplained, 'these reading paths are over the ceiling with nothing on record').toEqual([]);
  });

  it('a recorded exception has not quietly grown past what it was granted for', () => {
    const grown = chains
      .filter((chain) => waived.has(chain.name) && chain.value > (waived.get(chain.name)?.measuredAt ?? 0))
      .map((chain) => `${chain.name}: now ${chain.value}, granted at ${waived.get(chain.name)?.measuredAt}`);
    expect(grown, 'these exceptions cover less than the chain now costs').toEqual([]);
  });

  it('an exception whose path came back under the ceiling is deleted, not left lying around', () => {
    // A waiver nobody needs reads as "this is known to be over" and hides the next real breach.
    const dead = chains.filter((chain) => chain.value <= HARD_GATE && waived.has(chain.name)).map((c) => c.name);
    expect(dead, 'these exceptions are no longer needed').toEqual([]);
  });

  it('every recorded exception names a reading path that exists', () => {
    const known = new Set(chains.map((chain) => chain.name));
    expect(WAIVERS.map((w) => w.chain).filter((name) => !known.has(name)),
      'these exceptions name a path that no longer exists').toEqual([]);
  });
});
