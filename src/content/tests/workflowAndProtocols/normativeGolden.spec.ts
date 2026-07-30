import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import { filesUnder } from '../../../commons/support/buildTree';
import { readFile } from '../commands/support';
import { repoRoot } from '../../../commons/support/repo';

/**
 * The normative protocol files, pinned byte-for-byte.
 *
 * These two files are not documentation *about* behaviour — they **are** the behaviour. An agent
 * reads them and acts; every sentence is an instruction. That makes their content an unbounded
 * assertion surface, and this repo has now proved twice that sampling it cannot work: a review pass
 * over per-rule sentence pins ran 32 semantic mutations and 29 survived a green suite. The survivors
 * were never edits to a pinned sentence — they were a contradiction planted in a section that owned
 * no pin, a rubric row *added* beside the real one, a rule moved into a table cell, a whole section
 * deleted. No finite set of pins closes that, because the attacker chooses where to write.
 *
 * A byte pin closes it by construction. Anything at all — an addition, a deletion, a move, a
 * qualifier, a reordered table — fails here and has to be re-baselined deliberately.
 *
 * The cost is a required re-baseline on every intentional edit, which is the point: these files
 * change the behaviour of every future delivery, so an edit to them should be a decision, not a
 * side effect. `core.golden` already buys the same trade for the injected Core
 * (`CODE_OF_CONDUCT.md` § Golden files).
 *
 * A byte pin alone would be blind in one direction: it says the file has not changed, never that it
 * says the right thing, so a careless re-baseline could ship a wrong model quietly. That is why the
 * semantic layer stays — `parseScalingModel` and `parseConvergence` in `protocolFiles.spec.ts`
 * compare the parsed rules against `EXPECTED_MODEL` and `EXPECTED_CONVERGENCE`. Together: the golden
 * makes every change visible, the parsers make a wrong change fail.
 */

const ALL_TREES = ['claude-code', 'opencode', 'cursor', 'copilot-cli', 'gemini-cli', 'grok-build'] as const;

/** Each normative file and the golden that pins it. */
const PINNED = [
  { file: 'debate-consensus-protocol.md', golden: 'debate-consensus-protocol.golden' },
  { file: 'workflow-protocol.md', golden: 'workflow-protocol.golden' },
] as const;

/**
 * The reference skill's normative sections, pinned at section scope rather than whole-file.
 *
 * The skill is auto-loaded on every turn and these three sections are pure behaviour — how advisors
 * are scaled, when the user is asked, how a debate runs, who may judge a gate. Its other sections
 * (artifact roots, state file layout) are reference material that changes for unrelated reasons, so a
 * whole-file pin here would demand a re-bless for edits that carry no behavioural weight.
 *
 * Section scope was chosen after a lone-advisor-debate permission planted in § Agent scaling survived
 * the whole suite: the file was normative and owned no pin, which is the same gap that let a review
 * pass land 29 survivors against the protocol files.
 */
const NORMATIVE_SECTIONS = ['## Agent scaling', '## Debate protocol', '## Independent review'] as const;

/** A section's body, ending at the next heading of the same or higher level. Throws when absent. */
function sectionBody(md: string, heading: string): string {
  const at = md.indexOf(`\n${heading}\n`);
  if (at < 0) throw new Error(`the reference skill has no "${heading}" section — it was renamed or `
    + 'removed, and a renamed normative section is one this pin stops covering');
  const rest = md.slice(at + heading.length + 2);
  const end = rest.search(/\n#{1,2} /);
  return `${heading}\n${end < 0 ? rest : rest.slice(0, end)}`;
}

describe('the normative protocol files are pinned byte-for-byte', () => {
  it.each(PINNED)('$file matches its golden', ({ file, golden }) => {
    const shipped = readFile(`dist/claude-code/protocols/${file}`);
    const want = readFile(`src/content/tests/${golden}`);
    expect(shipped, `${file} differs from src/content/tests/${golden}.\n\n`
      + 'Every line of this file is an instruction an agent follows, so any change to it changes how '
      + 'future deliveries behave. If the change is intended, re-baseline the golden in the same '
      + 'commit and say in the message what behaviour changed. If it is not, this is the regression '
      + 'the pin exists to catch — a contradicting sentence, an added table row, or a deleted rule.')
      .toBe(want);
  });

  /**
   * The pin above guards one tree. Six ship, and a divergence between them is a defect the
   * requirements name outright — so the pin is extended to the other five by identity rather than by
   * five more goldens, which would drift apart from each other.
   */
  it.each(PINNED)('$file is identical on every edition', ({ file }) => {
    const canonical = readFile(`dist/claude-code/protocols/${file}`);
    for (const tree of ALL_TREES) {
      expect(readFile(`dist/${tree}/protocols/${file}`),
        `dist/${tree}/protocols/${file} differs from the claude-code edition — the protocols carry no `
        + 'host-specific wording, so a difference here means one edition of Hercules debates by '
        + 'different rules than another').toBe(canonical);
    }
  });

  it('pins the reference skill’s normative sections', () => {
    const skill = readFile('dist/claude-code/skills/hercules-reference/SKILL.md');
    const shipped = NORMATIVE_SECTIONS.map((h) => sectionBody(skill, h)).join('\n');
    expect(shipped, 'the reference skill\'s normative sections differ from '
      + 'src/content/tests/hercules-reference-normative.golden.\n\nThese sections tell an orchestrator '
      + 'how many advisors to convene, when to ask the user, how a debate runs and who may judge a '
      + 'gate — an agent reads them and acts. If the change is intended, re-baseline the golden in the '
      + 'same commit and say what behaviour changed. If it is not, this is a rule altered, contradicted '
      + 'or removed without a test noticing.')
      .toBe(readFile('src/content/tests/hercules-reference-normative.golden'));
  });

  it('pins every protocol that ships, so a new one cannot arrive unguarded', () => {
    const shipped = readFile('dist/claude-code/protocols/a2a-communication-protocol.md');
    expect(shipped.length, 'the A2A protocol must exist — its Core is pinned separately by core.golden')
      .toBeGreaterThan(0);
    // The A2A file carries host-substituted prose outside its Core, so it is pinned at Core scope by
    // core.golden rather than whole-file. Any *third* protocol file would be normative and unpinned.
    const known = new Set<string>(['a2a-communication-protocol.md', ...PINNED.map((p) => p.file)]);
    const actual = Object.keys(filesUnder(join(repoRoot, 'dist', 'claude-code', 'protocols')));
    expect(actual.length, 'the protocols directory read empty — a guard that opens nothing passes '
      + 'silently, which is the failure mode this whole spec exists to remove').toBeGreaterThan(0);
    const unpinned = actual.filter((f) => !known.has(f));
    expect(unpinned, `these protocol files ship with no golden pin: ${unpinned.join(', ')} — a `
      + 'normative file an agent obeys must be pinned, or it is the one place a rule can be changed '
      + 'without a test noticing').toEqual([]);
  });
});
