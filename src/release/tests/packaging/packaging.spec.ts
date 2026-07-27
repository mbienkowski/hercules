import { globSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

import { readRepoFile, readRepoJson, readRepoJsonc, repoRoot } from '../../../commons/support/repo';

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
    // package.json's `main` is the compiled OpenCode plugin, which uses require(), __dirname and
    // module.exports. Node decides a .js file's module format from the nearest package.json "type",
    // so declaring "type": "module" here would reinterpret the shipped plugin as ESM (ECMAScript
    // modules) and break it for every OpenCode user. If you need ESM for tooling, use a .mts file.
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
    // A caret range is how a tokenizer minor bump silently moves the token counts that
    // src/metrics/tests/testdata/thresholds.json gates on (gpt-tokenizer's 3.3.0 split-regex fix does exactly
    // that). Dependabot proposes bumps as reviewable pull requests instead.
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
    // The positive half. .mts emits .mjs, which Node loads as ESM whatever package.json says — that
    // is what lets the toolchain use ESM-only dependencies while the shipped plugin stays CommonJS.
    // A stray .ts compiles to a format the include glob does not match, dropping it from every gate.
    const build = readRepoJsonc<{ include: string[] }>('tsconfig.build.json');
    expect(build.include).toEqual(['src/builder/**/*.mts', 'src/release/**/*.mts', 'src/metrics/**/*.mts']);

    // Each domain's own tests/ nests INSIDE it (src/builder/tests/, not a separate sibling), so the
    // recursive `**` would also match .spec.ts files there — those belong to tsconfig.tests.json's
    // project, not this one, and must be excluded explicitly.
    const sources = build.include
      .flatMap((pattern) => globSync(pattern.replace(/\.mts$/, '.{ts,mts,cts}'), { cwd: repoRoot }))
      .filter((f) => !f.includes('/tests/'));
    expect(sources.length).toBeGreaterThan(0);
    expect(sources.filter((f) => !f.endsWith('.mts'))).toEqual([]);
  });

  it('has no configuration still describing the toolchain as CommonJS', () => {
    // The negative half, paired with the assertion above. These comments are the repo's only guard
    // against someone "modernising" the module split into a broken state, so a stale one aims that
    // guard at the wrong target.
    const stale = configs.filter((f) =>
      /(builder|release|metrics)\/[^\n]*CommonJS|CommonJS[^\n]*(builder|release|metrics)\//.test(readRepoFile(f)),
    );
    expect(stale).toEqual([]);
  });
});

describe('the npm install posture', () => {
  it('disables dependency lifecycle scripts for every install', () => {
    // A postinstall runs with the ambient environment of whatever job installed it. release.yml keeps
    // `npm ci` out of any job holding a push or publish credential; this is the unconditional layer.
    expect(readRepoFile('.npmrc')).toMatch(/^ignore-scripts=true$/m);
  });

  it('keeps a committed lockfile so CI installs the reviewed dependency graph', () => {
    const lock = readRepoJson<{ lockfileVersion: number }>('package-lock.json');
    expect(lock.lockfileVersion).toBeGreaterThanOrEqual(3);
  });
});
