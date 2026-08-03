/**
 * Loading-chain definitions for the instruction-budget gate: a chain is everything one agent
 * invocation reads at once. Every template is DATA, so a new chain is an entry, never a function.
 */

import { globSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

import { countAtomicInstructions, extractSection } from './instructionCounter.mjs';

/** The one absolute ceiling for every chain, grounded in arXiv:2507.11538 (IFScale): top models hold
 * near-perfect adherence through 150+ instructions. Frontier-specific — a cheaper tier degrades earlier. */
export const HARD_GATE = 150;

/** One fixed or variable part of a chain, resolved against `distRoot` (a target's `dist/<ecosystem>/`). */
interface ChainPart {
  readonly label: string;
  /** A literal file, relative to `distRoot`. Mutually exclusive with `glob`. */
  readonly file?: string;
  /** A glob (relative to `distRoot`) whose MATCHES ARE SUMMED into this one part. For "one chain per
   * match" instead, use a template's top-level `variable` field. */
  readonly sumGlob?: string;
  /** Restrict counting to the slice between two headers within the resolved file(s). */
  readonly section?: { readonly start: string; readonly stop?: string };
}

interface ChainTemplate {
  readonly name: string;
  readonly fixed: readonly ChainPart[];
  /** When present, this template expands into ONE concrete chain per glob match, each named
   * `${name}: ${basename}` and carrying that one file as an additional fixed-equivalent part. */
  readonly variable?: { readonly glob: string; readonly label: string };
}

interface ResolvedChain {
  readonly name: string;
  readonly value: number;
  readonly breakdown: ReadonlyMap<string, number>;
}

function measurePart(distRoot: string, part: ChainPart): number {
  const read = (relativePath: string): string => {
    const text = readFileSync(join(distRoot, relativePath), 'utf-8');
    return part.section ? extractSection(text, part.section.start, part.section.stop) : text;
  };
  if (part.file !== undefined) return countAtomicInstructions(read(part.file));
  if (part.sumGlob !== undefined) {
    return globSync(part.sumGlob, { cwd: distRoot }).reduce((sum, relativePath) => sum + countAtomicInstructions(read(relativePath)), 0);
  }
  throw new Error(`chain part '${part.label}' names neither 'file' nor 'sumGlob'`);
}

/**
 * The concrete chains one template expands to: itself when fixed, or one per glob match when
 * `variable`, each carrying that match as an extra part.
 */
function expandTemplate(
  template: ChainTemplate,
  distRoot: string,
): Array<{ name: string; extra: ChainPart | undefined }> {
  const { variable } = template;
  if (variable === undefined) return [{ name: template.name, extra: undefined }];
  return globSync(variable.glob, { cwd: distRoot }).sort().map((relativePath) => ({
    name: `${template.name}: ${relativePath}`,
    extra: { label: variable.label, file: relativePath },
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
 * A named, expiring exception for a chain over `HARD_GATE`. `measuredAt` PINS the accepted value, so
 * the chain cannot grow past it unreviewed, and a waiver back under the gate is flagged for deletion.
 */
interface Waiver {
  readonly chain: string;
  readonly measuredAt: number;
  readonly reason: string;
  readonly followUp: string;
}

// Every chain measures under HARD_GATE, so nothing is waived.
export const WAIVERS: readonly Waiver[] = [];
