/**
 * Writing one rendered file: bytes, then the mode its entry asked for.
 *
 * The mode is set explicitly because `writeFileSync` honours the umask, so the same recipe would
 * otherwise emit different permissions on different machines and a byte comparison would not see it.
 */

import { mkdirSync, writeFileSync, chmodSync } from 'node:fs';
import { dirname } from 'node:path';

/** The mode a file gets when its entry does not ask for one. */
export const DEFAULT_MODE = '644';

/** Write `text` to `path` (UTF-8), creating parents, then set `permissions` (default 644). */
export function writeEntry(path: string, text: string, permissions: string = DEFAULT_MODE): void {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, text, 'utf-8');
  chmodSync(path, Number.parseInt(permissions, 8));
}
