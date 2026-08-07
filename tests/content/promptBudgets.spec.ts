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
  // 3000 → 3100 → 3300 → 3400 at the owner's request. The 3300 rise bought Step 2 binding the
  // resolved path to Step 8 (so a repository keeps its own spelling) and Step 3b's architecture
  // extractor, the replacement for ~450 lines of per-language parsing deleted from coc_scan.py.
  // The last 100 buys what Step 3b must say when that extractor HANGS: the agent no longer runs it
  // (`extract` does, under a bound), a timeout is named as a hang rather than a wrong answer, the
  // retry is capped at one and honest about being a coin flip without per-file attribution, and a
  // denied extraction must be reported as denied — never allowed to read as "this repository has
  // no architecture". Re-measure DOWN when the update-mode section next shrinks.
  ['the code-of-conduct generator', 'skills/code-of-conduct-generator/SKILL.md', 3400],
  // 6600 → 6700 → 7300 at the owner's request. The first rise bought five gates a blind review
  // found being broken in real output. The second buys § Architecture extractor: the pseudocode,
  // the output schema and the five refusals that replace every per-language parser the scanner
  // used to carry. That catalogue was incomplete by construction and reported its own coverage as
  // complete while missing two ordinary layouts; instruction that travels to any language costs
  // tokens once, where a catalogue costs code forever. The third adds the extractor's runnable
  // blueprint: all the plumbing is identical everywhere, so the agent fills one function instead
  // of inventing the whole script under time pressure — a runtime failure that would otherwise
  // land differently every run. The blueprint also carries the symlink refusal forward: the
  // scanner no longer opens any file, so the exfiltration guard a security review forced had to
  // move to the one thing that still reads. 7900 → 8200 for what three review rounds found the
  // blueprint doing wrong: it dropped every ROOT-LEVEL file, starving `entrypoints` in exactly the
  // flat repositories whose entrypoint sits there; its `git ls-files` call had no timeout; four of
  // its six sections had no cap; and nothing recorded that the 2000-file cap had cut the reading
  // short, which is the same silent-truncation defect this file already paid for once.
  // Re-measure DOWN when the map next shrinks.
  ['its coverage map', 'skills/code-of-conduct-generator/coverage-map.md', 8200],
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
