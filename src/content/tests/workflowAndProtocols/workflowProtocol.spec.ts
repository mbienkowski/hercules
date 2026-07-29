import { existsSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import { readFile } from '../commands/support';
import { filesUnder } from '../../../commons/support/buildTree';
import { repoRoot } from '../../../commons/support/repo';
import {
  assertTokensInOrder, declaredAnchors, ENFORCEMENT_CLASSES, hookWiring, PROTOCOL,
  protocolSection, REQUIRED_ANCHORS, registryRows, SPAWNING_COMMANDS,
} from './workflowProtocolSupport';

/**
 * Structural gates over dist/claude-code/protocols/workflow-protocol.md, the source of truth for step
 * order and hard guardrails: anchors resolve, the delegation packet keeps its field order, the registry
 * stays well-formed and bidirectionally anchored to the commands, and the hook-class row maps to a live
 * PreToolUse hook. Text and structure only — no test proves an agent obeyed a prompt-only rule.
 */

it('every core protocol section can be linked to directly', () => {
  const anchors = declaredAnchors(readFile(PROTOCOL));
  const missing = [...REQUIRED_ANCHORS].filter((a) => !anchors.has(a));
  expect(missing, `workflow-protocol.md is missing explicit anchors: ${JSON.stringify(missing.sort())}`).toEqual([]);
});

it('every link to the protocol points to a real section', () => {
  const anchors = declaredAnchors(readFile(PROTOCOL));
  const refRe = /workflow-protocol\.md#([a-z0-9-]+)/g;
  const targets: Record<string, string> = { 'CODE_OF_CONDUCT.md': readFile('CODE_OF_CONDUCT.md') };
  for (const [rel, text] of Object.entries(filesUnder(join(repoRoot, 'dist', 'claude-code')))) {
    if (rel.endsWith('.md')) targets[`dist/claude-code/${rel}`] = text;
  }
  const refs = new Map<string, string[]>();
  for (const [rel, text] of Object.entries(targets)) {
    for (const m of text.matchAll(refRe)) {
      const anchor = m[1] as string;
      refs.set(anchor, [...(refs.get(anchor) ?? []), rel]);
    }
  }
  const unresolved = [...refs.entries()].filter(([a]) => !anchors.has(a));
  expect(unresolved, `references to undeclared protocol anchors: ${JSON.stringify(unresolved)}`).toEqual([]);
});

it.each(SPAWNING_COMMANDS)('%s includes the handoff packet at its spawns', (rel) => {
  expect(readFile(rel), `${rel} must compose the delegation packet (workflow-protocol.md#packet)`).toContain('workflow-protocol.md#packet');
});

it('agent handoff instructions reference the handoff packet', () => {
  const text = readFile('dist/claude-code/protocols/a2a-communication-protocol.md');
  expect(text, 'a2a § How to inject must name the delegation packet wrapping the Core').toContain('workflow-protocol.md#packet');
});

it('the handoff packet lists its fields in the required order', () => {
  const section = protocolSection(readFile(PROTOCOL), 'packet');
  const fence = /```\n([\s\S]*?)```/.exec(section);
  expect(fence, 'the {#packet} section must carry a fenced packet template').not.toBeNull();
  const body = (fence as RegExpExecArray)[1] as string;
  const chain = ['Phase:', 'Expected:', 'Guardrails:', 'Context:', '[Round:', 'A2A Agent-Injected Core follows'];
  const idxs = chain.map((label) => {
    expect(body, `packet template must declare ${label}`).toContain(label);
    return body.indexOf(label);
  });
  expect(idxs, `packet fields out of order: ${JSON.stringify(chain)}`).toEqual([...idxs].sort((a, b) => a - b));
  expect(section, 'the packet must require verbatim registry-row copies').toContain('verbatim');

  // Carried project material is labelled with its source, using the marker the Core already
  // defines for content an agent did not author — a second convention for one job is drift.
  expect(section, 'carried material must name the file and section it came from')
    .toMatch(/\[ATTACHMENT: .*§/);
  expect(section.toLowerCase(), 'the same marker governs outbound relay, so inbound has to say it is '
    + 'material to act on — otherwise a delegate may echo its own input back')
    .toMatch(/act on|not a relay|never relayed/);
  expect(section.toLowerCase(), 'material containing the closing marker would end its own wrapper and '
    + 'the remainder would read as instruction — a project file the plugin does not control')
    .toContain('closing marker');
});

it('every guardrail rule is completely and correctly documented', () => {
  const rows = registryRows(protocolSection(readFile(PROTOCOL), 'registry'));
  expect(rows.length, "the registry must carry the workflow's hard rules").toBeGreaterThanOrEqual(5);
  const seen = new Set<string>();
  for (const cells of rows) {
    expect(cells.length, `registry row too few cells: ${JSON.stringify(cells)}`).toBeGreaterThanOrEqual(5);
    const [gid, key, scope] = cells as [string, string, string];
    const klass = cells[cells.length - 1] as string;
    const rule = cells.slice(3, -1).join(' | ');
    expect(gid, `registry ID must be G<n>: ${gid}`).toMatch(/^G\d+$/);
    expect(seen.has(gid), `duplicate registry ID ${gid}`).toBe(false);
    seen.add(gid);
    expect(key, `registry key must be 'phase · step': ${key}`).toContain('·');
    expect(scope, `${gid} must declare a scope (step / span / phase)`).toBeTruthy();
    expect(rule.trim(), `${gid} must carry a non-empty rule`).not.toBe('');
    expect(ENFORCEMENT_CLASSES.has(klass), `${gid} class ${klass} not in ${[...ENFORCEMENT_CLASSES].sort().join(', ')}`).toBe(true);
  }
});

describe('the PreToolUse hook wiring behind the one hook-class registry row', () => {
  it('rules labeled as automatically enforced name their real enforcement mechanism', () => {
    const { hookRows } = hookWiring(readFile);
    expect(hookRows.length, 'the registry must carry at least one hook-class (runtime-enforced) row').toBeGreaterThan(0);
    for (const r of hookRows) {
      expect(r.join(' '), `${r[0]} claims class=hook but its rule text names no PreToolUse mechanism`).toContain('PreToolUse');
    }
  });

  it('the automatic safety checks are installed and watch file edits', () => {
    const { matchers, commands } = hookWiring(readFile);
    expect(matchers.some((m) => m.includes('Edit')), 'PreToolUse must match Edit for the frozen guard').toBe(true);
    for (const cmd of commands) {
      const script = cmd.split('${CLAUDE_PLUGIN_ROOT}/').pop()!.replace(/^"+|"+$/g, '');
      expect(existsSync(join(repoRoot, 'dist', 'claude-code', script)), `hook script missing: ${script}`).toBe(true);
    }
  });

  it('the frozen-test protection is actually installed and active', () => {
    const { hookRows, commands } = hookWiring(readFile);
    const frozenRow = hookRows.find((r) => r.join(' ').toLowerCase().includes('frozen'));
    expect(frozenRow, 'the hook-class row must be the frozen-tests guard').toBeDefined();
    expect(commands.some((c) => c.includes('frozen_tests.py')), 'hooks.json must wire the frozen_tests.py script').toBe(true);
  });
});

// Bidirectional drift anchors: the token must appear in the registry ROW text AND in the command
// file that owns the rule — the protocol can neither invent a rule the commands don't carry, nor
// can a command drop a rule the registry still claims.
const DRIFT_ANCHORS: ReadonlyArray<readonly [string, string, string]> = [
  ['G1', 'frozen', 'dist/claude-code/commands/build.md'],
  ['G2', '3 implementation rounds', 'dist/claude-code/commands/build.md'],
  ['G3', 'scaffold', 'dist/claude-code/commands/build.md'],
  ['G4', 'named passing test', 'dist/claude-code/commands/build.md'],
  ['G5', 'high-risk', 'dist/claude-code/commands/build.md'],
  ['G6', 'build_complete', 'dist/claude-code/commands/ship.md'],
  ['G7', 'scored once', 'dist/claude-code/skills/hercules-reference/SKILL.md'],
];

it.each(DRIFT_ANCHORS)('documented rule %s stays in sync with the command that carries it', (gid, token, command) => {
  const rows = registryRows(protocolSection(readFile(PROTOCOL), 'registry'));
  const row = rows.find((r) => r[0] === gid);
  expect(row, `registry must carry row ${gid}`).toBeDefined();
  const lowToken = token.toLowerCase();
  expect((row as string[]).join(' ').toLowerCase(), `${gid}'s row text must anchor on ${token}`).toContain(lowToken);
  expect(readFile(command).toLowerCase(), `${command} must carry the ${token} rule that ${gid} claims`).toContain(lowToken);
});

const PROTO_BUILD_TOKENS = [
  /scaffold/, /write failing tests/, /\bimplement\b/, /quality gates/, /mutation gate/,
  /traceability/, /\badvance\b/, /checkpoint/, /retire spec/, /cross-check/,
];
const BUILD_MD_TOKENS = [
  /\*\*scaffold\.\*\*/, /\*\*write failing tests\.\*\*/, /\*\*implement\.\*\*/, /\*\*quality gates\.\*\*/,
  /\*\*mutation gate\.\*\*/, /\*\*traceability\.\*\*/, /\*\*advance\.\*\*/, /\*\*write the checkpoint\.\*\*/,
  /\*\*retire the spec\.\*\*/, /## cross-check validation/,
];

it('the build phase steps are documented in the correct order in the protocol', () => {
  const proto = protocolSection(readFile(PROTOCOL), 'phase-build').toLowerCase();
  assertTokensInOrder(proto, PROTO_BUILD_TOKENS, 'protocol {#phase-build}');
});

it('the build command steps follow the same order as the protocol', () => {
  const build = readFile('dist/claude-code/commands/build.md').toLowerCase();
  assertTokensInOrder(build.slice(build.indexOf('## execution')), BUILD_MD_TOKENS, 'build.md ## Execution');
});

const TIER_SOURCES: ReadonlyArray<readonly [string, () => string]> = [
  ['protocol', () => protocolSection(readFile(PROTOCOL), 'phase-design')],
  ['design.md', () => readFile('dist/claude-code/commands/design.md')],
  ['diagram', () => readFile('docs/workflow/workflow-diagram-detailed.html')],
];

it.each(TIER_SOURCES)('the design phase (%s) checks the project tier before asking design questions', (source, getText) => {
  const text = getText().toLowerCase();
  const m = /read (?:the )?tier/.exec(text);
  expect(m, `${source} must carry a read-the-tier step`).not.toBeNull();
  expect((m as RegExpExecArray).index, `${source} must read the tier before the design questions`).toBeLessThan(text.indexOf('design questions'));
});

it('handoff-specific fields never leak into the shared core instructions', () => {
  const section = protocolSection(readFile(PROTOCOL), 'packet');
  expect(section).toContain('Expected:');
  expect(section).toContain('Guardrails:');
  const golden = readFile('src/content/tests/core.golden');
  for (const label of ['Expected:', 'Guardrails:', 'Phase: {phase}']) {
    expect(golden, `packet label ${label} leaked into the golden a2a Core`).not.toContain(label);
  }
});

it('role expectations only reference sections that exist in the spec template', () => {
  const designMd = readFile('dist/claude-code/commands/design.md');
  const templateHeadings = new Set(
    [...designMd.matchAll(/^## ([A-Z][^\n]*)$/gm)]
      .map((m) => (m[1] as string).trim())
      .filter((h) => !h.startsWith('Step')),
  );
  expect(templateHeadings.has('Scope'), 'sanity: design.md template must carry ## Scope').toBe(true);
  const roles = protocolSection(readFile(PROTOCOL), 'role-expectations');
  const sliceRefs = new Set([...roles.matchAll(/§([A-Z][a-z]+(?: [a-z]+)*)/g)].map((m) => m[1] as string));
  expect(sliceRefs.size, 'role expectations must name §-section slices').toBeGreaterThan(0);
  const unknown = [...sliceRefs].filter((s) => !templateHeadings.has(s));
  expect(unknown, `role slices name sections design.md's spec template does not emit: ${JSON.stringify(unknown)}`).toEqual([]);
});
