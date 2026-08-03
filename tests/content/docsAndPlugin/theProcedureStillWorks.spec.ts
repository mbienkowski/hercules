import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import { repoRoot } from '../../support/repo';
import {
  schemaFixedValues, schemaPropertyNames, stateKeysTheGuardReads,
} from '../../support/declaredVocabulary';

/**
 * Every configuration key the "add a tool" instructions name in backticks must be one the schema
 * defines: the schema refuses unknown keys, so a file written exactly as instructed is rejected.
 */

const DOCUMENTS = ['CONTRIBUTING.md', 'CODE_OF_CONDUCT.md'];

/**
 * Words a document presents as configuration keys: backticked lower_snake words in the sections about
 * adding a tool only, so the check speaks about the procedure and not every quoted word.
 */
function keysNamedIn(document: string): string[] {
  const text = readFileSync(join(repoRoot, document), 'utf-8');
  const found = new Set<string>();
  for (const line of text.split('\n')) {
    if (!/`[a-z_]+`/.test(line)) continue;
    for (const match of line.matchAll(/`([a-z][a-z0-9]*(?:_[a-z0-9]+)+)`/g)) {
      found.add(match[1] as string);
    }
  }
  return [...found].sort();
}

/**
 * Names these documents legitimately use that no declaration accounts for: state fields the guard
 * never reads back, hook and test filenames, and the capability tokens content is written with.
 */
const ACCOUNTED_FOR_ELSEWHERE = new Set([
  'build_complete', 'build_progress', 'delivered_specs', 'pending_specs', 'keep_specs',
  'docs_root', 'schema_version', 'handed_off_by', 'handoff_note',
  'frozen_tests', 'hercules_state', 'hercules_gate', 'write_gate_json', 'plugin_root',
  'test_no_retired_path_refs', 'tool_hygiene', 'test_every_registered_target_declares_a_gate',
  'plan_mode', 'command_title', 'forced_subagent', 'write_backstop', 'model_tier',
  'disable_model_invocation',
]);

/** Every word this project declares somewhere as part of its vocabulary. */
function declaredAnywhere(): Set<string> {
  return new Set([
    ...schemaPropertyNames(),
    ...schemaFixedValues(),
    ...stateKeysTheGuardReads(),
    ...ACCOUNTED_FOR_ELSEWHERE,
  ]);
}

describe('the written procedure for adding a tool names keys that exist', () => {
  const vocabulary = schemaPropertyNames();
  const declared = declaredAnywhere();

  it('the schema was actually read', () => {
    // Guards the guard: an empty vocabulary would make every name below look valid.
    expect(vocabulary.size, 'no property names were found in the schema').toBeGreaterThan(20);
    // The key both documents lean on hardest — if reading the schema returned nothing, this notices.
    expect(vocabulary.has('targets'), 'the schema should define targets').toBe(true);
    // And one from the nested shape, so a walk that stops at the root is caught too.
    expect(vocabulary.has('reason_at'), 'the nested shapes should be walked as well').toBe(true);
  });

  for (const document of DOCUMENTS) {
    it(`${document} names no configuration key the schema does not define`, () => {
      // The schema refuses unknown keys, so a file written exactly as instructed fails at build time.
      const invented = keysNamedIn(document)
        .filter((key) => !declared.has(key));
      expect(invented, `${document} names these as configuration keys, but the schema has no such key`)
        .toEqual([]);
    });
  }

  it('neither document still names a key from the retired vocabulary', () => {
    // The check above only sees multi-word keys; single words like `guard` and `gate` need naming.
    const RETIRED = ['guard', 'gate', 'dispatch', 'protocol', 'stem_prefix', 'descriptor'];
    for (const document of DOCUMENTS) {
      const text = readFileSync(join(repoRoot, document), 'utf-8');
      const revived = RETIRED.filter((name) => text.includes(`\`${name}\` —`) || text.includes(`\`${name}\` +`));
      expect(revived, `${document} presents these retired names as configuration keys`).toEqual([]);
    }
  });

  it('neither document sends a contributor to a content file that no longer exists', () => {
    // The other half of the same failure: the procedure pointing at a source file that is not there.
    for (const document of DOCUMENTS) {
      const text = readFileSync(join(repoRoot, document), 'utf-8');
      for (const match of text.matchAll(/`(src\/content\/[\w./-]+\.md)`/g)) {
        const referenced = match[1] as string;
        expect(() => readFileSync(join(repoRoot, referenced), 'utf-8'),
          `${document} points at ${referenced}, which does not exist`).not.toThrow();
      }
    }
  });
});
