import { globSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

import { readRepoFile, readRepoJson, readRepoJsonc, repoRoot } from '../../support/repo';

/**
 * What we publish, and what the machine building it may assume: the invariants that bite only at
 * `npm publish` or at a consumer's install, long after every test has passed.
 */

interface PackageManifest {
  type?: string;
  main: string;
  files: string[];
  engines?: { node?: string };
  dependencies?: Record<string, string>;
  devDependencies?: Record<string, string>;
}

const manifest = readRepoJson<PackageManifest>('package.json');

describe('the published npm package', () => {
  it('is still interpreted as CommonJS, because the shipped OpenCode plugin is CommonJS', () => {
    // `main` is the OpenCode plugin, which uses require() and __dirname; "type": "module" here would
    // reinterpret it as ESM (ECMAScript modules) and break it for every user. Need ESM? Use a .mts file.
    expect(manifest.type).toBeUndefined();

    const plugin = readRepoFile(manifest.main);
    expect(plugin).toContain('require(');
    expect(plugin).toContain('__dirname');
  });

  it('ships only the OpenCode plugin tree, never sources or tooling', () => {
    // A stray entry here would publish content/, builder/ or node_modules to npm.
    expect(manifest.files).toEqual(['dist/opencode']);
  });

  it('declares no runtime dependencies at all', () => {
    // The published artifact is a plugin tree; it must not pull anything into a user's install.
    expect(manifest.dependencies ?? {}).toEqual({});
  });

  it('pins every development dependency to an exact version', () => {
    // A caret range lets a tokenizer bump silently move the counts promptBudgets.spec.ts gates on, so
    // js-tiktoken is pinned exactly and Dependabot proposes bumps as reviewable pull requests.
    const ranged = Object.entries(manifest.devDependencies ?? {}).filter(
      ([, version]) => !/^\d+\.\d+\.\d+/.test(version),
    );
    expect(ranged).toEqual([]);
  });

  it('requires the Node version CI actually provisions', () => {
    expect(manifest.engines?.node).toBe('>=22');
  });
});

describe('the module format of the toolchain', () => {
  const configs = ['tsconfig.json', 'tsconfig.base.json', 'tsconfig.build.json', 'Makefile'];

  it('emits every domain as ESM, so every toolchain source is .mts', () => {
    // .mts emits .mjs, which Node loads as ESM whatever package.json says, so the toolchain can use
    // ESM-only dependencies while the shipped plugin stays CommonJS.
    const build = readRepoJsonc<{ include: string[] }>('tsconfig.build.json');

    // Derived from the Makefile, so dropping a domain from the build while a target still runs it
    // fails HERE rather than as a missing file in CI.
    const executed = [...new Set([...readRepoFile('Makefile').matchAll(/\.local\/ts-out\/([a-z-]+)\//g)]
      .map((match) => match[1] as string))].sort();
    const compiled = build.include.map((pattern) => pattern.split('/')[1] as string).sort();
    expect(executed.length, 'no compiled domain is executed — the pattern must have stopped matching')
      .toBeGreaterThan(0);
    expect(executed.filter((domain) => !compiled.includes(domain)),
      'these domains are run from .local/ts-out/ but never compiled into it').toEqual([]);

    // Specs live in the top-level tests/ tree, so this glob finds none in practice. The filter stays
    // as a guard: a stray spec under internal/ belongs to tsconfig.tests.json's project, not this one.
    const sources = build.include
      .flatMap((pattern) => globSync(pattern.replace(/\.mts$/, '.{ts,mts,cts}'), { cwd: repoRoot }))
      .filter((f) => !f.includes('/tests/'));
    expect(sources.length).toBeGreaterThan(0);
    expect(sources.filter((f) => !f.endsWith('.mts'))).toEqual([]);
  });

  it('has no configuration still describing the toolchain as CommonJS', () => {
    // These comments are the only guard against "modernising" the module split into a broken state.
    const stale = configs.filter((f) =>
      /(builder|release)\/[^\n]*CommonJS|CommonJS[^\n]*(builder|release)\//.test(readRepoFile(f)),
    );
    expect(stale).toEqual([]);
  });
});

describe('the npm install posture', () => {
  it('disables dependency lifecycle scripts for every install', () => {
    // A postinstall runs with the ambient environment of whatever job installed it — including its
    // credentials. release.yml also keeps `npm ci` out of any job holding one.
    expect(readRepoFile('.npmrc')).toMatch(/^ignore-scripts=true$/m);
  });

  it('keeps a committed lockfile so CI installs the reviewed dependency graph', () => {
    const lock = readRepoJson<{ lockfileVersion: number }>('package-lock.json');
    expect(lock.lockfileVersion).toBeGreaterThanOrEqual(3);
  });
});
