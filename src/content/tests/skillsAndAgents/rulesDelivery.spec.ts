import { readdirSync } from 'node:fs';

import { describe, expect, it } from 'vitest';

import { readFile } from '../commands/support';
import { repoRoot } from '../../../commons/support/repo';
import { TREES, type Tree } from '../workflowAndProtocols/editions';

/**
 * The project's own rules are carried to a delegate rather than fetched by it. The lead agent holds
 * the whole document because it synthesises and decides; every advisor is handed the slice that
 * binds its own work. An advisor told both "here is your slice" and "go read the file, its rules
 * override your defaults" reads the whole file — the second instruction wins — so the self-read has
 * to be conditional on no slice arriving.
 */

const LEAD = 'hercules';
const PACKET = 'dist/claude-code/protocols/workflow-protocol.md';

/**
 * Every advisor file on EVERY edition.
 *
 * Reading only `dist/claude-code/agents` left the rule reversible on the other five: a `${target:}`
 * split keeping claude-code correct and telling the `default` branch to read the code-of-conduct in
 * full shipped that reversal to opencode, cursor, copilot-cli, gemini-cli and grok-build with the suite
 * green. The manifest catches the change; it does not catch the wrong rule that ships with a re-bless.
 */
function advisorFiles(tree: Tree): { rel: string; md: string }[] {
  const dir = `${repoRoot}/dist/${tree}/agents`;
  const files = readdirSync(dir).filter((f) => /\.(?:md|agent\.md)$/.test(f) && !f.startsWith(`${LEAD}.`));
  if (files.length < 10) {
    throw new Error(`dist/${tree}/agents yielded only ${files.length} advisor files — the roster is not `
      + 'being read, and a guard over an almost-empty list reports success');
  }
  return files.map((f) => ({ rel: `dist/${tree}/agents/${f}`, md: readFile(`dist/${tree}/agents/${f}`) }));
}

/**
 * The whole paragraph that governs the project's rules — not sentence fragments of it. Splitting on
 * the full stop hid an override clause that had drifted into its own sentence, so the guard could
 * not see the very claim it exists to police.
 */
function rulesParagraphs(md: string): string[] {
  return md.split(/\n{2,}/).filter((p) => /code-of-conduct/i.test(p));
}

describe('the packet carries the rules', () => {
  it('hands the delegate its binding slice instead of naming a file to open', () => {
    const md = readFile(PACKET);
    const packet = md.slice(md.indexOf('{#packet}'), md.indexOf('{#role-expectations}'));
    expect(packet.toLowerCase(), 'a packet that names the document rather than carrying the slice '
      + 'leaves the delegate to find it, which is the step that silently fails')
      .toMatch(/binding slice/);
    expect(packet.toLowerCase(), 'the packet has to say it supersedes the self-read, or an agent '
      + 'holding both instructions obeys the one that claims to override its defaults')
      .toContain('supersed');
  });

  it('still forbids handing over a whole document', () => {
    const md = readFile(PACKET);
    const packet = md.slice(md.indexOf('{#packet}'), md.indexOf('{#role-expectations}'));
    expect(packet, 'the slice discipline artifacts already follow is what keeps an advisor inside '
      + 'the instruction range where it follows what it is given').toContain('never a whole document');
  });
});

describe('every advisor', () => {
  /**
   * The roster size is asserted, not merely floored inside the helper.
   *
   * Every check below loops `advisorFiles(tree)`, so a helper that returns nothing makes all of them
   * pass — and neutering its filter plus its own length guard did exactly that, silently. The count is
   * therefore a test in its own right rather than a precondition the helper can lose.
   */
  it.each(TREES)('%s ships the whole advisor roster', (tree) => {
    const files = advisorFiles(tree);
    expect(files.length, `dist/${tree}/agents holds ${files.length} advisor files — the plugin ships 15 `
      + 'besides the lead. A guard looping a shorter list checks proportionally less while still '
      + 'reporting success, and a guard looping an empty one checks nothing at all.').toBe(15);
    for (const { rel, md } of files) {
      expect(md.length, `${rel} is empty`).toBeGreaterThan(0);
    }
  });
  it.each(TREES)('%s is told a slice arrives, and reads the file only when one does not', (tree) => {
    const missing: string[] = [];
    const unconditional: string[] = [];
    for (const { rel: file, md } of advisorFiles(tree)) {
      // Positive: the carried slice must be stated. Asserting only the ABSENCE of a self-read
      // passes the moment the phrase is reworded, which proves nothing about what the agent is told.
      if (!/carries the slice of the project's code-of-conduct/i.test(md)) missing.push(file);
      for (const para of rulesParagraphs(md)) {
        if (/\bread the (file|project)/i.test(para)
          && !/no slice|none is supplied|not supplied|without a slice/i.test(para)) {
          unconditional.push(`${file}: ${para.trim().slice(0, 70)}`);
        }
        // The override claim must stay attached to its condition, or it reads as unconditional.
        if (/override (these|your) defaults/i.test(para)
          && !/no slice|none is supplied/i.test(para)) {
          unconditional.push(`${file}: an override claim with no slice condition beside it`);
        }
        // A fetch imperative, or any precedence claim over the slice, defeats the carry outright.
        if (/\b(open|consult|load)\b[^.]{0,40}\b(whole|entire|full)\b[^.]{0,20}file/i.test(para)
          || /\btake(s)? precedence over\b[^.]{0,30}slice/i.test(para)
          || /\bin every case\b/i.test(para)) {
          unconditional.push(`${file}: a fetch imperative or a precedence claim over the carried slice`);
        }
      }
    }
    expect(missing, `these are never told a slice is carried to them: ${missing.join(', ')}`).toEqual([]);
    expect(unconditional, `unconditional read still present:\n  ${unconditional.join('\n  ')}\n`
      + 'each reads the whole document even when a slice arrived, which is the saving this change makes')
      .toEqual([]);
  });

  it.each(TREES)('%s never claims the file it may read outranks the slice it was given', (tree) => {
    const offenders: string[] = [];
    for (const { rel: file, md } of advisorFiles(tree)) {
      for (const para of rulesParagraphs(md)) {
        if (/override (these|your) defaults/i.test(para) && !/no slice|none is supplied/i.test(para)) {
          offenders.push(file);
        }
      }
    }
    expect(offenders, `these still let the fetched file win over the carried slice: ${offenders.join(', ')}`)
      .toEqual([]);
  });

  it.each(TREES)('%s keeps naming the project rules at all', (tree) => {
    for (const { rel: file, md } of advisorFiles(tree)) {
      expect(md.toLowerCase(),
        `${file} stopped mentioning the project rules entirely — the fallback has to survive for a `
        + 'spawn that arrives outside the workflow, with no packet').toContain('code-of-conduct');
    }
  });
});

describe('the lead agent', () => {
  it('still reads the whole document, because it decides rather than advises', () => {
    const md = readFile(`dist/claude-code/agents/${LEAD}.md`);
    const paragraphs = rulesParagraphs(md);
    expect(paragraphs.length, 'the lead agent lost its full read — it synthesises the advisors and '
      + 'makes the decisions, so it is the one context that needs the complete picture')
      .toBeGreaterThan(0);
    expect(md, 'the lead agent must not be conditioned on a slice — nobody hands it one')
      .not.toMatch(/carries the slice of the project's code-of-conduct/i);
    expect(md, 'the lead agent reads the document itself').toMatch(/read the project's code-of-conduct/i);
  });
});
