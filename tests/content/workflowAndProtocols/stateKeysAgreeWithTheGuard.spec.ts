import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import { pathsUnder } from '../../support/buildTree';
import { schemaPropertyNames, stateKeysTheGuardReads } from '../../support/declaredVocabulary';
import { repoRoot } from '../../support/repo';

/**
 * Markdown tells an agent to record a state key; Python reads that key to decide whether to refuse a
 * write. Nothing links the two, so a rename leaves the guard finding nothing and allowing everything.
 */

const CONTENT = join(repoRoot, 'src', 'content');

/** Every markdown file shipped as instructions (commands, agents, protocols, skills). */
function instructionText(): string {
  return pathsUnder(CONTENT, { skipDirs: ['tests'] }).map((path) => readFileSync(path, 'utf-8')).join('\n');
}

// Names the HOST owns and puts in the event it sends us; the guard just reads what arrives.
const OWNED_BY_THE_HOST = new Set([
  'tool_name', 'tool_input', 'file_path', 'hook_event_name', 'workspace_roots', 'command', 'edits',
]);

describe('the written instructions and the runtime guard share one vocabulary', () => {
  const read = [...stateKeysTheGuardReads()].sort().filter((key) => !OWNED_BY_THE_HOST.has(key));
  const fromSchema = schemaPropertyNames();
  const instructions = instructionText();

  it('the guard was actually read', () => {
    // Guards the guard: an empty vocabulary would make both checks below pass by asking nothing.
    expect(read.length, 'no keys were found in the guard source').toBeGreaterThan(10);
    expect(fromSchema.size, 'no keys were found in the schema').toBeGreaterThan(10);
  });

  it('every session key the guard reads is one the instructions tell someone to write', () => {
    // A key the guard reads but nobody is told to write is a protection that never engages.
    const sessionKeys = read.filter((key) => !fromSchema.has(key));
    const orphaned = sessionKeys.filter((key) => !instructions.includes(key));
    expect(orphaned, 'the guard reads these, but no shipped instruction mentions them').toEqual([]);
  });

  it('every configuration key the guard reads is one the schema defines', () => {
    // The other half: a key the schema does not describe leaves a tool author no way to know of it.
    const configKeys = read.filter((key) => !instructions.includes(key));
    expect(configKeys.filter((key) => !fromSchema.has(key)),
      'the guard reads these from configuration, but the schema describes no such key').toEqual([]);
  });
});
