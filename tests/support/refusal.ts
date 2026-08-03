import { expect } from 'vitest';

/**
 * Asserts that something was refused AND that the refusal names the place. Taking the attempt as a
 * thunk lets one helper serve every refusing entry point without knowing which one it is.
 */
export function expectRefusal(attempt: () => unknown, mentions: readonly string[] = []): string {
  let message: string | null = null;
  try {
    attempt();
  } catch (error) {
    message = (error as Error).message;
  }
  return assertRefused(message, mentions);
}

/**
 * The same contract for a refusal arriving as a rejected promise: rendering is asynchronous, and a
 * test that forgets to `await` an assertion of failure passes whatever happens.
 */
export async function expectAsyncRefusal(
  attempt: () => Promise<unknown>,
  mentions: readonly string[] = [],
): Promise<string> {
  let message: string | null = null;
  try {
    await attempt();
  } catch (error) {
    message = (error as Error).message;
  }
  return assertRefused(message, mentions);
}

function assertRefused(message: string | null, mentions: readonly string[]): string {
  expect(message, 'this was accepted, but it should have been refused').not.toBeNull();
  for (const needle of mentions) {
    expect(message, `the refusal should say where the problem is (${needle})`).toContain(needle);
  }
  return message as string;
}
