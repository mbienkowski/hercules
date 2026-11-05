// Recipe and distribution checks: every shipped edition packages the shared memory programs and its host
// registers the memory hook at an event that can deliver context, with the right output dialect.
// OpenCode runs in a sandbox with a stubbed subprocess; no distribution build or user memory writes.
import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { createRequire } from 'node:module';
import { join } from 'node:path';
import { runInNewContext } from 'node:vm';
import { describe, expect, it, vi } from 'vitest';
import { readRepoJson, repoRoot } from '../support/repo';

interface Recipe { name: string; targets: Record<string, { sources: string[] } | null> }
interface Handler { command?: string; bash?: string; args?: string[]; timeout?: number; timeoutSec?: number }
interface HookConfig { hooks: Record<string, (Handler | { hooks: Handler[] })[]> }
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
    ['gemini-cli', 'BeforeAgent', '${extensionPath}', ''],
    ['codex', 'SessionStart', '$PLUGIN_ROOT', ''],
    ['claude-code', 'SessionStart', '${CLAUDE_PLUGIN_ROOT}', ''],
    ['gemini-cli', 'SessionStart', '${extensionPath}', ''],
    ['cursor', 'sessionStart', '${CURSOR_PLUGIN_ROOT}', ' cursor'],
  ])('%s invokes the packaged hook with its output dialect', (host, event, root, dialect) => {
    const registered = handlers(hookConfig(host!), event!);
    expect(registered).toHaveLength(1);
    expect(registered[0]?.command).toBe(`python3 "${root}/hooks/memory_hook.py"${dialect}`);
    expect(registered[0]?.args ?? []).toEqual([]);
  });

  it('Cursor uses session context rather than a prompt event that cannot inject', () => {
    expect(handlers(hookConfig('cursor'), 'sessionStart')).toHaveLength(1);
    expect(handlers(hookConfig('cursor'), 'beforeSubmitPrompt')).toHaveLength(0);
  });

  it('Copilot CLI injects at sessionStart with the copilot dialect', () => {
    const registered = handlers(hookConfig('copilot-cli'), 'sessionStart');
    expect(registered).toHaveLength(1);
    expect(registered[0]?.bash).toBe('python3 "$PLUGIN_ROOT/hooks/memory_hook.py" copilot || exit 0');
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

  it.each([
    ['claude-code', 'SessionStart', 10],
    ['claude-code', 'UserPromptSubmit', 10],
    ['codex', 'SessionStart', 10],
    ['codex', 'UserPromptSubmit', 10],
    ['gemini-cli', 'SessionStart', 10000],
    ['gemini-cli', 'BeforeAgent', 10000],
    ['cursor', 'sessionStart', 10],
  ])('%s %s bounds the memory hook with a host timeout of %d', (host, event, timeout) => {
    const registered = handlers(hookConfig(host!), event!);
    expect(registered[0]?.timeout).toBe(timeout);
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
    ['gemini-cli', 'SessionStart', '${extensionPath}/hooks/memory_hook.py"'],
    ['gemini-cli', 'BeforeAgent', '${extensionPath}/hooks/memory_hook.py"'],
    ['cursor', 'sessionStart', '${CURSOR_PLUGIN_ROOT}/hooks/memory_hook.py" cursor'],
  ])('dist/%s registers %s with the packaged hook', (edition, event, suffix) => {
    const registered = handlers(distHookConfig(edition), event!);
    expect(registered).toHaveLength(1);
    expect(registered[0]?.command?.endsWith(suffix)).toBe(true);
  });

  it('dist/copilot-cli registers sessionStart with the copilot dialect', () => {
    const registered = handlers(distHookConfig('copilot-cli'), 'sessionStart');
    expect(registered).toHaveLength(1);
    expect(registered[0]?.bash).toContain('/hooks/memory_hook.py" copilot');
  });

  it('dist/grok-build registers PostToolUse with the packaged hook', () => {
    const registered = handlers(distHookConfig('grok-build'), 'PostToolUse');
    expect(registered).toHaveLength(1);
    expect(registered[0]?.command).toContain('/hooks/memory_hook.py"');
  });
});

type Transform = (input: { sessionID?: string }, output: { system: string[] }) => Promise<void>;
const sourceDir = join(repoRoot, 'src/content/targets/opencode');
const distDir = join(repoRoot, 'dist/opencode');

async function loadPlugin(pluginDir: string, spawnSync: ReturnType<typeof vi.fn>) {
  const requireSource = createRequire(join(pluginDir, 'plugin.js'));
  const module = { exports: {} as { server: (input: { directory: string }) => Promise<Record<string, Transform>> } };
  runInNewContext(readFileSync(join(pluginDir, 'plugin.js'), 'utf8'), {
    module, __dirname: pluginDir, process: { env: {}, cwd: () => '/fallback' },
    require: (id: string) => id === 'child_process' ? { spawnSync }
      : id === 'fs' ? { existsSync: () => true } : requireSource(id),
  });
  return module.exports.server({ directory: '/project with spaces' });
}

describe.each([['source', sourceDir], ['dist', distDir]])('OpenCode appends memory to the existing system context (%s)', (_label, pluginDir) => {
  const load = (spawn: ReturnType<typeof vi.fn>) => loadPlugin(pluginDir!, spawn);

  it('passes the project and session to the text hook and preserves existing instructions', async () => {
    const spawn = vi.fn().mockReturnValue({ status: 0, stdout: ' compact memory and capture instructions \n' });
    const plugin = await load(spawn);
    const output = { system: ['existing instructions'] };
    await plugin['experimental.chat.system.transform']!({ sessionID: 'chat-1' }, output);
    expect(output.system).toEqual(['existing instructions', 'compact memory and capture instructions']);
    const [command, args, options] = spawn.mock.calls[0]!;
    expect(command).toBe('python3');
    expect(args).toEqual([join(pluginDir!, 'hooks/memory_hook.py'), 'text']);
    expect(options.cwd).toBe('/project with spaces');
    expect(JSON.parse(options.input)).toEqual({ cwd: '/project with spaces' });
    expect(options.timeout).toBeGreaterThan(0);
    expect(options.timeout).toBeLessThanOrEqual(10000);
    expect(plugin['tool.execute.before']).toBeTypeOf('function');
  });

  it('computes context once per session and re-attaches it on every model call', async () => {
    const spawn = vi.fn().mockReturnValue({ status: 0, stdout: 'compact context' });
    const plugin = await load(spawn);
    for (let request = 0; request < 3; request++) {
      const output = { system: ['existing instructions'] };
      await plugin['experimental.chat.system.transform']!({ sessionID: 'chat-1' }, output);
      expect(output.system).toEqual(['existing instructions', 'compact context']);
    }
    expect(spawn).toHaveBeenCalledTimes(1);
  });

  it('computes separately for each session', async () => {
    const spawn = vi.fn().mockReturnValue({ status: 0, stdout: 'compact context' });
    const plugin = await load(spawn);
    await plugin['experimental.chat.system.transform']!({ sessionID: 'chat-1' }, { system: [] });
    await plugin['experimental.chat.system.transform']!({ sessionID: 'chat-2' }, { system: [] });
    expect(spawn).toHaveBeenCalledTimes(2);
    expect(JSON.parse(spawn.mock.calls[1]![2].input)).not.toHaveProperty('session_id');
  });

  it('adds nothing and spawns nothing for calls without a session id', async () => {
    const spawn = vi.fn().mockReturnValue({ status: 0, stdout: 'compact context' });
    const plugin = await load(spawn);
    const output = { system: ['existing instructions'] };
    await plugin['experimental.chat.system.transform']!({}, output);
    expect(output.system).toEqual(['existing instructions']);
    expect(spawn).not.toHaveBeenCalled();
  });

  it('leaves existing instructions intact when the hook has no context', async () => {
    const plugin = await load(vi.fn().mockReturnValue({ status: 0, stdout: '' }));
    const output = { system: ['existing instructions'] };
    await plugin['experimental.chat.system.transform']!({ sessionID: 'chat-2' }, output);
    expect(output.system).toEqual(['existing instructions']);
  });

  it.each([
    { status: 1, stdout: 'failure' },
    { status: null, error: new Error('timeout'), stdout: 'partial' },
  ])('preserves instructions, warns, and does not retry a failed subprocess: %j', async (result) => {
    const spawn = vi.fn().mockReturnValue(result);
    const plugin = await load(spawn);
    for (let request = 0; request < 2; request++) {
      const output = { system: ['existing instructions'] };
      await plugin['experimental.chat.system.transform']!({ sessionID: 'chat-3' }, output);
      expect(output.system[0]).toBe('existing instructions');
      expect(output.system).toHaveLength(2);
      expect(output.system[1]).toMatch(/memory unavailable/i);
      expect(output.system[1]).not.toContain(result.stdout);
    }
    expect(spawn).toHaveBeenCalledTimes(1);
  });

  it('allows the model request when launching Python throws', async () => {
    const plugin = await load(vi.fn().mockImplementation(() => { throw new Error('Python unavailable'); }));
    const output = { system: ['existing instructions'] };
    await expect(plugin['experimental.chat.system.transform']!({ sessionID: 'chat-4' }, output)).resolves.toBeUndefined();
    expect(output.system[0]).toBe('existing instructions');
    expect(output.system).toHaveLength(2);
    expect(output.system[1]).toMatch(/memory unavailable/i);
  });
});
