/**
 * Mutation kill-rate gate for TypeScript (Stryker), symmetric with the Python gate
 * (src/release/check_mutation_gate.py, mutmut over src/hooks/): same thresholds
 * (src/release/mutation-gate.json), same failure modes, same wording.
 *
 * Usage: node .ts-out/bin/mutationGate.mjs
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';

/** Thresholds, single-sourced with the Python gate. */
export interface Thresholds {
  gate: number;
  warn: number;
}

/**
 * Mutant tallies, normalised from Stryker's report into the five buckets the Python gate counts.
 * `NoCoverage` folds into `survived` — counting an uncovered mutant any other way flatters the score.
 */
export interface Counts {
  killed: number;
  survived: number;
  timeout: number;
  /** Stryker `Pending` — a run that never finished. */
  untested: number;
  /** Stryker `RuntimeError` / `CompileError` — a result that is not a clean kill or survive. */
  suspicious: number;
}

export interface GateIo {
  out: (line: string) => void;
  err: (line: string) => void;
}

const DEFAULT_IO: GateIo = {
  out: (line) => process.stdout.write(`${line}\n`),
  err: (line) => process.stderr.write(`${line}\n`),
};

export function readThresholds(repoRoot: string): Thresholds {
  const raw = JSON.parse(readFileSync(join(repoRoot, 'src', 'release', 'mutation-gate.json'), 'utf-8')) as {
    gate: number;
    warn: number;
  };
  return { gate: raw.gate, warn: raw.warn };
}

/** Map Stryker's per-mutant statuses onto the Python gate's five buckets. */
export function tally(statuses: readonly string[]): Counts {
  const counts: Counts = { killed: 0, survived: 0, timeout: 0, untested: 0, suspicious: 0 };
  for (const status of statuses) {
    switch (status) {
      case 'Killed':
        counts.killed += 1;
        break;
      // An uncovered mutant survived; it just survived for a more specific reason.
      case 'Survived':
      case 'NoCoverage':
        counts.survived += 1;
        break;
      case 'Timeout':
        counts.timeout += 1;
        break;
      case 'Pending':
        counts.untested += 1;
        break;
      // `Ignored` is an explicit, reviewed exclusion — it is not evidence either way and is
      // deliberately not counted, matching mutmut's treatment of skipped mutants.
      case 'Ignored':
        break;
      default:
        // Everything else is suspicious: Stryker's error statuses (`RuntimeError`, `CompileError`)
        // and any status a future Stryker introduces, deliberately not listed as explicit cases
        // (that would produce equivalent mutants). A result that is not a clean kill, survive,
        // timeout or reviewed exclusion fails the gate rather than vanishing from the denominator.
        counts.suspicious += 1;
    }
  }
  return counts;
}

/** Read every mutant status out of a Stryker JSON report. */
export function statusesFromReport(reportJson: string): string[] {
  const report = JSON.parse(reportJson) as {
    files?: Record<string, { mutants?: Array<{ status?: string }> }>;
  };
  const statuses: string[] = [];
  for (const file of Object.values(report.files ?? {})) {
    for (const mutant of file.mutants ?? []) {
      if (mutant.status !== undefined) statuses.push(mutant.status);
    }
  }
  return statuses;
}

/**
 * Evaluate the gate; returns a process exit code. Failure modes match the Python gate's order and
 * meaning: incomplete run (a score over data that never existed), zero mutants (nothing proven),
 * all-timeout (no signal either way), below warn (pass, but say so), below gate (fail).
 */
export function evaluate(counts: Counts, thresholds: Thresholds, io: GateIo = DEFAULT_IO): number {
  const { killed, survived, timeout, untested, suspicious } = counts;
  const total = killed + survived + timeout;

  if (untested > 0 || suspicious > 0) {
    io.err(`ERROR: run incomplete — ${untested} untested, ${suspicious} suspicious mutants`);
    return 1;
  }

  if (total === 0) {
    io.err('ERROR: No mutants generated — check the stryker.conf.json mutate globs');
    return 1;
  }

  const denominator = killed + survived;
  if (denominator === 0) {
    io.err('ERROR: All mutants timed out — runner timeout too short');
    return 1;
  }

  const killRate = (killed / denominator) * 100;
  io.out(`Mutants: ${total} total | ${killed} killed | ${survived} survived | ${timeout} timeout`);
  io.out(`Kill rate: ${killRate.toFixed(1)}%`);

  if (killRate < thresholds.warn) {
    io.out(`WARNING: kill rate ${killRate.toFixed(1)}% below warn threshold (${thresholds.warn}%)`);
  }
  if (killRate < thresholds.gate) {
    io.err(`FAILED: kill rate ${killRate.toFixed(1)}% below gate (${thresholds.gate}%)`);
    return 1;
  }

  io.out('OK');
  return 0;
}

export function main(repoRoot: string, reportPath: string, io: GateIo = DEFAULT_IO): number {
  let reportJson: string;
  try {
    reportJson = readFileSync(reportPath, 'utf-8');
  } catch {
    io.err(`ERROR: no Stryker report at ${reportPath} — did \`make mutation-ts\` run?`);
    return 1;
  }
  return evaluate(tally(statusesFromReport(reportJson)), readThresholds(repoRoot), io);
}

/** Default location of Stryker's JSON report, relative to the repo root. */
export const REPORT_PATH = ['reports', 'mutation', 'mutation.json'] as const;
