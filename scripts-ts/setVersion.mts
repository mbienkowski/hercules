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

// Only run when invoked directly (`node setVersion.mjs X.Y.Z`), not when imported by a test —
// matching Python's `if __name__ == "__main__":` guard.
if (import.meta.url === `file://${process.argv[1]}`) {
  const [version] = process.argv.slice(2);
  if (process.argv.length !== 3 || version === undefined) {
    process.stderr.write('usage: setVersion.mjs X.Y.Z\n');
    process.exitCode = 1;
  } else {
    setVersion(version);
  }
}
