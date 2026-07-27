import { expect } from 'vitest';

import { discover } from '../../../builder/descriptor.mjs';
import { ECOSYSTEMS } from '../../../commons/support/descriptorFixtures';

/**
 * Shared helpers for workflowProtocol.spec.ts — kept in a companion module so the spec file stays a
 * readable list of `it()` bodies, each under the 20-line cap.
 */

export const PROTOCOL = 'dist/claude-code/protocols/workflow-protocol.md';
export const SPAWNING_COMMANDS = [
  'dist/claude-code/commands/discover.md',
  'dist/claude-code/commands/design.md',
  'dist/claude-code/commands/build.md',
];

const ANCHOR_RE = /\{#([a-z0-9-]+)\}/g;
export const REQUIRED_ANCHORS = new Set([
  'phase-discover', 'phase-design', 'phase-build', 'phase-ship', 'registry', 'packet', 'role-expectations',
]);
export const ENFORCEMENT_CLASSES = new Set(['hook', 'executable', 'state-checkable', 'prompt-only']);

export function declaredAnchors(md: string): Set<string> {
  return new Set([...md.matchAll(ANCHOR_RE)].map((m) => m[1] as string));
}

/** Parse the guardrail-registry table rows, tolerant of escaped pipes in rule text. */
export function registryRows(md: string): string[][] {
  const lines = md.split('\n');
  const headerI = lines.findIndex((ln) => ln.trim().startsWith('| ID |'));
  if (headerI === -1) throw new Error('guardrail-registry table header (| ID |) not found');
  const rows: string[][] = [];
  for (const ln of lines.slice(headerI + 2)) { // skip header + dash separator
    if (!ln.trim().startsWith('|')) break;
    const cells = ln.split(/(?<!\\)\|/).map((c) => c.trim()).filter((c) => c !== '');
    rows.push(cells);
  }
  return rows;
}

/** The slice from a `{#anchor}` heading to the next heading of the same-or-higher level. */
export function protocolSection(md: string, anchor: string): string {
  const headingRe = new RegExp(`^(#+)[^\\n]*\\{#${anchor}\\}\\s*$`, 'm');
  const m = headingRe.exec(md);
  expect(m, `protocol must declare a heading with {#${anchor}}`).not.toBeNull();
  const level = (m as RegExpExecArray)[1]!.length;
  const rest = md.slice((m as RegExpExecArray).index + (m as RegExpExecArray)[0].length);
  const nxt = new RegExp(`^#{1,${level}}\\s`, 'm').exec(rest);
  return nxt === null ? rest : rest.slice(0, nxt.index);
}

interface PreToolUseHook {
  readonly command?: string;
  readonly args?: readonly string[];
}
interface PreToolUseEntry {
  readonly matcher: string;
  readonly hooks: readonly PreToolUseHook[];
}
interface HooksJson {
  readonly hooks?: { readonly PreToolUse?: readonly PreToolUseEntry[] };
}

/** (hook-class registry rows, PreToolUse matchers, wired commands) — shared by the hook tests. */
export function hookWiring(readFile: (rel: string) => string): { hookRows: string[][]; matchers: string[]; commands: string[] } {
  const hookRows = registryRows(protocolSection(readFile(PROTOCOL), 'registry')).filter((r) => r[r.length - 1] === 'hook');
  const descriptor = discover(ECOSYSTEMS)['claude-code'];
  if (descriptor === undefined) throw new Error('no claude-code descriptor');
  const artifact = descriptor.artifacts.find((a) => a.dest === 'hooks/hooks.json');
  if (artifact === undefined) throw new Error('hooks/hooks.json artifact missing');
  const content = artifact.content as unknown as HooksJson;
  const pre = content.hooks?.PreToolUse ?? [];
  const matchers = pre.map((entry) => entry.matcher);
  // Fold exec-form `args` into the command string — the script path lives in `args` under exec
  // form, in `command` under shell form; joining keeps the wiring checks form-agnostic.
  const commands = pre.flatMap((entry) => entry.hooks.map((h) => [h.command ?? '', ...(h.args ?? [])].join(' ')));
  return { hookRows, matchers, commands };
}

/** Each token appears in `text`, and their positions form an increasing (ordered) subsequence. */
export function assertTokensInOrder(text: string, tokens: readonly RegExp[], name: string): void {
  const idxs: number[] = [];
  for (const tok of tokens) {
    const m = tok.exec(text);
    expect(m, `${name} must contain step token ${tok}`).not.toBeNull();
    idxs.push((m as RegExpExecArray).index);
  }
  expect(idxs, `${name} steps out of order: ${JSON.stringify(idxs)}`).toEqual([...idxs].sort((a, b) => a - b));
}
