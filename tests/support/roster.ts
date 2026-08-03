import { readdirSync } from 'node:fs';
import { join } from 'node:path';

import { repoRoot } from './repo';

/**
 * Who the project ships as agents, read from src/content/agents/ because that is what the build
 * reads. rosterSync then proves the shipped settings.json roster matches it.
 */

const AGENTS_DIR = join(repoRoot, 'src', 'content', 'agents');

/** The lead persona. Registered like the others, but never one of the advisors it convenes. */
export const LEAD = 'hercules';

/** The executor. A registered subagent, but not a debate advisor either. */
export const BUILDER = 'builder';

/** Every authored agent, by stem, sorted — lead and builder included. */
export function agentNames(): string[] {
  return readdirSync(AGENTS_DIR)
    .filter((name) => name.endsWith('.md'))
    .map((name) => name.slice(0, -'.md'.length))
    .sort();
}

/** Every advisor the debate can convene: the roster minus the lead and the executor. */
export function advisorNames(): string[] {
  return agentNames().filter((name) => name !== LEAD && name !== BUILDER);
}
