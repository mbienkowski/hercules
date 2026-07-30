import { readFileSync } from 'node:fs';
import { relative } from 'node:path';

import { describe, expect, it } from 'vitest';

import { repoRoot } from '../../../commons/support/repo';
import { TIER_ORDER } from '../../../metrics/scalingModel.mjs';
import {
  commandPath, distFile, PERSONA_PER_TREE, REFERENCE, RUBRIC, shippedFiles, TREES, type Tree,
} from './editions';

/**
 * Cross-surface consistency, asserted by forbidding a *shape* rather than by pinning prose.
 *
 * Several requirements are marked automatic and had no automatic check: "every place describing this
 * behaviour states the same numbers", "the floor lands on one tier", "carried material is labelled one
 * way". A pinned phrase cannot deliver them, because the claim they make is about everything that
 * ships — a mutation just writes the contradiction somewhere no pin is looking, which is how a review
 * pass landed 29 survivors against a green suite.
 *
 * What works instead is a sweep over every shipped file in every edition that forbids the shape a
 * violation must take. A second set of numbers has to pair a tier with a count; a second labelling
 * convention has to introduce a tag. Neither can be written anywhere without matching here, and
 * neither rule needs updating when the surrounding prose is reworded.
 */

const TIERS = TIER_ORDER.join('|');

/** A tier named on the same line as a count of advisors or rounds. */
const TIER_TOKEN = new RegExp(`\\b(?:${TIERS})\\b`, 'i');
const COUNT_OF_REVIEWERS = /\b\d+\s*(?:[–—-]\s*\d+\s*)?(?:advisors?|rounds?)\b|\b(?:advisors?|rounds?)\b[^.\n]{0,12}?\b\d/i;

/** Where the rubric's numbers are allowed to appear, and nowhere else. */
const MAY_STATE_THE_NUMBERS = [RUBRIC, 'README.md'];

/**
 * Every shipped file as addressable lines.
 *
 * The opencode edition embeds each command as a single JavaScript string literal, so its whole
 * `build.md` arrives as one physical line. Scanning that verbatim makes any two facts anywhere in a
 * command look adjacent — the first version of this sweep reported a false positive for exactly that
 * reason. Decoding the escaped newlines restores the line structure the rules are written against.
 */
function sweep(tree: Tree): { path: string; lines: string[] }[] {
  return shippedFiles(tree).map((abs) => {
    const path = relative(`${repoRoot}/dist/${tree}`, abs).split('\\').join('/');
    const raw = readFileSync(abs, 'utf-8');
    const text = path.endsWith('.js') ? raw.replace(/\\n/g, '\n') : raw;
    return { path, lines: text.split('\n') };
  });
}

describe('the rubric owns the numbers, and no other surface restates them', () => {
  /**
   * A detector that matches nothing reports success, which is the failure this whole spec exists to
   * remove — so the rule is proved against a synthetic restatement before it is trusted on real files.
   */
  it('recognises a restatement when it sees one', () => {
    const restatement = 'At `high` the orchestrator convenes 2 advisors for a single round.';
    expect(TIER_TOKEN.test(restatement) && COUNT_OF_REVIEWERS.test(restatement),
      'the detector no longer fires on a line that pairs a tier with an advisor count, so the sweep '
      + 'below passes over every edition while proving nothing').toBe(true);
    const prose = 'At `trivial` nobody is convened, so the phase proceeds directly.';
    expect(COUNT_OF_REVIEWERS.test(prose), 'the detector must not fire on tier prose that carries no '
      + 'figure — describing depth in words stays allowed everywhere').toBe(false);
  });

  it.each(TREES)('%s states an advisor or round count only in the rubric', (tree) => {
    const offenders: string[] = [];
    for (const { path, lines } of sweep(tree)) {
      if (MAY_STATE_THE_NUMBERS.some((allowed) => path.endsWith(allowed))) continue;
      lines.forEach((line, i) => {
        if (TIER_TOKEN.test(line) && COUNT_OF_REVIEWERS.test(line)) offenders.push(`${path}:${i + 1}  ${line.trim()}`);
      });
    }
    expect(offenders, `dist/${tree}: these lines pair a tier with a review count outside the rubric:\n`
      + `  ${offenders.join('\n  ')}\n\nThe rubric is the one table the model is read from. A second `
      + 'copy of a number anywhere else is drift the moment either changes, and it is drift no reader '
      + 'can resolve — they have two answers and no way to tell which ships. Cite the rubric instead, '
      + 'or describe the depth in words that carry no figure.').toEqual([]);
  });

  it.each(TREES)('%s carries the rubric itself, so the citation resolves', (tree) => {
    const md = distFile(tree, RUBRIC);
    for (const tier of TIER_ORDER) {
      expect(md, `dist/${tree}: the rubric omits ${tier} — every other surface defers to this table, `
        + 'so a missing row leaves that tier with no numbers at all').toContain(`complexity:${tier}`);
    }
  });
});

describe('the risk floor lands on one tier everywhere it is stated', () => {
  it.each(TREES)('%s names the same tier in every floor sentence', (tree) => {
    const found = new Map<string, string[]>();
    for (const { path, lines } of sweep(tree)) {
      for (const m of lines.join('\n').matchAll(/floor(?:s|ed)?\s+(?:at|to)\s+`?(?:complexity:)?([a-z]+)`?/gi)) {
        const tier = (m[1] ?? '').toLowerCase();
        if (!(TIER_ORDER as readonly string[]).includes(tier)) continue;
        found.set(tier, [...(found.get(tier) ?? []), path]);
      }
    }
    expect(found.size, `dist/${tree}: no surface states the risk floor — the floor is what raises a `
      + 'one-line change touching auth or money, so its absence removes the protection entirely')
      .toBeGreaterThan(0);
    expect([...found.keys()].sort(), `dist/${tree}: the floor names more than one tier — `
      + `${[...found].map(([t, ps]) => `${t}: ${ps.join(', ')}`).join(' | ')}. Two surfaces disagreeing `
      + 'about where the floor lands means a high-risk change gets whichever depth the agent happened '
      + 'to read.').toEqual(['high']);
  });
});

describe('carried material is labelled exactly one way', () => {
  /**
   * The convention is `[ATTACHMENT: {file} § {section}]`. A second convention is worse than none: an
   * agent handed two forms trusts whichever it recognises, and a tag-shaped one is also an injection
   * surface, since a project's own code-of-conduct may contain angle brackets that would close it.
   */
  it.each(TREES)('%s introduces no tag-shaped second convention', (tree) => {
    const offenders: string[] = [];
    for (const { path, lines } of sweep(tree)) {
      lines.forEach((line, i) => {
        // A closing tag, or an opening tag carrying an attribute — the two shapes a wrapper needs and
        // that a placeholder such as `<path>` or `<name>` never has.
        for (const shape of [/<\/[A-Za-z][\w-]*\s*>/, /<[A-Za-z][\w-]*\s+[a-z-]+\s*=/]) {
          if (shape.test(line)) offenders.push(`${path}:${i + 1}  ${line.trim()}`);
        }
      });
    }
    expect(offenders, `dist/${tree}: these lines introduce a tag-shaped wrapper:\n  `
      + `${offenders.join('\n  ')}\n\nCarried material is labelled with [ATTACHMENT: file § section] `
      + 'and closed with [/ATTACHMENT]. A second convention splits the vocabulary, and an angle-bracket '
      + "form can be closed early by bracket characters in the project's own files.").toEqual([]);
  });

  it.each(TREES)('%s names the file a slice came from', (tree) => {
    const packet = distFile(tree, 'protocols/workflow-protocol.md');
    const labels = [...packet.matchAll(/\[ATTACHMENT:([^\]]*)\]/g)].map((m) => (m[1] ?? '').trim());
    expect(labels.length, `dist/${tree}: the packet carries no ATTACHMENT label — unlabelled material `
      + 'is indistinguishable from the orchestrator\'s own instructions').toBeGreaterThan(0);
    const unnamed = labels.filter((l) => !/\.md|\{artifact\}|\{file\}|label/.test(l));
    expect(unnamed, `dist/${tree}: these labels name no source file: ${unnamed.join(' | ')} — an agent `
      + 'told a rule binds it cannot tell which document to reread when the slice runs out').toEqual([]);
  });
});

describe('every command that convenes advisors also asks the user first', () => {
  /**
   * Derived from what each command does, not from a list of command names: a command with an advisor
   * debate step convenes advisors, so it needs the consent gate, and a new one inherits the check.
   *
   * The signal is the step, not a citation of the protocol — Build and Ship cite the same file for
   * how deep their *review* goes, and a reviewer at a coverage gate is a separate category from an
   * advisor in a debate.
   */
  it.each(TREES)('%s gates each debating command on the roster', (tree) => {
    const debating = ['discover', 'design', 'build', 'ship', 'workflow']
      .map((name) => ({ name, text: distFile(tree, commandPath(tree, name)) }))
      .filter(({ text }) => /Advisor debate/i.test(text));
    expect(debating.map((c) => c.name).sort(), `dist/${tree}: the set of commands that convene advisors `
      + 'changed — Discover and Design are the generative phases; a third one appearing here needs its '
      + 'own consent gate reviewed, not inherited silently').toEqual(['design', 'discover']);
    for (const { name, text } of debating) {
      expect(text, `dist/${tree}/${commandPath(tree, name)} runs a debate without pointing at the `
        + 'consent flow — advisors would be spawned before the user has seen who is reviewing, which '
        + 'is the gate this delivery exists to add').toContain('Sub-agent consent');
    }
  });
});

describe('the coverage-gate reviewer is never offered as an advisor', () => {
  /**
   * The reviewer that decides the coverage and traceability gates cannot also have co-authored the
   * draft it reviews — that is what makes the review independent. Naming it in an example roster is
   * how a reader picks it anyway, and the example is what a reader copies.
   */
  it.each(TREES)('%s names no example roster containing it', (tree) => {
    const offenders: string[] = [];
    for (const { path, lines } of sweep(tree)) {
      lines.forEach((line, i) => {
        const looksLikeARoster = /\b(advisors?|roster|panel|debate)\b/i.test(line)
          && /\bcynical-reviewer\b/.test(line);
        const forbidsIt = /\bnever\b|\bnot\b|\bexclud|\bseparate\b|\breviewer\b\s*(?:,|\)|\.)/i.test(line);
        if (looksLikeARoster && !forbidsIt) offenders.push(`${path}:${i + 1}  ${line.trim()}`);
      });
    }
    expect(offenders, `dist/${tree}: these lines offer the coverage-gate reviewer as an advisor:\n  `
      + `${offenders.join('\n  ')}\n\nAn advisor helps author the draft; the reviewer then judges `
      + 'whether the draft covers its requirements. One agent doing both is the self-review the '
      + 'independent-review gate exists to prevent.').toEqual([]);
  });

  it.each(TREES)('%s says outright that it must not be picked', (tree) => {
    expect(distFile(tree, REFERENCE), `dist/${tree}: without the prohibition stated, the exclusion `
      + 'rests on nobody happening to choose it')
      .toMatch(/[Nn]ever pick `cynical-reviewer` as an advisor/);
  });
});

describe('the persona states how project rules reach an agent', () => {
  /**
   * The persona is loaded on every turn of every edition, so a stale sentence here outranks the
   * corrected wording everywhere else. It said each agent reads the code-of-conduct itself — the
   * mechanism this delivery replaced, and one an advisor was measured acting on.
   */
  it.each(TREES)('%s says the binding slice is carried, not fetched', (tree) => {
    const persona = distFile(tree, PERSONA_PER_TREE[tree]);
    expect(persona, `dist/${tree}: the persona must say the slice travels in the delegation packet, `
      + 'or an agent reads the whole document and spends the budget the slice was introduced to save')
      .toMatch(/binding slice is carried in the delegation packet/);
    expect(persona, `dist/${tree}: the persona must state the fallback — with no slice, the agent `
      + 'reads the file itself, or a delegation that omits one leaves the agent with no rules at all')
      .toMatch(/reads the file itself only when no slice arrives/);
    expect(persona, `dist/${tree}: "each agent reads" is the superseded mechanism — the persona ships `
      + 'on every turn, so it must not contradict the packet').not.toMatch(/code-of-conduct\.md` each agent reads/);
  });

  it('states it identically on every edition, bar the host name', () => {
    const wording = TREES.map((tree) => {
      const persona = distFile(tree, PERSONA_PER_TREE[tree]);
      return /all project variance lives in[\s\S]{0,200}?no slice arrives\./.exec(persona)?.[0]
        ?.replace(/\s+/g, ' ') ?? '';
    });
    expect(wording.filter((w) => w === ''), 'an edition whose persona omits the rule entirely would '
      + 'pass a per-edition containment check on a different sentence').toEqual([]);
    expect(new Set(wording).size, 'the editions must describe rule delivery identically, or an agent '
      + `behaves differently depending on which host it runs under: ${JSON.stringify(wording)}`).toBe(1);
  });
});
