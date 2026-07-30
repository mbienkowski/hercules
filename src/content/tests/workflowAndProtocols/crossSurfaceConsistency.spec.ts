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

/**
 * A tier referred to by name OR obliquely. Requiring the literal token let "The most demanding tier
 * runs 2 advisors across 1 round." ship to all six editions with the suite green.
 */
const TIER_REFERENCE = new RegExp(
  `\\b(?:${TIERS})\\b|\\b(?:most|least) demanding\\b|\\b(?:highest|lowest|lightest|simplest) tier\\b`, 'i',
);

/**
 * A count of advisors or rounds, in digits or in words. Requiring a digit let "convenes two advisors
 * for one round" ship green — prose spells small numbers out, which is exactly how a restatement gets
 * written by hand.
 */
const NUMERAL = '(?:\\d+|one|two|three|four|five|six|seven|eight|nine|ten|single)';
const COUNT_OF_REVIEWERS = new RegExp(
  `\\b${NUMERAL}(?:\\s*(?:[–—-]|to)\\s*${NUMERAL})?\\s+(?:advisors?|rounds?)\\b`
  + `|\\b(?:advisors?|rounds?)\\s*[:=]?\\s+${NUMERAL}\\b`, 'i',
);

/**
 * How far a tier reference carries.
 *
 * Requiring the tier and the count in ONE unit was defeated by a blank line: "For the most demanding
 * tier, size the board as follows:" followed by "Convene 9 advisors and allow 4 rounds of discussion."
 * shipped to all six editions green. A heading plus a lead-in sentence is two units, so the reference
 * has to reach the units that follow it.
 */
const TIER_CARRIES_FOR_UNITS = 2;

/**
 * Counts that are NOT the per-tier advisor model, each justified and each asserted to still be found.
 *
 * A loosened regex rots silently; an exemption listed as data does not. Every entry must still match
 * something, so an exemption that stops applying fails the suite instead of quietly widening the hole
 * it was cut for.
 *
 * Two things make an exemption narrow enough to be safe. It is scoped to the SECTION that justifies
 * it, not the file — scoped to the file, any tier paired with "three rounds" anywhere in the reference
 * skill was waved through, and "At `low` the board holds three rounds" shipped green. And it exempts
 * only the matching phrase, never the passage around it — an earlier version tested the first count in
 * a unit and skipped the rest of the unit on a hit, so appending "At `critical` the board is 2 advisors
 * and 1 round." to the same paragraph as the sanctioned phrase shipped green.
 */
/**
 * Sentences allowed to carry a count, because the count is not the per-tier board size.
 *
 * The exemption is keyed to the SENTENCE, not to a phrase and not to a file. Both looser forms were
 * holes. Scoped to a file, any tier paired with "three rounds" anywhere in the reference skill was
 * waved through, and "At `low` the board holds three rounds" shipped green. Scoped to a phrase, an
 * exemption for the floor's "two advisors" would equally excuse a planted "At `critical` the board is
 * two advisors and two rounds." Keyed to the sentence, a NEW sentence is never exempt however it is
 * worded, which is the property that matters.
 *
 * Each entry must still match, so an exemption that stops applying fails instead of widening silently.
 */
const SENTENCES_THAT_MAY_COUNT: readonly { file: string; section: string; sentence: string; why: string }[] = [
  {
    file: 'protocols/debate-consensus-protocol.md',
    section: '## complexity',
    sentence: 'a debate needs two advisors and two rounds.',
    why: 'the global floor, not a per-tier figure — the minimum any debating tier must meet, and pinned '
      + 'separately as a whole sentence by protocolFiles.spec.ts',
  },
  {
    file: 'protocols/debate-consensus-protocol.md',
    section: '## complexity',
    sentence: 'where the table allows a single round the advisors return their findings in parallel and '
      + 'the orchestrator synthesises them; that is a set of opinions, and no cross-examination takes place.',
    why: 'defers to the table rather than restating it — "a single round" names the table\'s own value '
      + 'instead of asserting a second one',
  },
  {
    file: 'protocols/debate-consensus-protocol.md',
    section: '## Round 1 — Blind',
    sentence: '## round 1 — blind',
    why: 'the round\'s name, not a count of rounds',
  },
  {
    file: 'protocols/a2a-communication-protocol.md',
    section: '## Agent-Injected Core',
    sentence: 'one advisor per position',
    why: 'one advisor per POSITION is the carrying rule, independent of how many advisors the tier '
      + 'convened. It appears inside the fenced Core, which core.golden pins byte-for-byte',
  },
  {
    file: 'skills/hercules-reference/SKILL.md',
    section: '## Agent scaling',
    sentence: 'a later round runs only where the one before it left a topic contested, and it carries '
      + 'one advisor per surviving position rather than the whole board, so a debate narrows as it proceeds.',
    why: 'the same per-position carrying rule, again not a per-tier figure',
  },
  {
    file: 'skills/hercules-reference/SKILL.md',
    section: '## Independent review',
    sentence: 'bounded (three rounds → the user)',
    why: 'the independent-review escalation bound. Reviewers at the coverage and traceability gates are '
      + 'a separate category from advisors in a debate, so this count is not the rubric\'s and cannot '
      + 'drift from it',
  },
];

/**
 * Does a marker's payload name a source? A labelling convention names a document or a section of one;
 * an unrelated placeholder such as `[PATH: …]` does not. Extracted so it can be tested directly —
 * tightened to `§` alone it re-opens the rival-convention hole with nothing failing.
 */
export function namesASource(payload: string): boolean {
  return /§|\.md\b|\bsection\b/.test(payload);
}

/** Every agent this plugin ships, so a roster can be checked by membership rather than by phrasing. */
const KNOWN_AGENTS = new Set(['challenger', 'cynical-reviewer', 'lead-architect', 'security-expert',
  'senior-qa-engineer', 'backend-engineer', 'frontend-engineer', 'devops-engineer', 'ux-ui-designer',
  'source-checker', 'maintainer', 'business-analyst', 'copywriter', 'document-specialist',
  'simplicity-advocate']);

/** Sentences of a unit, normalised for comparison against the allow-list above. */
function unitSentences(unit: string): string[] {
  return unit.replace(/\s+/g, ' ').split(/(?<=[.!?])\s+/)
    .map((x) => x.trim().toLowerCase()).filter(Boolean);
}

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

/**
 * Prose units for claims that span a sentence rather than a line.
 *
 * A physical line is the wrong window: "At `high` the panel is sized as follows:" on one line and
 * "advisors 9, and rounds 4." on the next defeated a line-scoped sweep while the identical claim on
 * one line was caught. A paragraph is the right window for prose, with two corrections.
 *
 * Each table row is its own unit — a whole guardrail registry is one paragraph, which made one rule's
 * TDD round count look adjacent to another rule's tier.
 *
 * Fenced blocks are KEPT. Deleting them was a hole big enough to walk a rule through: a lone-advisor
 * permission placed inside a fence in `design.md` shipped to all six editions green, while the same
 * sentence outside the fence was killed on all six. Only a block whose first line opens a JSON object
 * is skipped — that is the state-file example whose `"round": 1` sits beside an unrelated `"tier"`
 * field, and it is data rather than prose about the model.
 */
function proseUnits(text: string): string[] {
  const out: string[] = [];
  const withoutJson = text.replace(/```[a-z]*\n([\s\S]*?)```/g, (block, body: string) => (
    /^\s*[[{]/.test(body) ? '' : block
  ));
  for (const para of withoutJson.split('\n\n')) {
    const lines = para.split('\n').filter((l) => !/^\s*```/.test(l));
    out.push(...lines.filter((l) => l.trimStart().startsWith('|')));
    out.push(lines.filter((l) => !l.trimStart().startsWith('|')).join(' '));
  }
  return out.filter((u) => u.trim() !== '');
}

/**
 * Which `##` section a prose unit sits in, so an exemption can be scoped to the section that justifies
 * it rather than to the whole file. File-scoped exemptions are holes: any tier paired with the
 * sanctioned phrase anywhere in the file was waved through.
 */
function sectionOf(lines: string[], units: string[], index: number): string {
  const before = units.slice(0, index + 1).join('\n');
  const headings = before.match(/^## .*/gm) ?? [];
  const last = headings.at(-1);
  if (last !== undefined) return last.trim();
  // No heading yet — the unit is in the preamble. Name it after the file's own title when it has one.
  return (lines.find((l) => l.startsWith('# ')) ?? '(preamble)').trim();
}

describe('the sweep knobs are reviewed values, not silent dials', () => {
  /**
   * `HARD_GATE`/`WARN_AT` were pinned as literals after raising them to 400/380 left the suite green.
   * These two are the same class of dial and were not pinned: narrowing the carry window to 0, or
   * tightening the marker payload filter, weakens a sweep with nothing failing.
   */
  it('carries a tier reference far enough to survive a paragraph break', () => {
    expect(TIER_CARRIES_FOR_UNITS, 'a heading plus a lead-in sentence is two units, so a smaller window '
      + 'lets a tier and its numbers be separated by a blank line — the exact bypass this closed')
      .toBeGreaterThanOrEqual(2);
  });

  it('treats a marker naming only a file as a source label', () => {
    expect(namesASource(' project rules, testing section §'), 'a payload with a section mark labels a source')
      .toBe(true);
    expect(namesASource(' code-of-conduct.md'), 'a payload naming a file labels a source even with no '
      + 'section mark — tightening this to require § alone re-opens the rival-convention hole')
      .toBe(true);
    expect(namesASource(' n'), 'a bare placeholder is not a source label').toBe(false);
  });
});

describe('the rubric owns the numbers, and no other surface restates them', () => {
  /**
   * A detector that matches nothing reports success, which is the failure this whole spec exists to
   * remove — so every branch is proved against a synthetic restatement before it is trusted.
   *
   * One fixture is not enough: an earlier version had a single case that exercised only the
   * digits-plus-advisors branch, so deleting `rounds?` from the pattern left this test green while the
   * sweep went blind to every round-count restatement.
   */
  it.each([
    ['literal tier, digits', 'At `high` the orchestrator convenes 2 advisors for a single round.'],
    ['literal tier, words', 'At `critical` the orchestrator convenes two advisors for one round.'],
    ['oblique tier, digits', 'The most demanding tier runs 2 advisors across 1 round.'],
    ['range form', 'The `medium` tier convenes 2–3 advisors.'],
    ['round count alone', 'At `low` the debate is bounded to 1 round.'],
    ['trailing figure', 'For `high` work: advisors 4, rounds 2.'],
  ])('recognises a restatement written as %s', (_shape, restatement) => {
    expect(TIER_REFERENCE.test(restatement), 'the tier half of the detector missed this phrasing, so '
      + 'the sweep below passes over every edition while proving nothing').toBe(true);
    expect(COUNT_OF_REVIEWERS.test(restatement), 'the count half of the detector missed this phrasing')
      .toBe(true);
  });

  it.each([
    'At `trivial` nobody is convened, so the phase proceeds directly.',
    'At most 3 implementation rounds per spec, persisted; after round 3 the user decides.',
    'A contested topic carries one advisor per position, including the position that found nothing.',
  ])('does not fire on %s', (allowed) => {
    expect(TIER_REFERENCE.test(allowed) && COUNT_OF_REVIEWERS.test(allowed),
      'this is legitimate prose — depth described without a figure, the TDD round limit, or a rule '
      + 'about positions rather than tiers. Flagging it would make the sweep unusable and invite it '
      + 'to be switched off.').toBe(false);
  });

  /**
   * The rubric's TABLE ROWS are the only place a per-tier count may appear — not the rubric file.
   *
   * Exempting the whole file left its own prose unread by anything: `parseScalingModel` parses only
   * lines starting `| \`complexity:`, so "In practice the most demanding tier convenes 2 advisors for a
   * single round; the table above is an upper bound nobody reaches." shipped green inside the one file
   * every other surface defers to. Table rows are skipped here because the parser owns them and
   * compares them cell for cell against EXPECTED_MODEL.
   */
  it.each(TREES)('%s states a per-tier count only in the rubric table', (tree) => {
    const offenders: string[] = [];
    for (const { path, lines } of sweep(tree)) {
      const units = proseUnits(lines.join('\n'));
      // A tier reference reaches the units that follow it, so a paragraph break cannot separate the
      // tier from its numbers. Without this, a lead-in line plus a count on the next line shipped green.
      let tierSeenAgo = Number.POSITIVE_INFINITY;
      units.forEach((unit, i) => {
        if (TIER_REFERENCE.test(unit)) tierSeenAgo = 0; else tierSeenAgo += 1;
        if (tierSeenAgo > TIER_CARRIES_FOR_UNITS) return;
        // The rubric's table rows are the model itself; the parser asserts them cell for cell.
        if (path.endsWith(RUBRIC) && unit.trimStart().startsWith('|')) return;
        const section = sectionOf(lines, units, i);
        const allowed = SENTENCES_THAT_MAY_COUNT
          .filter((e) => path.endsWith(e.file) && section === e.section).map((e) => e.sentence);
        // EVERY sentence carrying a count is judged on its own. Judging only the first match in a unit
        // and skipping the rest let a contradiction ride behind a sanctioned phrase.
        for (const sentence of unitSentences(unit)) {
          if (!COUNT_OF_REVIEWERS.test(sentence)) continue;
          if (allowed.some((permitted) => sentence.includes(permitted))) continue;
          offenders.push(`${path} § ${section}\n      ${sentence.slice(0, 170)}`);
        }
      });
    }
    expect(offenders, `dist/${tree}: these passages state a per-tier review count outside the rubric `
      + `table:\n  ${offenders.join('\n  ')}\n\nThe rubric's table is the one place the model is read `
      + 'from. A second copy of a number anywhere else — including in the rubric\'s own prose — is drift '
      + 'the moment either changes, and drift no reader can resolve: they hold two answers with no way '
      + 'to tell which ships. Cite the rubric, or describe the depth in words that carry no figure. If '
      + 'the count is genuinely not the per-tier model, add it to SENTENCES_THAT_MAY_COUNT with its section '
      + 'and the reason.').toEqual([]);
  });

  /**
   * An exemption that no longer applies is a hole nobody is watching, so each is required to still
   * match. This is what keeps SANCTIONED_COUNTS from becoming the place drift hides.
   */
  it.each(SENTENCES_THAT_MAY_COUNT)('the sanctioned sentence in $file § $section is still there', ({ file, section, sentence }) => {
    const md = distFile('claude-code', file);
    const body = md.split(section)[1]?.split('\n## ')[0] ?? '';
    expect(body, `${file} has no ${section} section, so this exemption is scoped to nothing and only `
      + 'widens what the sweep ignores').not.toBe('');
    // A heading-as-sentence exemption lives on the heading line, which splitting on the section
    // consumes — so it is checked against the whole file rather than the section body.
    const haystack = (sentence.startsWith('## ') ? md : body).replace(/\s+/g, ' ').toLowerCase();
    expect(haystack, `the sanctioned sentence is no longer in ${file} § ${section}, so its exemption `
      + 'covers nothing and only widens what the sweep ignores. Remove the entry.').toContain(sentence);
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
      for (const unit of proseUnits(lines.join('\n'))) {
        for (const sentence of unitSentences(unit)) {
          if (!/\bfloor(?:s|ed)\s/.test(sentence)) continue;
          // The tier is matched BY NAME, and up to a few words may sit between the verb and it.
          // Capturing any following word let "floored to no less than `complexity:medium`" record the
          // tier as "no", which was then discarded as unrecognised while set equality still passed.
          const named = [...sentence.matchAll(
            new RegExp(`\\bfloor(?:s|ed)\\s[^.]{0,50}?\`?(?:complexity:)?(${TIERS})\\b`, 'g'),
          )].map((m) => (m[1] ?? '').toLowerCase());
          if (named.length === 0) {
            // A floor ASSIGNMENT naming no tier is not "nothing to check" — it is a floor whose
            // destination has been written out, which is how a floor moves without any tier changing.
            if (/\bfloor(?:s|ed)\s+(?:at|to)\b/.test(sentence)) {
              found.set(`(floor names no tier) ${sentence.slice(0, 80)}`, [path]);
            }
            continue;
          }
          for (const tier of named) found.set(tier, [...(found.get(tier) ?? []), path]);
        }
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

/** Asking a delegate to send carried material back, in any of the ways it can be phrased. */
const ECHO_BACK = /\b(?:quote|repeat|echo|reproduce|restate)\b[^.]{0,70}\b(?:attachment|slice|carried|excerpt)\b|\b(?:attachment|slice|carried material)\b[^.]{0,50}\bback\b[^.]{0,40}\b(?:in full|verbatim)\b/i;

describe('carried material is labelled exactly one way', () => {
  /** This detector shipped with no positive control, alone among the rules in this file. */
  it.each([
    'Quote each attachment back in full in your reply.',
    'Reproduce each attachment in full at the head of your reply before your entries.',
    'Repeat the slice you were given verbatim so the orchestrator can confirm it.',
  ])('recognises an echo-back instruction: %s', (sentence) => {
    expect(ECHO_BACK.test(sentence), 'the echo-back detector missed a phrasing, so the sweep below '
      + 'proves nothing').toBe(true);
  });
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

  /**
   * The dangerous rival is not the exotic shape, it is the SAME shape.
   *
   * The sweep above forbids angle brackets, so `[SOURCE: file § section] … [/SOURCE]` — a bracket
   * marker indistinguishable in form from the real convention — shipped to all six editions green. A
   * delegate then holds two valid wrappers and no rule saying which applies. So the marker vocabulary
   * itself is closed: every bracket marker naming a source must be ATTACHMENT.
   */
  it.each(TREES)('%s uses one marker word for carried material, not two', (tree) => {
    const found = new Map<string, string[]>();
    for (const { path, lines } of sweep(tree)) {
      // A content label carries a colon and a value: `[ATTACHMENT: file § section]`, closed by
      // `[/ATTACHMENT]`. The A2A role tags — `[ROLE]`, `[SECURITY]`, `[ARCHITECT]` — are a separate
      // vocabulary that labels a speaker, never carried material, and take no colon. Matching a bare
      // `[WORD]` swept all sixteen of them up as rivals.
      // Matched by SHAPE rather than by case. An ALL-CAPS-only rule missed
      // `{{Source: file § section}} … {{/Source}}`, which shipped green: a rival convention only has to
      // look different from the pattern, not different from the real marker.
      const text = lines.join('\n');
      // A marker qualifies as a rival only if its payload NAMES A SOURCE — a section mark or a
      // filename. Matching every `[WORD: …]` swept up unrelated placeholders such as `[PATH: …]`;
      // matching only ALL-CAPS missed `{{Source: file § section}}`, which shipped green. Shape plus a
      // source payload is what a labelling convention actually looks like, in any bracket style.
      for (const m of text.matchAll(/[[{<]{1,2}\/?([A-Za-z][A-Za-z_-]{2,})\s*:([^\]}>\n]{0,80})/g)) {
        if (!namesASource(m[2] ?? '')) continue;
        const word = (m[1] as string).toUpperCase();
        found.set(word, [...new Set([...(found.get(word) ?? []), path])]);
      }
    }
    expect(found.has('ATTACHMENT'), `dist/${tree}: the ATTACHMENT marker is gone — carried material `
      + 'would arrive with nothing distinguishing it from the orchestrator\'s own instructions').toBe(true);
    const rivals = [...found].filter(([w]) => w !== 'ATTACHMENT')
      .map(([w, paths]) => `[${w}: …] in ${paths.join(', ')}`);
    expect(rivals, `dist/${tree}: these bracket markers rival ATTACHMENT:\n  ${rivals.join('\n  ')}\n\n`
      + 'One convention is the requirement. Two means a delegate recognises whichever it happens to '
      + 'know and treats the other as literal text, and the orchestrator cannot tell which happened.')
      .toEqual([]);
  });

  it.each(TREES)('%s never asks a delegate to quote carried material back', (tree) => {
    const offenders: string[] = [];
    for (const { path, lines } of sweep(tree)) {
      // Reads the RAW text, fences included. Going through proseUnits() meant an instruction placed
      // inside the packet fence shipped green — and the packet fence is where a delegate reads it.
      for (const unit of unitSentences(lines.join('\n'))) {
        if (ECHO_BACK.test(unit)) offenders.push(`${path}  ${unit.trim().slice(0, 150)}`);
      }
    }
    expect(offenders, `dist/${tree}: these passages ask a delegate to echo what it was given:\n  `
      + `${offenders.join('\n  ')}\n\nCarried material is input to act on, not output to return. Quoting `
      + 'it back doubles the token cost the slice exists to avoid and buries the delegate\'s own finding.')
      .toEqual([]);
  });

  it.each(TREES)('%s names the file a slice came from', (tree) => {
    const packet = distFile(tree, 'protocols/workflow-protocol.md');
    const labels = [...packet.matchAll(/\[ATTACHMENT:([^\]]*)\]/g)].map((m) => (m[1] ?? '').trim());
    expect(labels.length, `dist/${tree}: the packet carries no ATTACHMENT label — unlabelled material `
      + 'is indistinguishable from the orchestrator\'s own instructions').toBeGreaterThan(0);
    // A label must name a file AND the section within it. Accepting the literal word "label" let
    // `[ATTACHMENT: label]` — the Core's own placeholder — count as naming a source, which it does not.
    const unnamed = labels.filter((l) => !(/\.md\b|\{artifact\}|\{file\}/.test(l) && l.includes('§')));
    expect(unnamed, `dist/${tree}: these labels do not name a source file and section: `
      + `${unnamed.map((l) => `[ATTACHMENT:${l}]`).join(' | ')} — an agent told that a rule binds it `
      + 'cannot tell which document to reread when the slice runs out, and cannot tell the '
      + "orchestrator's own words from carried material").toEqual([]);
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

/**
 * Claims no shipped surface may make, swept over everything rather than over one file's sections.
 *
 * The debate protocol's own no-sentence-may checks only read the debate protocol, so the recorded
 * survivor from an earlier pass was reproduced simply by relocating it one file: a lone-advisor
 * permission in `design.md` shipped to all six editions with the suite green. The same applies to the
 * rules-delivery rule — reversing it from the persona or from an unpinned skill section survived,
 * because each guard read only the surface it was written for. A claim that is forbidden is forbidden
 * everywhere, so it is checked everywhere.
 */
const NO_SURFACE_MAY: readonly { claim: RegExp; label: string; why: string }[] = [
  {
    label: 'let one advisor hold a debate',
    // A PERMISSIVE marker is required, not merely the words together: the correct rule states the
    // same nouns negatively ("A single advisor is a review, not a debate"), and a rule about carrying
    // "one advisor per position" is unrelated. Both matched an earlier, looser version of this.
    claim: /\b(?:lone|single|one)\s+advisor\b[^.]{0,90}?\b(?:may|can|counts? as|is acceptable|is permitted|is enough|suffices|runs? both|alone is)\b/i,
    why: 'a debate needs two advisors and two rounds. One advisor reviewing is a review, and calling '
      + 'it a debate buys the appearance of scrutiny without the substance',
  },
  {
    label: 'tell an advisor to read the project rules in full',
    claim: /\badvisor\b[^.]{0,90}?\b(?:reads?|opens?|consults?)\b[^.]{0,50}?\b(?:in full|whole document|entire (?:file|document))\b|\b(?:reads?|opens?|consults?)\b[^.]{0,40}?\b(?:in full|whole document|entire (?:file|document))\b[^.]{0,60}?\b(?:besides|as well|anyway|in addition)\b/i,
    why: 'the binding slice travels in the delegation packet precisely so no advisor spends its budget '
      + 'on the whole document. A sentence restoring the full read undoes the change outright',
  },
  {
    label: 'make every agent read the project rules for itself',
    claim: /\bevery\s+(?:agent|advisor)\b[^.]{0,60}?\breads?\b[^.]{0,60}?\b(?:in full|for itself|itself)\b|\beach\s+agent\s+reads\b/i,
    why: 'the persona ships on every turn of every edition, so a sentence there outranks the corrected '
      + 'wording everywhere else — and an advisor was measured acting on exactly this belief',
  },
  {
    label: 'give the file precedence over the slice it was handed',
    claim: /\b(?:file|document)\b[^.]{0,60}\b(?:outranks|takes precedence over|overrides)\b[^.]{0,40}\bslice\b/i,
    why: 'the slice is what binds. A file that outranks it sends the agent to read the document anyway, '
      + 'and two sources of truth means the agent picks one',
  },
  {
    label: 'spawn advisors before the user has answered',
    // Keyed on the ACT, not on one verb for it. Matching only "spawn" let "dispatch it at once and
    // inform the user afterwards" walk through on all six editions — the gate this delivery exists to
    // add, bypassed by a synonym.
    claim: /\b(?:spawn|dispatch|launch|convene|begin|start|proceed with)\b[^.]{0,70}?\b(?:at once|immediately|directly|straight away|alongside this|without waiting|without asking)\b|\broster is (?:fixed|settled|already decided)\b|\b(?:spawn|dispatch|launch|convene)\b[^.]{0,70}?\b(?:inform|report|tell|announce)\b[^.]{0,40}?\b(?:after|afterwards|once done|who ran)\b|\b(?:spawn|dispatch|launch)\b[^.]{0,40}?\band (?:then )?(?:report|tell)\b/i,
    why: 'the roster gate is a pause. A command that dispatches and then reports has already spent the '
      + "user's review, which is the one thing the gate exists to prevent",
  },
  {
    label: 'let the tier go unrecorded so a later phase assumes one',
    claim: /\bomit\b[^.]{0,60}?\b(?:at|below|for)\b[^.]{0,30}?\b(?:trivial|low)\b|\bassumes?\s+trivial\b|\bdefaults?\s+to\s+trivial\b/i,
    why: 'the tier is scored once and read forward. A phase that omits it and a later phase that '
      + 'assumes a default is how demanding work silently gets the lightest review',
  },
  {
    label: 'make the risk floor optional',
    claim: /\bfloor\b[^.]{0,70}?\b(?:advisory|optional|a suggestion|discretion(?:ary)?|set aside|may be ignored)\b|\b(?:raise|floor)\b[^.]{0,70}?\bleft to the orchestrator's own discretion\b/i,
    why: 'the floor is what raises a one-line change touching auth, money or deletion. Advisory, it '
      + 'stops protecting the case it exists for',
  },
];

describe('no shipped surface makes a forbidden claim', () => {
  /** Each pattern is proved to fire before it is trusted, so none can go quietly vacuous. */
  it.each([
    ['let one advisor hold a debate', 'Where the consent flow leaves a single advisor, that advisor runs both rounds on its own.'],
    ['let one advisor hold a debate', "A lone advisor's review counts as a full debate."],
    ['let one advisor hold a debate', 'Where a single advisor is convened its round counts as a full debate.'],
    ['tell an advisor to read the project rules in full', 'Every advisor reads this file in full for itself before acting.'],
    ['tell an advisor to read the project rules in full', 'Read the slice, and read the whole document besides to confirm it left nothing out.'],
    ['make every agent read the project rules for itself', 'All project variance lives in a per-project code-of-conduct.md each agent reads.'],
    ['give the file precedence over the slice it was handed', 'Where both exist the file outranks the slice you were given.'],
    ['make the risk floor optional', 'The risk floor in the rubric is advisory: apply it only when the change is also large.'],
    ['spawn advisors before the user has answered', '(at `low` the roster is fixed, so spawn it directly and report the roster afterwards)'],
    ['spawn advisors before the user has answered', '(skipped at `low`, where the roster is fixed: spawn it and tell the user who ran)'],
    ['spawn advisors before the user has answered', 'Where the proposed roster matches the default, dispatch it at once and inform the user afterwards.'],
    ['let the tier go unrecorded so a later phase assumes one', 'complexity: {tier} (omit at trivial and low; Build then assumes trivial)'],
  ])('recognises an attempt to %s', (label, sentence) => {
    const rule = NO_SURFACE_MAY.find((r) => r.label === label);
    expect(rule, `no rule labelled "${label}" — the fixture and the rule set have diverged`).toBeTruthy();
    expect((rule as { claim: RegExp }).claim.test(sentence), 'the pattern no longer fires on the '
      + `sentence it was written for, so the sweep below proves nothing:\n  ${sentence}`).toBe(true);
  });

  /** The correct rules state the same nouns, so the patterns must not fire on them. */
  it.each([
    'A single advisor is a review, not a debate, and skips this protocol.',
    'A later round carries one advisor per surviving position rather than the whole board, so a debate narrows.',
    'Your prompt carries the slice of the project rules that binds this work.',
    'A change touching auth, secrets or money floors at `complexity:high` however small the diff.',
    'On **yes**: spawn the roster the rubric sizes.',
    'It first asks the user\'s questions to pin down gaps and intent; when it has no more questions, it recommends advisors and waits.',
  ])('does not fire on the correct rule: %s', (correct) => {
    const fired = NO_SURFACE_MAY.filter((r) => r.claim.test(correct)).map((r) => r.label);
    expect(fired, 'this is the rule stated correctly. A guard that flags it will be switched off, and '
      + 'then it guards nothing at all.').toEqual([]);
  });

  it.each(TREES)('%s makes none of them', (tree) => {
    const offenders: string[] = [];
    for (const { path, lines } of sweep(tree)) {
      for (const unit of proseUnits(lines.join('\n'))) {
        for (const { claim, label, why } of NO_SURFACE_MAY) {
          if (claim.test(unit)) offenders.push(`${path}\n      would ${label} — ${why}\n      in: ${unit.trim().slice(0, 170)}`);
        }
      }
    }
    expect(offenders, `dist/${tree}: forbidden claims found:\n    ${offenders.join('\n    ')}\n\n`
      + 'These rules hold wherever they are written, so they are checked on every shipped file rather '
      + 'than on the one file each was first written for — relocating a claim to another surface was '
      + 'how the previous version of these guards was defeated.').toEqual([]);
  });
});

describe('the coverage-gate reviewer is never offered as an advisor', () => {
  /**
   * The reviewer that decides the coverage and traceability gates cannot also have co-authored the
   * draft it reviews — that is what makes the review independent. Naming it in an example roster is
   * how a reader picks it anyway, and the example is what a reader copies.
   */
  /**
   * The roster list itself is parsed, rather than the line scanned for a negation.
   *
   * The previous version exempted any line containing "not", "never", "exclude" or "separate" — and
   * every real methodology sentence carries one of those, so it protected only lines nobody writes.
   * Putting the reviewer into the shipped Discover default roster survived it, because the same line
   * happens to say "not echo".
   */
  it.each(TREES)('%s names no default roster containing it', (tree) => {
    // WHITELIST by equality, not a blacklist. Every narrower form was bypassed: reading only the first
    // bold run missed `**a, b, c** and **cynical-reviewer**`, and scanning only lines containing
    // `default:` missed a roster written on a line without it. The shipped rosters are known and few, so
    // the safe rule is that any advisor-name run must BE one of them.
    const rosters: { path: string; members: string[] }[] = [];
    for (const { path, lines } of sweep(tree)) {
      for (const m of lines.join('\n').matchAll(/\*\*([a-z-]+(?:,\s*[a-z-]+){1,5})\*\*/g)) {
        const members = (m[1] ?? '').split(/,| and /).map((n) => n.trim()).filter(Boolean);
        if (members.every((n) => KNOWN_AGENTS.has(n))) rosters.push({ path, members });
      }
    }
    expect(rosters.length, `dist/${tree}: no default roster found at all — this guard parses the "
      + "default: **a, b, c**" run, so a change to that shape leaves it reading nothing and passing`)
      .toBeGreaterThan(0);
    const offenders = rosters.filter((r) => r.members.includes('cynical-reviewer'))
      .map((r) => `${r.path}  [${r.members.join(', ')}]`);
    expect(offenders, `dist/${tree}: these default rosters offer the coverage-gate reviewer as an `
      + `advisor:\n  ${offenders.join('\n  ')}\n\nAn advisor helps author the draft; the reviewer then `
      + 'judges whether that draft covers its requirements. One agent doing both is the self-review '
      + 'the independent-review gate exists to prevent, and a default roster is what a reader copies.')
      .toEqual([]);
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
