import { globSync } from 'node:fs';

import { describe, expect, it } from 'vitest';

import { readRepoJson, repoRoot } from '../../../commons/support/repo';

// Ported from tests/plugin/test_manifest.py — dist/claude-code/settings.json structure and its
// sync with the shipped commands/ folder.

interface PluginSettings {
  agent?: unknown;
  advisors?: unknown;
  skills?: unknown;
  commands?: unknown;
}

describe('the installed plugin manifest (dist/claude-code/settings.json)', () => {
  it('declares its agent, advisors, skills, and commands', () => {
    const settings = readRepoJson<PluginSettings>('dist', 'claude-code', 'settings.json');
    expect(typeof settings.agent).toBe('string');
    expect(Array.isArray(settings.advisors)).toBe(true);
    expect(Array.isArray(settings.skills)).toBe(true);
    expect(Array.isArray(settings.commands)).toBe(true);
    expect((settings.advisors as unknown[]).length, 'advisors must not be empty').toBeGreaterThan(0);
    expect((settings.skills as unknown[]).length, 'skills must not be empty').toBeGreaterThan(0);
    expect((settings.commands as unknown[]).length, 'commands must not be empty').toBeGreaterThan(0);
  });

  it('lists every shipped command file, and vice versa', () => {
    const existing = new Set(
      globSync('*.md', { cwd: `${repoRoot}/dist/claude-code/commands` }).map((f) => f.replace(/\.md$/, '')),
    );
    const settings = readRepoJson<PluginSettings>('dist', 'claude-code', 'settings.json');
    const manifest = (settings.commands ?? []) as string[];
    const missing = manifest.filter((c) => !existing.has(c));
    const extra = [...existing].filter((c) => !manifest.includes(c));
    expect(missing, `Commands in settings.json but missing from commands/: ${missing}`).toEqual([]);
    expect(extra, `Commands in commands/ but missing from settings.json: ${extra}`).toEqual([]);
  });
});
