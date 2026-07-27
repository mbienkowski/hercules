import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative, sep } from 'node:path';

/** Every file under `root`, keyed by its POSIX-style relative path, read as UTF-8 text. */
export function filesUnder(root: string): Record<string, string> {
  const out: Record<string, string> = {};
  const walk = (dir: string): void => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const full = join(dir, entry.name);
      if (entry.isDirectory()) walk(full);
      else if (entry.isFile()) out[relative(root, full).split(sep).join('/')] = readFileSync(full, 'utf-8');
    }
  };
  walk(root);
  return out;
}

/** The sorted `.md` file stems directly under `srcContent/<subdir>`. */
export function srcStems(srcContent: string, subdir: string): string[] {
  return readdirSync(join(srcContent, subdir))
    .filter((name) => name.endsWith('.md'))
    .map((name) => name.slice(0, -'.md'.length))
    .sort();
}

/** The frontmatter block's ordered key list, given the document must open with a `---` fence. */
export function frontmatterKeys(text: string): string[] {
  if (!text.startsWith('---\n')) throw new Error('expected a frontmatter fence');
  const block = text.slice(4, text.indexOf('\n---', 4));
  return block.split('\n').filter((line) => line.includes(':')).map((line) => (line.split(':', 1)[0] as string).trim());
}

/** The top-level entry names (files and directories) directly under `root`. */
export function topLevelEntries(root: string): Set<string> {
  return new Set(readdirSync(root, { withFileTypes: true }).map((e) => e.name));
}

export function isFile(...segments: string[]): boolean {
  try {
    return statSync(join(...segments)).isFile();
  } catch {
    return false;
  }
}
