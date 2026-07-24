#!/usr/bin/env node
/**
 * `setVersion` CLI entry point. Run by `make release-version`.
 *
 * Deliberately logic-free — an entry-point guard (`import.meta.url === process.argv[1]`) inside
 * the module it guards is a branch no unit test can exercise from either side, so it would sit in
 * the mutation report forever as an unkillable survivor. Splitting it into this shim keeps
 * setVersion.mts fully mutation-covered and leaves nothing here worth mutating — same rationale as
 * mutationGate.mts's own shim.
 */

import { main } from '../setVersion.mjs';

process.exitCode = main(process.argv.slice(2));
