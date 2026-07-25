import { existsSync, mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { afterEach, describe, expect, it } from 'vitest';

import { buildTarget } from '../bin/cli.mjs';
import { discover } from '../descriptor.mjs';
import { readCanonicalVersion } from '../versionTargets.mjs';
import { srcStems } from '../../commons/support/buildTree';
import { ECOSYSTEMS } from '../../commons/support/descriptorFixtures';
import { repoRoot } from '../../commons/support/repo';

// Ported from tests/build/test_gemini_cli_build.py — the Gemini CLI target: an extension
// (gemini-extension.json + subagents, TOML commands, a GEMINI.md context). Determinism,
// routing/extensions, no per-agent model, the version-injected manifest, protocol-citation
// resolution, and ecosystem neutrality live in the generic universal-conformance suite already;
// this file carries the assertions that are specific to Gemini's TOML command shape and its
// version-injected extension manifest.
//
// NOT ported here: test_toml_escapers_handle_backslashes_and_triple_quotes — already covered
// verbatim (same tomlBasic/tomlMultiline pins) by builder/tests/genSerialize.spec.ts's
// "toml_command mode" describe block.

const SRC_CONTENT = join(repoRoot, 'src', 'content');

const dirs: string[] = [];

function build(): string {
  const root = mkdtempSync(join(tmpdir(), 'hercules-gemini-cli-build-'));
  dirs.push(root);
  const out = join(root, 'gemini-cli');
  buildTarget('gemini-cli', out);
  return out;
}

afterEach(() => {
  while (dirs.length > 0) rmSync(dirs.pop() as string, { recursive: true, force: true });
});

describe('persona ships as the plain GEMINI.md context file', () => {
  it('has no frontmatter fence and renders the Gemini product name, not Claude’s', () => {
    const out = build();
    const geminiMd = join(out, 'GEMINI.md');
    expect(existsSync(geminiMd), 'persona must land at GEMINI.md').toBe(true);
    const text = readFileSync(geminiMd, 'utf-8');
    expect(text.startsWith('---'), "GEMINI.md is a plain context file, not a frontmatter'd rule").toBe(false);
    expect(text, "the \\${product} token must render to 'Gemini CLI'").toContain('Gemini CLI plugin');
  });
});

describe('commands ship as TOML with prompt and description', () => {
  it('every command carries a required prompt and description, and drops the Claude marker', () => {
    const out = build();
    for (const name of srcStems(SRC_CONTENT, 'commands')) {
      expect(existsSync(join(out, 'commands', `${name}.md`)), `${name}: a .md command must not ship`).toBe(false);
      const f = join(out, 'commands', `${name}.toml`);
      expect(existsSync(f), `command ${name} must ship at commands/${name}.toml`).toBe(true);
      const text = readFileSync(f, 'utf-8');
      expect(text, `${name}: needs a TOML description`).toMatch(/^description = ".+"$/m);
      expect(text, `${name}: needs a multiline TOML prompt`).toContain('prompt = """\n');
      expect(text, "Claude's slash marker must be dropped").not.toContain('disable-model-invocation');
      expect(text.toLowerCase(), `${name}: plan-mode default branch rendered empty`).toContain('plan mode');
    }
  });
});

// A hand-rolled decoder for exactly the two TOML string constructs genSerialize.mts's
// tomlCommand emits: a basic (single-line) string and a multiline basic (`"""…"""`) string. No
// TOML parser is an existing devDependency (js-yaml is the only added parser, for YAML); this
// mirrors the real TOML escaping grammar independently of the emitter, so it still closes the
// class of bug the Python original's `tomllib.loads` guarded — a token that renders a stray
// backslash or `"""` into the body and produces invalid (or silently wrong) TOML.
function decodeTomlBasicString(raw: string): string {
  let out = '';
  for (let i = 0; i < raw.length; i++) {
    const ch = raw[i];
    if (ch === '\\') {
      const next = raw[++i];
      if (next === '"') out += '"';
      else if (next === '\\') out += '\\';
      else if (next === 'n') out += '\n';
      else if (next === 't') out += '\t';
      else out += next ?? '';
    } else {
      out += ch;
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
    // The real safety net: a source-only invariant can't catch a token that renders a backslash
    // or `"""` into a body; parsing the RENDERED .toml (and escaping the body in the emitter)
    // does. Closes the whole class.
    const out = build();
    for (const name of srcStems(SRC_CONTENT, 'commands')) {
      const f = join(out, 'commands', `${name}.toml`);
      const text = readFileSync(f, 'utf-8');
      const { description, prompt } = parseGeminiCommandToml(text);
      expect(description, `${name}.toml: description missing/empty after TOML parse`).toBeTruthy();
      expect(prompt, `${name}.toml: prompt missing/empty after TOML parse`).toBeTruthy();
      expect(prompt, `${name}.toml: plan-mode instruction lost in the prompt`).toContain('Plan mode — required');
    }
  });
});

describe('the extension manifest is valid and version-injected from canonical', () => {
  it('carries a kebab name, the canonical version, and GEMINI.md as contextFileName', () => {
    const out = build();
    const manifest = JSON.parse(readFileSync(join(out, 'gemini-extension.json'), 'utf-8')) as Record<string, unknown>;
    expect(manifest['name'], 'name must be kebab-case').toMatch(/^[a-z0-9]([a-z0-9-]*[a-z0-9])?$/);
    expect(manifest['contextFileName']).toBe('GEMINI.md');

    const descriptors = discover(ECOSYSTEMS);
    const geminiCli = descriptors['gemini-cli'];
    if (geminiCli === undefined) throw new Error('gemini-cli descriptor missing');
    const artifact = geminiCli.artifacts.find((a) => a.dest === 'gemini-extension.json');
    if (artifact === undefined) throw new Error('gemini-extension.json artifact missing');
    const sourceText = `${JSON.stringify(artifact.content, null, 2)}\n`;
    expect(sourceText, 'source manifest must carry the token, not a literal').toContain('"version": "${version}"');

    const canonical = readCanonicalVersion(repoRoot);
    expect(manifest['version']).toBe(canonical);
    expect(manifest, 'injection must change ONLY the version field').toEqual(
      JSON.parse(sourceText.replaceAll('${version}', canonical)),
    );
  });
});
