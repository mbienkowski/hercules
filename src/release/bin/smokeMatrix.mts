#!/usr/bin/env node
/**
 * `smokeMatrix` CLI entry point. Run by `make smoke-matrix`.
 *
 * Deliberately logic-free — see `bin/setVersion.mts`'s own comment for why an entry-point guard is
 * split out here rather than left inline.
 */

import { main } from '../smokeMatrix.mjs';

main();
