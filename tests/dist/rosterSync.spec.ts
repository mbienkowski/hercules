import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

import { afterAll, beforeAll, describe, expect, it } from 'vitest';

import { buildDistribution } from '../../internal/builder/build.mjs';
import { loadRecipe } from '../../internal/builder/recipe-loader.mjs';
import { repoRoot } from '../support/repo';
import { tempWorkspace } from '../support/tempWorkspace';

// The Claude-only settings.json roster stays in sync with content/agents/, read as it SHIPS — the
// file is an ordinary source rendered by the claude-code recipe's `settings.json` entry.

const AGENTS = join(repoRoot, 'src', 'content', 'agents');
const RECIPE_FILE = 'src/targets/claude-code.json';

const workspace = tempWorkspace();
let shipped: Record<string, unknown>;

beforeAll(async () => {
  const recipe = loadRecipe(RECIPE_FILE, repoRoot);
  // Fail loudly: a claude-code that ships no roster is the failure this file reports.
  expect(Object.keys(recipe.targets), 'claude-code must ship settings.json').toContain('settings.json');
  const out = join(workspace.make('hercules-roster-'), 'claude-code');
  await buildDistribution(recipe, RECIPE_FILE, out, repoRoot);
  shipped = JSON.parse(readFileSync(join(out, 'settings.json'), 'utf-8')) as Record<string, unknown>;
});

afterAll(workspace.cleanup);

describe('registered agent roster matches the agents that actually exist', () => {
  it('the default agent plus every advisor exactly matches content/agents/', () => {
    // Catches a new agent never registered, or a removed agent's registration left behind. The
    // builder is a registered subagent, so it counts alongside the default agent and the advisors.
    const roster = new Set(readdirSync(AGENTS).filter((n) => n.endsWith('.md')).map((n) => n.slice(0, -3)));
    const listed = new Set([shipped['agent'] as string, ...(shipped['advisors'] as string[]), 'builder']);
    expect(listed).toEqual(roster);
  });
});

describe('hercules is the default agent', () => {
  it('out of the box, with no explicit agent choice made, Claude Code defaults to hercules', () => {
    expect(shipped['agent']).toBe('hercules');
  });
});
