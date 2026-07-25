import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import { CHAIN_TEMPLATES, resolveChains, WAIVERS } from '../loadingChains.mjs';
import { tmpWorkspace } from './support';

// A SEPARATE file from instructionBudget.spec.ts, deliberately: that file's first describe block
// computes `resolveChains(DIST_CLAUDE_CODE, CHAIN_TEMPLATES)` at describe-body level (outside any
// `it()`), so a CHAIN_TEMPLATES/WAIVERS data mutant that makes resolveChains throw crashes that
// whole file's test COLLECTION, not just one test — none of ITS tests get a chance to run, so none
// can register a kill. Every test below either runs resolveChains inside its own `it()` (so a throw
// only fails that one test) or asserts directly against the exported data, insulating this file's
// results from that collection-time crash.

describe('measurePart (exercised via resolveChains): fixed file parts', () => {
  it('counts instructions from a literal file relative to distRoot', () => {
    const root = tmpWorkspace();
    writeFileSync(join(root, 'CLAUDE.md'), '- one\n- two\n');
    const [chain] = resolveChains(root, [{ name: 'x', fixed: [{ label: 'claude', file: 'CLAUDE.md' }] }]);
    expect(chain?.value).toBe(2);
  });

  it('restricts a file part to its named section when `section` is given', () => {
    const root = tmpWorkspace();
    writeFileSync(join(root, 'doc.md'), '- outside\n## A\n- inside one\n- inside two\n## B\n- outside again\n');
    const [chain] = resolveChains(root, [{
      name: 'x',
      fixed: [{ label: 'sec', file: 'doc.md', section: { start: '## A', stop: '## B' } }],
    }]);
    expect(chain?.value).toBe(2); // only the two bullets between ## A and ## B
  });

  it('sums every file matched by a sumGlob part into one value', () => {
    const root = tmpWorkspace();
    mkdirSync(join(root, 'protocols'));
    writeFileSync(join(root, 'protocols', 'a.md'), '- one\n');
    writeFileSync(join(root, 'protocols', 'b.md'), '- one\n- two\n');
    const [chain] = resolveChains(root, [{ name: 'x', fixed: [{ label: 'protocols', sumGlob: 'protocols/*.md' }] }]);
    expect(chain?.value).toBe(3); // 1 + 2 summed
  });

  it('throws a clear error when a chain part names neither file nor sumGlob', () => {
    const root = tmpWorkspace();
    expect(() => resolveChains(root, [{ name: 'x', fixed: [{ label: 'broken' }] }]))
      .toThrow("chain part 'broken' names neither 'file' nor 'sumGlob'");
  });

  it('reports the per-part breakdown alongside the total', () => {
    const root = tmpWorkspace();
    writeFileSync(join(root, 'a.md'), '- one\n');
    writeFileSync(join(root, 'b.md'), '- one\n- two\n');
    const [chain] = resolveChains(root, [{
      name: 'x',
      fixed: [{ label: 'a', file: 'a.md' }, { label: 'b', file: 'b.md' }],
    }]);
    expect(chain?.breakdown.get('a')).toBe(1);
    expect(chain?.breakdown.get('b')).toBe(2);
    expect(chain?.value).toBe(3);
  });
});

describe('resolveChains: variable template expansion', () => {
  it('expands a `variable` glob into one chain per match, named "<template>: <file>"', () => {
    const root = tmpWorkspace();
    mkdirSync(join(root, 'agents'));
    writeFileSync(join(root, 'agents', 'foo.md'), '- one\n');
    writeFileSync(join(root, 'agents', 'bar.md'), '- one\n- two\n');
    const chains = resolveChains(root, [{
      name: 'sub-agent', fixed: [], variable: { glob: 'agents/*.md', label: 'agent' },
    }]);
    expect(chains.map((c) => c.name)).toEqual(['sub-agent: agents/bar.md', 'sub-agent: agents/foo.md']);
  });

  it('sorts variable-expanded chains alphabetically by matched filename', () => {
    const root = tmpWorkspace();
    mkdirSync(join(root, 'agents'));
    writeFileSync(join(root, 'agents', 'zeta.md'), '- one\n');
    writeFileSync(join(root, 'agents', 'alpha.md'), '- one\n');
    const chains = resolveChains(root, [{
      name: 't', fixed: [], variable: { glob: 'agents/*.md', label: 'agent' },
    }]);
    expect(chains.map((c) => c.name)).toEqual(['t: agents/alpha.md', 't: agents/zeta.md']);
  });

  it('adds the matched file as an extra part, labeled per `variable.label`, into the breakdown', () => {
    const root = tmpWorkspace();
    mkdirSync(join(root, 'skills'));
    writeFileSync(join(root, 'skills', 'one.md'), '- a\n- b\n');
    const [chain] = resolveChains(root, [{
      name: 't', fixed: [], variable: { glob: 'skills/*.md', label: 'the-skill' },
    }]);
    expect(chain?.breakdown.get('the-skill')).toBe(2);
  });

  it("combines a template's fixed parts with its variable part in the resolved value", () => {
    const root = tmpWorkspace();
    writeFileSync(join(root, 'CLAUDE.md'), '- fixed one\n');
    mkdirSync(join(root, 'commands'));
    writeFileSync(join(root, 'commands', 'build.md'), '- var one\n- var two\n');
    const [chain] = resolveChains(root, [{
      name: 't',
      fixed: [{ label: 'claude', file: 'CLAUDE.md' }],
      variable: { glob: 'commands/*.md', label: 'command' },
    }]);
    expect(chain?.value).toBe(3); // 1 fixed + 2 variable
  });

  it('produces zero chains for a template whose variable glob matches nothing', () => {
    const root = tmpWorkspace();
    const chains = resolveChains(root, [{ name: 't', fixed: [], variable: { glob: 'nothing/*.md', label: 'x' } }]);
    expect(chains).toEqual([]);
  });

  it('produces exactly one chain for a template with no `variable` field, carrying only its fixed parts', () => {
    const root = tmpWorkspace();
    writeFileSync(join(root, 'a.md'), '- one\n');
    const chains = resolveChains(root, [{ name: 'fixed-only', fixed: [{ label: 'a', file: 'a.md' }] }]);
    expect(chains).toHaveLength(1);
    expect(chains[0]?.name).toBe('fixed-only');
  });

  it('resolves multiple templates independently, in the given order', () => {
    const root = tmpWorkspace();
    writeFileSync(join(root, 'a.md'), '- one\n');
    writeFileSync(join(root, 'b.md'), '- one\n- two\n');
    const chains = resolveChains(root, [
      { name: 'first', fixed: [{ label: 'a', file: 'a.md' }] },
      { name: 'second', fixed: [{ label: 'b', file: 'b.md' }] },
    ]);
    expect(chains.map((c) => c.name)).toEqual(['first', 'second']);
    expect(chains.map((c) => c.value)).toEqual([1, 2]);
  });
});

describe('CHAIN_TEMPLATES: pinned data shape', () => {
  // This module's own top comment: adding a chain is "a new entry in CHAIN_TEMPLATES ... not
  // hardcoded per-scenario logic" — so CHAIN_TEMPLATES is itself DATA this project depends on, and
  // deserves a pinning test exactly like a golden file, not just indirect exercise via real dist/.

  it('defines exactly the three templates this project gates today, in order', () => {
    expect(CHAIN_TEMPLATES.map((t) => t.name)).toEqual([
      'sub-agent',
      'orchestrator (per command)',
      'skill',
    ]);
  });

  it('the sub-agent template requires the A2A Core (Agent-Injected Core section) and CLAUDE.md, varying per agent file', () => {
    const subAgent = CHAIN_TEMPLATES.find((t) => t.name === 'sub-agent');
    expect(subAgent?.fixed).toEqual([
      {
        label: 'a2a-core',
        file: 'protocols/a2a-communication-protocol.md',
        section: { start: '## Agent-Injected Core', stop: '## Orchestrator Section' },
      },
      { label: 'CLAUDE.md', file: 'CLAUDE.md' },
    ]);
    expect(subAgent?.variable).toEqual({ glob: 'agents/*.md', label: 'agent' });
  });

  it('the orchestrator template requires CLAUDE.md and every protocol, varying per command file', () => {
    const orchestrator = CHAIN_TEMPLATES.find((t) => t.name === 'orchestrator (per command)');
    expect(orchestrator?.fixed).toEqual([
      { label: 'CLAUDE.md', file: 'CLAUDE.md' },
      { label: 'protocols', sumGlob: 'protocols/*.md' },
    ]);
    expect(orchestrator?.variable).toEqual({ glob: 'commands/*.md', label: 'command' });
  });

  it('the skill template carries no fixed parts, varying per skill file', () => {
    const skill = CHAIN_TEMPLATES.find((t) => t.name === 'skill');
    expect(skill?.fixed).toEqual([]);
    expect(skill?.variable).toEqual({ glob: 'skills/*/SKILL.md', label: 'skill' });
  });
});

describe('WAIVERS: pinned data content', () => {
  it('the build.md waiver records its exact reason and follow-up', () => {
    const waiver = WAIVERS.find((w) => w.chain === 'orchestrator (per command): commands/build.md');
    expect(waiver?.reason).toBe("ceiling 150, over by 10 — trim build.md's own instruction load");
    expect(waiver?.followUp).toBe(
      'migration spec § What this sets up: "Trimming build.md to retire the orchestrator waiver"',
    );
  });
});
