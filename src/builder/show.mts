/**
 * Render a value inside a build-error message: plain JSON (`"x"`, `["a","b"]`, `true`, `null`).
 *
 * Compiler diagnostics only — these strings never reach `dist/`. `JSON.stringify` returns `undefined`
 * for a value it cannot encode (a function, a symbol), so `String` keeps this total.
 */
export function show(value: unknown): string {
  return JSON.stringify(value) ?? String(value);
}
