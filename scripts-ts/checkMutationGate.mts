/**
 * Mutation kill-rate gate for the TypeScript side (Stryker), mirroring the Python side
 * (scripts/check_mutation_gate.py, mutmut over src/hooks/).
 *
 * The two gates are deliberately symmetric: same thresholds (scripts/mutation-gate.json), same
 * failure modes, same wording. A contributor who has debugged one has debugged both — which is the
 * whole point of splitting the mutation run across two runtimes rather than one.
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
 * Mutant tallies, normalised from Stryker's report into the same five buckets the Python gate
 * counts. Stryker's `NoCoverage` folds into `survived` — an uncovered mutant is a survived one
 * with a more specific cause, and counting it any other way would flatter the score.
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
  const raw = JSON.parse(readFileSync(join(repoRoot, 'scripts', 'mutation-gate.json'), 'utf-8')) as {
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
        // Everything else is suspicious: Stryker's own error statuses (`RuntimeError`,
        // `CompileError`) and any status a future Stryker introduces. They are deliberately NOT
        // listed as explicit cases — doing so would be redundant with this branch and produce
        // equivalent mutants. A result that is not a clean kill, survive, timeout or reviewed
        // exclusion must fail the gate loudly rather than vanish from the denominator.
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
 * Evaluate the gate. Returns a process exit code.
 *
 * Failure modes are in the same order and carry the same meaning as the Python gate:
 *   1. incomplete run (untested / suspicious mutants) — a kill rate over a partial run is a green
 *      gate over data that never existed;
 *   2. zero mutants — the config selected nothing, so nothing was proven;
 *   3. every mutant timed out — no signal in either direction;
 *   4. below warn — pass, but say so;
 *   5. below gate — fail.
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
