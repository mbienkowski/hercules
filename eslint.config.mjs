// Complexity gate for the TypeScript domains — the `make complexity-scan` half that mirrors, in
// the Node runtime, the same ceilings the Python hooks are held to (src/hooks, via flake8 —
// see the Makefile's `complexity-scan` target and CODE_OF_CONDUCT.md § Complexity).
//
// This config lints ONLY complexity: it deliberately enables no style, correctness, or type-aware
// rules, so it never competes with formatting and never needs TypeScript type information (both
// rules below are purely syntactic — the parser is here only to read `.mts`). Two metrics, one
// ceiling of 15 each:
//   - `complexity`                 — McCabe cyclomatic (independent paths through a function).
//   - `sonarjs/cognitive-complexity` — SonarSource cognitive complexity, which penalises NESTING;
//                                      this is the metric that catches "a junior can't follow the
//                                      nested loops", and 15 is SonarQube's own default.
//
// Tests are excluded on purpose: a table-driven, assertion-dense spec is legitimately branchy and
// is not shipped. The gate guards the product code a maintainer has to read under pressure.

import parser from '@typescript-eslint/parser';
import sonarjs from 'eslint-plugin-sonarjs';

const CEILING = 15;

export default [
  {
    // The three executable TypeScript domains (the compiler, the release tooling, the metrics),
    // ESM `.mts` throughout. dist/, .ts-out/ and node_modules/ carry no source and are left out.
    files: ['src/builder/**/*.mts', 'src/release/**/*.mts', 'src/metrics/**/*.mts'],
    ignores: ['**/tests/**'],
    languageOptions: { parser, sourceType: 'module' },
    plugins: { sonarjs },
    rules: {
      complexity: ['error', CEILING],
      'sonarjs/cognitive-complexity': ['error', CEILING],
    },
  },
];
