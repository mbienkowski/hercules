import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

/**
 * Disposable `mkdtemp`-backed scratch directories, cleaned up together. `track` adopts a directory a
 * helper created some other way, so it is removed on the same pass.
 */
export function tempWorkspace(): {
  make: (prefix: string) => string;
  track: (dir: string) => string;
  cleanup: () => void;
} {
  const created: string[] = [];
  return {
    make(prefix: string): string {
      const root = mkdtempSync(join(tmpdir(), prefix));
      created.push(root);
      return root;
    },
    track(dir: string): string {
      created.push(dir);
      return dir;
    },
    cleanup(): void {
      while (created.length > 0) rmSync(created.pop() as string, { recursive: true, force: true });
    },
  };
}
