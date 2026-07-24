/**
 * Write one version into every canonical version-bearing file (keeps them in sync).
 *
 * Used by the release workflow after the next version is computed from conventional commits. The
 * list of files lives in one place — `scripts-ts/build/versionTargets.mts` — shared with CI's
 * `validate` job so the writer and the reader can never disagree about which manifests carry the
 * version.
 */

import { writeVersion } from './build/versionTargets.mjs';

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
export function main(argv: readonly string[], root = '.'): number {
  const [version] = argv;
  if (argv.length !== 1 || version === undefined) {
    process.stderr.write('usage: setVersion.mjs X.Y.Z\n');
    return 1;
  }
  setVersion(version, root);
  return 0;
}
