/**
 * Shared helpers for the docs/plugin specs. Local to this directory rather than
 * tests/support/ — nothing outside docsAndPlugin/ needs them.
 */

/** The shape of dist/claude-code/.claude-plugin/plugin.json this directory's specs read. */
export interface PluginManifest {
  name?: string;
  description?: string;
  version: string;
  author?: unknown;
  license?: string;
}
