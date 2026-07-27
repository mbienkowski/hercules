/** Data-driven threshold checks driven by `thresholds.json`. */

import { globSync, readFileSync } from 'node:fs';
import { join, relative } from 'node:path';

import { countCoreEntries, extractA2aCore } from './a2aGrammar.mjs';
import { countAtomicInstructions } from './instructionCounter.mjs';
import { countTokens } from './tokenCounter.mjs';

type MetricFn = (text: string) => number;

// The closed vocabularies live as `as const` tuples so their literal unions (Op, Severity) are the
// single source of truth for the runtime checks below AND the ThresholdCheck field types — a value
// outside the set becomes a type error at every consumer, not just a silent string.
const OPS = ['==', '<=', '>=', '<', '>'] as const;
type Op = (typeof OPS)[number];
const SEVERITIES = ['gate', 'warn'] as const;
type Severity = (typeof SEVERITIES)[number];

// A pattern is treated as a glob (expanded via globSync) rather than a literal path when it contains
// any glob metacharacter: `*`, `?`, or `[`. (The `[` inside the class is a literal class member.)
const GLOB_CHARS = /[*?[]/;
function isGlob(pattern: string): boolean {
  return GLOB_CHARS.test(pattern);
}

/** Exported for direct unit testing (mirrors the Python original's own test importing `_core_token_count`). */
export function coreTokenCount(text: string): number {
  const { text: core, found } = extractA2aCore(text);
  if (!found) throw new Error('no fenced Core block found');
  return countTokens(core);
}

function coreEntryCount(text: string): number {
  return countCoreEntries(extractA2aCore(text).text);
}

const METRIC_REGISTRY = {
  instruction_count: countAtomicInstructions,
  token_count: countTokens,
  core_entry_count: coreEntryCount,
  core_token_count: coreTokenCount,
} as const satisfies Record<string, MetricFn>;
type MetricName = keyof typeof METRIC_REGISTRY;

export interface ThresholdCheck {
  readonly name: string;
  readonly target: string;
  readonly metric: MetricName;
  readonly op: Op;
  readonly limit: number;
  readonly severity: Severity;
  readonly warnAt: number | null;
  readonly perFile: boolean;
}

export interface CheckResult {
  readonly name: string;
  readonly value: number;
  readonly passed: boolean;
  readonly severity: Severity;
  readonly message: string;
  readonly nearWarn: boolean;
}

/**
 * One row exactly as `JSON.parse` produced it: every field stays `unknown` until `parseRow` proves
 * it. `thresholds.json` is untrusted input, so declaring the fields as `string`/`number` here would
 * assert the very shape this module exists to verify — and would make the checks below read as dead
 * code to anyone maintaining them.
 */
type RawRow = Readonly<Record<string, unknown>>;

/** A non-empty string field, or a throw naming the offending row and field. */
function requireText(value: unknown, row: string, field: string): string {
  if (typeof value !== 'string' || value === '') {
    throw new Error(`thresholds.json row '${row}': '${field}' must be a non-empty string, got ${JSON.stringify(value)}`);
  }
  return value;
}

/** A finite number field, or a throw naming the offending row and field. */
function requireFinite(value: unknown, row: string, field: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new Error(`thresholds.json row '${row}': '${field}' must be a finite number, got ${JSON.stringify(value)}`);
  }
  return value;
}

/** Validate one raw row into a ThresholdCheck, naming the offending field on any failure. */
function parseRow(row: RawRow): ThresholdCheck {
  const { name } = row;
  if (typeof name !== 'string' || name === '') {
    throw new Error(`thresholds.json: a row has a missing or empty 'name' (got ${JSON.stringify(name)})`);
  }
  // `.find` over the `as const` tuples narrows to the literal union (Op / Severity / MetricName)
  // without a cast — a bad value comes back `undefined` and throws loudly, so nothing string-typed
  // ever leaks into a ThresholdCheck.
  const metric = (Object.keys(METRIC_REGISTRY) as MetricName[]).find((m) => m === row['metric']);
  if (metric === undefined) {
    throw new Error(
      `thresholds.json row '${name}': unknown metric '${String(row['metric'])}' ` +
        `(known: ${JSON.stringify([...Object.keys(METRIC_REGISTRY)].sort())})`,
    );
  }
  const severity = SEVERITIES.find((s) => s === (row['severity'] ?? 'gate'));
  if (severity === undefined) {
    throw new Error(`thresholds.json row '${name}': unknown severity '${String(row['severity'])}' (must be 'gate' or 'warn')`);
  }
  const op = OPS.find((o) => o === row['op']);
  if (op === undefined) {
    throw new Error(`thresholds.json row '${name}': unknown op '${String(row['op'])}' (must be one of ${JSON.stringify([...OPS].sort())})`);
  }
  const limit = requireFinite(row['limit'], name, 'limit');
  const target = requireText(row['target'], name, 'target');
  const rawWarnAt = row['warn_at'] ?? null;
  const warnAt = rawWarnAt === null ? null : requireFinite(rawWarnAt, name, 'warn_at');
  if (warnAt !== null && warnAt > limit) {
    throw new Error(`thresholds.json row '${name}': warn_at (${warnAt}) > limit (${limit})`);
  }
  const perFile = row['per_file'] ?? false;
  if (typeof perFile !== 'boolean') {
    throw new Error(`thresholds.json row '${name}': 'per_file' must be a boolean, got ${JSON.stringify(perFile)}`);
  }
  return { name, target, metric, op, limit, severity, warnAt, perFile };
}

/** Load and validate `thresholds.json`; throw on any invalid row. */
export function loadThresholds(path: string): ThresholdCheck[] {
  const raw: unknown = JSON.parse(readFileSync(path, 'utf-8'));
  if (!Array.isArray(raw)) {
    throw new Error(`thresholds.json: the top level must be an array of rows, got ${JSON.stringify(raw)}`);
  }
  return raw.map((row: unknown, index) => {
    if (typeof row !== 'object' || row === null || Array.isArray(row)) {
      throw new Error(`thresholds.json: row ${index} must be an object, got ${JSON.stringify(row)}`);
    }
    return parseRow(row as RawRow);
  });
}

/** Evaluate `value op limit`; returns `[result, errorMessage]`. Error message is non-empty only for an unknown operator. */
export function compareValue(value: number, op: string, limit: number): [boolean, string] {
  if (op === '==') return [value === limit, ''];
  if (op === '<=') return [value <= limit, ''];
  if (op === '>=') return [value >= limit, ''];
  if (op === '<') return [value < limit, ''];
  if (op === '>') return [value > limit, ''];
  return [false, `unknown op '${op}'`];
}

/** The absolute paths one pattern resolves to: a glob's sorted matches, or the single literal path. */
function resolvePattern(repoRoot: string, pat: string): string[] {
  if (isGlob(pat)) {
    return [...globSync(pat, { cwd: repoRoot })].sort().map((rel) => join(repoRoot, rel));
  }
  return [join(repoRoot, pat)];
}

/** Expand a comma-separated list of paths or globs relative to `repoRoot`, into absolute paths. */
export function resolveTargets(repoRoot: string, target: string): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const rawPat of target.split(',')) {
    const pat = rawPat.trim();
    if (pat === '') continue;
    for (const full of resolvePattern(repoRoot, pat)) {
      if (seen.has(full)) continue; // dedup across patterns, keeping first-seen order
      seen.add(full);
      out.push(full);
    }
  }
  return out;
}

/** The outcome of evaluating one check: did it pass, the number to report, and the human message. */
interface Evaluation {
  passed: boolean;
  reported: number;
  msg: string;
}

/** Apply the limit to each matched file individually (e.g. "every agent <= 800"); report the worst. */
function evaluatePerFile(check: ThresholdCheck, targets: readonly string[], repoRoot: string, fn: MetricFn): Evaluation {
  const offenders: string[] = [];
  let worst = 0;
  for (const path of targets) {
    const value = fn(readFileSync(path, 'utf-8'));
    worst = Math.max(worst, value);
    const [ok, err] = compareValue(value, check.op, check.limit);
    if (err) throw new Error(`check '${check.name}': ${err}`);
    if (!ok) offenders.push(`${relative(repoRoot, path)}=${value}`);
  }
  const msg = `${check.name}: per-file ${check.metric}(${check.target}) want ${check.op} ${check.limit}` +
    (offenders.length > 0 ? ` — offenders: ${offenders.join(', ')}` : '');
  return { passed: offenders.length === 0, reported: worst, msg };
}

/** Sum the metric across all matched files (a combined budget); report the total. */
function evaluateSummed(check: ThresholdCheck, targets: readonly string[], fn: MetricFn): Evaluation {
  let total = 0;
  for (const path of targets) total += fn(readFileSync(path, 'utf-8'));
  const [ok, err] = compareValue(total, check.op, check.limit);
  if (err) throw new Error(`check '${check.name}': ${err}`);
  const msg = `${check.name}: ${check.metric}(${check.target})=${total}, want ${check.op} ${check.limit}`;
  return { passed: ok, reported: total, msg };
}

/**
 * Run all data-driven threshold checks and return results.
 *
 * Gate failures are returned as results with `passed: false`; they do not throw.
 */
export function runThresholdChecks(repoRoot: string, checks: readonly ThresholdCheck[]): CheckResult[] {
  const results: CheckResult[] = [];

  for (const check of checks) {
    const targets = resolveTargets(repoRoot, check.target);
    if (targets.length === 0) {
      results.push({
        name: check.name, value: 0, passed: false, severity: check.severity,
        message: `target '${check.target}' matched no files`, nearWarn: false,
      });
      continue;
    }

    const fn = METRIC_REGISTRY[check.metric];
    const { passed, reported, msg } = check.perFile
      ? evaluatePerFile(check, targets, repoRoot, fn)
      : evaluateSummed(check, targets, fn);

    const nearWarn = check.warnAt !== null && passed && reported >= check.warnAt;
    results.push({
      name: check.name, value: reported, passed, severity: check.severity, message: msg, nearWarn,
    });
  }

  return results;
}
