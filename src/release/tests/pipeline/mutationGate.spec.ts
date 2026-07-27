import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  type Counts,
  type GateIo,
  evaluate,
  main,
  readThresholds,
  statusesFromReport,
  tally,
} from '../../checkMutationGate.mjs';
import { readRepoJson, repoRoot } from '../../../commons/support/repo';

/** Collect the gate's output instead of writing it to the real streams. */
function capture(): { out: string[]; err: string[]; io: GateIo } {
  const out: string[] = [];
  const err: string[] = [];
  return {
    out,
    err,
    io: { out: (line) => void out.push(line), err: (line) => void err.push(line) },
  };
}

function counts(partial: Partial<Counts>): Counts {
  return { killed: 0, survived: 0, timeout: 0, untested: 0, suspicious: 0, ...partial };
}

const thresholds = { gate: 90, warn: 95 };

describe('the mutation kill-rate gate', () => {
  it('passes cleanly when almost every mutant was caught', () => {
    // 96 killed / 4 survived = 96%, clear of both the minimum bar and the warning line.
    const c = capture();
    expect(evaluate(counts({ killed: 96, survived: 4 }), thresholds, c.io)).toBe(0);
    expect(c.out.join('\n')).toContain('OK');
    expect(c.out.join('\n')).not.toContain('WARNING');
  });

  it('reports the exact mutant tally alongside the score', () => {
    // The tally is what a contributor reads to decide whether a red gate is a real coverage
    // regression or a run that half-failed, so its numbers are part of the gate's contract.
    const c = capture();
    evaluate(counts({ killed: 96, survived: 4, timeout: 7 }), thresholds, c.io);
    expect(c.out[0]).toBe('Mutants: 107 total | 96 killed | 4 survived | 7 timeout');
    expect(c.out[1]).toBe('Kill rate: 96.0%');
  });

  it('does not warn when the score lands exactly on the warning line', () => {
    // The warning fires strictly below the line. At exactly 95% the run is fine and saying
    // otherwise would train contributors to ignore the warning.
    const c = capture();
    expect(evaluate(counts({ killed: 95, survived: 5 }), thresholds, c.io)).toBe(0);
    expect(c.out.join('\n')).not.toContain('WARNING');
  });

  it('fails when the score lands exactly on the failing line minus a fraction', () => {
    // 89.9% — the gate is a floor, so anything under it fails no matter how close.
    const c = capture();
    expect(evaluate(counts({ killed: 899, survived: 101 }), thresholds, c.io)).toBe(1);
  });

  it('passes when the score lands exactly on the failing line', () => {
    // Exactly 90% passes: the gate is "below 90 fails", not "at 90 fails".
    const c = capture();
    expect(evaluate(counts({ killed: 90, survived: 10 }), thresholds, c.io)).toBe(0);
    expect(c.out.join('\n')).toContain('OK');
  });

  it('still passes but warns when the score clears the minimum without much room', () => {
    // 92% — above the 90% gate, below the 95% warning line. The build goes green, but the thinning
    // coverage is announced before it becomes a failure.
    const c = capture();
    expect(evaluate(counts({ killed: 92, survived: 8 }), thresholds, c.io)).toBe(0);
    expect(c.out.join('\n')).toContain('WARNING');
    expect(c.out.join('\n')).toContain('OK');
  });

  it('fails the build when too many mutants survived', () => {
    const c = capture();
    expect(evaluate(counts({ killed: 80, survived: 20 }), thresholds, c.io)).toBe(1);
    expect(c.err.join('\n')).toContain('FAILED');
  });

  it('leaves timed-out mutants out of the score entirely', () => {
    // 90 killed / 10 survived = exactly 90% and passes, even though 100 mutants timed out — a
    // batch of slow mutants must not drag down a run that otherwise clears the bar.
    const c = capture();
    expect(evaluate(counts({ killed: 90, survived: 10, timeout: 100 }), thresholds, c.io)).toBe(0);
    expect(c.out.join('\n')).toContain('OK');
  });

  it('refuses to score a run that generated no mutants', () => {
    // Zero mutants means the config selected nothing, so nothing was proven. Reporting a pass here
    // would be a green gate over an empty run.
    const c = capture();
    expect(evaluate(counts({}), thresholds, c.io)).toBe(1);
    expect(c.err.join('\n')).toContain('No mutants generated');
  });

  it('refuses to score a run where every mutant only timed out', () => {
    const c = capture();
    expect(evaluate(counts({ timeout: 50 }), thresholds, c.io)).toBe(1);
    expect(c.err.join('\n')).toContain('timed out');
  });

  it('refuses to score an incomplete run', () => {
    // A crashed run leaves mutants untested; a kill rate over only the tested subset is a green
    // gate over data that never existed.
    const c = capture();
    expect(evaluate(counts({ killed: 95, survived: 5, untested: 40 }), thresholds, c.io)).toBe(1);
    expect(c.err.join('\n')).toContain('incomplete');
  });

  it('refuses to score a run with results flagged unreliable', () => {
    const c = capture();
    expect(evaluate(counts({ killed: 95, survived: 5, suspicious: 3 }), thresholds, c.io)).toBe(1);
    expect(c.err.join('\n')).toContain('incomplete');
  });
});

describe('reading Stryker results', () => {
  it('counts an uncovered mutant as survived rather than ignoring it', () => {
    // NoCoverage is a survived mutant with a more specific cause. Dropping it from the denominator
    // would flatter the score exactly where the tests are weakest.
    expect(tally(['Killed', 'NoCoverage', 'Survived'])).toEqual(
      counts({ killed: 1, survived: 2 }),
    );
  });

  it('treats an unrecognised status as unreliable rather than as a pass', () => {
    // A Stryker upgrade that renames a status must fail loudly, not silently shrink the denominator.
    expect(tally(['Killed', 'SomeFutureStatus'])).toEqual(counts({ killed: 1, suspicious: 1 }));
  });

  it('leaves explicitly ignored mutants out of the score', () => {
    expect(tally(['Killed', 'Ignored'])).toEqual(counts({ killed: 1 }));
  });

  it('maps every Stryker status onto the bucket the Python gate uses for it', () => {
    // The whole Stryker-to-mutmut vocabulary translation in one assertion. The two gates must agree
    // on what "survived" and "incomplete" mean, or the same quality bar reads as two different
    // numbers depending on which runtime failed.
    expect(
      tally([
        'Killed',
        'Survived',
        'NoCoverage',
        'Timeout',
        'Pending',
        'RuntimeError',
        'CompileError',
        'Ignored',
      ]),
    ).toEqual({ killed: 1, survived: 2, timeout: 1, untested: 1, suspicious: 2 });
  });

  it('skips mutants a report lists without a status', () => {
    const report = JSON.stringify({ files: { 'a.ts': { mutants: [{ status: 'Killed' }, {}] } } });
    expect(statusesFromReport(report)).toEqual(['Killed']);
  });

  it('reads a report whose file entry lists no mutants', () => {
    expect(statusesFromReport(JSON.stringify({ files: { 'a.ts': {} } }))).toEqual([]);
  });

  it('reads every mutant across every file in a report', () => {
    const report = JSON.stringify({
      files: {
        'a.ts': { mutants: [{ status: 'Killed' }, { status: 'Survived' }] },
        'b.ts': { mutants: [{ status: 'Killed' }] },
      },
    });
    expect(statusesFromReport(report)).toEqual(['Killed', 'Survived', 'Killed']);
  });

  it('reads an empty report without crashing', () => {
    expect(statusesFromReport('{}')).toEqual([]);
  });
});

describe('running the gate against a report on disk', () => {
  const dirs: string[] = [];

  afterEach(() => {
    while (dirs.length > 0) rmSync(dirs.pop() as string, { recursive: true, force: true });
    vi.restoreAllMocks();
  });

  function reportFile(contents: unknown): string {
    const dir = mkdtempSync(join(tmpdir(), 'hercules-gate-'));
    dirs.push(dir);
    const path = join(dir, 'mutation.json');
    writeFileSync(path, JSON.stringify(contents), 'utf-8');
    return path;
  }

  it('scores a real Stryker report using the shared thresholds', () => {
    const path = reportFile({
      files: {
        'parse.ts': { mutants: [...Array(19).fill({ status: 'Killed' }), { status: 'Survived' }] },
      },
    });
    const c = capture();
    // 19/20 = 95%, at the warning line and clear of the gate.
    expect(main(repoRoot, path, c.io)).toBe(0);
    expect(c.out.join('\n')).toContain('OK');
  });

  it('fails with an actionable message when the report is missing', () => {
    // The likeliest cause is that the mutation run never happened, so the message names the
    // command that produces the file rather than just reporting a missing path.
    const c = capture();
    expect(main(repoRoot, join(tmpdir(), 'hercules-gate-absent', 'mutation.json'), c.io)).toBe(1);
    expect(c.err.join('\n')).toContain('make mutation-ts');
  });

  it('writes passing output to stdout and failures to stderr', () => {
    // An on-call engineer greps one stream or redirects the other; a gate that mixes them makes a
    // red run indistinguishable from a noisy green one.
    const stdout = vi.spyOn(process.stdout, 'write').mockReturnValue(true);
    const stderr = vi.spyOn(process.stderr, 'write').mockReturnValue(true);

    const path = reportFile({ files: { 'a.ts': { mutants: [{ status: 'Survived' }] } } });
    expect(main(repoRoot, path)).toBe(1);

    expect(stdout.mock.calls.flat().join('')).toContain('Kill rate: 0.0%');
    expect(stderr.mock.calls.flat().join('')).toContain('FAILED');
  });
});

describe('the shared kill-rate thresholds', () => {
  it('holds this project to a 90% kill rate, warning from 95%', () => {
    // The LIVE pin on the numbers themselves. Every behavioural test above feeds `evaluate` a local
    // 90/95 literal, exercising the scoring logic at fixed, readable values — so those tests stay
    // green if the real thresholds move. This one does not: change mutation-gate.json and it fails.
    expect(readThresholds(repoRoot)).toEqual({ gate: 90, warn: 95 });
    expect(thresholds).toEqual(readThresholds(repoRoot));
  });

  it('resolves and parses the shared file rather than carrying its own copy', () => {
    // Guards readThresholds' path join and field mapping — a gate/warn swap or a wrong relative path
    // fails here. The two gates agree structurally because both read this one file.
    const shared = readRepoJson<{ gate: number; warn: number }>('src', 'release', 'mutation-gate.json');
    expect(readThresholds(repoRoot)).toEqual({ gate: shared.gate, warn: shared.warn });
  });

  it('keep the warning line above the failing line', () => {
    const { gate, warn } = readThresholds(repoRoot);
    expect(warn).toBeGreaterThan(gate);
  });
});
