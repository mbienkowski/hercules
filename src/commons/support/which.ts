import { accessSync, constants, existsSync, statSync } from 'node:fs';
import { delimiter, join } from 'node:path';

/**
 * POSIX-only executable lookup: scan each `PATH`-delimited directory in order for an executable
 * regular file named `name`, returning its full path or `null`. Windows `PATHEXT` resolution is
 * deliberately not implemented — the live-CLI (command-line interface) smoke checks run only on
 * macOS/Linux CI (continuous integration).
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
