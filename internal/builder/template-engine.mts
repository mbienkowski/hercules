/**
 * The one template engine instance, configured here and nowhere else.
 *
 * Strict mode is the safety story: an undeclared variable throws instead of rendering nothing, so a
 * mistyped condition cannot pass for a paragraph that was meant to be absent. It fires only on an
 * ABSENT key — a key present with `null` renders silently, which is why the scope deletes instead.
 */

import { Liquid } from 'liquidjs';

/** A fresh engine. No filters, no globals, no caches shared between builds. */
export function createTemplateEngine(): Liquid {
  return new Liquid({ strictVariables: true, strictFilters: true });
}
