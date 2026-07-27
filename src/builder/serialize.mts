/**
 * The serializer registry — populated from the ecosystem descriptors, zero per-ecosystem classes.
 *
 * Every registered serializer is the ONE generic {@link DescriptorSerializer}, constructed from its
 * `ecosystems/<name>.json`. {@link buildRegistry} is an explicit FACTORY, never a module-scope
 * bootstrap loop, so a bare `import` of this module never touches the filesystem — `cli.mts`'s
 * composition root calls `buildRegistry(discover(...))`. A new descriptor file needs no new class.
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
 * A registry instance — deliberately NOT a module-scope singleton: each caller builds and owns its
 * own, so a test can register a stub target with no shared, order-dependent state leaking between them.
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
