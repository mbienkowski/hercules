import { beforeEach, describe, expect, it, vi } from 'vitest';

// A SEPARATE spec file, deliberately: vi.mock('node:fs') is module-scoped and hoisted (see
// descriptorSort.spec.ts), so it must live alone. cli.mts's composition-root functions must be plain
// functions, never import-time constants — a stray top-level `discover()`/`readdirSync()` in
// cli.mts, serialize.mts, or their imports fails this test on the IMPORT line itself.
vi.mock('node:fs', async (importOriginal) => {
  const actual = await importOriginal<typeof import('node:fs')>();
  const spied: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(actual)) {
    spied[key] = typeof value === 'function' ? vi.fn(value as (...a: unknown[]) => unknown) : value;
  }
  return spied;
});

describe('importing the compiler entry points performs zero filesystem syscalls', () => {
  // The mocked node:fs module and its call history are shared across both `it` blocks: ES-module
  // caching returns the SAME mock instance, so one test's calls would otherwise leak into the next.
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('cli.mts', async () => {
    const fs = await import('node:fs');
    await import('../../bin/cli.mjs');
    for (const [name, fn] of Object.entries(fs)) {
      if (typeof fn === 'function' && 'mock' in fn) {
        expect(fn, `node:fs.${name} was called during import`).not.toHaveBeenCalled();
      }
    }
  });

  it('serialize.mts, imported on its own', async () => {
    vi.resetModules();
    const fs = await import('node:fs');
    await import('../../serialize.mjs');
    for (const [name, fn] of Object.entries(fs)) {
      if (typeof fn === 'function' && 'mock' in fn) {
        expect(fn, `node:fs.${name} was called during import`).not.toHaveBeenCalled();
      }
    }
  });
});
