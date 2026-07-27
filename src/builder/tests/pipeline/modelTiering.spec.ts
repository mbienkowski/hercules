import { mkdtempSync, readdirSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { afterEach, describe, expect, it } from 'vitest';

import { discover } from '../../descriptor.mjs';
import { buildTarget } from '../../bin/cli.mjs';
import { buildRegistry } from '../../serialize.mjs';
import { ECOSYSTEMS } from '../../../commons/support/descriptorFixtures';

// Ported from tests/build/test_model_tiering.py.

const MODELS: Record<string, Record<string, string | null>> = {};
for (const [name, d] of Object.entries(discover(ECOSYSTEMS))) MODELS[name] = d.models;

const AGENT = (tier: string) =>
  `---\nname: x\ndescription: d\nmodel_tier: ${tier}\ntools: Read\n---\n\n# X\n`;

function modelOf(text: string): string | undefined {
  return /^model: (.+)$/m.exec(text)?.[1];
}

function registry() {
  return buildRegistry(Object.values(discover(ECOSYSTEMS)));
}

describe('per-tier model selection on claude-code', () => {
  it('each priority tier selects its configured model', () => {
    const reg = registry();
    expect(modelOf(reg.serializeFile('claude-code', AGENT('high'), new Map(), MODELS))).toBe('opus');
    expect(modelOf(reg.serializeFile('claude-code', AGENT('medium'), new Map(), MODELS))).toBe('sonnet');
    expect(modelOf(reg.serializeFile('claude-code', AGENT('low'), new Map(), MODELS))).toBe('haiku');
  });

  it('the per-tier model can be overridden for a build', () => {
    const override = { 'claude-code': { high: 'sonnet', medium: null, low: null } };
    const out = registry().serializeFile('claude-code', AGENT('high'), new Map(), override);
    expect(modelOf(out)).toBe('sonnet');
  });
});

describe('a full build', () => {
  const dirs: string[] = [];

  function out(): string {
    const root = mkdtempSync(join(tmpdir(), 'hercules-tiering-'));
    dirs.push(root);
    return root;
  }

  afterEach(() => {
    while (dirs.length > 0) rmSync(dirs.pop() as string, { recursive: true, force: true });
  });

  it('builds the hercules orchestrator on the top-tier model', () => {
    const root = out();
    buildTarget('claude-code', root);
    const text = readFileSync(join(root, 'agents', 'hercules.md'), 'utf-8');
    expect(modelOf(text)).toBe('opus');
  });

  it('produces agents on more than one model tier', () => {
    const root = out();
    buildTarget('claude-code', root);
    const models = new Set(
      readdirSync(join(root, 'agents')).map((name) => modelOf(readFileSync(join(root, 'agents', name), 'utf-8'))),
    );
    expect(models.has('opus')).toBe(true);
    expect(models.has('sonnet') || models.has('haiku')).toBe(true);
  });
});
