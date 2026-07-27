import { globSync } from 'node:fs';

import { describe, expect, it } from 'vitest';

import { readRepoFile, readRepoJson, repoRoot } from '../../../commons/support/repo';

// Skill-directory<->canonical-list sync, per-skill frontmatter/precondition checks, stack-literal and
// bare-subcommand bans, settings.json sync. Generator prose pins: skillsCodeOfConductGenerator.spec.ts.

/** Glob under dist/claude-code/, returning paths relative to the repo root (repo.ts-compatible). */
function glob(pattern: string): string[] {
  return [...globSync(`dist/claude-code/${pattern}`, { cwd: repoRoot })].sort();
}

const SKILL_PATHS = glob('skills/*/SKILL.md');
const DOC_FILES = [...glob('commands/*.md'), ...SKILL_PATHS, ...glob('agents/*.md')];

const SKILL_LIST = [
  'code-of-conduct-generator', 'learnings', 'write-test-scenarios',
  // Reference skill: carries the operational sections that plugin-root CLAUDE.md cannot load
  // (per Claude Code plugins-reference); auto-loads during any phase. Not an active procedure.
  'hercules-reference',
];

const ACTIVE_SKILLS = new Set(['code-of-conduct-generator', 'learnings', 'write-test-scenarios']);

const SKILL_NAME_RE = /^name:\s*(\S+)\s*$/m;

const STACK_LITERAL_PATTERNS = [
  /\bSpring\b/, /\bHibernate\b/, /\bLiquibase\b/, /\bFlyway\b/, /\bMapStruct\b/, /\bLombok\b/,
  /\bReact\b/, /\bZustand\b/, /\bRedux\b/, /\bPinia\b/, /\bJotai\b/, /\bDjango\b/, /\bRails\b/,
  /\bSQLAlchemy\b/, /\bPrisma\b/, /\bActiveRecord\b/, /@anthropic-ai/,
];

const BARE_SUBCOMMAND_RE = /hercules\s+(origin-trace|sessions)\b/;

const COC_GENERATOR = 'dist/claude-code/skills/code-of-conduct-generator/SKILL.md';

function skillName(path: string): string {
  return path.split('/').slice(-2, -1)[0] as string;
}

it('shipped skill directories match the documented skill list', () => {
  const existing = SKILL_PATHS.map(skillName);
  const missing = SKILL_LIST.filter((n) => !existing.includes(n));
  const extra = existing.filter((n) => !SKILL_LIST.includes(n));
  expect(missing, `Listed skills missing from skills/: ${missing}`).toEqual([]);
  expect(extra, `skills/ contains directories not in the canonical list: ${extra}`).toEqual([]);
});

describe.each(SKILL_PATHS.map((p) => [skillName(p), p] as const))(
  '%s/SKILL.md',
  (name, path) => {
    it('explains when to use it, and (if active) declares a hard-stop condition', () => {
      const md = readRepoFile(path);
      const lower = md.toLowerCase();
      expect(md.startsWith('---')).toBe(true);
      const m = SKILL_NAME_RE.exec(md);
      expect(m).not.toBeNull();
      expect(m?.[1]).toBe(name);
      expect(md).toContain('description:');
      const descM = /^description:\s*(.+)$/m.exec(md);
      expect(descM).not.toBeNull();
      const descLower = (descM?.[1] ?? '').toLowerCase();
      const whenPhrases = ['use ', 'use in', 'use on', 'use when', 'use to'];
      expect(whenPhrases.some((t) => descLower.includes(t))).toBe(true);
      expect(lower).toContain('code-of-conduct');
      if (ACTIVE_SKILLS.has(name)) {
        expect(lower).toContain('precondition');
        expect(/\bstop\b/.test(lower)).toBe(true);
      }
    });
  },
);

it('none of the shipped skills hard-code a specific framework or library name', () => {
  const violations: string[] = [];
  for (const path of SKILL_PATHS) {
    const md = readRepoFile(path);
    for (const pattern of STACK_LITERAL_PATTERNS) {
      const hit = pattern.exec(md);
      if (hit) violations.push(`${skillName(path)}/SKILL.md: matched ${JSON.stringify(hit[0])}`);
    }
  }
  expect(violations, `Skills contain stack literals:\n${violations.join('\n')}`).toEqual([]);
});

it.each(DOC_FILES.map((p) => [p] as const))(
  '%s always shows the working (--) form of a hercules command',
  (path) => {
    const hit = BARE_SUBCOMMAND_RE.exec(readRepoFile(path));
    expect(hit, `${path} uses the bare subcommand form ${hit?.[0]}`).toBeNull();
  },
);

it('the advertised skill list matches the installed plugin configuration', () => {
  const settings = readRepoJson<{ skills?: string[] }>('dist', 'claude-code', 'settings.json');
  const manifest = settings.skills ?? [];
  expect([...manifest].sort()).toEqual([...SKILL_LIST].sort());
});

it('code-of-conduct-generator lets the user review the draft before writing it', () => {
  const md = readRepoFile(COC_GENERATOR);
  expect(md).toContain('EnterPlanMode');
  expect(md).toContain('ExitPlanMode');
});

it('looking up the project code-of-conduct works regardless of filename case', () => {
  const forbidden = ['`code-of-conduct.md` if present', 'Read `code-of-conduct.md`', 'read `code-of-conduct.md`'];
  for (const path of SKILL_PATHS) {
    const text = readRepoFile(path);
    for (const pat of forbidden) {
      expect(text, `${path}: '${pat}' is a fixed-lowercase CoC read — use 'any capitalization'`).not.toContain(pat);
    }
  }
});

it('a new code-of-conduct is created with a lowercase filename unless asked otherwise', () => {
  const skill = readRepoFile(COC_GENERATOR);
  expect(skill).not.toContain('→ `CODE_OF_CONDUCT.md`');
  expect(skill).toContain('`code-of-conduct.md`');
});

it('the learnings skill only promises to run at a phase that actually calls it', () => {
  const skill = readRepoFile('dist/claude-code/skills/learnings/SKILL.md');
  if (skill.toLowerCase().includes('ship time')) {
    expect(readRepoFile('dist/claude-code/commands/ship.md')).toContain('learnings');
  }
});
