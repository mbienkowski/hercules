import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';

import { describe, expect, it } from 'vitest';

import { EXPECTED_MODEL, parseScalingModel, TIER_ORDER } from '../../../metrics/scalingModel.mjs';
import { readFile } from '../commands/support';
import { readRepoFile, repoRoot } from '../../../commons/support/repo';

/**
 * One model, stated on several surfaces, asserted equal on each — the numbers are compared, never
 * spot-checked for a substring, because a contradictory row left behind passes a containment check.
 *
 * Every edition is read, not just the gated one: they name and wrap the same artifacts differently,
 * so each path is resolved and its absence is a failure. A glob that opens nothing passes silently,
 * which is the exact defect this guard exists to prevent.
 */

const TREES = ['claude-code', 'opencode', 'cursor', 'copilot-cli', 'gemini-cli', 'grok-build'] as const;

/** Where each edition keeps the artifacts this guard reads. */
const PERSONA_PER_TREE: Record<(typeof TREES)[number], string> = {
  'claude-code': 'CLAUDE.md',
  'grok-build': 'CLAUDE.md',
  opencode: 'instructions.md',
  cursor: 'rules/hercules-persona.mdc',
  'copilot-cli': 'AGENTS.md',
  'gemini-cli': 'GEMINI.md',
};

const RUBRIC = 'protocols/debate-consensus-protocol.md';
const REFERENCE = 'skills/hercules-reference/SKILL.md';
const DIAGRAMS = ['workflow-diagram-detailed.html', 'workflow-diagram-simplified.svg'];

/** The spellings the numeric-agreement model used. None may survive on a shipped surface. */
const RETIRED = ['Agreement: N/5', '≤3/5', '5/5', 'Round 1 + 2 + 3', 'fresh-eyes(mandatory)'];

/** Every shipped text file in an edition — a four-entry literal skips the other ~30. */
function shippedFiles(tree: string): string[] {
  const root = `${repoRoot}/dist/${tree}`;
  const out: string[] = [];
  const walk = (dir: string): void => {
    for (const name of readdirSync(dir)) {
      const abs = `${dir}/${name}`;
      if (statSync(abs).isDirectory()) walk(abs);
      else if (/\.(md|toml|mdc|json|js)$/.test(name)) out.push(abs);
    }
  };
  walk(root);
  expect(out.length, `dist/${tree} yielded ${out.length} files — a sweep that opens almost nothing `
    + 'reports success').toBeGreaterThan(10);
  return out;
}

function distFile(tree: string, rel: string): string {
  const abs = `${repoRoot}/dist/${tree}/${rel}`;
  expect(existsSync(abs), `dist/${tree}/${rel} does not exist — this edition would be skipped `
    + 'silently, and a guard that opens nothing reports success').toBe(true);
  return readFile(`dist/${tree}/${rel}`);
}

describe('the model is identical on every edition', () => {
  it.each(TREES)('%s states the rubric exactly', (tree) => {
    const parsed = parseScalingModel(distFile(tree, RUBRIC), `dist/${tree}/${RUBRIC}`);
    expect(parsed, `dist/${tree}: a wrong cell here silently changes how much review every future `
      + 'feature gets on this edition').toEqual([...EXPECTED_MODEL]);
  });

  it.each(TREES)('%s states the same rounds in the injected core as in the rubric', (tree) => {
    const core = distFile(tree, 'protocols/a2a-communication-protocol.md');
    const line = core.split('\n').find((l) => /^\s*Rounds:/.test(l));
    expect(line, `dist/${tree}: rule 7 carries no Rounds line — the core is the only debate text a `
      + 'built-in agent ever sees').toBeTruthy();
    const norm = (v: string): string => v.replace(/[–—]/g, '-').replace(/\s*\+.*$/, '').trim();
    for (const m of EXPECTED_MODEL) {
      const found = new RegExp(`${m.tier}\\s+([0-9-]+|none)`).exec(line as string);
      expect(found, `dist/${tree}: rule 7 never states ${m.tier}`).toBeTruthy();
      const want = m.rounds === '0' ? 'none' : norm(m.rounds);
      expect(norm((found as RegExpExecArray)[1] ?? ''), `dist/${tree}: rule 7 gives ${m.tier} `
        + `"${(found as RegExpExecArray)[1]}" rounds while the rubric gives "${m.rounds}" — every `
        + 'agent is injected with the core, so it would run a different schedule than the orchestrator plans')
        .toBe(want);
    }
  });

  it('scores on both axes everywhere, so the higher of the two is computable', () => {
    for (const tree of TREES) {
      const md = distFile(tree, RUBRIC);
      for (const column of ['Effort signals', 'Blast-radius signals']) {
        expect(md, `dist/${tree}: without the "${column}" column an agent cannot score the axis it `
          + 'is told to take the higher of').toContain(column);
      }
    }
  });
});

describe('surfaces that restate the model', () => {
  it('keeps the README table on the same numbers as the rubric', () => {
    const readme = readRepoFile('README.md');
    for (const m of EXPECTED_MODEL) {
      const row = readme.split('\n').find((l) => l.startsWith(`| ${m.tier} |`));
      expect(row, `README has no row for ${m.tier} — a user reads the promise from this table`).toBeTruthy();
      const cells = (row as string).split('|').map((c) => c.trim());
      expect(`${cells[4]}|${cells[5]}`, `README promises ${m.tier} = ${cells[4]} advisors / ${cells[5]} `
        + `rounds while the rubric runs ${m.advisors} / ${m.rounds} — the published promise and the `
        + 'shipped behaviour disagree').toBe(`${m.advisors}|${m.rounds}`);
    }
  });

  it.each(TREES)('%s keeps per-tier numbers out of the reference skill and the persona', (tree) => {
    for (const rel of [REFERENCE, PERSONA_PER_TREE[tree]] as const) {
      const rows = distFile(tree, rel).split('\n')
        .filter((l) => new RegExp(`^\\|\\s*\`?(complexity:)?(${TIER_ORDER.join('|')})\`?\\s*\\|`).test(l));
      expect(rows, `dist/${tree}/${rel} carries a per-tier table — the rubric owns those numbers, and `
        + 'a second copy is exactly the drift this guard exists to catch').toEqual([]);

      // A prose restatement drifts exactly as a table does, and reads as authoritative.
      const text = distFile(tree, rel);
      for (const m of EXPECTED_MODEL.filter((x) => x.advisors !== '0')) {
        const near = new RegExp(`\\b${m.tier}\\b[^.\n]{0,40}(?<!\\d)${m.advisors.replace('–', '[–-]')}(?!\\d)`, 'i');
        expect(near.test(text), `dist/${tree}/${rel} restates ${m.tier} = ${m.advisors} advisors in `
          + 'prose — a second copy of the numbers on an auto-loaded surface is a stale-copy source')
          .toBe(false);
      }
    }
  });

  it('keeps per-tier numbers out of the diagrams', () => {
    for (const d of DIAGRAMS) {
      const html = readRepoFile('docs', 'workflow', d);
      for (const m of EXPECTED_MODEL.filter((x) => x.advisors !== '0')) {
        expect(html, `${d} states ${m.tier}'s advisor count — the diagram shows the shape, and a `
          + 'number here goes stale on the next change with nothing to catch it')
          .not.toMatch(new RegExp(`\\b${m.tier}\\b[^<]{0,40}(?<!\\d)${m.advisors.replace('–', '[–-]')}(?!\\d)`, 'i'));
      }
    }
  });
});

const RISK_TOKENS = ['auth', 'secrets', 'money', 'data migration', 'deletion', 'production config',
  'concurrency', 'personal data'];

describe('the floored risk list', () => {
  it.each(TREES)('names every category on every surface carrying it in %s', (tree) => {
    for (const rel of [RUBRIC, REFERENCE] as const) {
      const lower = distFile(tree, rel).toLowerCase();
      const missing = RISK_TOKENS.filter((t) => !lower.includes(t));
      expect(missing, `dist/${tree}/${rel} dropped ${missing.join(', ')} — this is the surface an `
        + 'agent reads the floor from, and a category missing here is never floored')
        .toEqual([]);
      expect(lower, `dist/${tree}/${rel} must mark the list open, or an unanticipated surface floors nothing`)
        .toContain('examples rather than a closed catalogue');
    }
  });
});

describe('the retired agreement notation', () => {
  it.each(TREES)('is gone from every shipped file in %s', (tree) => {
    const offenders: string[] = [];
    for (const abs of shippedFiles(tree)) {
      const text = readFileSync(abs, 'utf-8');
      for (const n of RETIRED.filter((x) => text.includes(x))) {
        offenders.push(`${abs.slice(abs.indexOf(`dist/${tree}`))}: ${n}`);
      }
    }
    expect(offenders, `retired notation still shipped:\n  ${offenders.join('\n  ')}\n`
      + 'a debate converges by topic, so a numeric agreement vote has no consumer and is dead text '
      + 'an agent may still obey').toEqual([]);
  });

  it('is gone from README and the diagrams', () => {
    const surfaces: [string, string][] = [['README.md', readRepoFile('README.md')]];
    for (const d of DIAGRAMS) surfaces.push([d, readRepoFile('docs', 'workflow', d)]);
    for (const [name, text] of surfaces) {
      const found = RETIRED.filter((n) => text.includes(n));
      expect(found, `${name} still states ${found.join(', ')}`).toEqual([]);
    }
  });
});
