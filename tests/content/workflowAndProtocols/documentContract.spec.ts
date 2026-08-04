/**
 * Pins the authoring skill against the standard it teaches.
 *
 * The whole reason `doc_rules.json` exists is that the guidance an author READS and the checks that
 * RUN come from one place. Nothing structural stops them drifting — the skill is prose and the rule
 * data is JSON — so this is the pin: a document kind, a rubric category, or a severity that exists
 * in one and not the other fails here rather than at somebody's keyboard.
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import { repoRoot } from '../../support/repo';

const SHIPPED = 'dist/claude-code';
const SKILL = 'skills/document-contract/SKILL.md';
const REQUIREMENTS = 'skills/document-contract/requirements-contract.md';
const DESIGN = 'skills/document-contract/design-contract.md';

const read = (relativePath: string): string =>
  readFileSync(join(repoRoot, SHIPPED, relativePath), 'utf-8');

interface Rules {
  readonly kinds: Record<string, { readonly sections: ReadonlyArray<{ readonly name: string }> }>;
  readonly rules: ReadonlyArray<{
    readonly id: string; readonly severity: string;
    readonly title: string; readonly fix: string;
  }>;
  readonly review: {
    readonly severities: readonly string[];
    readonly rubrics: Record<string, ReadonlyArray<{ readonly category: string }>>;
  };
}

const rules = (): Rules =>
  JSON.parse(read('tools/doc_rules.json')) as Rules;

describe('the authoring skill and the standard describe the same thing', () => {
  it('there is a standard to compare against', () => {
    // Guards the guard: an empty rule file would make every check below pass vacuously.
    const parsed = rules();
    expect(Object.keys(parsed.kinds).length).toBeGreaterThanOrEqual(2);
    expect(Object.keys(parsed.review.rubrics).length).toBeGreaterThanOrEqual(2);
  });

  it('every section the rules require is named in the half that teaches it', () => {
    const parsed = rules();
    const pages: Record<string, string> = {
      'business-requirements': read(REQUIREMENTS),
      spec: read(DESIGN),
    };
    const missing: string[] = [];
    for (const [kind, body] of Object.entries(parsed.kinds)) {
      const page = pages[kind];
      // A kind with no page at all is the louder failure: it means a document type ships with
      // nothing teaching how to write it.
      expect(page, `no half of the skill teaches the ${kind} document`).toBeTypeOf('string');
      for (const section of body.sections) {
        if (!(page ?? '').includes(section.name)) missing.push(`${kind}: ${section.name}`);
      }
    }
    expect(missing, 'these sections are enforced but never explained').toEqual([]);
  });

  it('the shipped severities are the ones the skill tells a reviewer to use', () => {
    const parsed = rules();
    const skill = read(SKILL);
    const missing = parsed.review.severities.filter((name) => !skill.includes(`\`${name}\``));
    expect(missing, 'these severities are judged but never described').toEqual([]);
  });

  it('the skill points at the two halves it delegates to', () => {
    const skill = read(SKILL);
    expect(skill).toContain('requirements-contract.md');
    expect(skill).toContain('design-contract.md');
  });
});

describe('the skill does not restate what would drift', () => {
  it('it names no per-tier count of its own', () => {
    // The tier tolerances live in doc_rules.json and are printed by the tool. A number copied into
    // prose is a number that will disagree with the policy the moment either moves.
    const skill = read(SKILL);
    expect(skill).not.toMatch(/\b\d+\s+majors?\b/i);
    expect(skill).toContain('doc_report.py rubric');
  });

  it('it tells the author the checks are not theirs to run', () => {
    // The promise this whole change rests on: the gates fire on the host's schedule, so an
    // instruction asking the agent to run a checker would be a lie about how it works.
    const skill = read(SKILL).toLowerCase();
    expect(skill).toContain('you are not asked to run anything');
  });

  it('it states which kind of finding blocks, and agrees with the rules about it', () => {
    // Pins the promise on both sides: the skill names the blocking CATEGORY, and every rule that
    // actually blocks belongs to it. A blocking rule added outside that class fails here.
    expect(read(SKILL)).toMatch(/dead\s+reference/i);
    const blocking = rules().rules.filter((rule) => rule.severity === 'block');
    expect(blocking.length).toBeGreaterThan(0);
    for (const rule of blocking) {
      expect(`${rule.title} ${rule.fix}`).toMatch(/resolve|exist|names nothing/i);
    }
  });
});
