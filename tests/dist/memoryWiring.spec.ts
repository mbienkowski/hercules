// Recipe and distribution checks: every shipped edition packages the shared memory programs and its host
// registers the memory hook at an event that can deliver context, with the right output dialect.
// OpenCode runs in a sandbox with a stubbed subprocess; no distribution build or user memory writes.
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { join } from 'node:path';
import { runInNewContext } from 'node:vm';
import { describe, expect, it, vi, type Mock } from 'vitest';
import { readRepoJson, repoRoot } from '../support/repo';

interface Recipe { name: string; targets: Record<string, { sources: string[] } | null> }
interface Handler { command?: string; bash?: string; args?: string[]; timeout?: number; timeoutSec?: number }
interface HookConfig { hooks: Record<string, (Handler | { matcher?: string; hooks: Handler[] })[]> }
const recipeFiles = readdirSync(join(repoRoot, 'src/targets'))
  .filter((name) => name.endsWith('.json') && name !== 'recipe.schema.json');
const recipes = recipeFiles.map((name) => readRepoJson<Recipe>('src/targets', name));
const hookConfig = (host: string) => readRepoJson<HookConfig>('src/content/targets', host, 'hooks/hooks.json');
const distHookConfig = (edition: string) => JSON.parse(readFileSync(join(repoRoot, 'dist', edition, 'hooks/hooks.json'), 'utf8')) as HookConfig;
const handlers = (config: HookConfig, event: string) =>
  (config.hooks[event] ?? []).flatMap((entry) => 'hooks' in entry ? entry.hooks : [entry]);

describe('every edition ships the same memory entry points', () => {
  it('discovers a nonempty recipe roster', () => {
    expect(recipes.length).toBeGreaterThan(0);
  });

  it.each(recipes)('$name packages the hook and its shared core at sibling paths', (recipe) => {
    for (const [target, source] of Object.entries({
      'hooks/memory_hook.py': 'src/scripts/hooks/memory_hook.py',
      'tools/memory_core.py': 'src/scripts/tools/memory_core.py',
      'hooks/hercules_state.py': 'src/scripts/hooks/hercules_state.py',
    })) {
      expect(recipe.targets[target]?.sources).toEqual([source]);
      expect(existsSync(join(repoRoot, source))).toBe(true);
    }
  });
});

describe('hosts register memory at events that can deliver context', () => {
  it.each([
    ['codex', 'UserPromptSubmit', '$PLUGIN_ROOT', ''],
    ['claude-code', 'UserPromptSubmit', '${CLAUDE_PLUGIN_ROOT}', ''],
    ['gemini-cli', 'BeforeAgent', '${extensionPath}', ' gemini'],
    ['codex', 'SessionStart', '$PLUGIN_ROOT', ''],
    ['claude-code', 'SessionStart', '${CLAUDE_PLUGIN_ROOT}', ''],
    ['gemini-cli', 'SessionStart', '${extensionPath}', ' gemini'],
    ['cursor', 'sessionStart', '${CURSOR_PLUGIN_ROOT}', ' cursor'],
    ['cursor', 'postToolUse', '${CURSOR_PLUGIN_ROOT}', ' cursor'],
    ['cursor', 'preCompact', '${CURSOR_PLUGIN_ROOT}', ' cursor'],
  ])('%s %s invokes the packaged hook with its output dialect', (host, event, root, dialect) => {
    const registered = handlers(hookConfig(host!), event!);
    expect(registered).toHaveLength(1);
    expect(registered[0]?.command).toBe(`python3 "${root}/hooks/memory_hook.py"${dialect}`);
    expect(registered[0]?.args ?? []).toEqual([]);
  });

  it('Cursor uses session context rather than a prompt event that cannot inject', () => {
    expect(handlers(hookConfig('cursor'), 'sessionStart')).toHaveLength(1);
    expect(handlers(hookConfig('cursor'), 'beforeSubmitPrompt')).toHaveLength(0);
  });

  it('Gemini CLI re-delivers after a manual /compress only, never on automatic compression', () => {
    const config = hookConfig('gemini-cli');
    expect(config.hooks['PreCompress']).toEqual([
      expect.objectContaining({ matcher: 'manual' }),
    ]);
    const registered = handlers(config, 'PreCompress');
    expect(registered).toHaveLength(1);
    expect(registered[0]?.command).toBe('python3 "${extensionPath}/hooks/memory_hook.py" gemini');
  });

  it('Gemini CLI quotes the write-gate command so a path with spaces resolves', () => {
    expect(handlers(hookConfig('gemini-cli'), 'BeforeTool')[0]?.command)
      .toBe('python3 "${extensionPath}/hooks/hercules_gate.py" || exit 0');
  });

  it.each(['sessionStart', 'userPromptSubmitted', 'preCompact'])('Copilot CLI %s runs the memory hook with the copilot dialect', (event) => {
    const registered = handlers(hookConfig('copilot-cli'), event);
    expect(registered).toHaveLength(1);
    expect(registered[0]?.bash).toBe(`python3 "$PLUGIN_ROOT/hooks/memory_hook.py" copilot ${event} || exit 0`);
    expect(registered[0]?.timeoutSec).toBe(10);
  });

  it('Grok Build injects through PostToolUse, the only event whose output reaches the model', () => {
    const config = hookConfig('grok-build');
    const registered = handlers(config, 'PostToolUse');
    expect(registered).toHaveLength(1);
    expect(registered[0]?.command).toBe('python3 "${GROK_PLUGIN_ROOT}/hooks/memory_hook.py"');
    expect(registered[0]?.timeout).toBe(10);
    expect(handlers(config, 'SessionStart')).toHaveLength(0);
    expect(handlers(config, 'UserPromptSubmit')).toHaveLength(0);
  });

  it('Grok Build re-delivers after PostCompact', () => {
    const registered = handlers(hookConfig('grok-build'), 'PostCompact');
    expect(registered).toHaveLength(1);
    expect(registered[0]?.command).toBe('python3 "${GROK_PLUGIN_ROOT}/hooks/memory_hook.py"');
    expect(registered[0]?.timeout).toBe(10);
  });

  it('Grok Build frozen_tests gate names python3 in the command, with no args field Grok would ignore', () => {
    const registered = handlers(hookConfig('grok-build'), 'PreToolUse');
    expect(registered).toHaveLength(1);
    expect(registered[0]?.command).toBe('python3 "${GROK_PLUGIN_ROOT}/hooks/frozen_tests.py"');
    expect(registered[0]).not.toHaveProperty('args');
  });

  it.each([
    ['claude-code', 'SessionStart', 10],
    ['claude-code', 'UserPromptSubmit', 10],
    ['codex', 'SessionStart', 10],
    ['codex', 'UserPromptSubmit', 10],
    ['gemini-cli', 'SessionStart', 10000],
    ['gemini-cli', 'BeforeAgent', 10000],
    ['gemini-cli', 'PreCompress', 10000],
    ['cursor', 'sessionStart', 10],
    ['cursor', 'postToolUse', 10],
    ['cursor', 'preCompact', 10],
  ])('%s %s bounds the memory hook with a host timeout of %d', (host, event, timeout) => {
    const registered = handlers(hookConfig(host!), event!);
    expect(registered[0]?.timeout ?? registered[0]?.timeoutSec).toBe(timeout);
  });
});

describe.each(['claude-code', 'codex', 'copilot-cli', 'cursor', 'gemini-cli', 'grok-build', 'opencode'])(
  'dist/%s ships the memory programs', (edition) => {
    it('ships hooks/memory_hook.py and tools/memory_core.py', () => {
      expect(existsSync(join(repoRoot, 'dist', edition, 'hooks/memory_hook.py'))).toBe(true);
      expect(existsSync(join(repoRoot, 'dist', edition, 'tools/memory_core.py'))).toBe(true);
    });
  },
);

describe('dist hook registrations match the source hooks', () => {
  it.each([
    ['claude-code', 'SessionStart', '${CLAUDE_PLUGIN_ROOT}/hooks/memory_hook.py"'],
    ['claude-code', 'UserPromptSubmit', '${CLAUDE_PLUGIN_ROOT}/hooks/memory_hook.py"'],
    ['codex', 'SessionStart', '$PLUGIN_ROOT/hooks/memory_hook.py"'],
    ['codex', 'UserPromptSubmit', '$PLUGIN_ROOT/hooks/memory_hook.py"'],
    ['gemini-cli', 'SessionStart', '${extensionPath}/hooks/memory_hook.py" gemini'],
    ['gemini-cli', 'BeforeAgent', '${extensionPath}/hooks/memory_hook.py" gemini'],
    ['gemini-cli', 'PreCompress', '${extensionPath}/hooks/memory_hook.py" gemini'],
    ['cursor', 'sessionStart', '${CURSOR_PLUGIN_ROOT}/hooks/memory_hook.py" cursor'],
    ['cursor', 'postToolUse', '${CURSOR_PLUGIN_ROOT}/hooks/memory_hook.py" cursor'],
    ['cursor', 'preCompact', '${CURSOR_PLUGIN_ROOT}/hooks/memory_hook.py" cursor'],
  ])('dist/%s registers %s with the packaged hook', (edition, event, suffix) => {
    const registered = handlers(distHookConfig(edition), event!);
    expect(registered).toHaveLength(1);
    expect(registered[0]?.command?.endsWith(suffix)).toBe(true);
  });

  it.each(['sessionStart', 'userPromptSubmitted', 'preCompact'])('dist/copilot-cli registers %s with the copilot dialect and its event name', (event) => {
    const registered = handlers(distHookConfig('copilot-cli'), event);
    expect(registered).toHaveLength(1);
    expect(registered[0]?.bash).toContain(`/hooks/memory_hook.py" copilot ${event} || exit 0`);
  });

  it('dist/grok-build registers PostToolUse and PostCompact with the packaged hook', () => {
    for (const event of ['PostToolUse', 'PostCompact']) {
      const registered = handlers(distHookConfig('grok-build'), event);
      expect(registered).toHaveLength(1);
      expect(registered[0]?.command).toContain('/hooks/memory_hook.py"');
    }
  });
});

describe('every CAPABILITIES.md states the host version its notes were verified against', () => {
  const editions = readdirSync(join(repoRoot, 'src/content/targets'))
    .filter((edition) => existsSync(join(repoRoot, 'src/content/targets', edition, 'CAPABILITIES.md')));

  it('finds the edition notes', () => {
    expect(editions.length).toBeGreaterThan(0);
  });

  it.each(editions)('%s', (edition) => {
    const text = readFileSync(join(repoRoot, 'src/content/targets', edition, 'CAPABILITIES.md'), 'utf8');
    expect(text).toMatch(/^> Verified against: .+ — .+\. Re-check these notes when upgrading past it\.$/m);
  });
});

type Transform = (input: { sessionID?: string }, output: { system: string[] }) => Promise<void>;
type Hooks = {
  'experimental.chat.system.transform'?: Transform;
  'tool.execute.before'?: unknown;
  event?: (input: { event: { type: string; properties: Record<string, unknown> } }) => Promise<void>;
};
type ExecResult = { error?: Error; stdout?: string };
const sourceDir = join(repoRoot, 'src/content/targets/opencode');
const distDir = join(repoRoot, 'dist/opencode');

// Stands in for child_process.execFile. The callback fires on a later tick, as a real child process does.
function fakeExecFile(result: ExecResult = { stdout: 'compact context' }) {
  return vi.fn((_command: string, _args: string[], _options: { cwd: string; timeout: number }, callback: (error: Error | null, stdout: string) => void) => {
    setTimeout(() => callback(result.error ?? null, result.stdout ?? ''), 0);
    return { stdin: { on: vi.fn(), end: vi.fn() } };
  });
}

// The session client's lookup: a child session reports its parent through `data.parentID`.
function fakeClient(parents: Record<string, string> = {}) {
  return { session: { get: vi.fn(async ({ path }: { path: { id: string } }) => ({ data: { id: path.id, parentID: parents[path.id] } })) } };
}

// The JSON that was written to the child's stdin for the nth execFile call.
function stdinPayload(execFile: Mock, call: number) {
  const child = execFile.mock.results[call]!.value as { stdin: { end: Mock } };
  return JSON.parse(child.stdin.end.mock.calls[0]![0] as string);
}

async function loadPlugin(pluginDir: string, execFile: Mock, client?: unknown) {
  const requireSource = createRequire(join(pluginDir, 'plugin.js'));
  const module = { exports: {} as { server: (input: { directory: string; client?: unknown }) => Promise<Hooks> } };
  runInNewContext(readFileSync(join(pluginDir, 'plugin.js'), 'utf8'), {
    module, __dirname: pluginDir, process: { env: {}, cwd: () => '/fallback' }, setTimeout,
    require: (id: string) => id === 'child_process' ? { spawnSync: vi.fn(), execFile }
      : id === 'fs' ? { existsSync: () => true } : requireSource(id),
  });
  return module.exports.server({ directory: '/project with spaces', client });
}

describe.each([['source', sourceDir], ['dist', distDir]])('OpenCode appends memory to the existing system context (%s)', (_label, pluginDir) => {
  const load = (execFile: Mock, client?: unknown) => loadPlugin(pluginDir!, execFile, client);

  it('passes the project and session to the text hook and preserves existing instructions', async () => {
    const execFile = fakeExecFile({ stdout: ' compact memory and capture instructions \n' });
    const plugin = await load(execFile, fakeClient());
    const output = { system: ['existing instructions'] };
    await plugin['experimental.chat.system.transform']!({ sessionID: 'chat-1' }, output);
    expect(output.system).toEqual(['existing instructions', 'compact memory and capture instructions']);
    const [command, args, options] = execFile.mock.calls[0]!;
    expect(command).toBe('python3');
    expect(args).toEqual([join(pluginDir!, 'hooks/memory_hook.py'), 'text']);
    expect(options.cwd).toBe('/project with spaces');
    expect(stdinPayload(execFile, 0)).toEqual({ cwd: '/project with spaces' });
    expect(options.timeout).toBe(3000);
    expect(plugin['tool.execute.before']).toBeTypeOf('function');
  });

  it('spawns once per session under concurrent calls and re-attaches the context on every model call', async () => {
    const execFile = fakeExecFile();
    const plugin = await load(execFile, fakeClient());
    const transform = plugin['experimental.chat.system.transform']!;
    const concurrent = [0, 1, 2].map(() => ({ system: ['existing instructions'] }));
    await Promise.all(concurrent.map((output) => transform({ sessionID: 'chat-1' }, output)));
    expect(execFile).toHaveBeenCalledTimes(1);
    for (const output of concurrent) {
      expect(output.system).toEqual(['existing instructions', 'compact context']);
    }
    const later = { system: ['existing instructions'] };
    await transform({ sessionID: 'chat-1' }, later);
    expect(later.system).toEqual(['existing instructions', 'compact context']);
    expect(execFile).toHaveBeenCalledTimes(1);
  });

  it('computes separately for each session', async () => {
    const execFile = fakeExecFile();
    const plugin = await load(execFile, fakeClient());
    await plugin['experimental.chat.system.transform']!({ sessionID: 'chat-1' }, { system: [] });
    await plugin['experimental.chat.system.transform']!({ sessionID: 'chat-2' }, { system: [] });
    expect(execFile).toHaveBeenCalledTimes(2);
    expect(stdinPayload(execFile, 1)).not.toHaveProperty('session_id');
  });

  it('skips a child (delegate) session: no context and no spawn', async () => {
    const execFile = fakeExecFile();
    const plugin = await load(execFile, fakeClient({ 'child-1': 'chat-1' }));
    const output = { system: ['existing instructions'] };
    await plugin['experimental.chat.system.transform']!({ sessionID: 'child-1' }, output);
    expect(output.system).toEqual(['existing instructions']);
    expect(execFile).not.toHaveBeenCalled();
  });

  it('drops the cached context on session.compacted and session.deleted', async () => {
    const execFile = fakeExecFile();
    const plugin = await load(execFile, fakeClient());
    const transform = plugin['experimental.chat.system.transform']!;
    await transform({ sessionID: 'chat-1' }, { system: [] });
    await plugin.event!({ event: { type: 'session.compacted', properties: { sessionID: 'chat-1' } } });
    await transform({ sessionID: 'chat-1' }, { system: [] });
    expect(execFile).toHaveBeenCalledTimes(2);
    await plugin.event!({ event: { type: 'session.deleted', properties: { info: { id: 'chat-1' } } } });
    await transform({ sessionID: 'chat-1' }, { system: [] });
    expect(execFile).toHaveBeenCalledTimes(3);
  });

  it('adds nothing and spawns nothing for calls without a session id', async () => {
    const execFile = fakeExecFile();
    const plugin = await load(execFile, fakeClient());
    const output = { system: ['existing instructions'] };
    await plugin['experimental.chat.system.transform']!({}, output);
    expect(output.system).toEqual(['existing instructions']);
    expect(execFile).not.toHaveBeenCalled();
  });

  it('leaves existing instructions intact when the hook has no context', async () => {
    const plugin = await load(fakeExecFile({ stdout: '' }), fakeClient());
    const output = { system: ['existing instructions'] };
    await plugin['experimental.chat.system.transform']!({ sessionID: 'chat-2' }, output);
    expect(output.system).toEqual(['existing instructions']);
  });

  it.each([
    ['a nonzero exit', { error: new Error('Command failed'), stdout: 'failure' }],
    ['a timeout', { error: new Error('timeout'), stdout: 'partial' }],
  ])('preserves instructions, warns, and does not retry after %s', async (_name, result) => {
    const execFile = fakeExecFile(result);
    const plugin = await load(execFile, fakeClient());
    for (let request = 0; request < 2; request++) {
      const output = { system: ['existing instructions'] };
      await plugin['experimental.chat.system.transform']!({ sessionID: 'chat-3' }, output);
      expect(output.system[0]).toBe('existing instructions');
      expect(output.system).toHaveLength(2);
      expect(output.system[1]).toMatch(/memory unavailable/i);
      expect(output.system[1]).not.toContain(result.stdout);
    }
    expect(execFile).toHaveBeenCalledTimes(1);
  });

  it('fails open to the fresh context when the session lookup never answers', async () => {
    const execFile = fakeExecFile({ stdout: 'compact context' });
    const hung = { session: { get: vi.fn(() => new Promise(() => {})) } };
    const plugin = await load(execFile, hung);
    const output = { system: ['existing instructions'] };
    await plugin['experimental.chat.system.transform']!({ sessionID: 'chat-hung' }, output);
    expect(output.system).toEqual(['existing instructions', 'compact context']);
    expect(execFile).toHaveBeenCalledTimes(1);
  });

  it('allows the model request when launching Python throws', async () => {
    const execFile = vi.fn(() => { throw new Error('Python unavailable'); });
    const plugin = await load(execFile, fakeClient());
    const output = { system: ['existing instructions'] };
    await expect(plugin['experimental.chat.system.transform']!({ sessionID: 'chat-4' }, output)).resolves.toBeUndefined();
    expect(output.system[0]).toBe('existing instructions');
    expect(output.system).toHaveLength(2);
    expect(output.system[1]).toMatch(/memory unavailable/i);
  });
});
