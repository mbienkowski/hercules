import { describe, expect, it } from 'vitest';

import { PROJECT_RESET, readFile, section } from './support';

// The shipped wording of the one command that deletes. Every assertion here exists because the
// meaning it pins is load-bearing at a moment the person cannot take back — and because the first
// build of this command silently dropped its danger banner with a fully green suite.

describe('project-reset: what the person is told, and when', () => {
  it('warns that the action cannot be undone before it offers a single choice', () => {
    const text = readFile(PROJECT_RESET);
    expect(text.indexOf('cannot be undone')).toBeLessThan(text.indexOf('Choose what you want to delete'));
  });

  it('names the danger before the choices and again at the confirmation', () => {
    const text = readFile(PROJECT_RESET);
    const warnings = [...text.matchAll(/cannot be undone/g)].map((m) => m.index as number);
    expect(warnings.length).toBeGreaterThanOrEqual(2);
    expect(warnings[warnings.length - 1]).toBeGreaterThan(text.indexOf('Confirm — this deletes'));
  });

  it('presents itself as a danger zone rather than routine maintenance', () => {
    // Pinned in BOTH places it belongs. A bare `toContain` passes while one of the two is lost —
    // which is exactly how the screen banner vanished from the first build of this command.
    const text = readFile(PROJECT_RESET);
    expect([...text.matchAll(/DANGER ZONE/g)].length).toBeGreaterThanOrEqual(2);
    const screen = section(text, 'Project    hercules', 'Choose what you want to delete');
    expect(screen, 'the findings screen carries no danger banner').toContain('DANGER ZONE');
  });

  it('says there is no way back, positively rather than by omission', () => {
    // A ban on the word "backup" would pass the moment the sentence were reworded, so the sentence
    // itself is pinned — and in both places, since losing either one leaves a screen that never
    // says it while the other still does.
    const text = readFile(PROJECT_RESET);
    const sentence = 'There is no backup, no undo, no restore.';
    expect([...text.matchAll(/There is no backup, no undo, no restore\./g)].length).toBe(2);
    expect(section(text, 'Confirm — this deletes', '```\n\nSay "the last account')).toContain(sentence);
  });

  it('says what it does not touch before it says what it will', () => {
    const text = readFile(PROJECT_RESET);
    expect(text.indexOf('does not touch your code')).toBeLessThan(text.indexOf('What Hercules holds'));
  });

  it('names the documents exception in the same breath as the promise', () => {
    // The requirement is explicit that the caveat travels WITH the promise. Stated three steps
    // later it reads as a correction to something the person already believed.
    const promise = section(readFile(PROJECT_RESET), 'does not touch your code', 'This cannot be undone');
    expect(promise).toContain('the documents folder');
  });

  it('warns when the documents folder sits inside the code repository', () => {
    const text = readFile(PROJECT_RESET);
    expect(text).toContain('inside_code_repo');
    expect(text).toContain('deletes files from that repository');
  });
});

describe('project-reset: the four things it can clear', () => {
  it('offers each of the four as its own selectable item', () => {
    const choices = section(readFile(PROJECT_RESET), 'Choose what you want to delete', 'Reply with numbers');
    for (const item of ['1) Documents', '2) Settings', "3) One feature's record", "4) Every feature's record"]) {
      expect(choices, `missing choice: ${item}`).toContain(item);
    }
  });

  it('states that any combination is valid, so nothing is bundled behind one yes', () => {
    expect(readFile(PROJECT_RESET)).toContain('Any combination is valid');
  });

  it('names the four settings it clears, so the person knows what to set again', () => {
    const text = readFile(PROJECT_RESET);
    for (const s of ['documents folder', 'linked repositories', 'test-guard', 'spec retention']) {
      expect(text, `missing setting: ${s}`).toContain(s);
    }
  });
});

describe('project-reset: how it talks to the program', () => {
  it('states the contract version on every call, so a stale plugin refuses instead of guessing', () => {
    // Asserted as "no invocation lacks it" rather than a count: a count passes while a third,
    // unversioned call sits beside two correct ones.
    const invocations = readFile(PROJECT_RESET)
      .split('\n')
      .filter((line) => line.includes('project_reset.py'));
    expect(invocations.length).toBeGreaterThanOrEqual(2);
    for (const line of invocations) expect(line, `unversioned call: ${line}`).toContain('--contract 1');
  });

  it('relays the program refusal word for word rather than paraphrasing it', () => {
    expect(readFile(PROJECT_RESET)).toContain('word for word');
  });

  it('treats any non-zero exit as a full stop with no other route to deleting', () => {
    const text = readFile(PROJECT_RESET);
    expect(text).toContain('A non-zero exit is a full stop');
    expect(text).toContain('never fall back to deleting by another route');
  });

  it('tells the two meanings of a partial failure apart', () => {
    // Exit 4 means "some of it landed" or "none of it did", and the person is owed a different
    // answer in each case. Reading them as one would report a half-finished clear as a clean stop.
    const text = readFile(PROJECT_RESET);
    expect(text).toContain('Exit `4` on an `apply` means two different things');
    expect(text).toContain('never call the run a success');
  });

  it('renders the screens from the program reply rather than reading the record itself', () => {
    expect(readFile(PROJECT_RESET)).toContain('Do not read `~/.hercules` yourself');
  });
});

describe('project-reset: what it says afterwards', () => {
  it('reports what went, what stayed, and what could not be removed', () => {
    const closeOut = section(readFile(PROJECT_RESET), 'Done — here is what happened', 'Omit the third block');
    for (const block of ['Deleted', 'Kept', 'Not removed']) {
      expect(closeOut, `missing close-out block: ${block}`).toContain(block);
    }
  });

  it('names every path it could not remove instead of summarising them', () => {
    expect(readFile(PROJECT_RESET)).toContain('never summarise them');
  });

  it('says what happens next, since there is no phase to point at', () => {
    expect(readFile(PROJECT_RESET)).toContain('Hercules asks again where documents');
  });

  it('distinguishes itself from abandoning a session', () => {
    const text = readFile(PROJECT_RESET);
    expect(text).toContain('abandon this session');
    expect(text).toContain('the only one of the two that deletes files');
  });
});
