/**
 * Render a value inside a build-error message (TS-native).
 *
 * Compiler diagnostics only — these strings are shown when a descriptor or source file is malformed
 * at build time and never reach `dist/`, so plain JSON is the right, honest formatting: a string
 * becomes `"x"`, a list `["a","b"]`, a boolean `true`, absence `null`. `JSON.stringify` returns
 * `undefined` for a value it cannot encode (a function, a symbol), so fall back to `String` to keep
 * this total.
 */
export function show(value: unknown): string {
  return JSON.stringify(value) ?? String(value);
}
