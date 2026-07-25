/**
 * Process entry point for the TypeScript mutation gate. Run by `make mutation-ts`.
 *
 * Deliberately logic-free. An entry-point guard (`import.meta.url === process.argv[1]`) inside the
 * module it guards is a branch no unit test can exercise from either side, so it would sit in the
 * mutation report forever as an unkillable survivor. Splitting it into this shim keeps
 * checkMutationGate.mts fully mutation-covered and leaves nothing here worth mutating — which is
 * why stryker.conf.json excludes every domain's bin/ rather than silencing individual mutants.
 */

import { join } from 'node:path';

import { REPORT_PATH, main } from '../checkMutationGate.mjs';

// process.cwd(), not an `import.meta.dirname` relative hop — this shim runs only as compiled
// output (`.ts-out/release/bin/mutationGate.mjs`, via `make mutation-ts`), but a fixed relative-hop
// count is still the wrong tool: it silently breaks again the next time a domain's nesting depth
// changes. `make mutation-ts` always runs from the repo root (see descriptor.mts's own REPO_ROOT
// for the fuller reasoning), so `process.cwd()` resolves correctly without tracking depth at all.
const repoRoot = process.cwd();
process.exit(main(repoRoot, join(repoRoot, ...REPORT_PATH)));
