/**
 * Process entry point for the TypeScript mutation gate. Run by `make mutation-ts`.
 *
 * Deliberately logic-free: an entry-point guard (`import.meta.url === process.argv[1]`) inside the
 * module it guards is a branch no unit test can exercise, so isolating it here keeps
 * checkMutationGate.mts fully mutation-covered and lets stryker.conf.json exclude every domain's bin/.
 */

import { join } from 'node:path';

import { REPORT_PATH, main } from '../checkMutationGate.mjs';

// process.cwd(), not an `import.meta.dirname` relative hop: a fixed hop count silently breaks the
// next time a domain's nesting depth changes. `make mutation-ts` always runs from the repo root
// (see descriptor.mts's REPO_ROOT for the fuller reasoning), so cwd resolves without tracking depth.
const repoRoot = process.cwd();
process.exit(main(repoRoot, join(repoRoot, ...REPORT_PATH)));
