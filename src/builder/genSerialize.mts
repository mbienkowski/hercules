/**
 * The ONE generic serializer — descriptor-driven, zero per-ecosystem branches.
 *
 * `DescriptorSerializer` renders any source artifact for any ecosystem from its
 * {@link EcosystemDescriptor}: a named *dispatch* picks the role (agent/command/persona/default),
 * the role's named *mode* shapes the output, and named *field generators* compute frontmatter
 * values — the closed vocabulary `descriptor.mts` validates, implemented as typed TypeScript.
 *
 * Byte-fidelity contracts (pinned by `genSerialize.spec.ts` and the dist drift gate):
 * - `preserve` passes raw frontmatter bytes through untouched, rebuilding ONLY when `model_tier`
 *   is present (in-slot swap for the resolved `model`, omitted when the tier maps to null).
 * - `fields`/`wrap` join `renderFrontmatter(out) + "\n\n" + body`; `preserve` joins the raw block
 *   (ending `---\n`) directly to the body — both blank-line topologies are load-bearing.
 * - Frontmatter values render tokens only where a field says `render: true`; bodies always render.
 * - Body trim policies are exact: `keep` / `lstrip_newlines` / `strip_newlines` (newlines only).
 *
 * `meta`/`tokens`/frontmatter parameters are `ReadonlyMap<string, string>`: insertion order is the
 * emitted key order, and a plain object would reorder any integer-like key ahead of the rest.
 */

import type { EcosystemDescriptor, FieldSpec, RoleSpec } from './descriptor.mjs';
import type { ModelsMap } from './modelMap.mjs';
import { resolve as resolveModel } from './modelMap.mjs';
import { parseFrontmatter, renderFrontmatter, splitDocument } from './parse.mjs';
import { show } from './show.mjs';
import { renderBody } from './render.mjs';

/** Raised when a source artifact is missing frontmatter a target requires. */
export class SerializeError extends Error {
  override readonly name = 'SerializeError';
}

/** Return `meta.get(key)` or throw {@link SerializeError} with a scripted, actionable message. */
export function requireField(meta: ReadonlyMap<string, string>, key: string): string {
  if (!meta.has(key)) {
    const name = meta.get('name') ?? '<unnamed>';
    throw new SerializeError(
      `source artifact ${show(name)} is missing required frontmatter field ${show(key)} ` +
        `— add a '${key}:' line to its frontmatter`,
    );
  }
  return meta.get(key) as string;
}

/** A TOML basic (double-quoted) single-line string: escape backslash then double-quote. */
export function tomlBasic(s: string): string {
  return `"${s.replaceAll('\\', '\\\\').replaceAll('"', '\\"')}"`;
}

/**
 * Escape a body for a TOML multiline basic (`"""…"""`) string: backslash is TOML's escape character
 * (a trailing one would swallow the closing newline) so it is doubled, and a run of three-or-more
 * quotes — which would close the delimiter early — is broken by escaping its third quote. A no-op on
 * today's command bodies; it guards a token that later renders a `\` or `"""` into one.
 */
export function tomlMultiline(s: string): string {
  const escaped = s.replaceAll('\\', '\\\\');
  const out: string[] = [];
  let consecutiveQuotes = 0;
  for (const ch of escaped) {
    if (ch !== '"') {
      consecutiveQuotes = 0;
      out.push(ch);
      continue;
    }
    consecutiveQuotes += 1;
    // Escape every third quote in a run, so `"""` (which would close the delimiter) becomes `""\"`.
    // A 4th/5th quote restarts the count, so a longer run keeps getting broken up the same way.
    if (consecutiveQuotes === 3) {
      out.push('\\"');
      consecutiveQuotes = 0;
    } else {
      out.push(ch);
    }
  }
  return out.join('');
}

/**
 * A TOML custom-command file: a one-line `description` + a multiline `prompt`.
 *
 * The `prompt` uses a TOML multiline basic string whose opening `"""` is followed by a newline
 * (TOML trims that first newline) so the body starts on its own line.
 */
export function tomlCommand(description: string, prompt: string): string {
  return `description = ${tomlBasic(description)}\n\nprompt = """\n${tomlMultiline(prompt)}\n"""\n`;
}

/**
 * Map a `content` path through the descriptor's routes (ordered, first match wins, identity
 * fallback); `null` means the source ships NOTHING on this target (`omit`). Swapped extensions are
 * load-bearing — a wrong one makes the host silently ignore the file — so each ecosystem's route
 * data is pinned by its build tests.
 */
export function dest(descriptor: EcosystemDescriptor, rel: string): string | null {
  for (const route of descriptor.routes) {
    if (route.kind === 'exact' && rel === route.src) return route.dest;
    if (route.kind === 'omit' && rel === route.src) return null;
    if (
      route.kind === 'suffix_swap' &&
      route.prefix !== null && rel.startsWith(route.prefix) &&
      route.fromSuffix !== null && rel.endsWith(route.fromSuffix)
    ) {
      return rel.slice(0, rel.length - route.fromSuffix.length) + route.toSuffix;
    }
  }
  return rel;
}

/** Apply a role's `body` trim policy — newlines only, never general whitespace. */
function applyBodyPolicy(body: string, policy: string): string {
  if (policy === 'lstrip_newlines') return body.replace(/^\n+/, '');
  if (policy === 'strip_newlines') return body.replace(/^\n+/, '').replace(/\n+$/, '');
  return body;
}

/** The source file stem (`commands/build.md` -> `build`) for the `stem` field generator. */
function stemOf(rel: string | null): string | null {
  if (rel === null) return null;
  const base = rel.includes('/') ? (rel.split('/').pop() as string) : rel;
  return base.endsWith('.md') ? base.slice(0, -'.md'.length) : base;
}

/**
 * Evaluate a role's ordered field specs into the output frontmatter map (insertion order IS the
 * emitted key order).
 *
 * Each generator is single-purpose with data operands only (the descriptor vocabulary is closed):
 * `frontmatter` requires its source key and optionally token-renders the value; `stem` emits the
 * source file stem; `stem_prefix` emits a descriptor-supplied prefix plus the source stem; `literal` a static; `primary_mode` the primary/subagent split;
 * `flag_if_name_in` emits its value for the named roles and OMITS the key otherwise.
 */
export function computeFields(
  fields: readonly FieldSpec[],
  meta: ReadonlyMap<string, string>,
  target: string,
  tokens: ReadonlyMap<string, string>,
  stem: string | null = null,
): Map<string, string> {
  const out = new Map<string, string>();
  for (const spec of fields) {
    // Exhaustive over FieldSource (descriptor.mts): a sixth generator added to FieldSchema without
    // a matching case here fails `tsc`, not just the runtime DescriptorError a widened `string`
    // type would have deferred to. See FieldSource's own doc comment for why the type stays narrow.
    switch (spec.source) {
      case 'frontmatter': {
        const value = requireField(meta, spec.field as string);
        out.set(spec.key, spec.render ? renderBody(value, target, tokens) : value);
        break;
      }
      case 'stem': {
        if (stem === null) {
          throw new SerializeError(`field ${show(spec.key)} needs the source file stem, but none was provided`);
        }
        out.set(spec.key, stem);
        break;
      }
      case 'stem_prefix': {
        if (stem === null) {
          throw new SerializeError(`field ${show(spec.key)} needs the source file stem, but none was provided`);
        }
        out.set(spec.key, `${spec.prefix as string}${stem}`);
        break;
      }
      case 'literal':
        out.set(spec.key, spec.value as string);
        break;
      case 'primary_mode':
        out.set(spec.key, meta.get('name') === spec.primary ? 'primary' : 'subagent');
        break;
      case 'flag_if_name_in':
        if (spec.names.includes(meta.get('name') ?? '')) out.set(spec.key, spec.value as string);
        break;
      default:
        spec.source satisfies never;
    }
  }
  return out;
}

/** One serializer instance per ecosystem, wholly driven by its descriptor. */
export class DescriptorSerializer {
  readonly descriptor: EcosystemDescriptor;
  readonly target: string;

  constructor(descriptor: EcosystemDescriptor) {
    this.descriptor = descriptor;
    this.target = descriptor.name;
  }

  // ---- role dispatch (two named dispatchers — the descriptor picks one) ----

  private roleByPath(rel: string | null): string {
    if (rel === 'persona.md') return 'persona';
    if (rel !== null && rel.startsWith('agents/')) return 'agent';
    if (rel !== null && rel.startsWith('commands/')) return 'command';
    return 'default';
  }

  /**
   * OpenCode's shape sniff, verbatim: no frontmatter -> persona; `name` plus a model/tools marker
   * -> agent; Claude's slash-command marker -> command; anything else -> default.
   */
  private roleByFrontmatter(text: string): string {
    const { block } = splitDocument(text);
    if (block === null) return 'persona';
    const { metadata } = parseFrontmatter(block);
    if (metadata.has('name') && (metadata.has('model_tier') || metadata.has('tools'))) return 'agent';
    if (metadata.has('disable-model-invocation')) return 'command';
    return 'default';
  }

  /**
   * An explicitly passed model map wins (the tiering tests inject overrides); otherwise the
   * descriptor's own row serves, keyed under this target.
   */
  private models(models: ModelsMap | null): ModelsMap {
    if (models !== null && Object.hasOwn(models, this.target)) return models;
    return { [this.target]: this.descriptor.models };
  }

  // ---- the Serializer protocol ----

  serializeFile(
    text: string,
    tokens: ReadonlyMap<string, string>,
    models: ModelsMap | null = null,
    rel: string | null = null,
  ): string {
    const d = this.descriptor;
    const role = d.dispatch === 'path' ? this.roleByPath(rel) : this.roleByFrontmatter(text);
    const spec = d.roles[role] as RoleSpec;
    if (spec.mode === 'plain') return renderBody(text, this.target, tokens);
    if (spec.mode === 'wrap') {
      const out = computeFields(spec.fields, new Map(), this.target, tokens);
      return `${renderFrontmatter(out)}\n\n${renderBody(text, this.target, tokens)}`;
    }
    const { block: fmBlock, body } = splitDocument(text);
    // protocols, companion docs, any plain file — every mode passes through
    if (fmBlock === null) return renderBody(text, this.target, tokens);
    const { metadata: meta } = parseFrontmatter(fmBlock);
    if (spec.mode === 'preserve') return this.preserve(spec, fmBlock, meta, body, tokens, models);
    if (spec.mode === 'toml_command') return this.toml(spec, meta, body, tokens);
    return this.fields(spec, meta, body, tokens, stemOf(rel)); // mode === 'fields'
  }

  // ---- mode implementations ----

  /**
   * Raw frontmatter bytes pass through; the block is rebuilt ONLY when `model_tier` is present
   * (in-slot swap — key order preserved, the line vanishing entirely on a null tier). Never
   * round-trip frontmatter that needs no change: that would silently normalise it.
   */
  private preserve(
    spec: RoleSpec, fmBlock: string, meta: ReadonlyMap<string, string>, body: string,
    tokens: ReadonlyMap<string, string>, models: ModelsMap | null,
  ): string {
    for (const key of spec.required) requireField(meta, key);
    let block = fmBlock;
    if (spec.resolveModelTier && meta.has('model_tier')) {
      const out = new Map<string, string>();
      for (const [key, value] of meta) {
        if (key === 'model_tier') {
          const model = resolveModel(this.models(models), this.target, value);
          if (model !== null) out.set('model', model);
        } else {
          out.set(key, value);
        }
      }
      block = `${renderFrontmatter(out)}\n`;
    }
    return block + renderBody(body, this.target, tokens);
  }

  private fields(
    spec: RoleSpec, meta: ReadonlyMap<string, string>, body: string,
    tokens: ReadonlyMap<string, string>, stem: string | null = null,
  ): string {
    const out = computeFields(spec.fields, meta, this.target, tokens, stem);
    const rendered = applyBodyPolicy(renderBody(body, this.target, tokens), spec.body);
    return `${renderFrontmatter(out)}\n\n${rendered}`;
  }

  private toml(spec: RoleSpec, meta: ReadonlyMap<string, string>, body: string, tokens: ReadonlyMap<string, string>): string {
    const out = computeFields(spec.fields, meta, this.target, tokens);
    const prompt = applyBodyPolicy(renderBody(body, this.target, tokens), spec.body);
    return tomlCommand(out.get('description') as string, prompt);
  }

  // ---- role-direct sugar (the per-role entry points tests and generators call) ----

  /**
   * Serialize `frontmatter`/`body` through the agent role, joined `fm + "\n\n" + body`.
   *
   * For a `preserve` agent role the frontmatter is rebuilt from the map (the sugar has no raw
   * bytes) — identical output for any in-order source, which the roundtrip gate pins.
   */
  serializeAgent(
    frontmatter: ReadonlyMap<string, string>, body: string, tokens: ReadonlyMap<string, string>,
    models: ModelsMap | null = null,
  ): string {
    return this.roleDirect('agent', frontmatter, body, tokens, models, null);
  }

  serializeCommand(
    frontmatter: ReadonlyMap<string, string>, body: string, tokens: ReadonlyMap<string, string>,
    stem: string | null = null,
  ): string {
    return this.roleDirect('command', frontmatter, body, tokens, null, stem);
  }

  serializePersona(text: string, tokens: ReadonlyMap<string, string>): string {
    const spec = this.descriptor.roles['persona'] as RoleSpec;
    if (spec.mode === 'wrap') {
      const out = computeFields(spec.fields, new Map(), this.target, tokens);
      return `${renderFrontmatter(out)}\n\n${renderBody(text, this.target, tokens)}`;
    }
    return renderBody(text, this.target, tokens);
  }

  private roleDirect(
    role: string, meta: ReadonlyMap<string, string>, body: string, tokens: ReadonlyMap<string, string>,
    models: ModelsMap | null, stem: string | null,
  ): string {
    const spec = this.descriptor.roles[role] as RoleSpec;
    if (spec.mode === 'toml_command') return this.toml(spec, meta, body, tokens);
    if (spec.mode === 'preserve') {
      for (const key of spec.required) requireField(meta, key);
      const out = new Map<string, string>();
      for (const [key, value] of meta) {
        if (key === 'model_tier' && spec.resolveModelTier) {
          const model = resolveModel(this.models(models), this.target, value);
          if (model !== null) out.set('model', model);
        } else {
          out.set(key, value);
        }
      }
      return `${renderFrontmatter(out)}\n\n${renderBody(body, this.target, tokens)}`;
    }
    return this.fields(spec, meta, body, tokens, stem);
  }
}
