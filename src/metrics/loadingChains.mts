/**
 * Data-driven loading-chain definitions for the instruction-budget gate.
 *
 * A "chain" is everything one agent invocation actually has to read at once. Each chain TEMPLATE
 * below is DATA — a list of fixed parts (always present) plus at most one variable part (a glob
 * that fans out into one concrete chain per matching file, e.g. one chain per agent, per command,
 * per skill) — not hardcoded per-scenario logic. Adding a chain for a new action, or a per-ecosystem
 * chain, is a new entry in `CHAIN_TEMPLATES`, never a new function.
 *
 * The ceiling is ABSOLUTE (150 hard, 130 warn — see `HARD_GATE`/`WARN_AT`), not the old
 * `_SUB_AGENT_GATE`/`_ORCHESTRATOR_GATE`/`_SKILL_GATE` trio, each an independently-guessed ÷3
 * scaling of the same 150-instruction research ceiling. One ceiling, uniformly applied, is simpler
 * and removes three numbers that could silently drift apart from each other.
 */

import { globSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

import { countAtomicInstructions, extractSection } from './instructionCounter.mjs';

/** Absolute ceiling, grounded in arXiv:2507.11538 (IFScale): top models hold near-perfect
 * adherence through 150+ instructions before declining. Frontier-reasoning-specific — a cheaper
 * model tier degrades earlier (a documented, deliberately deferred follow-up: tier-aware ceilings,
 * once a chain's resolved model tier is available at gate time). */
export const HARD_GATE = 150;
/** NOT a research figure — a project safety margin (~87% of the hard gate), documented as such. */
export const WARN_AT = 130;

/** One fixed or variable part of a chain, resolved against `distRoot` (a target's `dist/<eco>/`). */
export interface ChainPart {
  readonly label: string;
  /** A literal file, relative to `distRoot`. Mutually exclusive with `glob`. */
  readonly file?: string;
  /** A glob (relative to `distRoot`) whose MATCHES ARE SUMMED into this one part — e.g. every
   * shipped protocol. For "one chain per match" instead (agents, commands, skills), use a template's
   * top-level `variable` field, not this. */
  readonly sumGlob?: string;
  /** Restrict counting to the slice between two headers within the resolved file(s). */
  readonly section?: { readonly start: string; readonly stop?: string };
}

export interface ChainTemplate {
  readonly name: string;
  readonly fixed: readonly ChainPart[];
  /** When present, this template expands into ONE concrete chain per glob match, each named
   * `${name}: ${basename}` and carrying that one file as an additional fixed-equivalent part. */
  readonly variable?: { readonly glob: string; readonly label: string };
}

export interface ResolvedChain {
  readonly name: string;
  readonly value: number;
  readonly breakdown: ReadonlyMap<string, number>;
}

function measurePart(distRoot: string, part: ChainPart): number {
  const read = (rel: string): string => {
    const text = readFileSync(join(distRoot, rel), 'utf-8');
    return part.section ? extractSection(text, part.section.start, part.section.stop) : text;
  };
  if (part.file !== undefined) return countAtomicInstructions(read(part.file));
  if (part.sumGlob !== undefined) {
    return globSync(part.sumGlob, { cwd: distRoot }).reduce((sum, rel) => sum + countAtomicInstructions(read(rel)), 0);
  }
  throw new Error(`chain part '${part.label}' names neither 'file' nor 'sumGlob'`);
}

/**
 * The concrete chains one template expands to: just itself for a fixed template, or one per glob
 * match for a `variable` template (each carrying that match as an extra part). Because the glob arm
 * runs only after the early return, `variable` is provably defined there — no `?.` or cast needed.
 */
function expandTemplate(
  template: ChainTemplate,
  distRoot: string,
): Array<{ name: string; extra: ChainPart | undefined }> {
  const { variable } = template;
  if (variable === undefined) return [{ name: template.name, extra: undefined }];
  return globSync(variable.glob, { cwd: distRoot }).sort().map((rel) => ({
    name: `${template.name}: ${rel}`,
    extra: { label: variable.label, file: rel },
  }));
}

/** Expand every template into its concrete chains (one per glob match, for a `variable` template). */
export function resolveChains(distRoot: string, templates: readonly ChainTemplate[]): ResolvedChain[] {
  const out: ResolvedChain[] = [];
  for (const template of templates) {
    for (const { name, extra } of expandTemplate(template, distRoot)) {
      const parts = extra === undefined ? template.fixed : [...template.fixed, extra];
      const breakdown = new Map<string, number>();
      let value = 0;
      for (const part of parts) {
        const n = measurePart(distRoot, part);
        breakdown.set(part.label, n);
        value += n;
      }
      out.push({ name, value, breakdown });
    }
  }
  return out;
}

const A2A_CORE: ChainPart = {
  label: 'a2a-core',
  file: 'protocols/a2a-communication-protocol.md',
  section: { start: '## Agent-Injected Core', stop: '## Orchestrator Section' },
};
const CLAUDE_MD: ChainPart = { label: 'CLAUDE.md', file: 'CLAUDE.md' };
const ALL_PROTOCOLS: ChainPart = { label: 'protocols', sumGlob: 'protocols/*.md' };

/** The loading chains this project gates today — data, per this module's own top comment. */
export const CHAIN_TEMPLATES: readonly ChainTemplate[] = [
  {
    name: 'sub-agent',
    fixed: [A2A_CORE, CLAUDE_MD],
    variable: { glob: 'agents/*.md', label: 'agent' },
  },
  {
    name: 'orchestrator (per command)',
    fixed: [CLAUDE_MD, ALL_PROTOCOLS],
    variable: { glob: 'commands/*.md', label: 'command' },
  },
  {
    name: 'skill',
    fixed: [],
    variable: { glob: 'skills/*/SKILL.md', label: 'skill' },
  },
];

/**
 * A named, expiring exception: a chain that measures over `HARD_GATE` today, recorded — not
 * hidden — so CI stays green without the breach being invisible. `measuredAt` PINS the accepted
 * value: a chain may not grow even one instruction past it without the waiver itself being edited
 * (a reviewed diff), and shrinking below `HARD_GATE` again makes the waiver dead code the gate
 * test flags on its own (see `instructionBudget.spec.ts`), which is the signal to delete it.
 */
export interface Waiver {
  readonly chain: string;
  readonly measuredAt: number;
  readonly reason: string;
  readonly followUp: string;
}

export const WAIVERS: readonly Waiver[] = [
  {
    chain: 'orchestrator (per command): commands/build.md',
    measuredAt: 160,
    reason: "ceiling 150, over by 10 — trim build.md's own instruction load",
    followUp: 'migration spec § What this sets up: "Trimming build.md to retire the orchestrator waiver"',
  },
];
