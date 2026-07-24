import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import { discover } from '../../scripts-ts/build/descriptor.mjs';
import { buildRegistry } from '../../scripts-ts/build/serialize.mjs';
import { ECOSYSTEMS } from '../support/descriptorFixtures';
import { repoRoot } from '../support/repo';

// Ported from tests/build/test_target_switches.py — a guard that every `${target:NAME}` switch
// names a real target (or default/end). render.mts's switch resolution silently renders an empty
// branch when a switch matches no target and has no default — deliberate for single-target blocks
// (e.g. an opencode-only note that is empty on Claude). The failure mode this guards is a TYPO'D
// target name (${target:opencde}), which would silently drop content on every target with no
// error. Coverage is intentionally NOT required (single-target blocks are supported); only name
// validity is.

const SRC_CONTENT = join(repoRoot, 'src', 'content');
const DIRECTIVE = /^\$\{target:([^}]*)\}$/;

function validNames(): Set<string> {
  const names = new Set<string>(['default', 'end']);
  const registry = buildRegistry(Object.values(discover(ECOSYSTEMS)));
  for (const target of registry.registeredTargets()) {
    names.add(target);
    names.add(target.split('-', 1)[0] as string); // short alias, e.g. claude-code -> claude
  }
  return names;
}

function markdownFilesUnder(dir: string): string[] {
  const out: string[] = [];
  const walk = (d: string): void => {
    for (const entry of readdirSync(d)) {
      const full = join(d, entry);
      if (statSync(full).isDirectory()) walk(full);
      else if (entry.endsWith('.md')) out.push(full);
    }
  };
  walk(dir);
  return out.sort();
}

describe('content files never reference an unknown target switch', () => {
  it('every ${target:NAME} marker names a real target — a typo would silently drop content everywhere', () => {
    const valid = validNames();
    const offenders: string[] = [];
    for (const md of markdownFilesUnder(SRC_CONTENT)) {
      const text = readFileSync(md, 'utf-8');
      const lines = text.split('\n');
      for (let i = 0; i < lines.length; i++) {
        const m = DIRECTIVE.exec((lines[i] as string).trim());
        if (m !== null && !valid.has(m[1] as string)) {
          const rel = md.slice(SRC_CONTENT.length + 1).split('\\').join('/');
          offenders.push(`${rel}:${i + 1} -> \${target:${m[1]}}`);
        }
      }
    }
    expect(offenders, `unknown \${target:…} switch name(s):\n${offenders.join('\n')}`).toEqual([]);
  });
});
