import { mkdirSync, mkdtempSync, statSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { repoRoot } from '../support/repo';

/**
 * The scaffolding every live-install check needs: where the authored content lives, whether a file is
 * really there, and how to reach a real CLI without touching a real $HOME.
 */

export const SRC_CONTENT = join(repoRoot, 'src', 'content');

/** Is there a file at these path segments? (A directory, or nothing at all, is not.) */
export function isFile(...segments: string[]): boolean {
  try {
    return statSync(join(...segments)).isFile();
  } catch {
    return false;
  }
}

/**
 * A scratch `$HOME` so a live-CLI smoke check never touches a real config, credentials or telemetry.
 * `extraEnv` layers host-specific overrides on top; the caller owns cleanup via `tempWorkspace().track`.
 */
export function scratchHome(extraEnv: (home: string) => NodeJS.ProcessEnv = () => ({})): {
  root: string;
  home: string;
  env: NodeJS.ProcessEnv;
} {
  const root = mkdtempSync(join(tmpdir(), 'hercules-scratch-home-'));
  const home = join(root, 'home');
  mkdirSync(home);
  return { root, home, env: { ...process.env, HOME: home, ...extraEnv(home) } };
}
