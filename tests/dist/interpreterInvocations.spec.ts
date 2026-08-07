import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';

import { describe, expect, it } from 'vitest';

import { repoRoot } from '../support/repo';

// Every shipped instruction that runs one of our own programs must name it by an ABSOLUTE path.
//
// The failure this exists to stop is not cosmetic. An agent runs these commands with the user's
// authority, and its working directory is the repository being worked on. `python3 tools/x.py`
// resolves there — so a repository carrying a file at that path has it executed. A host-resolved
// `${PLUGIN_ROOT}/tools/x.py` cannot be captured that way, and if the variable is ever unset it
// yields `/tools/x.py` and fails loudly rather than running the checkout's copy.

const DIST = join(repoRoot, 'dist');
const ECOSYSTEMS = readdirSync(DIST).filter((name) => statSync(join(DIST, name)).isDirectory());

// An interpreter followed by whatever it is pointed at, up to the first space. Interpreter flags
// may sit between, and a quoted path is still a path — single quotes as much as double.
const INVOCATION =
  /\b(python3?|node|bun|sh|bash|uv\s+run)\s+(?:-{1,2}[\w=.-]+\s+)*(["']?)([^\s"']+\.(?:py|js|mjs|cjs|sh))\2/g;

// `python -m tools.x` names a shipped program with no suffix at all, and resolves against the
// working directory exactly as a relative path does. There is no way to anchor a module, so every
// match of ours is a finding.
const MODULE_INVOCATION =
  /\b(python3?)\s+(?:-(?!m\b)[\w=.-]+\s+)*-m\s+(["']?)((?:tools|hooks)\.[\w.]+)\2/g;

// Only the programs WE ship are our problem: a target repository's own `npm test` is not ours to
// anchor, and neither is a command the user is told to type about their own code.
const OURS = /(?:^|\/)(tools|hooks)\//;

const PROSE = ['.md', '.toml', '.json'];

function proseUnder(root: string): string[] {
  const found: string[] = [];
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir)) {
      const path = join(dir, entry);
      if (statSync(path).isDirectory()) walk(path);
      else if (PROSE.some((suffix) => entry.endsWith(suffix))) found.push(path);
    }
  };
  walk(root);
  return found;
}

// Anchored means an absolute path or a HOST-RESOLVED plugin-root variable. Any other `$VAR` is no
// proof at all: a variable the host never sets expands to nothing and the rest resolves against
// the user's repository — the exact failure this sweep exists to stop.
const HOST_ANCHOR = /^(?:\/|\$\{?[A-Za-z_]*(?:PLUGIN_ROOT|extensionPath)[A-Za-z_]*\}?\/)/;

function isAnchored(target: string): boolean {
  return HOST_ANCHOR.test(target);
}

function unanchored(root: string): string[] {
  const found: string[] = [];
  for (const file of proseUnder(root)) {
    const text = readFileSync(file, 'utf-8');
    for (const [, , , target] of text.matchAll(INVOCATION)) {
      if (!target || !OURS.test(target) || isAnchored(target)) continue;
      found.push(`${relative(repoRoot, file)} runs "${target}", resolved against the user's repository`);
    }
    for (const [, , , module] of text.matchAll(MODULE_INVOCATION)) {
      found.push(`${relative(repoRoot, file)} runs module "${module}", resolved against the user's repository`);
    }
  }
  return [...new Set(found)];
}

describe('a shipped instruction never runs one of our programs by a relative path', () => {
  it('at least one ecosystem is built, so the sweep below is never vacuous', () => {
    expect(ECOSYSTEMS.length).toBeGreaterThan(0);
  });

  it.each(ECOSYSTEMS)('%s anchors every invocation of a shipped program', (ecosystem) => {
    expect(unanchored(join(DIST, ecosystem))).toEqual([]);
  });

  it('recognises an unanchored invocation when it sees one', () => {
    // Guard the guard: a matcher that silently stopped matching would pass every ecosystem above.
    const anchored = 'run `python3 ${PLUGIN_ROOT}/tools/state_patch.py apply` to record it';
    const relativeCall = 'run `python3 tools/state_patch.py apply` to record it';
    const matches = (text: string) =>
      [...text.matchAll(INVOCATION)].filter(([, , , t]) => OURS.test(t ?? '') && !isAnchored(t ?? ''));
    expect(matches(relativeCall)).toHaveLength(1);
    expect(matches(anchored)).toHaveLength(0);
  });

  it('is not fooled by quoting, flags, runners, or a variable the host never resolves', () => {
    const matches = (text: string) =>
      [...text.matchAll(INVOCATION)].filter(([, , , t]) => OURS.test(t ?? '') && !isAnchored(t ?? ''));
    expect(matches("run `python3 'tools/state_patch.py' apply`")).toHaveLength(1);
    expect(matches('run `python3 "tools/state_patch.py" apply`')).toHaveLength(1);
    expect(matches('run `python3 -u tools/state_patch.py apply`')).toHaveLength(1);
    expect(matches('run `python3 ./tools/state_patch.py apply`')).toHaveLength(1);
    expect(matches('run `uv run tools/state_patch.py apply`')).toHaveLength(1);
    // $SOME_VAR looks anchored and is not: unset, it expands to nothing and the path goes relative.
    expect(matches('run `python3 $SOME_REPO_VAR/tools/state_patch.py apply`')).toHaveLength(1);
    expect(matches('run `python3 ${HERCULES_PLUGIN_ROOT}/tools/state_patch.py`')).toHaveLength(0);
    expect(matches('run `python3 ${extensionPath}/tools/state_patch.py`')).toHaveLength(0);
  });

  it('recognises a module invocation of a shipped program', () => {
    const modules = (text: string) => [...text.matchAll(MODULE_INVOCATION)];
    expect(modules('run `python3 -m tools.state_patch apply`')).toHaveLength(1);
    expect(modules('run `python3 -u -m tools.state_patch apply`')).toHaveLength(1);
    expect(modules('run `python3 -m pytest` over the suite')).toHaveLength(0);
  });

  it('leaves a target repository\'s own commands alone', () => {
    // We anchor what we ship. `npm test` in a project's own code-of-conduct is not ours to rewrite.
    const theirs = 'run `python3 scripts/migrate.py` before deploying';
    const matches = [...theirs.matchAll(INVOCATION)].filter(([, , , t]) => OURS.test(t ?? ''));
    expect(matches).toHaveLength(0);
  });
});
