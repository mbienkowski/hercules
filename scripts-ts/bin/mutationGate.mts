/**
 * Process entry point for the TypeScript mutation gate. Run by `make mutation-ts`.
 *
 * Deliberately logic-free. An entry-point guard (`import.meta.url === process.argv[1]`) inside the
 * module it guards is a branch no unit test can exercise from either side, so it would sit in the
 * mutation report forever as an unkillable survivor. Splitting it into this shim keeps
 * checkMutationGate.mts fully mutation-covered and leaves nothing here worth mutating — which is
 * why stryker.conf.json excludes scripts-ts/bin/ rather than silencing individual mutants.
 */

import { join } from 'node:path';

import { REPORT_PATH, main } from '../checkMutationGate.mjs';

const repoRoot = join(import.meta.dirname, '..', '..');
process.exit(main(repoRoot, join(repoRoot, ...REPORT_PATH)));
