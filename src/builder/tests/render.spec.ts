import { describe, expect, it } from 'vitest';

import { RenderError, renderBody } from '../render.mjs';

const NO_TOKENS = new Map<string, string>();

describe('substituting tokens in a document body', () => {
  it('replaces a known token with its value', () => {
    expect(renderBody('Hello ${name}.', 'claude-code', new Map([['name', 'World']]))).toBe(
      'Hello World.',
    );
  });

  it('leaves an unknown token exactly as written', () => {
    // ${CLAUDE_PLUGIN_ROOT} appears in shipped prose and hook wiring and is resolved by the HOST at
    // runtime. Substituting or blanking it would break the shipped plugin.
    expect(renderBody('root is ${CLAUDE_PLUGIN_ROOT}', 'claude-code', NO_TOKENS)).toBe(
      'root is ${CLAUDE_PLUGIN_ROOT}',
    );
  });

  it('writes a replacement value literally even when it looks like a capture reference', () => {
    // A naive string replacement would treat `$&` as "the whole match" and re-insert the token.
    expect(renderBody('v=${n}', 'claude-code', new Map([['n', '$& and $1']]))).toBe('v=$& and $1');
  });

  it('never reflows or trims the surrounding text', () => {
    // Only marker spans may change; every other byte must survive, or dist/ drifts on every build.
    const source = '  leading\n\ttab\n\n\nblank lines\n   ';
    expect(renderBody(source, 'claude-code', NO_TOKENS)).toBe(source);
  });
});

describe('choosing a branch for the target being built', () => {
  const source = [
    'before',
    '${target:claude-code}',
    'CLAUDE',
    '${target:opencode}',
    'OPEN',
    '${target:default}',
    'FALLBACK',
    '${target:end}',
    'after',
  ].join('\n');

  it('picks the branch naming the target exactly', () => {
    expect(renderBody(source, 'claude-code', NO_TOKENS)).toBe('before\nCLAUDE\nafter');
  });

  it('picks another target’s branch when that is the one named', () => {
    expect(renderBody(source, 'opencode', NO_TOKENS)).toBe('before\nOPEN\nafter');
  });

  it('falls back to the default branch for a target with no branch of its own', () => {
    expect(renderBody(source, 'cursor', NO_TOKENS)).toBe('before\nFALLBACK\nafter');
  });

  it('accepts a short alias for the target family', () => {
    // `claude` matches `claude-code`, so shared prose does not have to name every variant.
    const short = 'a\n${target:claude}\nSHORT\n${target:end}\nz';
    expect(renderBody(short, 'claude-code', NO_TOKENS)).toBe('a\nSHORT\nz');
  });

  it('emits nothing for the switch when no branch matches and there is no default', () => {
    const noDefault = 'a\n${target:opencode}\nOPEN\n${target:end}\nz';
    expect(renderBody(noDefault, 'cursor', NO_TOKENS)).toBe('a\n\nz');
  });
});

describe('refusing a switch that cannot be understood', () => {
  it('rejects a switch that is never closed', () => {
    // Silently treating the rest of the file as one branch would drop content from dist/ with no
    // signal at all.
    expect(() => renderBody('a\n${target:claude-code}\nX\n', 'claude-code', NO_TOKENS)).toThrow(
      RenderError,
    );
    expect(() => renderBody('a\n${target:claude-code}\nX\n', 'claude-code', NO_TOKENS)).toThrow(
      'unclosed',
    );
  });

  it('rejects an end marker with no branch open', () => {
    expect(() => renderBody('a\n${target:end}\n', 'claude-code', NO_TOKENS)).toThrow(
      'without an opening branch',
    );
  });

  it('names the offending line when a branch name is malformed', () => {
    // The failure message has to identify WHICH line, or a contributor is left grepping a 600-line
    // document for an invisible typo.
    expect(() =>
      renderBody('a\n${target:Bad-Name}\nX\n${target:end}\n', 'claude-code', NO_TOKENS),
    ).toThrow("malformed switch directive: \"${target:Bad-Name}\"");
  });

  it('rejects a malformed name on a later branch, not just the first', () => {
    expect(() =>
      renderBody('a\n${target:claude}\nX\n${target:BAD}\nY\n${target:end}\n', 'claude-code', NO_TOKENS),
    ).toThrow('malformed switch directive');
  });
});

describe('recognising a switch directive exactly', () => {
  it('ignores a directive with trailing text on the same line', () => {
    // Without the end anchor this would open a branch and swallow the rest of the document.
    const source = 'a\n${target:claude-code} and more\nb';
    expect(renderBody(source, 'claude-code', NO_TOKENS)).toBe(source);
  });

  it('ignores a directive with leading text on the same line', () => {
    const source = 'a\nprefix ${target:claude-code}\nb';
    expect(renderBody(source, 'claude-code', NO_TOKENS)).toBe(source);
  });

  it('rejects a branch name with a trailing uppercase character', () => {
    // Without the end anchor on the name pattern, `claudeX` would validate as `claude`.
    expect(() =>
      renderBody('a\n${target:claudeX}\nX\n${target:end}\n', 'claude-code', NO_TOKENS),
    ).toThrow('malformed switch directive');
  });

  it('identifies its failures as render errors', () => {
    try {
      renderBody('a\n${target:end}\n', 'claude-code', NO_TOKENS);
      expect.unreachable('should have thrown');
    } catch (error) {
      expect((error as Error).name).toBe('RenderError');
    }
  });

  it('keeps a chosen branch’s line breaks', () => {
    const source = 'a\n${target:claude}\nX\nY\n${target:end}\nz';
    expect(renderBody(source, 'claude-code', NO_TOKENS)).toBe('a\nX\nY\nz');
  });
});
