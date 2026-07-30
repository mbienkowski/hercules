import { defineConfig } from 'vitest/config';

/**
 * The live-CLI smoke gate, run by `make test-smoke`.
 *
 * The default config excludes `src/builder/tests/smoke/**` because those specs launch the real host
 * binaries: their runtime tracks network, npm cache and machine load rather than the code under test,
 * and a flaky spec in the default run makes every single-run result untrustworthy — one produced a
 * false "the guard caught it" verdict during a mutation audit here. That exclusion also beats an
 * explicit file list on the command line, so this gate needs a config of its own.
 *
 * Declared standalone rather than merged from the base config: `mergeConfig` concatenates arrays, so
 * merging would union this `include` with the base one and quietly run the whole suite instead.
 *
 * No coverage thresholds: six specs cannot speak to a repo-wide percentage, so measuring one here
 * would fail every run while saying nothing about what these specs exercised.
 */
export default defineConfig({
  test: {
    include: ['src/builder/tests/smoke/**/*.spec.ts'],
    exclude: ['node_modules/**', 'dist/**', '.ts-out/**'],
    root: import.meta.dirname,
    // Installing into a real CLI and launching it is minutes, not seconds, on a cold cache.
    testTimeout: 180_000,
  },
});
