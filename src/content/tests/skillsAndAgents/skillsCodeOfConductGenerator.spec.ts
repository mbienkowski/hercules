import { describe, expect, it } from 'vitest';

import { readRepoFile } from '../../../commons/support/repo';

// Prose pins for code-of-conduct-generator/SKILL.md and its coverage-map.md companion, plus the one
// write-test-scenarios pin. Text is whitespace-collapsed so a pinned phrase survives line-wrapping.

const COC_GENERATOR = 'dist/claude-code/skills/code-of-conduct-generator/SKILL.md';
const COC_MAP = 'dist/claude-code/skills/code-of-conduct-generator/coverage-map.md';

function flat(path: string): string {
  return readRepoFile(path).split(/\s+/).filter(Boolean).join(' ');
}

describe('code-of-conduct-generator: v4 lean spine + coverage-map companion', () => {
  it('offers a quick option before committing to a full scan', () => {
    const text = flat(COC_GENERATOR);
    expect(text).toContain('call `EnterPlanMode` first, before any scanning');
    expect(text).toContain('chat summary of the');
    expect(text).toContain('Quick');
    expect(text).toContain('Thorough');
    expect(text).toContain('low-stakes');
  });

  it("the generator's main instructions defer details to its companion reference doc", () => {
    const text = flat(COC_GENERATOR);
    expect(text).toContain('§ Scan playbook');
    expect(text).toContain('§ Output format');
    expect(text).toContain('coverage-map.md');
    expect(text).toContain('this file is the spine');
  });

  it('confirms which repo and file before writing anything', () => {
    const text = flat(COC_GENERATOR);
    expect(text).toContain('any capitalization');
    expect(text.toLowerCase()).toContain('case-insensitiv');
    expect(text).toContain('More than one');
    expect(text).toContain('never silently');
    expect(text).toContain('Contributor Covenant is not an engineering standard');
    expect(text).toContain('hercules-reference § Code-of-conduct resolution');
    expect(text).toContain('which repo the CoC is for');
    expect(text).toContain('one CoC per repo, never merged');
  });

  it('asks a substantial batch of questions and holds a quality bar', () => {
    const text = flat(COC_GENERATOR);
    expect(text).toContain('no trickle');
    expect(text).toContain('never asks fewer than 5–8 questions');
    expect(text).toContain('minimum 5');
    expect(text).toContain('accept/decline on each recommended gate');
    expect(text).toContain('branch (not just line) coverage');
    expect(text).toContain('mutation gate where a mutation tool exists');
  });

  it('walks through its nine steps in the documented order', () => {
    const skill = readRepoFile(COC_GENERATOR);
    const labels = [
      '1. **Plan mode', '2. **Find existing', '3. **Scan', '4. **Questions', '5. **Draft',
      '6. **Gap pass', '7. **Gate', '8. **Approve', '9. **Review',
    ];
    const positions = labels.map((s) => skill.indexOf(s));
    expect(positions, 'the nine steps must appear in execution order').toEqual([...positions].sort((a, b) => a - b));
  });
});

describe('coverage-map companion: the relocated scan-playbook and output-format detail', () => {
  it('the coverage gate requires objective checks, not just reviewer opinion', () => {
    const text = flat(COC_MAP);
    expect(text).toContain('reads exactly one way');
    expect(text).toContain('conflicts with no other');
    expect(text).toContain('"it looks nice"');
    expect(text).toContain('is not proof');
    expect(text).toContain('names an **objective** mechanical check');
    expect(text).toContain('reviewer-judgment-only is rejected');
    expect(text).toContain('auditable appendix');
    expect(text).toContain('dry-run each cited check');
  });

  it('warns about broad wildcard architecture rule patterns', () => {
    const text = flat(COC_MAP);
    expect(text, 'coverage-map must warn about broad wildcard package patterns').toContain('broad wildcard');
    expect(text, 'coverage-map must name infrastructure packages as the false-positive source').toContain(
      'infrastructure',
    );
    expect(text, 'coverage-map must recommend narrow patterns as the fix').toContain('narrow');
  });
});

describe('write-test-scenarios', () => {
  it('captures actual counts before freezing, never guessing an expected count', () => {
    const skill = readRepoFile('dist/claude-code/skills/write-test-scenarios/SKILL.md');
    const lower = skill.toLowerCase();
    expect(lower, 'write-test-scenarios must instruct capturing actual counts before freezing').toContain('capture');
    expect(lower).toContain('actual');
    expect(lower, 'write-test-scenarios must explicitly forbid guessing expected counts').toContain('never guess');
  });
});
