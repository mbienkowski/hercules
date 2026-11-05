import { spawnSync } from 'node:child_process';
import { mkdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

import { afterEach, expect, it } from 'vitest';

import { repoRoot } from '../support/repo';
import { tempWorkspace } from '../support/tempWorkspace';
import { countTokens } from './tokenCounter.mjs';

// This measures retrieval overhead against reading the memory store, not total task-token savings.
const scratch = tempWorkspace();
afterEach(scratch.cleanup);

it('compact memory costs less than rereading its store and unchanged turns add no context', () => {
  const root = scratch.make('hercules-memory-budget-');
  const project = join(root, 'project');
  mkdirSync(project);
  const code = `
import contextlib, importlib.util, io, json, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("memory_hook", sys.argv[1])
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)
core = hook.load_core()
project, home = sys.argv[2:4]
for i in range(20):
    core.capture_entry(project, "decision", f"Preference {i}: " + "Use reproducible builds. " * 12,
                       pinned=True, topic=f"topic-{i}", home=home)
payload = json.dumps({"cwd": project, "session_id": "budget-session", "hook_event_name": "UserPromptSubmit"})
with contextlib.redirect_stdout(io.StringIO()) as first:
    hook.main(payload, home=home, dialect="common")
with contextlib.redirect_stdout(io.StringIO()) as second:
    hook.main(payload, home=home, dialect="common")
store = core.memory_root(core.resolve_slug(project, home), home) / "entries.md"
print(json.dumps({"first": json.loads(first.getvalue()), "second": json.loads(second.getvalue()), "store": str(store)}))
`;
  const run = spawnSync('python3', ['-c', code, join(repoRoot, 'src/scripts/hooks/memory_hook.py'), project, root],
    { encoding: 'utf8', timeout: 10000, env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1' } });
  expect(run.status, run.stderr).toBe(0);
  const result = JSON.parse(run.stdout) as {
    first: { hookSpecificOutput: { additionalContext: string } }; second: object; store: string;
  };
  const compact = result.first.hookSpecificOutput.additionalContext;
  const baseline = countTokens(readFileSync(result.store, 'utf8'));
  expect(Buffer.byteLength(compact)).toBeLessThanOrEqual(2400);
  expect(countTokens(compact)).toBeLessThan(baseline);
  expect(result.second).toEqual({});
});
