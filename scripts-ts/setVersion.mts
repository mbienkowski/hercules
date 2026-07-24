/**
 * Write one version into every canonical version-bearing file (keeps them in sync).
 *
 * Used by the release workflow after the next version is computed from conventional commits. The
 * list of files lives in one place — `scripts-ts/build/versionTargets.mts` — shared with CI's
 * `validate` job so the writer and the reader can never disagree about which manifests carry the
 * version.
 */

import { writeVersion } from './build/versionTargets.mjs';

// `root`'s default value ('.') only ever reaches `writeVersion` -> `path.join(root, rel)`
// (versionTargets.mts), and Node's `path.join('.', rel)` and `path.join('', rel)` are byte-for-byte
// identical for every `rel` in VERSION_TARGETS (verified directly: both normalize the leading `.`
// segment away). No test — with or without `process.chdir()` — can ever observe a difference, so
// mutating this default's literal is a TRUE equivalent mutant per CODE_OF_CONDUCT.md's Testing
// section's pragma exception ("static strings whose mutants are all behaviourally equivalent" — this
// is a default-parameter string feeding only a path-join, never a branch/comparison/return value).
// Stryker disable next-line StringLiteral: root='.' and root='' resolve identically through path.join(root, rel) — see comment above
export function setVersion(version: string, root = '.'): void {
  writeVersion(version, root);
}

/**
 * CLI argument handling, split out from the process entry point (`bin/setVersion.mts`) so it is
 * fully unit-testable — matching `cli.mts`'s own `main(argv)` convention. `argv` is already sliced
 * (no `node`/script-path entries), same contract as `cli.mts`'s `main`.
 *
 * `root` (an addition over the real CLI's implicit `process.cwd()`-relative default, purely for
 * test benefit — same rationale as `cli.mts`'s `distRoot` param) lets a test point the write at a
 * scratch directory without `process.chdir()`, which Stryker's worker-thread test runner does not
 * support (`process.chdir() is not supported in workers`).
 */
// Same TRUE equivalent mutant as setVersion()'s own `root` default just above, and for the identical
// reason: this default only reaches `setVersion(version, root)` -> `path.join(root, rel)`, where
// '.' and '' are indistinguishable.
// Stryker disable next-line StringLiteral: root='.' and root='' resolve identically through path.join(root, rel) — see setVersion()'s comment above
export function main(argv: readonly string[], root = '.'): number {
  const [version] = argv;
  if (argv.length !== 1 || version === undefined) {
    process.stderr.write('usage: setVersion.mjs X.Y.Z\n');
    return 1;
  }
  setVersion(version, root);
  return 0;
}
