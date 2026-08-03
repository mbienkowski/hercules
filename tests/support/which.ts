import { accessSync, constants, existsSync, statSync } from 'node:fs';
import { delimiter, join } from 'node:path';

/**
 * POSIX-only executable lookup along `PATH`, returning the full path or `null`. Windows `PATHEXT` is
 * not implemented — the live-CLI (command-line interface) smoke checks run on macOS/Linux only.
 */
export function which(name: string, pathEnv: string | undefined = process.env['PATH']): string | null {
  for (const dir of (pathEnv ?? '').split(delimiter)) {
    if (dir === '') continue;
    const candidate = join(dir, name);
    if (!existsSync(candidate)) continue;
    try {
      if (!statSync(candidate).isFile()) continue;
      accessSync(candidate, constants.X_OK);
    } catch {
      continue;
    }
    return candidate;
  }
  return null;
}
