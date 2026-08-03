#!/usr/bin/env node
/**
 * The build's process entry point. All logic lives in `../build.mjs`; this turns a thrown refusal
 * into a message, never a stack trace. Importing it performs zero filesystem syscalls.
 */

import { pathToFileURL } from 'node:url';

import { main } from '../build.mjs';

// Only when invoked directly, never when imported by a test.
if (import.meta.url === pathToFileURL(process.argv[1] ?? '').href) {
  try {
    process.exitCode = await main(process.argv.slice(2));
  } catch (error) {
    // A refusal from this build is a MESSAGE, not a crash. Anything that is not one of our own
    // errors keeps its stack, because then the trace really is the information.
    const named = error instanceof Error && /^(Recipe|Lint|Scope|RenderEntry)Error$/.test(error.name);
    if (!named) throw error;
    process.stderr.write(`${(error as Error).message}\n`);
    process.exitCode = 1;
  }
}
