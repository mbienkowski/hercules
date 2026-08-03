// Reading a shipped file at runtime, from beside this one — knows nothing about agents, only
// files, frontmatter and directories. `plugin.js` reads agent/command bodies through here, so
// editing a shipped file changes what it serves.

const fs = require("fs");
const path = require("path");

const FRONTMATTER = /^---\n([\s\S]*?)\n---\n?/;

/** Read a UTF-8 file at `relPath`, relative to `root`. */
function readFile(root, relPath) {
  return fs.readFileSync(path.join(root, relPath), "utf8");
}

/** `{key: value}` of a document's leading frontmatter — empty when it carries none. */
function frontmatter(text) {
  const match = FRONTMATTER.exec(text);
  if (!match) return {};
  const fields = {};
  for (const line of match[1].split("\n")) {
    const at = line.indexOf(": ");
    if (at > 0) fields[line.slice(0, at)] = line.slice(at + 2);
  }
  return fields;
}

/** Everything after the frontmatter, trimmed — the document's body as a prompt. */
function stripFrontmatter(text) {
  return text.replace(FRONTMATTER, "").trim();
}

/**
 * Every `<stem>` whose `<dir>/<stem>.md` exists, sorted.
 *
 * A missing directory reads as empty rather than throwing: a partial install must degrade to "this
 * plugin offers no agents", never to an exception during OpenCode's start-up.
 */
function listMarkdown(root, dir) {
  let entries;
  try {
    entries = fs.readdirSync(path.join(root, dir));
  } catch (error) {
    return [];
  }
  return entries.filter((name) => name.endsWith(".md")).map((name) => name.slice(0, -3)).sort();
}

module.exports = { readFile, frontmatter, stripFrontmatter, listMarkdown };
