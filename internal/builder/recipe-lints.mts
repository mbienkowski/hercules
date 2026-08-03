/**
 * Seven checks over every recipe and every source it names, run before a byte is rendered.
 *
 * The strict engine already refuses an undeclared variable, but one at a time, from inside a
 * template, about a file it cannot name. These answer the same questions across all seven
 * distributions at once, naming the configuration, the entry, the source and the variable.
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import type { Recipe } from './recipe-loader.mjs';
import { buildVariableScope, type VariableValue } from './variable-scope.mjs';
import { readCanonicalVersion } from '../release/version-files.mjs';

/** Raised when the recipes and the sources they name disagree with each other. */
export class LintError extends Error {
  override readonly name = 'LintError';
}

/** One recipe, with the file it was read from. */
export interface NamedRecipe {
  readonly file: string;
  readonly recipe: Recipe;
}

interface Token {
  readonly kind: 'tag' | 'output';
  readonly inner: string;
  readonly trimLeft: boolean;
  readonly trimRight: boolean;
  readonly start: number;
  readonly end: number;
  readonly line: number;
}

const TOKEN = /\{([{%])(-?)([\s\S]*?)(-?)([%}])\}/g;
const NAME = /^[a-z][a-z0-9_]*$/;
const CONDITION = /^([a-z][a-z0-9_]*)(?:\s*==\s*"([^"]*)")?$/;

function lineAt(text: string, index: number): number {
  let line = 1;
  for (let i = 0; i < index; i += 1) if (text[i] === '\n') line += 1;
  return line;
}

/** Every `{{ … }}` and `{% … %}` in `text`, in order. */
function tokenize(text: string): Token[] {
  const out: Token[] = [];
  TOKEN.lastIndex = 0;
  let match: RegExpExecArray | null = TOKEN.exec(text);
  while (match !== null) {
    const [whole, open, left, inner, right, close] =
      match as unknown as [string, string, string, string, string, string];
    // `{{ … %}` and `{% … }}` are neither: reported by the caller's grammar check as the malformed
    // things they are, rather than silently classified as whichever end happened to be read first.
    if ((open === '{') !== (close === '}')) {
      throw new LintError(
        `mismatched delimiters in '${whole}' — a substitution is '{{ … }}' and a tag is '{% … %}'`,
      );
    }
    out.push({
      kind: open === '%' ? 'tag' : 'output',
      inner: inner.trim(),
      trimLeft: left === '-',
      trimRight: right === '-',
      start: match.index,
      end: match.index + whole.length,
      line: lineAt(text, match.index),
    });
    match = TOKEN.exec(text);
  }
  return out;
}

/** The character ranges covered by fenced code blocks. */
function fencedRanges(text: string): Array<[number, number]> {
  const ranges: Array<[number, number]> = [];
  const fence = /^ {0,3}(`{3,}|~{3,})/gm;
  let open: number | null = null;
  let match: RegExpExecArray | null = fence.exec(text);
  while (match !== null) {
    if (open === null) open = match.index;
    else {
      ranges.push([open, match.index + match[0].length]);
      open = null;
    }
    match = fence.exec(text);
  }
  if (open !== null) ranges.push([open, text.length]);
  return ranges;
}

// Half-open. `<=` is an equivalent mutant: `b` lands on the newline ending a fence line, where no
// tag can begin.
function inRanges(ranges: ReadonlyArray<readonly [number, number]>, index: number): boolean {
  return ranges.some(([a, b]) => index >= a && index < b);
}

// ---- the block structure a source declares ----

/** One branch of one conditional block: which condition selects it, and where its body sits. */
export interface Branch {
  /** `null` for `{% else %}` — the branch taken when no earlier condition matched. */
  readonly variable: string | null;
  /** `null` when the condition is a bare truthiness test. */
  readonly literal: string | null;
  readonly line: number;
}

/** One `{% if %}…{% endif %}` block. */
export interface Block {
  readonly branches: readonly Branch[];
  readonly line: number;
}

function parseCondition(inner: string, keyword: string, file: string, line: number): Branch {
  const condition = inner.slice(keyword.length).trim();
  const match = CONDITION.exec(condition);
  if (match === null) {
    throw new LintError(
      `${file}:${line}: '{% ${inner} %}' is not a permitted condition. The vocabulary is equality ` +
        'and nothing else: `{% if name %}` or `{% if name == "value" %}`. `unless`, `and`, `or`, ' +
        '`!=`, `case` and filters are deliberately absent — a condition says "this value, or not ' +
        'this value", so a configuration stays data.',
    );
  }
  return { variable: match[1] as string, literal: match[2] ?? null, line };
}

/**
 * The conditional blocks in `text`, and every variable it mentions.
 *
 * Fenced code is parsed like any other text — the engine renders it either way. A fence only changes
 * the advice on a failure, since a malformed tag there is more likely a quotation than a mistake.
 */
export function parseTemplateStructure(text: string, file: string): { blocks: Block[]; mentions: Set<string> } {
  const blocks: Block[] = [];
  const mentions = new Set<string>();
  const stack: Array<{ branches: Branch[]; line: number }> = [];
  const fences = fencedRanges(text);
  const quoted = (token: Token): string => (inRanges(fences, token.start)
    ? ' It sits inside a fenced code block — if this is an EXAMPLE of syntax rather than something ' +
      'to render, wrap the fence in `{% raw %}` … `{% endraw %}`.'
    : '');
  let inRaw = false;
  for (const token of tokenize(text)) {
    if (token.kind === 'output') {
      if (inRaw) continue;
      if (!NAME.test(token.inner)) {
        throw new LintError(
          `${file}:${token.line}: '{{ ${token.inner} }}' is not a permitted substitution. Only a ` +
            `bare lower-snake variable name is allowed — no filters, no paths, no expressions.${quoted(token)}`,
        );
      }
      mentions.add(token.inner);
      continue;
    }
    const inner = token.inner;
    if (inner === 'raw') { inRaw = true; continue; }
    if (inner === 'endraw') { inRaw = false; continue; }
    if (inRaw) continue;
    if (inner.startsWith('if ')) {
      stack.push({ branches: [parseCondition(inner, 'if', file, token.line)], line: token.line });
      continue;
    }
    if (inner.startsWith('elsif ')) {
      const top = stack[stack.length - 1];
      if (top === undefined) throw new LintError(`${file}:${token.line}: '{% ${inner} %}' with no open '{% if %}'`);
      top.branches.push(parseCondition(inner, 'elsif', file, token.line));
      continue;
    }
    if (inner === 'else') {
      const top = stack[stack.length - 1];
      if (top === undefined) throw new LintError(`${file}:${token.line}: '{% else %}' with no open '{% if %}'`);
      top.branches.push({ variable: null, literal: null, line: token.line });
      continue;
    }
    if (inner === 'endif') {
      const top = stack.pop();
      if (top === undefined) throw new LintError(`${file}:${token.line}: '{% endif %}' with no open '{% if %}'`);
      blocks.push({ branches: top.branches, line: top.line });
      continue;
    }
    throw new LintError(
      `${file}:${token.line}: '{% ${inner} %}' is not a permitted tag. The vocabulary is ` +
        `\`if\` / \`elsif\` / \`else\` / \`endif\` / \`raw\` / \`endraw\` — nothing else.${quoted(token)}`,
    );
  }
  if (stack.length > 0) {
    throw new LintError(`${file}:${(stack[0] as { line: number }).line}: '{% if %}' is never closed`);
  }
  if (inRaw) throw new LintError(`${file}: '{% raw %}' is never closed`);
  for (const block of blocks) {
    for (const branch of block.branches) if (branch.variable !== null) mentions.add(branch.variable);
  }
  return { blocks, mentions };
}


// ---- the individual lints ----

/** Block tags stand alone on their lines, and a trim mark removes exactly one newline. */
export function lintTrimMarks(text: string, file: string): string[] {
  const problems: string[] = [];
  const fences = fencedRanges(text);
  for (const token of tokenize(text)) {
    if (token.kind === 'output' || inRanges(fences, token.start)) continue;
    if (token.inner === 'raw' || token.inner === 'endraw') continue;
    const before = text.slice(0, token.start);
    const after = text.slice(token.end);
    const where = `${file}:${token.line}: '{% ${token.inner} %}'`;
    if (!/(^|\n)[ \t]*$/.test(before)) {
      problems.push(`${where} shares its line with other text — a block tag stands alone on its line.`);
    }
    if (!/^[ \t]*(\n|$)/.test(after)) {
      problems.push(`${where} is followed by text on the same line — a block tag stands alone on its line.`);
    }
    if (token.trimLeft && /\n[ \t]*\n[ \t]*$/.test(before)) {
      problems.push(
        `${where} carries a left trim mark ('{%-') but a BLANK line precedes it, so the trim would ` +
          'swallow the blank line as well as the tag\'s own newline. Drop the blank line, or drop the trim mark.',
      );
    }
    if (token.trimRight && /^[ \t]*\n[ \t]*\n/.test(after)) {
      problems.push(
        `${where} carries a right trim mark ('-%}') but a BLANK line follows it, so the trim would ` +
          'swallow the blank line as well as the tag\'s own newline. Drop the blank line, or drop the trim mark.',
      );
    }
  }
  return problems;
}

/**
 * A control tag inside a fenced code block must be wrapped in `{% raw %}`.
 *
 * The line is between substituting and executing: `{{ path }}` in an example is wanted, a `{% if %}`
 * would be RUN, and in a project that teaches its own syntax it is nearly always a quotation.
 */
function lintStrayTags(text: string, file: string): string[] {
  const problems: string[] = [];
  const fences = fencedRanges(text);
  const raw: Array<[number, number]> = [];
  let openRaw: number | null = null;
  for (const token of tokenize(text)) {
    if (token.kind !== 'tag') continue;
    if (token.inner === 'raw') openRaw = token.start;
    else if (token.inner === 'endraw' && openRaw !== null) { raw.push([openRaw, token.end]); openRaw = null; }
  }
  for (const token of tokenize(text)) {
    if (token.kind !== 'tag') continue;
    if (token.inner === 'raw' || token.inner === 'endraw') continue;
    if (!inRanges(fences, token.start) || inRanges(raw, token.start)) continue;
    problems.push(
      `${file}:${token.line}: '{% ${token.inner} %}' sits inside a fenced code block without ` +
        '`{% raw %}`. Liquid has never heard of markdown, so it would RUN this rather than show it. ' +
        'Wrap the fence in `{% raw %}` … `{% endraw %}` to quote it. (A `{{ substitution }}` in a ' +
        'fence is fine — an example should show the real path.)',
    );
  }
  return problems;
}

// ---- the cross-configuration lints ----

/** One rendering context: a source as rendered by one entry of one recipe. */
interface Context {
  readonly file: string;
  readonly dest: string;
  readonly source: string;
  readonly scope: Readonly<Record<string, string | boolean>>;
}

function contexts(recipes: readonly NamedRecipe[], version: string): Context[] {
  const out: Context[] = [];
  for (const { file, recipe } of recipes) {
    for (const [dest, entry] of Object.entries(recipe.targets)) {
      if (entry === null) continue;
      // `version` as the build injects it, so the lints see the scope a render will see.
      const scope = buildVariableScope({ version, ...recipe.variables }, entry.variables ?? {});
      for (const source of entry.sources) out.push({ file, dest, source, scope });
    }
  }
  return out;
}

/** Does `branch` select, given `scope`? Mirrors Liquid: only `false` and absence are falsy. */
function selects(branch: Branch, scope: Readonly<Record<string, string | boolean>>): boolean {
  if (branch.variable === null) return true; // `{% else %}`
  const value = scope[branch.variable];
  if (value === undefined) return false;
  if (branch.literal === null) return value !== false;
  return value === branch.literal;
}

/** Every value any recipe assigns to `name`, anywhere. */
function assignedValues(recipes: readonly NamedRecipe[], name: string): Set<string | boolean> {
  const out = new Set<string | boolean>();
  for (const { recipe } of recipes) {
    const global: VariableValue | undefined = recipe.variables[name];
    if (global !== undefined && global !== null) out.add(global);
    for (const entry of Object.values(recipe.targets)) {
      const value = entry?.variables?.[name];
      if (value !== undefined && value !== null) out.add(value);
    }
  }
  return out;
}

/** Every lint over every recipe, throwing with ALL problems at once rather than the first. */
export function lintRecipes(recipes: readonly NamedRecipe[], repoRoot: string): void {
  if (recipes.length === 0) {
    throw new LintError('no recipes to lint — a check with nothing to inspect passes forever; refusing');
  }
  const all = contexts(recipes, readCanonicalVersion(repoRoot));
  if (all.length === 0) {
    throw new LintError('no source is rendered by any recipe — refusing to report a clean bill of health');
  }
  const problems: string[] = [];
  const sources = [...new Set(all.map((c) => c.source))].sort();
  const blocksPerSource = new Map<string, Block[]>();
  const namesPerSource = new Map<string, Set<string>>();

  for (const source of sources) {
    const text = readFileSync(join(repoRoot, source), 'utf-8');
    // A grammar violation throws rather than joining the list — the rest would be guesswork.
    const { blocks, mentions } = parseTemplateStructure(text, source);
    blocksPerSource.set(source, blocks);
    namesPerSource.set(source, mentions);
    problems.push(...lintTrimMarks(text, source), ...lintStrayTags(text, source));
  }

  // undeclared variable, per rendering context
  for (const ctx of all) {
    for (const name of namesPerSource.get(ctx.source) ?? []) {
      if (!Object.hasOwn(ctx.scope, name)) {
        problems.push(
          `${ctx.file} → '${ctx.dest}' ← ${ctx.source}: You mentioned a variable that is not set in ` +
            `context for this ecosystem: '${name}'. Declared here: ` +
            `${Object.keys(ctx.scope).sort().join(', ') || '(none)'}.`,
        );
      }
    }
  }

  // a variable used in a CONDITION must be declared by every recipe rendering that source
  for (const source of sources) {
    const conditional = new Set<string>();
    for (const block of blocksPerSource.get(source) ?? []) {
      for (const branch of block.branches) if (branch.variable !== null) conditional.add(branch.variable);
    }
    for (const name of [...conditional].sort()) {
      const absent = all
        .filter((c) => c.source === source && !Object.hasOwn(c.scope, name))
        .map((c) => c.file);
      for (const file of [...new Set(absent)].sort()) {
        problems.push(
          `${file}: '${source}' branches on '${name}', but this configuration does not declare it. ` +
            'A conditional variable is declared by EVERY configuration that renders the source — ' +
            'with `false` when the branch is not wanted, never by omission.',
        );
      }
    }
  }

  // every compared literal is a value some configuration assigns
  for (const source of sources) {
    for (const block of blocksPerSource.get(source) ?? []) {
      for (const branch of block.branches) {
        if (branch.variable === null || branch.literal === null) continue;
        const values = assignedValues(recipes, branch.variable);
        if (!values.has(branch.literal)) {
          const legal = [...values].map((v) => JSON.stringify(v)).sort().join(', ') || '(none)';
          problems.push(
            `${source}:${branch.line}: branches on '${branch.variable} == "${branch.literal}"', but ` +
              `no configuration ever assigns that value. Legal values: ${legal}.`,
          );
        }
      }
    }
  }

  // a branch no configuration selects
  for (const source of sources) {
    const rendering = all.filter((c) => c.source === source);
    for (const block of blocksPerSource.get(source) ?? []) {
      block.branches.forEach((branch, index) => {
        const taken = rendering.some(
          (c) => block.branches.findIndex((b) => selects(b, c.scope)) === index,
        );
        if (!taken) {
          const label = branch.variable === null
            ? 'else'
            : `${branch.variable}${branch.literal === null ? '' : ` == "${branch.literal}"`}`;
          problems.push(
            `${source}:${branch.line}: the '${label}' branch is selected by no configuration — it ` +
              'ships to nobody. Either a value is wrong, or the branch is dead and should go.',
          );
        }
      });
    }
  }

  if (problems.length > 0) {
    throw new LintError(`${problems.length} problem(s) found:\n${problems.map((p) => `  ${p}`).join('\n')}`);
  }
}
