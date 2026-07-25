#!/usr/bin/env node
/**
 * `validatePackage` CLI entry point. Run by `make validate`.
 *
 * Deliberately logic-free — see `bin/setVersion.mts`'s own comment for why an entry-point guard is
 * split out here rather than left inline.
 */

import { main } from '../validatePackage.mjs';

main();
