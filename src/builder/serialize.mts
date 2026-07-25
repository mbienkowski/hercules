/**
 * The serializer registry — populated from the ecosystem descriptors, zero per-ecosystem classes.
 *
 * Every registered serializer is the ONE generic {@link DescriptorSerializer}, constructed from its
 * `ecosystems/<name>.json`. Unlike the Python original, {@link buildRegistry} is an explicit
 * FACTORY rather than a module-scope bootstrap loop — `serialize.py:58-59` runs a full filesystem
 * scan (`discover()`) as a side effect of `import serialize`, which the migration spec's few-shot
 * catalogue (#5) names directly as a pattern NOT to replicate: a bare `import` must never touch the
 * filesystem. `cli.mts`'s composition root calls `buildRegistry(discover(...))` explicitly instead.
 * A 7th descriptor file still needs no new serializer class — only a new call to `discover()`.
 */

import type { EcosystemDescriptor } from './descriptor.mjs';
import { DescriptorSerializer, SerializeError } from './genSerialize.mjs';
import type { ModelsMap } from './modelMap.mjs';

export { DescriptorSerializer, SerializeError, requireField } from './genSerialize.mjs';

/** Turns a source `(frontmatter, body)` into one target's output text. */
export interface SerializerLike {
  readonly target: string;
  serializeAgent(
    frontmatter: ReadonlyMap<string, string>,
    body: string,
    tokens: ReadonlyMap<string, string>,
    models: ModelsMap,
  ): string;
  serializeFile(
    text: string,
    tokens: ReadonlyMap<string, string>,
    models: ModelsMap,
    rel?: string | null,
  ): string;
}

/**
 * A registry instance — deliberately NOT a module-scope singleton (unlike Python's `_REGISTRY`
 * dict): each caller builds and owns its own, so tests can register a stub target without any
 * shared, order-dependent global state leaking between them.
 */
export interface Registry {
  /** Register `serializer` under its `.target` key; returns it (usable as a decorator). */
  register<T extends SerializerLike>(serializer: T): T;
  /** The registered serializer for `target`; throws {@link SerializeError} if absent. */
  get(target: string): SerializerLike;
  /** The sorted list of registered target keys. */
  registeredTargets(): string[];
  /** Serialize `text` for `target` using its registered serializer. */
  serializeFile(
    target: string,
    text: string,
    tokens: ReadonlyMap<string, string>,
    models: ModelsMap,
    rel?: string | null,
  ): string;
}

/** Build a registry with one generic `DescriptorSerializer` per descriptor, already registered. */
export function buildRegistry(descriptors: readonly EcosystemDescriptor[]): Registry {
  const table = new Map<string, SerializerLike>();

  const registry: Registry = {
    register<T extends SerializerLike>(serializer: T): T {
      table.set(serializer.target, serializer);
      return serializer;
    },
    get(target: string): SerializerLike {
      const found = table.get(target);
      if (found === undefined) throw new SerializeError(`no serializer registered for target: '${target}'`);
      return found;
    },
    registeredTargets(): string[] {
      return [...table.keys()].sort();
    },
    serializeFile(target, text, tokens, models, rel = null): string {
      return registry.get(target).serializeFile(text, tokens, models, rel);
    },
  };

  for (const descriptor of descriptors) registry.register(new DescriptorSerializer(descriptor));
  return registry;
}
