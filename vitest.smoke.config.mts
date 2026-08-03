import { defineConfig } from 'vitest/config';

// The live-CLI smoke gate, run by `make test-smoke`. Standalone, not merged from the base config —
// `mergeConfig` concatenates arrays, so a merge would union the two `include`s and run the whole suite.
export default defineConfig({
  test: {
    include: [
      'tests/dist/**/smoke.spec.ts', 'tests/dist/universalSmoke.spec.ts',
    ],
    exclude: ['node_modules/**', 'dist/**', '.local/**'],
    root: import.meta.dirname,
    // Installing into a real CLI and launching it is minutes, not seconds, on a cold cache.
    testTimeout: 180_000,
  },
});
