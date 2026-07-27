import { beforeEach, describe, expect, it, vi } from 'vitest';

// A SEPARATE spec file, deliberately — vi.mock('node:fs') is module-scoped and hoisted (see
// descriptorSort.spec.ts for the fuller rationale), so it must live alone to avoid spying on every
// other test's real filesystem calls.
//
// Proves the migration spec's few-shot catalogue item #5 directly: cli.mts's composition-root
// functions (targets/buildTarget/checkTarget/main) must be plain functions, never module-scope
// constants computed at import time — Python's cli.py:35 (`TARGETS = tuple(descriptor.names())`)
// and serialize.py:58-59 (`for _descriptor in discover().values(): register(...)`) both run a full
// filesystem scan as a side effect of a bare `import`. A regression here (a stray top-level
// `discover()`/`readdirSync()`/etc. call reintroduced into cli.mts, serialize.mts, or any module
// they import) would make this test fail on the IMPORT line itself, before any test body runs.
vi.mock('node:fs', async (importOriginal) => {
  const actual = await importOriginal<typeof import('node:fs')>();
  const spied: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(actual)) {
    spied[key] = typeof value === 'function' ? vi.fn(value as (...a: unknown[]) => unknown) : value;
  }
  return spied;
});

describe('importing the compiler entry points performs zero filesystem syscalls', () => {
  // The mocked node:fs module (and its per-function call history) is shared across both `it`
  // blocks below — ESM module caching means `import('node:fs')` returns the SAME mock instance
  // each time, so a call recorded by one test would otherwise still be visible to the next.
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
