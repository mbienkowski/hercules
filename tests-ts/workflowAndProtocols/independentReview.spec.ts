import { existsSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import { discover } from '../../scripts-ts/build/descriptor.mjs';
import { ECOSYSTEMS } from '../support/descriptorFixtures';
import { readRepoFile, repoRoot } from '../support/repo';

// Ported from tests/workflow/test_independent_review.py — the two true self-judgment gates
// (Design coverage, Build traceability) are performed by a freshly-spawned `cynical-reviewer`
// reading the source directly, never by the producing session. Pins the swap so a green suite
// can't hide a lingering self-review (QA panel Blocker). Checked across EVERY shipped edition
// (claude-code, opencode, cursor); each edition names the reviewer with its own agent namespace
// (`hercules:` on Claude Code, bare elsewhere), so the assertions are namespace-aware.

const TREES = ['claude-code', 'opencode', 'cursor'] as const;

// Self-judgment verbs that would mean the MAIN agent still judges its own artifact at the gate.
const SELF_VERBS = ['self-scan', 'you verify', 'you check', 'self-review'];

function distPath(tree: string, ...segments: string[]): string {
  return join(repoRoot, 'dist', tree, ...segments);
}

function slice(text: string, start: string, end: string | null): string {
  const i = text.indexOf(start);
  if (i === -1) throw new Error(`section start marker not found: ${start}`);
  if (end === null) return text.slice(i);
  const j = text.indexOf(end, i);
  if (j === -1) throw new Error(`section stop marker not found after start: ${end}`);
  return text.slice(i, j);
}

function agentNs(tree: string): string {
  const descriptor = discover(ECOSYSTEMS)[tree];
  if (descriptor === undefined) throw new Error(`no descriptor for ${tree}`);
  const ns = descriptor.vars['agent_ns'];
  if (ns === undefined) throw new Error(`descriptor ${tree} has no vars.agent_ns`);
  return ns;
}

function coverageSlice(tree: string): string {
  const md = readRepoFile('dist', tree, 'commands', 'design.md');
  const step7 = slice(md, '## Step 7', '## Step 8');
  return slice(step7, 'coverage', null);
}

function traceabilitySlice(tree: string): string {
  const md = readRepoFile('dist', tree, 'commands', 'build.md');
  const line = md.split('\n').find((p) => p.includes('**Traceability') || p.includes('Traceability.'));
  if (line === undefined) throw new Error(`no Traceability line found in ${tree}/commands/build.md`);
  return line;
}

describe.each(TREES)('independent review — %s', (tree) => {
  it('design coverage is judged by a fresh reviewer, not the author', () => {
    const s = coverageSlice(tree);
    const reviewer = `${agentNs(tree)}cynical-reviewer`;
    expect(s, `${tree}: coverage gate must spawn ${reviewer}`).toContain(reviewer);
    expect(s, `${tree}: coverage gate must compose the delegation packet`).toContain('workflow-protocol.md#packet');
    expect(s, `${tree}: coverage gate must reference § Independent review`).toContain('Independent review');
    expect(s, `${tree}: reviewer must read the requirements source directly`).toContain('business-requirements');
  });

  it('build traceability is judged by a fresh reviewer, not the author', () => {
    const s = traceabilitySlice(tree);
    const reviewer = `${agentNs(tree)}cynical-reviewer`;
    expect(s, `${tree}: traceability gate must spawn ${reviewer}`).toContain(reviewer);
    expect(s, `${tree}: traceability gate must compose the delegation packet`).toContain('workflow-protocol.md#packet');
    expect(s, `${tree}: traceability gate must reference § Independent review`).toContain('Independent review');
  });

  it('neither gate can slip back into self-judgment', () => {
    const slices: Array<[string, string]> = [['coverage', coverageSlice(tree)], ['traceability', traceabilitySlice(tree)]];
    for (const [name, s] of slices) {
      const low = s.toLowerCase();
      for (const v of SELF_VERBS) expect(low, `${tree} ${name} gate still carries self-review verb ${v}`).not.toContain(v);
    }
  });

  it('the independent reviewer is available wherever hercules ships', () => {
    expect(existsSync(distPath(tree, 'agents', 'cynical-reviewer.md')), `cynical-reviewer must ship to dist/${tree}/agents/`).toBe(true);
  });
});

describe('cursor-only reviewer wiring', () => {
  it('the reviewer is a read-locked subagent, not a rule', () => {
    const text = readRepoFile('dist', 'cursor', 'agents', 'cynical-reviewer.md');
    expect(text.startsWith('---\nname: cynical-reviewer\n'), 'must be a subagent with a name').toBe(true);
    expect(text, 'reviewer subagent must be read-locked').toContain('readonly: true');
    expect(text, 'a reviewer is a subagent, not an always-applied rule').not.toContain('alwaysApply');
    expect(existsSync(distPath('cursor', 'rules', 'cynical-reviewer.mdc')), 'the reviewer must not also ship as a same-context rule').toBe(false);
  });

  it('both gates demand a handshake or halt', () => {
    for (const cmd of ['design', 'build']) {
      const text = readRepoFile('dist', 'cursor', 'commands', `${cmd}.md`);
      expect(text, `cursor ${cmd}: must instruct an explicit reviewer spawn`).toContain('@cynical-reviewer');
      expect(text, `cursor ${cmd}: must HALT when the handshake is missing`).toContain('HALT and tell the user');
    }
  });
});
