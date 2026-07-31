import { globSync } from 'node:fs';

import { describe, expect, it } from 'vitest';

import { readRepoFile, readRepoJson, repoRoot } from '../../../commons/support/repo';
import { ALL_COMMANDS, section } from './support';
import type { PluginManifest } from './support';

// README/CLAUDE.md/pyproject.toml/plugin.json consistency, marketing prose pins, and
// code-of-conduct resolution rules. The "Plugin permissions" pins live in docsPermissions.spec.ts.

const PLUGIN_JSON = ['dist', 'claude-code', '.claude-plugin', 'plugin.json'];

describe('README install/uninstall/update guidance', () => {
  it('explains how to install via the marketplace', () => {
    const content = readRepoFile('README.md');
    expect(content).toContain('/plugin marketplace add');
    expect(content).toContain('/plugin install');
    expect(content).toContain('codex plugin marketplace add mbienkowski/hercules');
    expect(content).toContain('codex plugin add hercules@mbienkowski');
  });

  it('documents remote Codex updates and removal', () => {
    const content = readRepoFile('README.md');
    expect(content).toContain('codex plugin marketplace upgrade mbienkowski');
    expect(content).toContain('codex plugin marketplace remove mbienkowski');
    expect(content).not.toContain('replace the local `dist/codex/` plugin');
  });

  it('never mentions the removed auto-sync CLI', () => {
    const content = readRepoFile('README.md');
    for (const banned of ['--sync', '--branch', 'auto-sync', 'every 30 min']) {
      expect(content, `README still references removed CLI surface: ${banned}`).not.toContain(banned);
    }
  });

  it('explains how teams can install without clicking through prompts', () => {
    const content = readRepoFile('README.md');
    expect(content).toContain('enabledPlugins');
    expect(content).toContain('extraKnownMarketplaces');
  });

  it('never implies updates happen automatically by default', () => {
    const content = readRepoFile('README.md');
    const low = content.toLowerCase();
    expect(low).not.toContain('keeps the plugin updated');
    expect(content).toContain('claude plugin update hercules');
    expect(low).toContain('cli');
    expect(content).toContain('/reload-plugins');
    expect(low).toContain('auto-update');
    expect(low).toContain('opt-in');
  });

  it('explains how to fully uninstall the plugin', () => {
    const content = readRepoFile('README.md');
    expect(content).toContain('/plugin uninstall');
    expect(content).toContain('## Uninstalling');
  });

  it('mentions that saved project data survives uninstall', () => {
    const readme = readRepoFile('README.md');
    const uninstall = section(readme, '## Uninstalling', '\n## ');
    expect(uninstall).toContain('.hercules');
  });

  it('names the repo-side files left behind after uninstall', () => {
    const readme = readRepoFile('README.md');
    const start = readme.indexOf('## Uninstalling');
    const stopIdx = readme.indexOf('\n## ', start);
    const uninstall = stopIdx === -1 ? readme.slice(start) : readme.slice(start, stopIdx);
    expect(uninstall).toContain('code-of-conduct.md');
    expect(uninstall).toContain('CLAUDE.md');
  });
});

describe('README packaging-file consistency', () => {
  it('the published version number matches across packaging files', () => {
    const py = readRepoFile('pyproject.toml');
    const m = py.match(/^version\s*=\s*"([^"]+)"/m);
    expect(m, 'pyproject.toml must declare a version').toBeTruthy();
    const plugin = readRepoJson<PluginManifest>(...PLUGIN_JSON);
    expect(m?.[1]).toBe(plugin.version);
  });

  it('the declared license matches across packaging files', () => {
    const py = readRepoFile('pyproject.toml');
    const plugin = readRepoJson<PluginManifest>(...PLUGIN_JSON);
    const lic = plugin.license ?? '';
    expect(lic).toBeTruthy();
    expect(py, `pyproject license must match plugin.json's ${lic}`).toContain(lic.split('-')[0] as string);
  });

  it('shipped documentation never mentions the removed sync feature', () => {
    const files = globSync('dist/claude-code/**/*.md', { cwd: repoRoot });
    for (const rel of files) {
      const low = readRepoFile(rel).toLowerCase();
      expect(low, `${rel} references a removed 'sync source'`).not.toContain('sync source');
      expect(low, `${rel} references removed auto-sync`).not.toContain('auto-sync');
    }
  });
});

describe('README onboarding and behavioral disclosures', () => {
  it('explains the one-time setup step for new projects', () => {
    const content = readRepoFile('README.md');
    expect(content).toContain('code-of-conduct-generator');
    const low = content.toLowerCase();
    expect(low.includes('set up this project') || low.includes('onboarding')).toBe(true);
  });

  it('never claims only one approval happens per phase', () => {
    expect(readRepoFile('README.md')).not.toContain('One approval per phase; nothing happens before it');
  });

  it('discloses that commands write files into the users repository', () => {
    const readme = readRepoFile('README.md');
    expect(readme).toContain('INDEX.md');
    expect(readme.toLowerCase()).toContain('learnings');
  });

  it('never claims the advisory board runs without approval', () => {
    expect(readRepoFile('README.md')).not.toContain('every other tier runs it');
  });

  it('warns Windows users the safety guard may silently never activate', () => {
    const readme = readRepoFile('README.md');
    const start = readme.indexOf('**Python 3');
    const req = readme.slice(start, readme.indexOf('\n\n', start));
    expect(req, 'the python3 requirement must name the Windows gap').toContain('Windows');
  });

  it('explains that shell edits are covered by a different safeguard', () => {
    const readme = readRepoFile('README.md');
    const start = readme.indexOf('**Hooks**');
    const hooks = readme.slice(start, readme.indexOf('- **Shell**', start));
    expect(hooks.includes('git diff') || hooks.includes('diff backstop')).toBe(true);
  });

  it('correctly describes the generated file as lowercase-named', () => {
    const readme = readRepoFile('README.md');
    expect(readme).not.toContain('a `CODE_OF_CONDUCT.md` with');
    expect(readme).toContain('a `code-of-conduct.md` with');
  });

  it('cites the correct published paper, not a dead link', () => {
    const readme = readRepoFile('README.md');
    expect(readme, 'cite Cheng et al., Science 2026 (aec8352)').toContain('science.aec8352');
    expect(readme, 'the old DOI resolves to nothing').not.toContain('adp9289');
  });
});

describe('shipped agent configuration', () => {
  it('never grants edit permissions to the review and architecture agents', () => {
    for (const name of ['cynical-reviewer', 'lead-architect']) {
      const md = readRepoFile(`dist/claude-code/agents/${name}.md`);
      const toolsLine = md.split('\n').find((ln) => ln.startsWith('tools:'));
      expect(toolsLine, `${name} must declare a tools: line`).toBeDefined();
      expect(toolsLine, `${name} must not carry Edit`).not.toContain('Edit');
      expect(toolsLine, `${name} must not carry Write`).not.toContain('Write');
    }
  });

  it('admits the safety hooks need python3 installed to run', () => {
    expect(readRepoFile('dist/claude-code/hooks/hooks.json')).toContain('python3');
    const readme = readRepoFile('README.md');
    const start = readme.indexOf('## Requirements');
    const req = readme.slice(start, readme.indexOf('## ', start + 3));
    expect(req.toLowerCase()).not.toContain('only for contributing');
    expect(readme.toLowerCase()).not.toContain("you don't need any extra executables");
  });

  it('the first-run setup prompt never interrupts unrelated work', () => {
    const agent = readRepoFile('dist/claude-code/agents/hercules.md');
    const gate = agent.slice(agent.indexOf('**First-run onboarding.**'));
    expect(gate, 'the gate must promise never to intercept unrelated work').toContain('unrelated');
    expect(gate, 'the gate must scope itself to Hercules-directed requests').toContain('/hercules:');
  });

  it('the default persona is configured to use the opus model', () => {
    const agent = readRepoFile('dist/claude-code/agents/hercules.md');
    const head = agent.slice(0, agent.indexOf('\n---', 3));
    expect(head).toMatch(/^model:\s*opus\s*$/m);
  });
});

describe('code-of-conduct resolution rules', () => {
  it('names the workflow protocol document as the single authority on the workflow', () => {
    const protocol = readRepoFile('dist/claude-code/protocols/workflow-protocol.md').toLowerCase();
    expect(protocol).toContain('source of truth');
    expect(protocol).toContain('workflow');

    const coc = section(readRepoFile('CODE_OF_CONDUCT.md'), '### Changing the workflow', '\n### ', 'CODE_OF_CONDUCT.md');
    expect(coc, "the CoC 'Changing the workflow' section must name workflow-protocol.md").toContain('workflow-protocol.md');

    const inverted = /workflow'?s source of truth\s+is\b(?:(?!protocol).){0,60}?command/is;
    for (const rel of ['CODE_OF_CONDUCT.md', ...ALL_COMMANDS]) {
      expect(inverted.test(readRepoFile(rel)), `${rel} crowns commands as the workflow's source of truth`).toBe(false);
    }
  });

  it('claude.md defines one consistent way to find the code-of-conduct file', () => {
    const combined = `${readRepoFile('dist/claude-code/CLAUDE.md')}\n${readRepoFile('dist/claude-code/skills/hercules-reference/SKILL.md')}`;
    const resolution = section(combined, '## Code-of-conduct resolution', '\n## ', 'CLAUDE.md');
    const low = resolution.toLowerCase();
    expect(low.includes('any capitalization') || low.includes('case-insensitiv')).toBe(true);
    expect(resolution).toContain('repositories');
    expect(resolution).toContain('directory');
    expect(low.includes('nearest') || low.includes('closest') || low.includes('launch')).toBe(true);
    expect(low.includes('validate') || low.includes('confirm')).toBe(true);
    expect(low).toContain('exactly one');
    expect(low).toContain('no extra prompt');
  });

  it('build looks up the service code of conduct by matching, not a fixed path', () => {
    expect(readRepoFile('dist/claude-code/commands/build.md')).not.toContain('{service-path}/code-of-conduct.md');
  });
});
