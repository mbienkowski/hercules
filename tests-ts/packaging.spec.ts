import { describe, expect, it } from 'vitest';

import { readRepoFile, readRepoJson } from './support/repo';

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
    // package.json's `main` is the compiled OpenCode plugin, and that file uses require(),
    // __dirname and module.exports. Node decides a .js file's module format from the nearest
    // package.json "type" field, so declaring "type": "module" here would reinterpret the shipped
    // plugin as ESM and break it for every OpenCode user — a silent, user-visible breakage that no
    // other test in this repo would catch. If you need ESM for tooling, use a .mts file; do not
    // add this field.
    expect(manifest.type).toBeUndefined();

    const plugin = readRepoFile(manifest.main);
    expect(plugin).toContain('require(');
    expect(plugin).toContain('__dirname');
  });

  it('ships only the OpenCode plugin tree, never sources or tooling', () => {
    // A stray entry here would publish src/, scripts-ts/ or node_modules to npm.
    expect(manifest.files).toEqual(['dist/opencode']);
  });

  it('declares no runtime dependencies at all', () => {
    // The Python side had zero runtime dependencies and the Node side keeps that posture: the
    // published artifact is a plugin tree, and it must not pull anything into a user's install.
    expect(manifest.dependencies ?? {}).toEqual({});
  });

  it('pins every development dependency to an exact version', () => {
    // A caret range is how a tokenizer minor bump silently moves the token counts that
    // tests/testdata/thresholds.json gates on — js-tiktoken's sibling gpt-tokenizer shipped
    // exactly that (a split-regex fix in 3.3.0 that changed counts). Dependabot proposes bumps as
    // reviewable PRs instead.
    const ranged = Object.entries(manifest.devDependencies ?? {}).filter(
      ([, version]) => !/^\d+\.\d+\.\d+/.test(version),
    );
    expect(ranged).toEqual([]);
  });

  it('requires the Node version CI actually provisions', () => {
    expect(manifest.engines?.node).toBe('>=22');
  });
});

describe('the npm install posture', () => {
  it('disables dependency lifecycle scripts for every install', () => {
    // A postinstall runs with the ambient environment of whatever job installed it. release.yml is
    // structured so `npm ci` never shares a job with a push or publish credential; this is the
    // second, unconditional layer.
    expect(readRepoFile('.npmrc')).toMatch(/^ignore-scripts=true$/m);
  });

  it('keeps a committed lockfile so CI installs the reviewed dependency graph', () => {
    const lock = readRepoJson<{ lockfileVersion: number }>('package-lock.json');
    expect(lock.lockfileVersion).toBeGreaterThanOrEqual(3);
  });
});
