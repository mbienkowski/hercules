import { defineConfig } from 'vitest/config';

// Hercules holds itself to >= 90% branch coverage, the same bar it enforces on its users and the
// same number pytest-cov gates at. Branch, not line: line coverage passes on untested conditionals.
export default defineConfig({
  test: {
    include: ['src/{builder,release,metrics,content}/tests/**/*.spec.ts'],
    // dist/ is committed build output and node_modules/ is vendored; neither holds our specs.
    exclude: ['node_modules/**', 'dist/**', '.ts-out/**'],
    // Scopes spec discovery to this directory without changing the process working directory —
    // specs resolve repo paths from cwd via src/commons/support/repo.ts.
    root: import.meta.dirname,
    // Build-driving specs render all six targets; 5s (the default) is a false failure under load.
    testTimeout: 30_000,
    coverage: {
      provider: 'v8',
      include: ['src/builder/**/*.mts', 'src/release/**/*.mts', 'src/metrics/**/*.mts'],
      // Every domain's bin/ holds logic-free process entry points, exercised by `make build` rather
      // than unit specs. stryker.conf.json excludes the same directories; keep the two in step.
      exclude: [
        'src/builder/**/*.d.mts', 'src/release/**/*.d.mts', 'src/metrics/**/*.d.mts',
        'src/builder/bin/**', 'src/release/bin/**',
      ],
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
