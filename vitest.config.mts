import { defineConfig } from 'vitest/config';

// Hercules holds itself to >= 90% BRANCH coverage — the same bar it enforces on its users, and the
// same number the Python side gates at via pytest-cov (see the Makefile's test-py target). Branch,
// not line: a line-coverage gate passes on code whose conditionals were never both-way exercised.
export default defineConfig({
  test: {
    include: ['tests-ts/**/*.spec.ts'],
    // dist/ is committed build output and node_modules/ is vendored; neither holds our specs.
    exclude: ['node_modules/**', 'dist/**', '.ts-out/**'],
    // Scopes spec DISCOVERY to this directory. It does not change the process working directory —
    // specs resolve repo paths from cwd via tests-ts/support/repo.ts, which documents why every
    // supported entry point already runs from the repo root.
    root: import.meta.dirname,
    coverage: {
      provider: 'v8',
      include: ['scripts-ts/**/*.ts'],
      // scripts-ts/bin/ holds logic-free process entry points — a few lines that resolve a path and
      // call process.exit. They are exercised by `make mutation-ts` and `make build`, not by unit
      // specs, and counting them would push the gate toward testing process.exit wiring instead of
      // logic. stryker.conf.json excludes the same directory for the same reason; keep the two
      // exclusions in step.
      exclude: ['scripts-ts/**/*.d.ts', 'scripts-ts/bin/**'],
      reporter: ['text', 'json-summary'],
      thresholds: {
        branches: 90,
        functions: 90,
        lines: 90,
        statements: 90,
      },
    },
  },
});
