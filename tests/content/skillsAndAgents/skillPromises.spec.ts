import { globSync } from 'node:fs';

import { describe, expect, it } from 'vitest';

import { readFile } from '../commands/support';
import { readRepoFile, repoRoot } from '../../support/repo';
import { advisorNames } from '../../support/roster';

/**
 * The main promises the agent and skill rosters make: every advisor stays stack- and internals-free,
 * QA and the reviewer never overstep, rules reach a delegate as a slice, and nothing is overwritten.
 */

function glob(pattern: string): string[] {
  return [...globSync(`dist/claude-code/${pattern}`, { cwd: repoRoot })].sort();
}

const AGENT_PATHS = glob('agents/*.md');
const DEFAULT_AGENT = 'hercules';

const STACK_LITERAL_PATTERNS = [
  /\bSpring\b/, /\bHibernate\b/, /\bReact\b/, /\bRedux\b/, /\bDjango\b/, /\bRails\b/, /\bPrisma\b/,
  /\bActiveRecord\b/, /@anthropic-ai/,
];
// Hercules-internal literals a reusable specialist must never hardcode; the command injects them.
const HERCULES_INTERNAL_PATTERNS = [
  /\/hercules:/, /\bcurrent_spec(?:_round)?\b/, /\bfrozen_test_files\b/, /\bfrozen_override\b/,
  /-spec-\d/, /workflow-protocol/,
];

function agentName(path: string): string {
  return (path.split('/').at(-1) as string).replace(/\.md$/, '');
}

describe('the agent roster', () => {
  it('carries no hardcoded stack literal, and no Hercules-internal literal outside the orchestrator', () => {
    const stackViolations: string[] = [];
    const internalViolations: string[] = [];
    for (const path of AGENT_PATHS) {
      const md = readRepoFile(path);
      const name = agentName(path);
      for (const pattern of STACK_LITERAL_PATTERNS) if (pattern.test(md)) stackViolations.push(`${name}.md: ${pattern}`);
      if (name === DEFAULT_AGENT) continue;
      for (const pattern of HERCULES_INTERNAL_PATTERNS) if (pattern.test(md)) internalViolations.push(`${name}.md: ${pattern}`);
    }
    expect(stackViolations, `agents assume a specific stack:\n${stackViolations.join('\n')}`).toEqual([]);
    expect(internalViolations, `reusable agents hardcode Hercules internals:\n${internalViolations.join('\n')}`).toEqual([]);
  });

  it('QA never writes test code, the reviewer treats inline prompt content as the spec, and reports back to its caller', () => {
    const qa = readRepoFile('dist/claude-code/agents/senior-qa-engineer.md');
    const toolsLine = qa.split('\n').find((ln) => ln.startsWith('tools:')) as string;
    expect(toolsLine).not.toContain('Edit');
    expect(qa).toContain('Never writes test code');

    const reviewer = readRepoFile('dist/claude-code/agents/cynical-reviewer.md').toLowerCase();
    expect(reviewer).toContain('spec-sync (mandatory last step)');
    expect(reviewer).toContain('report the disposition back to the caller');
    expect(reviewer).toContain('spec documents not provided');
    expect(reviewer).toContain('treat the inline content');
  });
});

describe('project rules reach a delegate as a carried slice, never a fetch', () => {
  const PACKET = 'dist/claude-code/protocols/workflow-protocol.md';
  const LEAD = 'hercules';

  it('the packet says the carried slice supersedes a self-read, while still forbidding a whole document', () => {
    const md = readFile(PACKET);
    const packet = md.slice(md.indexOf('{#packet}'), md.indexOf('{#role-expectations}'));
    expect(packet.toLowerCase()).toMatch(/binding slice/);
    expect(packet.toLowerCase()).toContain('supersed');
    expect(packet).toContain('never a whole document');
  });

  it('claude-code ships its whole advisor roster, told a slice is carried and reading the file only when one is not', () => {
    const dir = `${repoRoot}/dist/claude-code/agents`;
    const files = (globSync('*.md', { cwd: dir }) as string[])
      .filter((f) => !f.startsWith(`${LEAD}.`) && !f.startsWith('builder.'));
    // Counted from src/content/agents/: the number is only meaningful as "all of them".
    const advisors = advisorNames();
    expect(advisors.length, 'no advisors were found to check').toBeGreaterThan(10);
    expect(files.length,
      `dist/claude-code must ship all ${advisors.length} advisors besides the lead and the builder`,
    ).toBe(advisors.length);
    const missing: string[] = [];
    const unconditional: string[] = [];
    for (const file of files) {
      const md = readFile(`dist/claude-code/agents/${file}`);
      if (!/carries the slice of the project's code-of-conduct/i.test(md)) missing.push(file);
      for (const para of md.split(/\n{2,}/).filter((p) => /code-of-conduct/i.test(p))) {
        if (/\bread the (file|project)/i.test(para) && !/no slice|none is supplied|not supplied|without a slice/i.test(para)) {
          unconditional.push(`${file}: unconditional read`);
        }
      }
    }
    expect(missing, `never told a slice is carried: ${missing.join(', ')}`).toEqual([]);
    expect(unconditional, `reads the whole document even when a slice arrived:\n  ${unconditional.join('\n  ')}`).toEqual([]);

    // The lead agent decides rather than advises, so nobody hands it a slice — it reads the whole document itself.
    const lead = readFile(`dist/claude-code/agents/${LEAD}.md`);
    expect(lead).not.toMatch(/carries the slice of the project's code-of-conduct/i);
    expect(lead).toMatch(/read the project's code-of-conduct/i);
  });
});

const GENERATOR = 'dist/claude-code/skills/code-of-conduct-generator/SKILL.md';

/** A shipped file with its line wrapping removed, so a promise split across lines still reads. */
function flat(path: string): string {
  return readRepoFile(path).split(/\s+/).filter(Boolean).join(' ');
}

describe('the code-of-conduct generator keeps its promises to whoever runs it', () => {
  it('offers to plan before scanning, and never silently overwrites an existing document', () => {
    const text = flat(GENERATOR);
    expect(text).toContain('EnterPlanMode');
    expect(text).toContain('never silently');
    expect(text).toContain('one CoC per repo, never merged');
  });

  it('runs its documented steps in the order they run', () => {
    const skill = readRepoFile(GENERATOR);
    const steps = ['1. **Plan mode', '2. **Find existing', '3. **Scan', '4. **Questions', '5. **Draft',
      '6. **Gap pass', '7. **Gate', '8. **Approve', '9. **Review'];
    const positions = steps.map((label) => skill.indexOf(label));
    expect(positions.filter((at) => at === -1), 'every documented step must be present').toEqual([]);
    expect(positions).toEqual([...positions].sort((a, b) => a - b));
  });

  it('decides the gate with a program rather than asking an agent to be careful', () => {
    // The whole point of the gate: a rule an agent cannot justify to a validator does not ship.
    const text = flat(GENERATOR);
    expect(text).toContain('tools/coc_audit.py draft --contract 1');
    expect(text).toContain('Exit 0 ships');
  });

  it('makes every group teach its rules, not just state them', () => {
    // A rule without its reason is generalised wrongly; a rule without an example is read
    // generically. Both were optional before, which meant absent.
    const map = flat('dist/claude-code/skills/code-of-conduct-generator/coverage-map.md');
    expect(map).toContain('Open every group with one');
    expect(map).toMatch(/DON'T.{0,40}DO.{0,40}pair where local idiom/);
  });

  it('caps the annotations that the directive budget exempts', () => {
    // Exempting WHY and example lines from the count is what makes them affordable; capping them is
    // what stops the exemption from doubling a file the budget exists to keep short.
    expect(flat('dist/claude-code/skills/code-of-conduct-generator/coverage-map.md'))
      .toContain('capped at one of each per group');
  });

  it('tells the drafting agent where the envelope it must fill is specified', () => {
    // A gate whose input shape is undocumented is a gate the agent guesses its way past.
    expect(flat(GENERATOR)).toContain('§ Rules envelope');
    expect(flat('dist/claude-code/skills/code-of-conduct-generator/coverage-map.md'))
      .toContain('## § Rules envelope');
  });
});
