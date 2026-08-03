#!/usr/bin/env node
/** `setVersion` CLI entry point (`make release-version`). Logic-free, for full mutation coverage of `setVersion.mts`. */

import { main } from '../setVersion.mjs';

process.exitCode = main(process.argv.slice(2));
