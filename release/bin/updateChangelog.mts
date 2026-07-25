#!/usr/bin/env node
/**
 * `updateChangelog` CLI entry point. Run by `make changelog`.
 *
 * Deliberately logic-free — see `bin/setVersion.mts`'s own comment for why an entry-point guard is
 * split out here rather than left inline.
 */

import { main } from '../updateChangelog.mjs';

main(process.env);
