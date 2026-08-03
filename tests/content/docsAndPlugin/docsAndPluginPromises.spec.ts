import { describe, expect, it } from 'vitest';

import { readRepoFile, readRepoJson } from '../../support/repo';
import type { PluginManifest } from './support';

/**
 * The main promises README and the shipped plugin manifest make to someone deciding whether to install:
 * the install/update/uninstall commands, no reviewing agent that can edit, one owner of the version.
 */

const PLUGIN_JSON = ['dist', 'claude-code', '.claude-plugin', 'plugin.json'];

describe('README installation, updates, and uninstall', () => {
  it('states the commands a user actually types to install, update, and uninstall the plugin', () => {
    const content = readRepoFile('README.md');
    expect(content).toContain('/plugin marketplace add');
    expect(content).toContain('/plugin install');
    expect(content).toContain('claude plugin update hercules');
    expect(content).toContain('/plugin uninstall');
  });
});

describe('no shipped review or architecture agent can also edit', () => {
  it('never grants edit permissions to the review and architecture agents', () => {
    for (const name of ['cynical-reviewer', 'lead-architect']) {
      const md = readRepoFile(`dist/claude-code/agents/${name}.md`);
      const toolsLine = md.split('\n').find((ln) => ln.startsWith('tools:'));
      expect(toolsLine, `${name} must declare a tools: line`).toBeDefined();
      expect(toolsLine).not.toContain('Edit');
      expect(toolsLine).not.toContain('Write');
    }
  });
});

describe('packaging consistency', () => {
  it('the published version and license have exactly one owning source, matched across pyproject.toml and plugin.json', () => {
    const py = readRepoFile('pyproject.toml');
    const versionM = py.match(/^version\s*=\s*"([^"]+)"/m);
    expect(versionM, 'pyproject.toml must declare a version').toBeTruthy();
    const plugin = readRepoJson<PluginManifest>(...PLUGIN_JSON);
    expect(versionM?.[1]).toBe(plugin.version);
    const lic = plugin.license ?? '';
    expect(lic).toBeTruthy();
    expect(py).toContain(lic.split('-')[0] as string);
  });
});
