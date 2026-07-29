import { describe, expect, it } from 'vitest';

import { BUILD, DESIGN, DISCOVER, readFile } from '../commands/support';
import { readRepoFile } from '../../../commons/support/repo';

/**
 * Two decisions are taken on the user's behalf before any advisor runs — how demanding the work was
 * judged, and who will review it — so both are shown with the choices open to them. Both are stated
 * as choices rather than as a widget: only some editions offer a native selection control, and an
 * edition without one shows the identical choices as a plain numbered list.
 */

const ALL_TREES = ['claude-code', 'opencode', 'cursor', 'copilot-cli', 'gemini-cli', 'grok-build'] as const;
const RUBRIC = 'dist/claude-code/protocols/debate-consensus-protocol.md';
const REFERENCE = 'dist/claude-code/skills/hercules-reference/SKILL.md';
const WORKFLOW_PROTOCOL = 'dist/claude-code/protocols/workflow-protocol.md';

/** Editions name and wrap the same command differently, so a path is resolved, never assumed. */
const DISCOVER_PER_TREE: Record<string, string> = {
  'claude-code': 'commands/discover.md',
  opencode: 'commands/discover.md',
  cursor: 'commands/discover.md',
  'grok-build': 'commands/discover.md',
  'copilot-cli': 'commands/discover.prompt.md',
  'gemini-cli': 'commands/discover.toml',
};

/** The consent block only — a claim satisfied by prose elsewhere in the skill proves nothing. */
function consentSection(): string {
  const md = readFile(REFERENCE);
  const start = md.indexOf('### Sub-agent consent');
  if (start < 0) throw new Error('no "### Sub-agent consent" heading — the roster gate lost its home');
  const rest = md.slice(start + 1);
  const end = rest.search(/\n#{2,3} /);
  return end < 0 ? rest : rest.slice(0, end);
}

describe('gate 1 — how demanding the work is', () => {
  it('offers keep, lower, raise and a free answer', () => {
    const lower = readFile(DISCOVER).toLowerCase();
    for (const choice of ['keep it', 'lower it', 'raise it']) {
      expect(lower, `the judgement gate must offer "${choice}" — a score shown without its choices `
        + 'is a notification, not a decision').toContain(choice);
    }
    expect(lower, 'the user must be able to answer outside the offered choices').toContain('answer freely');
  });

  it('is shown at every level, trivial included', () => {
    const lower = readFile(DISCOVER).toLowerCase();
    expect(lower, 'skipping the gate on simple work is the optimisation that makes it invisible')
      .toMatch(/at every level\W{0,6}trivial included/);
    expect(lower, 'a qualifier after "at every level" turns the universal gate into a conditional one '
      + 'while keeping the words that promise it is universal')
      .not.toMatch(/at every level\s+(above|from|for|except)/);
  });

  it('keeps its confirm-or-override wording in Discover and nowhere else', () => {
    expect(readFile(DISCOVER), 'the tier is confirmed where it is scored').toContain('confirm or override');
    for (const cmd of [DESIGN, BUILD]) {
      expect(readFile(cmd), `${cmd} reads the tier forward — offering to override it here would re-open `
        + 'a settled decision').not.toContain('confirm or override');
    }
  });

  it('cites the rubric rather than restating any of its numbers', () => {
    expect(readFile(DISCOVER), 'the tier is scored from one table, so the command points at it')
      .toContain('debate-consensus-protocol.md');
  });
});

describe('gate 2 — who reviews', () => {
  it('lets the user accept, remove or add advisors', () => {
    const consent = consentSection().toLowerCase();
    expect(consent, 'a roster shown without per-advisor control is a yes/no prompt, not a decision')
      .toMatch(/accept, remove or add per advisor/);
  });

  it('does not appear where no advisor is convened', () => {
    const lower = readFile(REFERENCE).toLowerCase();
    expect(lower, 'a roster prompt at trivial shows an empty list and asks nothing')
      .toMatch(/no roster gate\*{0,2}\s+at\s+`?trivial/);
    expect(lower, '"no roster gate exemption" keeps the pinned words and reverses the rule')
      .not.toContain('no roster gate exemption');
  });

  it('never spawns an advisor before the user has answered', () => {
    const consent = consentSection().toLowerCase();
    expect(consent, 'the rule has to sit in the consent block, not merely somewhere in the file')
      .toContain('never spawns advisors silently');
    expect(consent, 'the wait is the rule — announcing a roster and proceeding satisfies the phrase '
      + 'while defeating the gate').toMatch(/recommends advisors and waits/);
    for (const inversion of ['spawns it immediately', 'without waiting', 'then proceeds']) {
      expect(consent, `"${inversion}" keeps the pinned phrase and removes the wait`)
        .not.toContain(inversion);
    }
  });

  it('states the tier count at runtime rather than pinning numbers into the skill', () => {
    const skill = readFile(REFERENCE);
    const rows = skill.split('\n').filter((l) => /^\|\s*(trivial|low|medium|high|critical)\s*\|/.test(l));
    expect(rows, 'the skill must carry no per-tier table — the rubric owns those numbers, and a second '
      + 'copy here is the drift this change exists to remove').toEqual([]);
  });

  it('routes a user-initiated raise to the state write, and only a user-initiated one', () => {
    const consent = consentSection().toLowerCase();
    expect(consent, 'a tier raised at the roster gate that never reaches state leaves Design and Build '
      + 'reading the superseded value').toContain('reaches the state write');
    expect(consent, 'the restriction has to sit with the permission, or the permission stands alone')
      .toMatch(/only the user\*{0,2}[^.]*never re-judges/);
    for (const verb of ['re-score the tier here', 'raise it yourself']) {
      expect(consent, `"${verb}" is the automatic re-judging G7 forbids and the requirement puts out of scope`)
        .not.toContain(verb);
    }
  });
});

describe('a raised tier reaches the state write', () => {
  it.each(ALL_TREES)('%s writes the tier the user last set, not the one first scored', (tree) => {
    const rel = DISCOVER_PER_TREE[tree];
    expect(rel, `no Discover path known for ${tree}`).toBeTruthy();
    const lower = readFile(`dist/${tree}/${rel}`).toLowerCase();
    expect(lower, `dist/${tree}: the write must take the user's latest tier, or a raise made at the `
      + 'roster gate is silently discarded and Design and Build read the superseded value')
      .toMatch(/as the user last\s+set them/);
    expect(lower, `dist/${tree}: "from step 3" pins the write to the first judgement and drops a `
      + 'later raise').not.toContain('from step 3');
  });
});

describe('both gates, on every edition', () => {
  it('offers the same choices where no native selection control exists', () => {
    for (const tree of ALL_TREES) {
      const md = readFile(`dist/${tree}/skills/hercules-reference/SKILL.md`);
      expect(md, `${tree}: the fallback must carry the same choices, not a reduced yes/skip prompt`)
        .toMatch(/identical choices as a plain numbered list/);
    }
    for (const tree of ALL_TREES) {
      const rel = DISCOVER_PER_TREE[tree];
      expect(rel, `no Discover path known for ${tree} — a guard that opens nothing passes silently`).toBeTruthy();
      const lower = readFile(`dist/${tree}/${rel}`).toLowerCase();
      for (const choice of ['keep it', 'lower it', 'raise it', 'answer freely']) {
        expect(lower, `${tree}: the judgement gate lost "${choice}" — the editions stop agreeing`)
          .toContain(choice);
      }
    }
  });

  it('describes the control generically, so no edition is told to use one it lacks', () => {
    const wording = ALL_TREES.map((t) => {
      const md = readFile(`dist/${t}/skills/hercules-reference/SKILL.md`);
      return /native selection control[^.]*/.exec(md)?.[0] ?? '';
    });
    expect(wording.filter((w) => w === ''), 'an edition with no such wording gets no fallback rule')
      .toEqual([]);
    expect(new Set(wording).size, 'the editions must describe the control identically, or their '
      + `behaviour diverges: ${JSON.stringify(wording)}`).toBe(1);
  });
});

describe('the roster gate in the step order', () => {
  it('appears in the Discover and Design phase lines, not only in the registry', () => {
    const md = readFile(WORKFLOW_PROTOCOL);
    const discover = md.slice(md.indexOf('{#phase-discover}'), md.indexOf('{#phase-design}'));
    const design = md.slice(md.indexOf('{#phase-design}'), md.indexOf('{#phase-build}'));
    for (const [name, section] of [['Discover', discover], ['Design', design]] as const) {
      expect(section.toLowerCase(), `${name}'s step line omits the roster gate — a gate absent from `
        + 'the ordered steps is a gate a resuming agent can skip').toContain('roster');
    }
  });

  it('carries a guardrail row for the gate', () => {
    const md = readFile(WORKFLOW_PROTOCOL);
    const registry = md.slice(md.indexOf('{#registry}'), md.indexOf('{#packet}'));
    const row = registry.split('\n').find((l) => l.startsWith('| G8 |'));
    expect(row, 'no G8 row — the delegation packet copies registry rows verbatim, so without one no '
      + 'delegate is ever told the gate exists').toBeTruthy();
    expect((row as string).toLowerCase(), 'the G8 row must carry the no-spawn rule itself')
      .toContain('no advisor spawns before the user accepts the roster');
  });

  it('shows both gates in the detailed diagram', () => {
    const html = readRepoFile('docs', 'workflow', 'workflow-diagram-detailed.html');
    expect((html.match(/Roster gate/g) ?? []).length,
      'the Discover and Design lanes each need the roster gate — the diagram is one of the surfaces '
      + 'the requirement says must agree').toBe(2);
    expect(html, 'the diagram must show the judgement gate offers choices, not just a confirmation')
      .toMatch(/keep, lower, raise/);
  });
});

it('the rubric a gate cites actually carries the tiers it is cited for', () => {
  const md = readFile(RUBRIC);
  for (const tier of ['trivial', 'low', 'medium', 'high', 'critical']) {
    expect(md, `the rubric is missing ${tier} — a command citing it would send the agent nowhere`)
      .toContain(`complexity:${tier}`);
  }
});
