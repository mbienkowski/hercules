import { readdirSync } from 'node:fs';

import { describe, expect, it } from 'vitest';

import { readFile } from '../commands/support';
import { repoRoot } from '../../../commons/support/repo';

/**
 * The project's own rules are carried to a delegate rather than fetched by it. The lead agent holds
 * the whole document because it synthesises and decides; every advisor is handed the slice that
 * binds its own work. An advisor told both "here is your slice" and "go read the file, its rules
 * override your defaults" reads the whole file — the second instruction wins — so the self-read has
 * to be conditional on no slice arriving.
 */

const AGENTS_DIR = `${repoRoot}/dist/claude-code/agents`;
const LEAD = 'hercules';
const PACKET = 'dist/claude-code/protocols/workflow-protocol.md';

function advisorFiles(): string[] {
  const all = readdirSync(AGENTS_DIR).filter((f) => f.endsWith('.md'));
  const advisors = all.filter((f) => f !== `${LEAD}.md`);
  if (advisors.length < 10) throw new Error(`only ${advisors.length} advisor files found — the roster is not being read`);
  return advisors;
}

/** Every sentence that has the agent reading the project's rules — carried slice or self-read. */
function rulesSentences(md: string): string[] {
  return md
    .split(/(?<=\.)\s+|\n/)
    .filter((s) => /code-of-conduct/i.test(s) && /\bread\b|\bcarries\b|\binfer/i.test(s));
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
  it('is told a slice arrives, and reads the file only when one does not', () => {
    const missing: string[] = [];
    const unconditional: string[] = [];
    for (const file of advisorFiles()) {
      const md = readFile(`dist/claude-code/agents/${file}`);
      // Positive: the carried slice must be stated. Asserting only the ABSENCE of a self-read
      // passes the moment the phrase is reworded, which proves nothing about what the agent is told.
      if (!/carries the slice of the project's code-of-conduct/i.test(md)) missing.push(file);
      for (const sentence of rulesSentences(md)) {
        if (/\bread the (file|project)/i.test(sentence)
          && !/no slice|none is supplied|not supplied|without a slice/i.test(sentence)) {
          unconditional.push(`${file}: ${sentence.trim().slice(0, 70)}`);
        }
      }
    }
    expect(missing, `these are never told a slice is carried to them: ${missing.join(', ')}`).toEqual([]);
    expect(unconditional, `unconditional read still present:\n  ${unconditional.join('\n  ')}\n`
      + 'each reads the whole document even when a slice arrived, which is the saving this change makes')
      .toEqual([]);
  });

  it('never claims the file it may read outranks the slice it was given', () => {
    const offenders: string[] = [];
    for (const file of advisorFiles()) {
      for (const sentence of rulesSentences(readFile(`dist/claude-code/agents/${file}`))) {
        if (/override (these|your) defaults/i.test(sentence) && !/no slice|none is supplied/i.test(sentence)) {
          offenders.push(file);
        }
      }
    }
    expect(offenders, `these still let the fetched file win over the carried slice: ${offenders.join(', ')}`)
      .toEqual([]);
  });

  it('keeps naming the project rules at all', () => {
    for (const file of advisorFiles()) {
      expect(readFile(`dist/claude-code/agents/${file}`).toLowerCase(),
        `${file} stopped mentioning the project rules entirely — the fallback has to survive for a `
        + 'spawn that arrives outside the workflow, with no packet').toContain('code-of-conduct');
    }
  });
});

describe('the lead agent', () => {
  it('still reads the whole document, because it decides rather than advises', () => {
    const md = readFile(`dist/claude-code/agents/${LEAD}.md`);
    const sentences = rulesSentences(md);
    expect(sentences.length, 'the lead agent lost its full read — it synthesises the advisors and '
      + 'makes the decisions, so it is the one context that needs the complete picture')
      .toBeGreaterThan(0);
    expect(md, 'the lead agent must not be conditioned on a slice — nobody hands it one')
      .not.toMatch(/carries the slice of the project's code-of-conduct/i);
    expect(md, 'the lead agent reads the document itself').toMatch(/read the project's code-of-conduct/i);
  });
});
