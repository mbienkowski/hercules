import { readdirSync } from 'node:fs';
import { join } from 'node:path';

import { expect, it } from 'vitest';

import { BUILD, DESIGN, DISCOVER, readFile, readPersona, SHIP, WORKFLOW } from '../commands/support';
import { readRepoFile, repoRoot } from '../../../commons/support/repo';

/**
 * The workflow's phase/mode orchestration is explicit and human-first. Static gates only: Claude
 * Code's permission-mode state is not inspectable from the plugin, so these assert the directives
 * the commands carry; the effect is the manual smoke documented in CODE_OF_CONDUCT.md.
 */

const CLAUDE_MD = 'dist/claude-code/CLAUDE.md';

it('the workflow command opens and closes plan mode at each phase', () => {
  const md = readFile(WORKFLOW);
  expect(md, 'workflow must call EnterPlanMode to open each plan-mode phase').toContain('EnterPlanMode');
  expect(md, 'workflow must call ExitPlanMode at the approval gate').toContain('ExitPlanMode');
});

it('every phase requires plan mode and blocks writes until approved', () => {
  for (const f of [DISCOVER, DESIGN, BUILD, WORKFLOW, SHIP]) {
    const lower = readFile(f).toLowerCase();
    expect(lower, `${f} must require plan mode`).toContain('plan mode');
    expect(lower, `${f} must gate writes/execution on approval`).toContain('approv');
  }
});

it('build presents a delivery plan before writing any code', () => {
  const lower = readFile(BUILD).toLowerCase();
  expect(lower, 'build must OPEN in plan mode like every other phase').toContain('**plan mode — required');
  expect(lower).toContain('enterplanmode');
  expect(lower).toContain('exitplanmode');
  expect(lower, "build's plan mode must present a delivery plan for approval").toContain('delivery plan');
  expect(
    lower.includes('implement') || lower.includes('write the minimum code'),
    'build must still implement after Plan approval',
  ).toBe(true);
});

it('the workflow walks through phases in a fixed order with a gate between each', () => {
  const md = readFile(WORKFLOW);
  const heads = ([[1, 'Discover'], [2, 'Design'], [3, 'Build'], [4, 'Ship']] as const)
    .map(([n, name]) => md.indexOf(`## Phase ${n} — ${name}`));
  expect(heads, 'the four phase sections must appear in workflow order').toEqual([...heads].sort((a, b) => a - b));
  const lower = md.toLowerCase();
  for (const gate of ['move to design', 'move to build', 'move to ship']) {
    expect(lower, `workflow must gate each transition on the user (${gate})`).toContain(gate);
  }
  expect(lower.indexOf('move to design') < lower.indexOf('move to build')
    && lower.indexOf('move to build') < lower.indexOf('move to ship'),
  'the transition gates must appear in phase order').toBe(true);
});

it('advisors are never brought in without the user being told', () => {
  const surface = readPersona();
  expect(surface, 'the loaded instruction surface must keep the human-first consent rule')
    .toContain('never spawns advisors silently');
});

it('project complexity is judged once and reused by later phases', () => {
  const discover = readFile(DISCOVER).toLowerCase();
  expect(discover, 'discover must classify complexity').toContain('complexity');
  expect(discover, 'discover must ask the user to confirm the classification').toContain('confirm or override');
  for (const f of [DESIGN, BUILD]) {
    const lower = readFile(f).toLowerCase();
    expect(lower.includes('tier') && lower.includes('state'), `${f} must read the tier from state`).toBe(true);
    expect(lower, `${f} must NOT re-classify complexity`).not.toContain('confirm or override');
  }
});

it('ship drafts a commit plan and waits for approval', () => {
  const md = readFile(SHIP);
  expect(md, 'ship must call EnterPlanMode to draft its commit plan').toContain('EnterPlanMode');
  expect(md.toLowerCase(), 'ship must gate execution on user approval of the commit plan').toContain('approved');
});

it('leaving plan mode always switches to auto mode, never accept-edits', () => {
  const files = [DISCOVER, DESIGN, BUILD, SHIP, WORKFLOW, 'dist/claude-code/skills/code-of-conduct-generator/SKILL.md'];
  for (const f of files) {
    const text = readFile(f);
    expect(/ExitPlanMode`?\s*\(`auto`\)/.test(text), `${f} must call ExitPlanMode with the literal (\`auto\`) mode argument`).toBe(true);
    expect(text.toLowerCase(), `${f} must not use accept-edits`).not.toContain('accept-edits');
  }
});

it('design checks the plan is sound before asking for approval', () => {
  const lower = readFile(DESIGN).toLowerCase();
  const i7 = lower.indexOf('## step 7');
  const i8 = lower.indexOf('## step 8 — plan approval');
  const i9 = lower.indexOf('## step 9');
  expect(i7 < i8 && i8 < i9, 'design order must be validation gates (Step 7) → Plan approval (Step 8) → write specs (Step 9)').toBe(true);
  const ic = lower.indexOf('implementability check');
  expect(i7 < ic && ic < i8, 'the implementability check must sit in the Step 7 validation gates, before Plan approval').toBe(true);
});

it('discover does not save the complexity tier before the session exists', () => {
  const md = readFile(DISCOVER);
  const step3 = md.slice(md.indexOf('## Step 3'), md.indexOf('## Step 4'));
  expect(step3, 'Step 3 must not write the state file — plan mode is active and no session slug exists yet')
    .not.toContain('~/.hercules/state');
  const step7 = md.slice(md.indexOf('## Step 7'));
  expect(step7.includes('tier') && step7.includes('~/.hercules/'), "Step 7's session-init write must persist the Step 3 tier").toBe(true);
});

it('finishing a build tells the user to review before shipping, not ship automatically', () => {
  const md = readFile(BUILD);
  const closeout = md.slice(md.toLowerCase().indexOf('## close-out'));
  expect(/Then run `\/hercules:ship`/.test(closeout), 'close-out must point to Ship, never invoke it — the user reviews the diff first').toBe(false);
  expect(closeout, 'close-out must still point forward to Ship').toContain('/hercules:ship');
  const closeoutLower = closeout.toLowerCase();
  expect(closeoutLower.includes('review') && closeoutLower.includes('ready'), 'close-out must hand the user the review-then-ship decision').toBe(true);
});

it('every project status shown to users is actually set by some command', () => {
  const dir = join(repoRoot, 'dist', 'claude-code', 'commands');
  const commands = readdirSync(dir).filter((n) => n.endsWith('.md')).map((n) => readRepoFile('dist', 'claude-code', 'commands', n));
  for (const status of ['discover', 'design', 'build', 'delivered']) {
    const found = commands.some((text) => text.split('\n\n').some((para) => para.includes('INDEX.md') && para.includes(`\`${status}\``)));
    expect(found, `no command writes INDEX status \`${status}\` — CLAUDE.md documents it as a live value`).toBe(true);
  }
});

it('the workflow never promises a later lock that contradicts the real lock point', () => {
  const wf = readFile(WORKFLOW);
  expect(/once (?:we|you) move to \w+, the (?:requirements|specs) are locked/.test(wf),
    'workflow.md must not promise a later lock — artifacts lock at their phase\'s save').toBe(false);
  expect(/fresh Discover pass|through `\/hercules:design`/.test(wf),
    'workflow.md must state the sanctioned change path after a phase\'s save').toBe(true);
});

it('the orchestrator falls back to a safe documented action when something breaks', () => {
  const md = readFile(CLAUDE_MD);
  expect(md.includes('fall back to the safest action') && md.includes('never improvise'),
    'CLAUDE.md must carry the protocol-aligned fallback rule').toBe(true);
});

it('the workflow advances to the next phase automatically instead of asking the user to type a command', () => {
  const md = readFile(WORKFLOW);
  expect(md.includes('reading its file') || md.includes('read its file'),
    'workflow must say phases continue by reading the command file inline').toBe(true);
  expect(md, '…and locate the phase files generically (beside this file), not via a path variable').toContain('same directory as this file');
  expect(md.includes('${CLAUDE_PLUGIN_ROOT}') || md.includes('${CLAUDE_SKILL_DIR}'),
    'the guided flow must not depend on a path variable substituting').toBe(false);
  expect(md, 'the guided flow must not push invocation back onto the user').toContain('never ask the user to type');
});
