import { describe, expect, it } from 'vitest';

import { isFile } from '../support/buildTree';
import { repoRoot } from '../support/repo';
import {
  ALL_COMMANDS,
  BAD_DATE_RE,
  BUILD,
  DESIGN,
  DISCOVER,
  ISO_DATE_RE,
  LETTER_STEP_RE,
  SHIP,
  WORKFLOW,
  pluginMarkdownFiles,
  readFile,
  readPersona,
} from './support';

// Ported from tests/commands/test_commands_contracts.py (part 1 of 2) — shared contracts:
// naming/date/format, documentation coverage, Development-principles pins.

describe('command naming, date, and documentation contracts', () => {
  it('documentation lists exactly the commands that exist', () => {
    const doc = readPersona();
    const docCommands = new Set([...doc.matchAll(/\/hercules:([a-z-]+)/g)].map((m) => m[1] as string));
    for (const name of docCommands) {
      expect(
        isFile(repoRoot, 'dist', 'claude-code', 'commands', `${name}.md`),
        `CLAUDE.md names /hercules:${name} but the command file does not exist`,
      ).toBe(true);
    }
    for (const stepFile of [DISCOVER, DESIGN, BUILD]) {
      const name = (stepFile.split('/').pop() as string).replace('.md', '');
      expect(docCommands.has(name), `${stepFile} exists but is not documented in CLAUDE.md`).toBe(true);
    }
  });

  it('step numbers in commands are never letter-suffixed', () => {
    for (const rel of ALL_COMMANDS) {
      const hits = readFile(rel).match(LETTER_STEP_RE) ?? [];
      expect(hits, `${rel} uses letter-suffixed step numbering ${JSON.stringify(hits)}`).toEqual([]);
    }
  });

  it('dates in commands are never ambiguous', () => {
    for (const rel of [DISCOVER, DESIGN, BUILD]) {
      expect(BAD_DATE_RE.test(readFile(rel)), `${rel} uses non-ISO YYYY-DD-MM`).toBe(false);
    }
    for (const rel of [DISCOVER, DESIGN]) {
      expect(ISO_DATE_RE.test(readFile(rel)), `${rel} must use YYYY-MM-DD`).toBe(true);
    }
  });

  it('each command file contains its own trigger phrase', () => {
    const triggers: Record<string, string> = {
      [DISCOVER]: '/hercules:discover',
      [DESIGN]: '/hercules:design',
      [BUILD]: '/hercules:build',
      [WORKFLOW]: '/hercules:workflow',
      [SHIP]: '/hercules:ship',
    };
    for (const [file, trigger] of Object.entries(triggers)) {
      expect(readFile(file), `${file} must contain its own trigger phrase ${trigger}`).toContain(trigger);
    }
  });

  it('every phase command points at the canonical Plan-approval trigger words', () => {
    const persona = readFile('dist/claude-code/CLAUDE.md');
    const canonical = ['approved', 'approve', 'yes', 'continue', 'proceed', 'go', 'Accept'];
    for (const word of canonical) expect(persona).toContain(word);
    for (const rel of [DISCOVER, DESIGN, BUILD, SHIP]) {
      const md = readFile(rel);
      expect(md).toContain('canonical Plan-approval trigger words');
      expect(md).toContain('persona.md § Delivery workflow');
    }
  });

  it('output file paths are dated and descriptively named', () => {
    for (const [rel, expectedSuffix] of [
      [DISCOVER, 'business-requirements.md'],
      [DESIGN, '-spec-'],
    ] as const) {
      const md = readFile(rel);
      expect(md).toContain(expectedSuffix);
      expect(md).toContain('YYYY-MM-DD');
    }
  });

  it('main commands keep the session index up to date', () => {
    for (const rel of [DISCOVER, DESIGN, BUILD]) {
      expect(readFile(rel)).toContain('INDEX.md');
    }
  });

  it('no shortcut path exists for trivial or low-tier work', () => {
    const targets = [
      ...ALL_COMMANDS,
      'dist/claude-code/CLAUDE.md',
      'dist/claude-code/skills/write-test-scenarios/SKILL.md',
      'README.md',
    ];
    for (const path of targets) {
      const text = readFile(path);
      const lower = text.toLowerCase();
      expect(text).not.toContain('session.md');
      expect(lower).not.toContain('lightweight');
      expect(lower).not.toContain('fast pass');
    }
  });

  it('only the trivial tier skips advisor review', () => {
    const lower = readFile(DISCOVER).toLowerCase();
    expect(lower).not.toContain('advisor recommendation (medium+)');
    expect(lower).toContain('trivial');
    expect(lower).toContain('runs none');
    expect(lower).toContain('reduced set');
  });

  it('advisor disagreements are resolved through a real debate', () => {
    for (const rel of [DISCOVER, DESIGN]) {
      const md = readFile(rel);
      expect(md).toContain('Advisor debate');
      expect(md).toContain('debate-consensus-protocol.md');
    }
  });

  it('docs never say specs are deleted on merge to main', () => {
    const targets = ['README.md', ...pluginMarkdownFiles()];
    for (const path of targets) {
      const lower = readFile(path).toLowerCase();
      expect(lower).not.toContain('merge to main');
      expect(lower).not.toContain('merged to main');
    }
  });

  it('README never claims a single dissent auto-escalates the tier', () => {
    const readme = readFile('README.md').toLowerCase();
    expect(readme).not.toContain('escalates the tier');
    expect(readPersona().toLowerCase()).toContain('never re-scores');
  });

  it('high-risk categories are named the same way everywhere', () => {
    const readme = readFile('README.md').toLowerCase();
    const claude = readPersona().toLowerCase();
    const canonical = ['auth', 'secrets', 'money', 'migration', 'deletion', 'production config', 'concurrency'];
    for (const token of canonical) {
      expect(claude).toContain(token);
      expect(readme).toContain(token);
    }
  });

  it('the session index columns are documented and stay in sync', () => {
    const md = readPersona();
    expect(md).toContain('Status');
    expect(md).toContain('Tier');
    const statusLine = md.split('\n').find((ln) => ln.includes('Status values')) ?? '';
    expect(statusLine).not.toBe('');
    for (const status of ['discover', 'design', 'build', 'delivered', 'abandoned']) {
      expect(statusLine).toContain(status);
    }
  });

  it('where output files get written is defined once and reused', () => {
    const claudeMd = readPersona().toLowerCase();
    expect(claudeMd).toContain('artifact root resolution');
    expect(claudeMd).toContain('default to');
    expect(claudeMd).toContain('docs/');
  });
});
