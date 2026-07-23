/**
 * Process entry point for the TypeScript mutation gate. Run by `make mutation-ts`.
 *
 * Deliberately logic-free. A `require.main === module` guard inside the module it guards is a
 * branch no unit test can exercise from either side, so it would sit in the mutation report
 * forever as an unkillable survivor. Splitting it into this shim keeps checkMutationGate.ts
 * fully mutation-covered and leaves nothing here worth mutating — which is why stryker.conf.json
 * excludes scripts-ts/bin/ rather than silencing individual mutants.
 */

import { join } from 'node:path';

import { REPORT_PATH, main } from '../checkMutationGate';

const repoRoot = join(__dirname, '..', '..');
process.exit(main(repoRoot, join(repoRoot, ...REPORT_PATH)));
