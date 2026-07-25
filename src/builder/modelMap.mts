/**
 * Tier -> per-target model resolution (pure).
 *
 * Each ecosystem descriptor's `models` maps a model tier (`high|medium|low`) to a per-target value.
 * A missing tier falls back toward HIGHER capability (`low` -> `medium` -> `high`). A `null` value
 * is first-class and means **omit the field** — which is why the return type is `string | null` and
 * the lookup tests for key PRESENCE rather than truthiness.
 */

export const TIER_FALLBACK = ['high', 'medium', 'low'] as const;

export type Tier = (typeof TIER_FALLBACK)[number];

/** A per-target tier map. A present key with a `null` value means "omit the field". */
export type TierMap = Readonly<Record<string, string | null>>;

export type ModelsMap = Readonly<Record<string, TierMap>>;

/** Raised on an unknown tier or an unconfigured target. */
export class ModelMapError extends Error {
  override readonly name = 'ModelMapError';
}

function isTier(value: string): value is Tier {
  return (TIER_FALLBACK as readonly string[]).includes(value);
}

/**
 * The model id for `target`/`tier`, falling back toward higher tiers when unset.
 *
 * Returns `null` when the resolved value is `null` (field omitted) or no tier is configured.
 * Throws {@link ModelMapError} on an unknown `tier` or a `target` absent from `models`.
 */
export function resolve(models: ModelsMap, target: string, tier: string): string | null {
  if (!isTier(tier)) throw new ModelMapError(`unknown tier: '${tier}'`);
  if (!Object.hasOwn(models, target)) {
    throw new ModelMapError(`target not configured in any models map: '${target}'`);
  }

  const tierMap = models[target] as TierMap;
  const index = TIER_FALLBACK.indexOf(tier);
  // Requested tier first, then every HIGHER tier, nearest first.
  const order = [tier, ...TIER_FALLBACK.slice(0, index).reverse()];

  for (const candidate of order) {
    // Presence, not truthiness: a configured `null` means "omit the field" and must stop the
    // fallback here rather than falling through to a higher tier's model.
    if (Object.hasOwn(tierMap, candidate)) return tierMap[candidate] ?? null;
  }
  return null;
}
