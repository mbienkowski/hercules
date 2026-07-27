/**
 * Write one version into every canonical version-bearing file, for the release workflow. The file
 * list lives once in `builder/versionTargets.mts`, shared with CI's `validate` job, so the writer
 * and the reader cannot disagree about which manifests carry the version.
 */

import { writeVersion } from '../builder/versionTargets.mjs';

// `root`'s default reaches only `writeVersion` -> `path.join(root, rel)`, and Node's
// `path.join('.', rel)` and `path.join('', rel)` are byte-for-byte identical for every
// VERSION_TARGETS entry — so no test can observe this literal, making it a TRUE equivalent mutant
// under CODE_OF_CONDUCT.md's Testing pragma exception for behaviourally equivalent static strings.
// Stryker disable next-line StringLiteral: root='.' and root='' resolve identically through path.join(root, rel) — see comment above
export function setVersion(version: string, root = '.'): void {
  writeVersion(version, root);
}

/**
 * CLI argument handling, split out from the entry point (`bin/setVersion.mts`) so it is fully
 * unit-testable, matching `cli.mts`'s `main(argv)` convention: `argv` is already sliced. `root` lets
 * a test write to a scratch directory without `process.chdir()`, unsupported in Stryker's workers.
 */
// Same TRUE equivalent mutant as setVersion()'s `root` default above: this one reaches only
// `setVersion(version, root)` -> `path.join(root, rel)`, where '.' and '' are indistinguishable.
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
