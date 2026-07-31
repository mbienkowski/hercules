import { globSync } from 'node:fs';

import { describe, expect, it } from 'vitest';

import { readRepoFile, readRepoJson, repoRoot } from '../../../commons/support/repo';

// Agent roster completeness, frontmatter identity, the A2A (agent-to-agent) reply shape, stack- and
// Hercules-internal-literal bans, tool-permission and persona prose pins, roster<->settings.json sync.

function glob(pattern: string): string[] {
  return [...globSync(`dist/claude-code/${pattern}`, { cwd: repoRoot })].sort();
}

const AGENT_PATHS = glob('agents/*.md');

const ADVISOR_AGENTS = [
  // code / process
  'challenger', 'cynical-reviewer', 'lead-architect', 'security-expert',
  'senior-qa-engineer', 'backend-engineer', 'frontend-engineer', 'devops-engineer',
  'ux-ui-designer', 'source-checker', 'maintainer',
  // non-code / universal
  'business-analyst', 'copywriter', 'document-specialist', 'simplicity-advocate',
];
const DEFAULT_AGENT = 'hercules'; // the plugin's default agent / orchestrator persona — not an advisor
// The Build execution subagent — a delegated editor, not a debate advisor, so it is neither in the
// advisor roster nor subject to the advisor-only rules below.
const BUILDER_AGENT = 'builder';

const AGENT_NAME_RE = /^name:\s*(\S+)\s*$/m;

const STACK_LITERAL_PATTERNS = [
  /\bSpring\b/, /\bHibernate\b/, /\bLiquibase\b/, /\bFlyway\b/, /\bMapStruct\b/, /\bLombok\b/,
  /\bReact\b/, /\bZustand\b/, /\bRedux\b/, /\bPinia\b/, /\bJotai\b/, /\bDjango\b/, /\bRails\b/,
  /\bSQLAlchemy\b/, /\bPrisma\b/, /\bActiveRecord\b/, /@anthropic-ai/,
];

// Hercules-internal literals a reusable specialist agent must never hardcode — that knowledge
// belongs in the orchestrating command file, injected via the delegation prompt at call time.
const HERCULES_INTERNAL_PATTERNS = [
  /\/hercules:/, // command references
  /\bbuild_progress\b/, /\bcurrent_spec(?:_round)?\b/, /\bpending_specs\b/, /\bdelivered_specs\b/,
  /\bcross_check_dispositions\b/, /\bfrozen_test_files\b/, /\bfrozen_override\b/, /\bfrozen_hook\b/,
  /\bconstraints_for_later_specs\b/, /\bhand(?:off_note|ed_off_by)\b/, /\bbuild_complete\b/,
  /-spec-\d/, // *-spec-NN-* artifact filename pattern
  /workflow-protocol/, // the protocol reaches agents only via the orchestrator-injected packet
];

// The only agent allowed to reference Hercules internals: the orchestrator persona, not a delegate.
const HERCULES_LITERAL_EXEMPT = new Set(['hercules']);

function agentName(path: string): string {
  return (path.split('/').at(-1) as string).replace(/\.md$/, '');
}

const HERCULES_MD = 'dist/claude-code/agents/hercules.md';

it('all specialist agents are present', () => {
  const existing = AGENT_PATHS.map(agentName);
  const missing = ADVISOR_AGENTS.filter((n) => !existing.includes(n));
  const extra = existing.filter((n) => !ADVISOR_AGENTS.includes(n) && n !== DEFAULT_AGENT && n !== BUILDER_AGENT);
  expect(missing, `Specialist advisors missing from agents/: ${missing}`).toEqual([]);
  expect(extra, `agents/ has files that are neither an advisor, the default agent, nor the builder: ${extra}`).toEqual([]);
  expect(AGENT_PATHS).toContain(HERCULES_MD);
});

it('all agents are listed in the project documentation', () => {
  const doc = readRepoFile('dist/claude-code/CLAUDE.md');
  const missing = ADVISOR_AGENTS.filter((n) => !doc.includes(n));
  expect(missing, `Advisors not documented in CLAUDE.md: ${missing}`).toEqual([]);
});

describe.each(AGENT_PATHS.map((p) => [agentName(p), p] as const))(
  '%s.md',
  (name, path) => {
    it('declares its identity and how it replies', () => {
      const md = readRepoFile(path);
      expect(md.startsWith('---')).toBe(true);
      const m = AGENT_NAME_RE.exec(md);
      expect(m).not.toBeNull();
      expect(m?.[1]).toBe(name);
      expect(md).toContain('description:');
      expect(md).toContain('model:');
      expect(md.toLowerCase()).toContain('code-of-conduct');
      expect(md).toContain('a2a-communication-protocol.md');
      expect(md).toContain('STATUS | CONTENT | ACTION');
    });
  },
);

it('agents carry no framework assumptions', () => {
  const violations: string[] = [];
  for (const path of AGENT_PATHS) {
    const md = readRepoFile(path);
    for (const pattern of STACK_LITERAL_PATTERNS) {
      const hit = pattern.exec(md);
      if (hit) violations.push(`${agentName(path)}.md: matched ${JSON.stringify(hit[0])}`);
    }
  }
  expect(violations, `Agents contain stack literals:\n${violations.join('\n')}`).toEqual([]);
});

for (const [name, path] of AGENT_PATHS.map((p) => [agentName(p), p] as const)) {
  const run = HERCULES_LITERAL_EXEMPT.has(name) ? it.skip : it;
  run(`${name}.md stays usable outside Hercules internals`, () => {
    const md = readRepoFile(path);
    const hits = HERCULES_INTERNAL_PATTERNS.map((p) => p.exec(md)?.[0]).filter((h): h is string => h !== undefined);
    expect(hits, `${name}.md carries Hercules-internal literals ${hits}`).toEqual([]);
  });
}

it('QA never writes test code', () => {
  const qa = readRepoFile('dist/claude-code/agents/senior-qa-engineer.md');
  const toolsLine = qa.split('\n').find((ln) => ln.startsWith('tools:')) as string;
  expect(toolsLine).not.toContain('Edit');
  expect(toolsLine).not.toContain('Write');
  expect(qa).toContain('Never writes test code');
});

it('cynical-reviewer reports missing specs back to whoever called it', () => {
  const lower = readRepoFile('dist/claude-code/agents/cynical-reviewer.md').toLowerCase();
  expect(lower).toContain('spec-sync (mandatory last step)');
  expect(lower).toContain('report the disposition back to the caller');
});

it('cynical-reviewer treats inline prompt content as the spec at the Design gate', () => {
  const lower = readRepoFile('dist/claude-code/agents/cynical-reviewer.md').toLowerCase();
  expect(lower).toContain('inline');
  expect(lower).toContain('design');
  expect(lower).toContain('spec documents not provided');
  expect(lower).toContain('treat the inline content');
});

it('the hercules agent has first-run detection', () => {
  const content = readRepoFile(HERCULES_MD);
  const lower = content.toLowerCase();
  expect(lower.includes('first-run') || lower.includes('first run')).toBe(true);
  expect(content).toContain('code-of-conduct-generator');
  expect(content).toContain('config.json');
});

it('persona version read is not hardcoded', () => {
  expect(readRepoFile(HERCULES_MD)).not.toMatch(/\d+\.\d+\.\d+/);
});

it('persona reads plugin.json live', () => {
  const persona = readRepoFile(HERCULES_MD);
  expect(persona).toContain('.claude-plugin/');
  expect(persona).toContain('plugin.json');
  expect(persona).toContain('version');
});

it('persona describes its capabilities', () => {
  const persona = readRepoFile(HERCULES_MD);
  for (const phase of ['Discover', 'Design', 'Build', 'Ship']) {
    expect(persona, `hercules.md must name the ${phase} phase`).toContain(phase);
  }
  expect(persona).toContain('/hercules:workflow');
  expect(persona).toContain('/hercules:discover');
});

it('the plugin declares a default agent with the Hercules persona', () => {
  const settings = readRepoJson<{ agent?: string }>('dist', 'claude-code', 'settings.json');
  expect(settings.agent).toBeTruthy();
  const agentPath = `dist/claude-code/agents/${settings.agent}.md`;
  expect(AGENT_PATHS).toContain(agentPath);
  expect(readRepoFile(agentPath)).toContain('You are **Hercules**');
});

it('the advisor roster matches what the plugin actually ships', () => {
  const settings = readRepoJson<{ advisors?: string[] }>('dist', 'claude-code', 'settings.json');
  const manifest = settings.advisors ?? [];
  expect([...manifest].sort()).toEqual([...ADVISOR_AGENTS].sort());
});
