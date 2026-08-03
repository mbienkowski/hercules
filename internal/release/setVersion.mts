/** Write one version into every canonical file, for the release workflow. */

import { writeVersion } from './version-files.mjs';

// `root='.'` and `root=''` resolve identically through path.join — a true equivalent mutant.
// Stryker disable next-line StringLiteral: '.' and '' resolve identically through path.join(root, relativePath)
export function setVersion(version: string, root = '.'): void {
  writeVersion(version, root);
}

/** CLI handling for `bin/setVersion.mts`; `root` lets a test target a scratch directory. */
// Same equivalent mutant as setVersion()'s `root` default.
// Stryker disable next-line StringLiteral: same equivalence as setVersion()'s root default
export function main(argv: readonly string[], root = '.'): number {
  const [version] = argv;
  if (argv.length !== 1 || version === undefined) {
    process.stderr.write('usage: setVersion.mjs X.Y.Z\n');
    return 1;
  }
  setVersion(version, root);
  return 0;
}
