import { defineConfig } from 'vitest/config';

// The default gate: every TypeScript spec except the ones that launch a real host CLI.
export default defineConfig({
  test: {
    include: ['tests/{builder,release,budgets,content}/**/*.spec.ts', 'tests/dist/**/*.spec.ts'],
    // Only specs that launch a host binary are excluded — one was measured timing out at 48s — and
    // they keep their own gate in vitest.smoke.config.mts. dist/ and node_modules/ hold no specs.
    exclude: [
      'node_modules/**', 'dist/**', '.local/**',
      'tests/dist/**/smoke.spec.ts', 'tests/dist/universalSmoke.spec.ts',
    ],
    // Scopes discovery without changing cwd — specs resolve repo paths from it via support/repo.ts.
    root: import.meta.dirname,
    // Build-driving specs render all seven targets; 5s (the default) is a false failure under load.
    testTimeout: 30_000,
    coverage: {
      provider: 'v8',
      include: ['internal/builder/**/*.mts', 'internal/release/**/*.mts', 'tests/budgets/**/*.mts'],
      // Each bin/ holds logic-free entry points, exercised by `make build`. stryker.conf.json
      // excludes the same directories; keep the two in step.
      exclude: [
        'internal/builder/**/*.d.mts', 'internal/release/**/*.d.mts', 'tests/budgets/**/*.d.mts',
        'internal/builder/bin/**', 'internal/release/bin/**',
      ],
      reporter: ['text', 'json-summary'],
      // All transient tool output lives under one gitignored /.local/ tree (see .gitignore).
      reportsDirectory: '.local/coverage',
      thresholds: { statements: 80, branches: 80, functions: 80, lines: 80 },
    },
  },
});
