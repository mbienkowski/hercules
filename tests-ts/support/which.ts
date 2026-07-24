import { accessSync, constants, existsSync, statSync } from 'node:fs';
import { delimiter, join } from 'node:path';

/**
 * A POSIX-only mirror of Python's `shutil.which(name)`: scan each `PATH`-delimited directory (in
 * order) for an executable regular file named `name`, returning its full path or `null` if none is
 * found.
 *
 * Windows `PATHEXT` resolution is deliberately not implemented — this project only runs its live-CLI
 * smoke checks on macOS/Linux CI, matching the same scope carve-out `shutil.which` itself documents
 * for non-Windows platforms it's used from.
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
