import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import { filesUnder } from '../../../commons/support/buildTree';
import { readFile } from '../commands/support';
import { repoRoot } from '../../../commons/support/repo';
import { section } from '../../../metrics/scalingModel.mjs';
import { TREES } from './editions';

/**
 * Readable goldens for the most contested normative text.
 *
 * These files are not documentation *about* behaviour — they **are** the behaviour. An agent reads
 * them and acts; every sentence is an instruction. Sampling such a surface does not work, and this
 * repo has three campaigns proving it: mutation passes over per-rule sentence pins lost 11, then 29 of
 * 32, then 8 of 10 and 16 of 21 to a fully green suite. No survivor edited a pinned sentence — each
 * was written where no pin was looking. A finite set of pins cannot close that, because whoever writes
 * the contradiction picks the location.
 *
 * Coverage of *every* shipped file is now the manifest's job
 * (`docsAndPlugin/shippedContentManifest.spec.ts` hashes all six editions). What these goldens add is
 * a readable failure: a diff of the actual sentence that changed, rather than a hash that moved. They
 * are kept for the files where a wrong edit is most costly and the text is worth reading in a failure
 * message — the two protocol files whole, and the reference skill at section scope, since its other
 * sections are reference material that changes for reasons carrying no behavioural weight.
 *
 * A pin says only that the text has not changed, never that it says the right thing, so a careless
 * re-bless can still ship a wrong rule. The semantic layer is what covers that: `parseScalingModel`
 * and `parseConvergence` compared against `EXPECTED_MODEL` and `EXPECTED_CONVERGENCE` in
 * `protocolFiles.spec.ts`, and the cross-surface sweeps in `crossSurfaceConsistency.spec.ts`. Both
 * layers were verified by re-blessing a golden alongside its mutation and confirming the parsers still
 * failed. See `CODE_OF_CONDUCT.md` § Golden files.
 */

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

/**
 * A section's body with its heading, ending at the next heading of the same or higher level.
 *
 * Delegates to `section()` rather than re-implementing the slice. The first version had its own copy,
 * which meant its "reject a duplicated heading" branch had no test of its own — deleting that branch
 * left the whole suite green, so a protection that reads as load-bearing was decoration. `section()`
 * is unit-tested for the missing heading, the duplicated heading, a nested `###`, a near-miss heading
 * and a section running to EOF, and it throws on all the cases this needs.
 *
 * The duplicate case is not hypothetical: appending a second `## Agent scaling` that permitted a lone
 * advisor to hold a full debate passed everything, because a first-match read never saw it.
 */
function sectionBody(md: string, heading: string): string {
  return `${heading}${section(md, heading, 'the reference skill')}`;
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
    for (const tree of TREES) {
      expect(readFile(`dist/${tree}/protocols/${file}`),
        `dist/${tree}/protocols/${file} differs from the claude-code edition — the protocols carry no `
        + 'host-specific wording, so a difference here means one edition of Hercules debates by '
        + 'different rules than another').toBe(canonical);
    }
  });

  /**
   * A section-scoped pin covers the sections it names and nothing else, so the set of sections has to
   * be closed. Otherwise a new `##` section is normative, unpinned, and indistinguishable from one
   * that was always there — the same "unpinned surface" gap that produced every survivor so far.
   */
  it('leaves no unaccounted section in the reference skill', () => {
    const skill = readFile('dist/claude-code/skills/hercules-reference/SKILL.md');
    const headings = skill.split('\n').filter((l) => /^## /.test(l));
    expect(headings.length, 'the skill lost its section structure').toBeGreaterThan(0);
    expect(new Set(headings).size, `the skill repeats a "## " heading: ${JSON.stringify(headings)} — a `
      + 'duplicate heading ships unpinned, because every section-scoped read takes the first match')
      .toBe(headings.length);
    expect(headings, 'the skill\'s section list changed. Each section here is prompt text an agent '
      + 'obeys, so a new one must be a deliberate decision: either add it to NORMATIVE_SECTIONS so it '
      + 'is pinned, or add it here having decided it carries no rule.').toEqual([
      '## Artifact root resolution',
      '## Code-of-conduct resolution',
      '## Machine-local state (`~/.hercules/`)',
      '## Agent scaling',
      '## Debate protocol',
      '## Independent review',
    ]);
  });

  it.each(TREES)('%s states the skill’s normative sections identically', (tree) => {
    const canonical = 'dist/claude-code/skills/hercules-reference/SKILL.md';
    // The only sanctioned per-edition differences are the plugin-root prefix — which some hosts
    // express as a variable and opencode omits entirely — and the agent-name namespace. Removing
    // both leaves the rules themselves, which must be identical.
    const strip = (t: string): string => t
      .replace(/\$\{[A-Za-z_]+\}\/?/g, '')
      .replace(/\bhercules:(?=[a-z])/g, '');
    const want = NORMATIVE_SECTIONS.map((h) => sectionBody(readFile(canonical), h)).join('\n');
    const got = NORMATIVE_SECTIONS
      .map((h) => sectionBody(readFile(`dist/${tree}/skills/hercules-reference/SKILL.md`), h)).join('\n');
    expect(strip(got), `dist/${tree}: the skill's normative sections differ from the claude-code `
      + 'edition beyond host naming — one edition would then scale advisors, run debates or judge '
      + 'gates by different rules than another').toBe(strip(want));
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
