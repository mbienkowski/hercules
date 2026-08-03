import { readFileSync } from 'node:fs';
import { relative } from 'node:path';

import { describe, expect, it } from 'vitest';

import { loadRecipe } from '../../../internal/builder/recipe-loader.mjs';
import { repoRoot } from '../../support/repo';
import { extractA2aCore } from '../../budgets/a2aGrammar.mjs';
import { section as pSection, sentences, TIER_ORDER } from '../../budgets/scalingModel.mjs';
import { readFile } from '../commands/support';
import {
  commandPath, distFile, REFERENCE, RUBRIC, shippedFiles, TREES,
} from './editions';

/**
 * The workflow protocol's main promises: fixed step order, the two consent gates, independent review
 * with no self-judgment, one owning source for the scaling numbers, and the delegate prohibitions.
 */

const PROTOCOL = 'dist/claude-code/protocols/workflow-protocol.md';
const DEBATE_PROTOCOL = 'dist/claude-code/protocols/debate-consensus-protocol.md';

function protocolSection(md: string, anchor: string): string {
  const m = new RegExp(`^(#+)[^\\n]*\\{#${anchor}\\}\\s*$`, 'm').exec(md);
  expect(m, `protocol must declare a heading with {#${anchor}}`).not.toBeNull();
  const level = (m as RegExpExecArray)[1]!.length;
  const rest = md.slice((m as RegExpExecArray).index + (m as RegExpExecArray)[0].length);
  const nxt = new RegExp(`^#{1,${level}}\\s`, 'm').exec(rest);
  return nxt === null ? rest : rest.slice(0, nxt.index);
}

function registryRows(md: string): string[][] {
  const lines = md.split('\n');
  const headerI = lines.findIndex((ln) => ln.trim().startsWith('| ID |'));
  expect(headerI, 'guardrail-registry table header (| ID |) not found').not.toBe(-1);
  const rows: string[][] = [];
  for (const ln of lines.slice(headerI + 2)) {
    if (!ln.trim().startsWith('|')) break;
    rows.push(ln.split(/(?<!\\)\|/).map((c) => c.trim()).filter((c) => c !== ''));
  }
  return rows;
}

describe('the workflow protocol — order and hard guardrails', () => {
  it('every guardrail rule is documented once, and a hook-class row maps to a real installed PreToolUse hook', () => {
    const rows = registryRows(protocolSection(readFile(PROTOCOL), 'registry'));
    expect(rows.length, "the registry must carry the workflow's hard rules").toBeGreaterThanOrEqual(5);
    const ids = rows.map((r) => r[0]);
    expect(ids.every((id) => /^G\d+$/.test(id as string)), 'every registry ID must be G<n>').toBe(true);
    expect(new Set(ids).size, 'no registry ID may repeat').toBe(ids.length);
    const hookRows = rows.filter((r) => r[r.length - 1] === 'hook');
    expect(hookRows.length, 'the registry must carry at least one hook-class row').toBeGreaterThan(0);
    // "Installed" is two things: the recipe DECLARES the hook file, so it is not a stray left in
    // dist/, and the shipped bytes really register the guard.
    const declared = Object.keys(loadRecipe('src/targets/claude-code.json', repoRoot).targets);
    expect(declared, 'claude-code must declare hooks/hooks.json as a shipped file').toContain('hooks/hooks.json');
    const installed = JSON.parse(readFile('dist/claude-code/hooks/hooks.json')) as {
      hooks?: { PreToolUse?: { matcher: string; hooks: { command?: string; args?: readonly string[] }[] }[] };
    };
    const pre = installed.hooks?.PreToolUse ?? [];
    expect(pre.some((entry) => entry.matcher.includes('Edit')), 'PreToolUse must match Edit for the frozen guard').toBe(true);
    const commands = pre.flatMap((entry) => entry.hooks.map((h) => [h.command ?? '', ...(h.args ?? [])].join(' ')));
    expect(commands.some((c) => c.includes('frozen_tests.py')), 'hooks.json must wire frozen_tests.py').toBe(true);
  });

  it('the delegation packet lists its fields in order, labels carried material one way, and forbids echoing it back', () => {
    const section = protocolSection(readFile(PROTOCOL), 'packet');
    const fence = /```\n([\s\S]*?)```/.exec(section);
    expect(fence, 'the {#packet} section must carry a fenced template').not.toBeNull();
    const body = (fence as RegExpExecArray)[1] as string;
    const chain = ['Phase:', 'Expected:', 'Guardrails:', 'Context:', '[Round:', 'A2A Agent-Injected Core follows'];
    const idxs = chain.map((label) => {
      expect(body, `packet template must declare ${label}`).toContain(label);
      return body.indexOf(label);
    });
    expect(idxs, `packet fields out of order: ${JSON.stringify(chain)}`).toEqual([...idxs].sort((a, b) => a - b));
    expect(section).toContain('verbatim');
    const wrappers = [...new Set([...section.matchAll(/\[([A-Z][A-Z-]+):[^\]]*§/g)].map((m) => m[1]))];
    expect(wrappers, 'one labelling convention, not two').toEqual(['ATTACHMENT']);
    expect(section.toLowerCase()).toContain('closing marker is carried by reference, never inline');

    const { text: core, found } = extractA2aCore(readFile('dist/claude-code/protocols/a2a-communication-protocol.md'));
    expect(found, 'the A2A protocol must ship a fenced Core').toBe(true);
    expect(core, 'packet-only labels must not leak into the shared A2A Core').not.toMatch(/Expected:|Guardrails:/);
  });

  it('the build phase runs in the same step order in the protocol and in build.md', () => {
    const assertOrdered = (text: string, tokens: RegExp[], name: string): void => {
      const idxs = tokens.map((tok) => {
        const m = tok.exec(text);
        expect(m, `${name} must contain step token ${tok}`).not.toBeNull();
        return (m as RegExpExecArray).index;
      });
      expect(idxs, `${name} steps out of order`).toEqual([...idxs].sort((a, b) => a - b));
    };
    const proto = protocolSection(readFile(PROTOCOL), 'phase-build').toLowerCase();
    assertOrdered(proto, [/scaffold/, /write failing tests/, /\bimplement\b/, /quality gates/, /mutation gate/,
      /traceability/, /\badvance\b/, /checkpoint/, /retire spec/, /cross-check/], 'protocol {#phase-build}');
    const build = readFile('dist/claude-code/commands/build.md').toLowerCase();
    assertOrdered(build.slice(build.indexOf('## execution')), [/\*\*scaffold\.\*\*/, /\*\*write failing tests\.\*\*/,
      /\*\*implement\.\*\*/, /\*\*quality gates\.\*\*/, /\*\*mutation gate\.\*\*/, /\*\*traceability\.\*\*/,
      /\*\*advance\.\*\*/, /\*\*write the checkpoint\.\*\*/, /\*\*retire the spec\.\*\*/, /## cross-check validation/],
    'build.md ## Execution');
  });
});

/**
 * The rules of the debate, pinned as WHOLE SENTENCES: a fragment survives the mutation that matters —
 * keep the pinned words, add a nearby qualifier that reverses the rule.
 */
const DEBATE_RULES: { heading: string; anchor: string; sentence: string }[] = [
  { heading: 'opening', anchor: 'a single advisor is a review', sentence: 'a single advisor is a review, not a debate, and skips this protocol.' },
  { heading: '## complexity', anchor: 'ceiling, never an itinerary', sentence: 'the high end of the rounds column is a ceiling, never an itinerary — a further round runs only when the one before it left something contested.' },
  { heading: '## complexity', anchor: 'the low end binds only at', sentence: 'the low end binds only at `complexity:critical`, which runs its second round and its fresh-eyes panel whatever the convergence state, because that is the level where a missed problem is least recoverable.' },
  { heading: '## complexity', anchor: 'a debate needs two advisors', sentence: 'a debate needs two advisors and two rounds.' },
  { heading: '## Carrying a position', anchor: 'a position is what an advisor concluded', sentence: 'a position is what an advisor concluded — the verdict it gave and the problems it named — never its speciality.' },
  { heading: '## Carrying a position', anchor: 'same conclusion are one position', sentence: 'two advisors of different specialities who reached the same conclusion are one position; two of the same speciality who disagreed are two.' },
  { heading: '## Carrying a position', anchor: 'carries one advisor per position', sentence: 'a contested topic carries one advisor per position, including the position that found nothing wrong, so that view is argued rather than dropped.' },
  { heading: '## Fresh-eyes panel', anchor: 'convenes a panel after its final round', sentence: '`complexity:critical` convenes a panel after its final round whatever the convergence state, drawn inside its advisor maximum and carrying no history of the rounds before it.' },
  { heading: '## Synthesis', anchor: 'resolves only when every raised topic', sentence: 'a debate resolves only when every raised topic is settled.' },
  { heading: '## Synthesis', anchor: 'never auto-applied', sentence: 'the choices are accept as-is, another angle, or override; a surviving finding is never auto-applied.' },
  { heading: '## Synthesis', anchor: 'never resolved by the orchestrator', sentence: 'a reservation is carried to the user\'s decision, never resolved by the orchestrator, and any contested finding is presented to the user verbatim as an open question.' },
];

describe('the debate rules, pinned as whole sentences (critical)', () => {
  const md = readFile(DEBATE_PROTOCOL);
  const bodyOf = (heading: string): string => (heading === 'opening'
    ? md.slice(0, md.indexOf('## complexity')) : pSection(md, heading, DEBATE_PROTOCOL));

  it.each(DEBATE_RULES)('$heading — $anchor', ({ heading, anchor, sentence }) => {
    const hit = sentences(bodyOf(heading)).filter((s) => s.includes(anchor));
    expect(hit.length, `"${anchor}" must appear exactly once in ${heading}`).toBe(1);
    expect(hit[0], 'a qualifier added anywhere in the sentence must fail this equality').toBe(sentence);
  });

  it('a debate settles a topic only on two-or-more agreement, and closes only when every topic is settled', () => {
    const converging = pSection(md, '## Converging a round', DEBATE_PROTOCOL);
    const said = sentences(converging);
    expect(said.find((s) => s.includes('a topic is settled')))
      .toBe('a topic is settled — two or more advisors spoke on the topic and state the same position.');
    expect(said.find((s) => s.includes('closes when every topic is settled')))
      .toBe("a debate closes when every topic is settled and the level's floor is met.");
  });
});

describe('gate 1 and gate 2 — how demanding the work is, and who reviews it', () => {
  // Every edition: a per-target split once kept claude-code correct while showing the other five no choices.
  it.each(TREES)('%s\'s judgement gate offers keep/lower/raise/a free answer, shows at every level, and waits for the answer', (tree) => {
    const lower = readFile(`dist/${tree}/${commandPath(tree, 'discover')}`).toLowerCase();
    for (const choice of ['keep it', 'lower it', 'raise it', 'answer freely']) {
      expect(lower, `dist/${tree}: judgement gate must offer "${choice}"`).toContain(choice);
    }
    expect(lower, `dist/${tree}: must show at every level, trivial included`).toMatch(/at every level\W{0,6}trivial included/);
    expect(lower, `dist/${tree}: must wait for the answer`).toContain('wait for the user to confirm or override');
  });

  it('gate 2 lets the user accept, remove, or add advisors, and never spawns one before they answer', () => {
    const md = readFile(REFERENCE_SKILL());
    const start = md.indexOf('### Sub-agent consent');
    expect(start, 'no "### Sub-agent consent" heading').toBeGreaterThanOrEqual(0);
    const rest = md.slice(start + 1);
    const end = rest.search(/\n#{2,3} /);
    const consent = (end < 0 ? rest : rest.slice(0, end)).toLowerCase();
    expect(consent).toMatch(/accept, remove or add per advisor/);
    expect(consent).toContain('never spawns advisors silently');
    expect(consent).toMatch(/recommends advisors and waits/);
  });
  function REFERENCE_SKILL(): string { return 'dist/claude-code/skills/hercules-reference/SKILL.md'; }
});

/** Cross-surface consistency, by forbidding a SHAPE rather than pinning prose — claude-code only. */
const TIER_REFERENCE = new RegExp(
  `\\b(?:${TIER_ORDER.join('|')})\\b|\\b(?:most|least) demanding\\b|\\b(?:highest|lowest|lightest|simplest) tier\\b`, 'i',
);
const NUMERAL = '(?:\\d+|one|two|three|four|five|six|seven|eight|nine|ten|single)';
const COUNT_OF_REVIEWERS = new RegExp(
  `\\b${NUMERAL}(?:\\s*(?:[–—-]|to)\\s*${NUMERAL})?\\s+(?:advisors?|rounds?)\\b|\\b(?:advisors?|rounds?)\\s*[:=]?\\s+${NUMERAL}\\b`, 'i',
);
// Sentences legitimately carrying a count that is NOT the per-tier board size (debate floor, round name, carrying rule, review bound).
const EXEMPT_SENTENCES = [
  'a debate needs two advisors and two rounds.', '## round 1 — blind', 'one advisor per position',
  'bounded (three rounds → the user)',
  'where the table allows a single round the advisors return their findings in parallel and the '
    + 'orchestrator synthesises them; that is a set of opinions, and no cross-examination takes place.',
  'a later round runs only where the one before it left a topic contested, and it carries one advisor '
    + 'per surviving position rather than the whole board, so a debate narrows as it proceeds.',
];
const NO_SURFACE_MAY: { label: string; claim: RegExp }[] = [
  { label: 'let one advisor hold a debate', claim: /\b(?:lone|single|one)\s+advisor\b[^.]{0,90}?\b(?:may|can|counts? as|is acceptable|is permitted|is enough|suffices|runs? both|alone is)\b/i },
  { label: 'spawn advisors before the user has answered', claim: /\b(?:spawn|dispatch|launch|convene|begin|start|proceed with)\b[^.]{0,70}?\b(?:at once|immediately|directly|straight away|alongside this|without waiting|without asking)\b|\broster is (?:fixed|settled|already decided)\b/i },
  { label: 'make the risk floor optional', claim: /\bfloor\b[^.]{0,70}?\b(?:advisory|optional|a suggestion|discretion(?:ary)?|set aside|may be ignored)\b|\b(?:raise|floor)\b[^.]{0,70}?\bleft to the orchestrator's own discretion\b/i },
];

/** Every shipped file on `tree`, decoded so an opencode-style escaped-newline JS literal still reads as lines. */
function sweep(tree: (typeof TREES)[number]): { path: string; text: string }[] {
  return shippedFiles(tree).map((abs) => {
    const path = relative(`${repoRoot}/dist/${tree}`, abs).split('\\').join('/');
    const raw = readFileSync(abs, 'utf-8');
    return { path, text: path.endsWith('.js') ? raw.replace(/\\n/g, '\n') : raw };
  });
}

/** Paragraph-scale prose units — a claim can span a line break, so a line is the wrong window. */
function proseUnits(text: string): string[] {
  const out: string[] = [];
  const withoutJson = text.replace(/```[a-z]*\n([\s\S]*?)```/g, (block, body: string) => (/^\s*[[{]/.test(body) ? '' : block));
  for (const para of withoutJson.split('\n\n')) {
    const lines = para.split('\n').filter((l) => !/^\s*```/.test(l));
    out.push(...lines.filter((l) => l.trimStart().startsWith('|')));
    out.push(lines.filter((l) => !l.trimStart().startsWith('|')).join(' '));
  }
  return out.filter((u) => u.trim() !== '');
}

function unitSentences(unit: string): string[] {
  return unit.replace(/\s+/g, ' ').split(/(?<=[.!?])\s+/).map((x) => x.trim().toLowerCase()).filter(Boolean);
}

describe('cross-surface consistency — the numbers live in one place, and no shipped file makes a forbidden claim', () => {
  it('states a per-tier review count only inside the rubric table', () => {
    const offenders: string[] = [];
    for (const { path, text } of sweep('claude-code')) {
      const units = proseUnits(text);
      let tierAgo = Number.POSITIVE_INFINITY;
      units.forEach((unit, i) => {
        if (TIER_REFERENCE.test(unit)) tierAgo = 0; else tierAgo += 1;
        if (tierAgo > 2) return;
        if (path.endsWith(RUBRIC) && (units[i] as string).trimStart().startsWith('|')) return;
        for (const sentence of unitSentences(unit)) {
          if (!COUNT_OF_REVIEWERS.test(sentence)) continue;
          if (EXEMPT_SENTENCES.some((s) => sentence.includes(s))) continue;
          offenders.push(`${path}: ${sentence.slice(0, 140)}`);
        }
      });
    }
    expect(offenders, `a per-tier count is restated outside the rubric table:\n  ${offenders.join('\n  ')}`).toEqual([]);
  });

  it('makes none of the forbidden claims about advisors or the risk floor, and never offers the reviewer as a default advisor', () => {
    const offenders: string[] = [];
    for (const { path, text } of sweep('claude-code')) {
      for (const unit of proseUnits(text)) {
        for (const { claim, label } of NO_SURFACE_MAY) {
          if (claim.test(unit)) offenders.push(`${path} would ${label}: ${unit.trim().slice(0, 140)}`);
        }
      }
    }
    expect(offenders, `forbidden claims found:\n  ${offenders.join('\n  ')}`).toEqual([]);
    expect(distFile('claude-code', REFERENCE)).toMatch(/[Nn]ever pick `cynical-reviewer` as an advisor/);
  });
});
