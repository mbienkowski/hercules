import { describe, expect, it, vi } from 'vitest';

/**
 * Importing `bin/recipe.mts` touches the filesystem ZERO times — every scan happens inside a call
 * from `main()`. The whole of `node:fs` is mocked, so ANY filesystem call fails this.
 */

// `then` and the module-shape keys are probed by the ESM loader itself on every dynamic import —
// they are the runtime asking "is this a thenable?", not the build reading a file.
const NOT_A_CALL = new Set(['then', 'default', '__esModule']);

vi.mock('node:fs', () => new Proxy({}, {
  get: (_target, property: string) => {
    if (typeof property !== 'string' || NOT_A_CALL.has(property)) return undefined;
    return (...args: unknown[]) => {
      throw new Error(
        `importing the build entry point called fs.${property}(${JSON.stringify(args[0])}) at module `
          + 'scope — every scan belongs inside a call from main(), the composition root',
      );
    };
  },
}));

describe('the build entry point is pure to import', () => {
  it('reads nothing from disk until something calls it', async () => {
    const entry = await import('../../../internal/builder/build.mjs');
    // Every module it pulls in is evaluated too; a read initialising a constant throws on the mock.
    expect(typeof entry.main).toBe('function');
    expect(typeof entry.parseCommandLine).toBe('function');
  });

  it('still parses its arguments with no filesystem at all', async () => {
    // Real work happens, so the guard above is not passing on a cached, unexecuted module.
    const { parseCommandLine } = await import('../../../internal/builder/build.mjs');
    expect(parseCommandLine(['--target', 'cursor', '--check'])).toEqual({ target: 'cursor', check: true });
  });
});
