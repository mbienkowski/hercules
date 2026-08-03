#!/usr/bin/env node
/** `updateChangelog` CLI entry point (`make changelog`). Logic-free, same reason as `bin/setVersion.mts`. */

import { main } from '../updateChangelog.mjs';

main(process.env);
