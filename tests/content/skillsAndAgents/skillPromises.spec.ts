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
    expect(text).toContain('tools/code_of_conduct/coc_gate.py draft --contract 2');
    expect(text).toContain('Exit 0 ships');
  });

  it('records what it reads in the code as citable, path-verified observations', () => {
    // The valuable rules are architectural, and architecture is read, not measured. Without a
    // recorded observation the only way such a rule passes the gate is disguised as a fact
    // nothing produced — the exact invented-evidence shape the gate exists to refuse.
    const text = flat(GENERATOR);
    expect(text).toContain('observation');
    expect(text).toMatch(/code:<observation/i);
    const map = flat('dist/claude-code/skills/code-of-conduct-generator/coverage-map.md');
    expect(map).toContain('"observations"');
    expect(map).toMatch(/code:<observation/i);
  });

  it('writes back to the path the repository already uses, without asking', () => {
    // A repository spelling it CODE_OF_CONDUCT.md keeps that name. Emitting the lowercase default
    // beside it leaves two standards files — and on a case-insensitive filesystem the second write
    // silently clobbers the first. So the path found in step 2 is the path written in step 8, and
    // the default applies only where nothing was found.
    const text = flat(GENERATOR);
    expect(text).toContain('Whatever it finds is the path Step 8 writes');
    expect(text).toContain('Never a second file beside it');
    expect(text).toContain('The default applies **only** here');
    expect(text).toContain('Write to **the path Step 2 resolved**, overwriting it in place');
    expect(text).toContain('The existing file is the output file');
  });

  it('never creates or edits any file besides the code-of-conduct itself', () => {
    // The divergence the first real run surfaced: step 8 used to add an @-reference to the
    // instructions file, creating it when missing. The owner's rule is absolute — the reference
    // line is offered in chat, and adding it is the user's edit.
    const text = flat(GENERATOR);
    expect(text).toMatch(/never creates? or edits? any (other )?file/i);
    expect(text).not.toContain('creating it when missing');
  });

  it('gathers its evidence with a program before it reasons about any of it', () => {
    const text = flat(GENERATOR);
    expect(text).toContain('tools/code_of_conduct/coc_scan.py all --root');
    expect(text).toContain('never hand-scan around a refusal');
  });

  it('keeps one authority for the scan rather than a tool and a rival prose procedure', () => {
    // The playbook used to specify the mechanics the tool now performs. Left in place it would be a
    // second, drifting description of one job, paid for twice out of the same budget.
    const map = flat('dist/claude-code/skills/code-of-conduct-generator/coverage-map.md');
    expect(map).toContain('this is what the tool cannot decide');
    expect(map).not.toContain('git log -n 200');
  });

  it('tells the agent to weigh living code above code nobody maintains', () => {
    const map = flat('dist/claude-code/skills/code-of-conduct-generator/coverage-map.md');
    expect(map).toContain('liveness.top_files');
    expect(map).toContain('describes what nobody maintains');
  });

  it('turns a split convention into a question rather than counting the votes', () => {
    // Code is edited while a convention is being adopted and equally while it is being torn out, so
    // a count is an argument to put to someone, never an answer to act on. The split arrives from
    // the agent-authored extractor's `conventions` section now that the scan parses no language.
    const text = flat(GENERATOR);
    expect(text).toContain('Every `conventions` entry the extractor reported becomes one question');
    expect(text).toContain('Never pick for the user');
    expect(flat('dist/claude-code/skills/code-of-conduct-generator/coverage-map.md'))
      .toContain('a question, never majority rule');
  });

  it('formats the file the way its owner reads: tiered runs, reasons last, plain text', () => {
    // A reader wants the requirement, then the argument; markup tokens are spent from every
    // agent's context on every task, forever. The shape lives in the spine, so it is asserted
    // there — the map carries only what the spine does not say.
    const text = flat(GENERATOR);
    expect(text).toMatch(/MUST.{0,80}SHOULD.{0,160}AVOID.{0,160}NEVER_DO/);
    expect(text).toContain('closing Why section');
    expect(text).toContain('no markup');
  });

  it('teaches how the repository grows, not just what it forbids', () => {
    // A family is an extension point: the standard way this repository grows. Leaving one
    // unnamed hands the next contributor a whole extension path to guess at, so the map
    // requires covering each and the linter reports any the document never mentions.
    const map = flat('dist/claude-code/skills/code-of-conduct-generator/coverage-map.md');
    expect(map).toContain('Cover every `arch.families` entry the scan reported');
    expect(map).toContain('arch.families');
  });

  it('checks the shape of the file it emits, and again once it is on disk', () => {
    // The draft that passed is not evidence about the bytes that landed.
    const text = flat(GENERATOR);
    expect(text).toContain('tools/code_of_conduct/coc_lint.py');
    expect(text).toContain('re-run the linter against the file on disk');
  });

  it('reads an existing document mechanically before proposing a single change to it', () => {
    const text = flat(GENERATOR);
    expect(text).toContain('coc_lint.py --contract 2 --file <coc> --root <root>');
    expect(text).toContain('never an edit');
  });

  it('exempts the bullets that predate the gate rather than refusing every update', () => {
    // Rules written before the envelope existed carry no tags or citations. Submitting them would
    // make a passing update impossible, which is how an additions-only promise gets quietly broken.
    const text = flat(GENERATOR);
    expect(text).toContain('never submitted to the gate');
    expect(text).toContain('New rules and new sections meet the full bar');
  });

  it('tells the drafting agent where the envelope it must fill is specified', () => {
    // A gate whose input shape is undocumented is a gate the agent guesses its way past.
    expect(flat(GENERATOR)).toContain('§ Rules envelope');
    expect(flat('dist/claude-code/skills/code-of-conduct-generator/coverage-map.md'))
      .toContain('## § Rules envelope');
  });
});
