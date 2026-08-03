import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

import { afterAll, beforeAll, describe, expect, it } from 'vitest';

import { buildDistribution } from '../../../internal/builder/build.mjs';
import { loadRecipe } from '../../../internal/builder/recipe-loader.mjs';
import { srcStems } from '../../support/buildTree';
import { repoRoot } from '../../support/repo';
import { tempWorkspace } from '../../support/tempWorkspace';

// The Gemini CLI (command-line interface) target ships an extension: gemini-extension.json, TOML commands, a GEMINI.md
// context. This file covers what is Gemini-specific; generic cross-target checks live in tests/dist/universalConformance.spec.ts.

const SRC_CONTENT = join(repoRoot, 'src', 'content');
const RECIPE_FILE = 'src/targets/gemini-cli.json';

const workspace = tempWorkspace();
let out: string;

beforeAll(async () => {
  out = join(workspace.make('hercules-gemini-cli-build-'), 'gemini-cli');
  await buildDistribution(loadRecipe(RECIPE_FILE, repoRoot), RECIPE_FILE, out, repoRoot);
});

afterAll(workspace.cleanup);

describe('persona ships as the plain GEMINI.md context file', () => {
  it('has no frontmatter fence and renders the Gemini product name, not Claude’s', () => {
    const geminiMd = join(out, 'GEMINI.md');
    expect(existsSync(geminiMd), 'persona must land at GEMINI.md').toBe(true);
    const text = readFileSync(geminiMd, 'utf-8');
    expect(text.startsWith('---'), "GEMINI.md is a plain context file, not a frontmatter'd rule").toBe(false);
    expect(text, "the `product` variable must render to 'Gemini CLI'").toContain('Gemini CLI plugin');
  });
});

// A hand-rolled decoder for the only two TOML string forms the sources emit: basic and multiline basic
// (`"""…"""`). The build registers ZERO filters, so what reaches a host is exactly what an author typed.
function decodeTomlBasicString(raw: string): string {
  let out = '';
  for (let i = 0; i < raw.length; i++) {
    const character = raw[i];
    if (character === '\\') {
      const next = raw[++i];
      if (next === '"') out += '"';
      else if (next === '\\') out += '\\';
      else if (next === 'n') out += '\n';
      else if (next === 't') out += '\t';
      else out += next ?? '';
    } else {
      out += character;
    }
  }
  return out;
}

function decodeTomlMultilineString(raw: string): string {
  const body = raw.startsWith('\n') ? raw.slice(1) : raw; // TOML trims the delimiter's first newline
  return decodeTomlBasicString(body);
}

function parseGeminiCommandToml(text: string): { description: string; prompt: string } {
  const descMatch = text.match(/^description = "((?:\\.|[^"\\])*)"$/m);
  if (descMatch === null) throw new Error('description key not found');
  const description = decodeTomlBasicString(descMatch[1] as string);

  const marker = 'prompt = """\n';
  const start = text.indexOf(marker);
  if (start === -1) throw new Error('prompt key not found');
  const bodyStart = start + marker.length;
  if (!text.endsWith('\n"""\n')) throw new Error('prompt is not properly closed');
  const bodyEnd = text.length - '"""\n'.length; // keep the newline right before the closing fence
  const prompt = decodeTomlMultilineString(text.slice(bodyStart, bodyEnd));
  return { description, prompt };
}

describe('the emitted command TOML parses with the prompt preserved', () => {
  it('every command file is valid TOML with the plan-mode instruction intact', () => {
    // Parsing the RENDERED .toml catches a variable whose value renders a backslash or `"""` into a body.
    for (const name of srcStems(SRC_CONTENT, 'commands')) {
      // Gemini alone reads commands as TOML, so a `.md` beside the `.toml` is a file the CLI ignores.
      expect(existsSync(join(out, 'commands', `${name}.md`)), `${name}: a .md command must not ship`).toBe(false);
      const f = join(out, 'commands', `${name}.toml`);
      const text = readFileSync(f, 'utf-8');
      const { description, prompt } = parseGeminiCommandToml(text);
      expect(description, `${name}.toml: description missing/empty after TOML parse`).toBeTruthy();
      expect(prompt, `${name}.toml: prompt missing/empty after TOML parse`).toBeTruthy();
      expect(prompt, `${name}.toml: plan-mode instruction lost in the prompt`).toContain('Plan mode — required');
    }
  });
});
