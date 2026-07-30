import { globSync } from 'node:fs';
import { join } from 'node:path';

import { load as parseYaml } from 'js-yaml';
import { describe, expect, it } from 'vitest';

import { readRepoFile, repoRoot } from '../../../commons/support/repo';

// Covers the workflow and CI-script TEXT directly — the make-only invariant, the CI job graph, and
// the release pipeline — rather than calling into any of the modules those workflows run.

interface WorkflowStep {
  readonly run?: string;
  readonly uses?: string;
  readonly [key: string]: unknown;
}

interface WorkflowJob {
  readonly needs?: string | readonly string[];
  readonly if?: string;
  readonly steps?: readonly WorkflowStep[];
  readonly [key: string]: unknown;
}

interface Workflow {
  readonly permissions?: Record<string, string>;
  readonly jobs?: Record<string, WorkflowJob>;
}

const WORKFLOWS_DIR = join(repoRoot, '.github', 'workflows');

function loadWorkflow(name: string): Workflow {
  return parseYaml(readRepoFile('.github', 'workflows', name)) as Workflow;
}

const CI = loadWorkflow('ci.yml');
const RELEASE = loadWorkflow('release.yml');
const CI_JOBS = CI.jobs ?? {};

function jobNeeds(job: WorkflowJob | undefined): string[] {
  const needs = job?.needs;
  if (needs === undefined) return [];
  return typeof needs === 'string' ? [needs] : [...needs];
}

describe('every GitHub Actions run: step calls only make', () => {
  // CI behaviour lives in the Makefile + release/ci/ (one source of truth, testable and runnable
  // locally), never in YAML heredocs or multi-line shell scattered across workflow files.

  function runSteps(): Array<{ file: string; job: string; index: number; run: string }> {
    const steps: Array<{ file: string; job: string; index: number; run: string }> = [];
    for (const path of globSync('*.yml', { cwd: WORKFLOWS_DIR }).sort()) {
      const doc = loadWorkflow(path);
      for (const [jobName, job] of Object.entries(doc.jobs ?? {})) {
        (job.steps ?? []).forEach((step, index) => {
          if (typeof step.run === 'string') {
            steps.push({ file: path, job: jobName, index, run: step.run });
          }
        });
      }
    }
    return steps;
  }

  it('workflows exist and have run: steps (guarding the guard against a vacuous pass)', () => {
    const steps = runSteps();
    expect(steps.length).toBeGreaterThan(0);
    const files = new Set(steps.map((s) => s.file));
    expect(files.has('ci.yml')).toBe(true);
    expect(files.has('release.yml')).toBe(true);
  });

  it('every run: step is a single make <target> invocation (comments/blank lines allowed)', () => {
    const offenders: string[] = [];
    for (const step of runSteps()) {
      const logic = step.run
        .split('\n')
        .map((line) => line.trim())
        .filter((line) => line.length > 0 && !line.startsWith('#'));
      const allMake = logic.length > 0 && logic.every((line) => line === 'make' || line.startsWith('make '));
      if (!allMake) {
        offenders.push(`${step.file} · job '${step.job}' · step ${step.index}: ${JSON.stringify(logic)}`);
      }
    }
    expect(offenders, offenders.join('\n')).toEqual([]);
  });
});

describe('the CI job graph', () => {
  it('test and validate only run against a freshly built project', () => {
    expect(jobNeeds(CI_JOBS['test'])).toContain('build');
    expect(jobNeeds(CI_JOBS['validate'])).toContain('build');
  });

  it('smoke is a peer of test/validate, not gated behind the unit suite', () => {
    expect(jobNeeds(CI_JOBS['smoke'])).toEqual(['build']);
  });

  it("smoke's if: still requires a green build but is not gated to main or pull_request", () => {
    const smokeIf = CI_JOBS['smoke']?.if ?? '';
    expect(smokeIf).toContain("needs.build.result == 'success'");
    expect(smokeIf).not.toContain('refs/heads/main');
    expect(smokeIf).not.toContain('pull_request');
  });

  // mutation-py and mutation-ts run as two PARALLEL jobs, each provisioning only the toolchain it
  // needs — both must carry identical gating so neither is the weak link.
  it.each(['mutation-py', 'mutation-ts'])(
    "'%s' waits for ALL five fast checks via needs (it is the sole job at the end)",
    (jobName) => {
      expect(new Set(jobNeeds(CI_JOBS[jobName]))).toEqual(
        new Set(['test', 'validate', 'smoke', 'complexity-scan', 'vulnerability-scan']),
      );
      // The success gate is `needs` itself: the if carries NO status-check function, so GitHub keeps
      // the implicit needs-success requirement rather than re-spelling it with `.result` checks —
      // the same gating dialect every job uses, differing only in the branch restriction below.
      const mutationIf = CI_JOBS[jobName]?.if ?? '';
      expect(mutationIf).not.toContain('cancelled()');
      expect(mutationIf).not.toContain('.result');
    },
  );

  it.each(['mutation-py', 'mutation-ts'])(
    "'%s' runs only on a push to main — the release gate",
    (jobName) => {
      const mutationIf = CI_JOBS[jobName]?.if ?? '';
      expect(mutationIf).toContain("github.event_name == 'push'");
      expect(mutationIf).toContain("github.ref == 'refs/heads/main'");
      expect(mutationIf).not.toContain('pull_request');
    },
  );

  it("the mutation job id and make target are the same string (mutation-py / mutation-ts); the display name is a separate readable label", () => {
    // The id (used by `needs:` and `make`) still reproduces a red check via `make {id}`; the display
    // name in the GitHub UI is a human-readable label instead of the raw id (see ci-check-name-unification).
    const readableName: Record<string, string> = {
      'mutation-py': 'Hooks mutation tests',
      'mutation-ts': 'Plugin builder mutation tests',
    };
    for (const jobName of ['mutation-py', 'mutation-ts']) {
      expect(CI_JOBS[jobName]?.['name']).toBe(readableName[jobName]);
      const runSteps = (CI_JOBS[jobName]?.steps ?? []).map((s) => s.run).filter(Boolean) as string[];
      expect(runSteps.some((run) => run.trim() === `make ${jobName}`)).toBe(true);
    }
  });

  it('there is no separate discover job — the smoke matrix is a build output', () => {
    expect(CI_JOBS).not.toHaveProperty('discover');
  });

  // complexity-scan and vulnerability-scan are static quality gates in the SAME tier as
  // test/validate/smoke: they `needs: [build]` only and run in PARALLEL on EVERY commit. The default
  // `if: success()` gates them on `build` alone, unrestricted by branch or event.
  it.each(['complexity-scan', 'vulnerability-scan'])(
    "'%s' runs in parallel with test/validate/smoke (needs only build), every commit",
    (jobName) => {
      expect(new Set(jobNeeds(CI_JOBS[jobName]))).toEqual(new Set(['build']));
      const jobIf = CI_JOBS[jobName]?.if ?? '';
      expect(jobIf).not.toContain('refs/heads/main');
      expect(jobIf).not.toContain('pull_request');
    },
  );

  it.each(['complexity-scan', 'vulnerability-scan'])(
    "'%s' job id and make target are the same string; the display name is a separate readable label",
    (jobName) => {
      const readableName: Record<string, string> = {
        'complexity-scan': 'Complexity scan',
        'vulnerability-scan': 'Vulnerability scan',
      };
      expect(CI_JOBS[jobName]?.['name']).toBe(readableName[jobName]);
      const runSteps = (CI_JOBS[jobName]?.steps ?? []).map((s) => s.run).filter(Boolean) as string[];
      expect(runSteps.some((run) => run.trim() === `make ${jobName}`)).toBe(true);
    },
  );
});

describe('the build-output tracked guard', () => {
  it('CI runs the build gates, whose script checks dist/ is tracked', () => {
    const gatesSh = readRepoFile('src', 'release', 'ci', 'build_gates.sh');
    const buildRunSteps = (CI_JOBS['build']?.steps ?? []).map((s) => s.run).filter(Boolean);
    expect(buildRunSteps.some((run) => run?.includes('make ci-build'))).toBe(true);
    expect(gatesSh).toContain('git status --porcelain');
    expect(gatesSh).toContain('dist');
  });
});

describe('CI jobs that run compiled TypeScript scripts install the toolchain first', () => {
  // The build job emits the smoke matrix (release/smokeMatrix.mts, which imports the zod-validated
  // descriptor module) and validate checks the package (release/validatePackage.mts) — both need the
  // compiled toolchain present.
  it.each(['build', 'validate'])("the '%s' job installs and compiles the TypeScript toolchain", (jobName) => {
    const runSteps = (CI_JOBS[jobName]?.steps ?? []).map((s) => s.run).filter(Boolean) as string[];
    expect(runSteps.some((run) => run.includes('make install-ts'))).toBe(true);
    expect(runSteps.some((run) => run.includes('make compile'))).toBe(true);
  });
});

describe('the release pipeline', () => {
  const releaseJob = RELEASE.jobs?.['release'];
  const releaseSteps = (releaseJob?.steps ?? []).map((s) => s.run).filter(Boolean) as string[];

  it('rebuilds and commits the output after bumping the version, in order', () => {
    const commitSh = readRepoFile('src', 'release', 'ci', 'release_commit.sh');
    const verIdx = releaseSteps.findIndex((run) => run.includes('make release-version'));
    const buildIdx = releaseSteps.findIndex((run) => run.includes('make build'));
    const commitIdx = releaseSteps.findIndex((run) => run.includes('make release-commit'));
    expect([verIdx, buildIdx, commitIdx]).not.toContain(-1);
    expect(verIdx).toBeLessThan(buildIdx);
    expect(buildIdx).toBeLessThan(commitIdx);
    expect(commitSh).toMatch(/git add[^\n]*\bdist\b/);
  });

  it('acts only on the CI-validated commit', () => {
    const verifySh = readRepoFile('src', 'release', 'ci', 'release_verify_checkout.sh');
    const releaseYaml = readRepoFile('.github', 'workflows', 'release.yml');
    const headSha = 'github.event.workflow_run.head_sha';
    const pinned = releaseYaml.includes(`ref: \${{ ${headSha} }}`);
    const guarded =
      releaseYaml.includes(headSha) && verifySh.includes('rev-parse HEAD') && verifySh.includes('exit 1');
    expect(pinned || guarded).toBe(true);
  });

  it('is a single job that installs and compiles the toolchain itself, before bumping the version', () => {
    // No separate unprivileged prepare job / artifact hand-off: the release job runs npm ci directly,
    // so the compiled toolchain can never silently go missing between jobs (e.g. an artifact step
    // dropping a dot-prefixed output directory).
    expect(RELEASE.jobs).not.toHaveProperty('prepare');
    expect(RELEASE.permissions).toEqual({ contents: 'write' });
    const installIdx = releaseSteps.findIndex((run) => run.includes('make install-ts'));
    const compileIdx = releaseSteps.findIndex((run) => run.includes('make compile'));
    const verIdx = releaseSteps.findIndex((run) => run.includes('make release-version'));
    expect([installIdx, compileIdx, verIdx]).not.toContain(-1);
    expect(installIdx).toBeLessThan(compileIdx);
    expect(compileIdx).toBeLessThan(verIdx);
  });

  /**
   * The smoke matrix must be runnable by the script CI actually invokes.
   *
   * These two drifted apart once and took every smoke leg red: the everyday vitest config gained an
   * exclusion for `src/builder/tests/smoke/**` so the default suite would stop flaking, and that
   * exclusion beats an explicit file path on the command line — so `run_smoke.sh`, which passed the
   * matrix path with no `--config`, exited 1 with "No test files found" on all six legs. Nothing failed
   * locally, because `make test-smoke` had been given the new config and the CI script had not.
   */
  it('runs the smoke matrix under a config that can actually discover it', () => {
    const script = readRepoFile('src', 'release', 'ci', 'run_smoke.sh');
    const defaultExcludesSmoke = readRepoFile('vitest.config.mts').includes('src/builder/tests/smoke/**');
    expect(defaultExcludesSmoke, 'if the default config no longer excludes the smoke specs this guard '
      + 'is measuring a condition that has gone away — re-read it rather than deleting it').toBe(true);
    expect(script, 'run_smoke.sh must pass --config vitest.smoke.config.mts. The default config excludes '
      + 'the smoke specs, and that exclusion wins over the explicit $TEST path, so without the flag '
      + 'every CI leg exits 1 with "No test files found" while every local target stays green.')
      .toContain('--config vitest.smoke.config.mts');

    const smokeConfig = readRepoFile('vitest.smoke.config.mts');
    expect(smokeConfig, 'the smoke config must include the directory the matrix paths live in')
      .toContain('src/builder/tests/smoke/**');
    expect(smokeConfig, 'the smoke config must not inherit the exclusion it exists to lift')
      .not.toContain("exclude: ['node_modules/**', 'dist/**', '.ts-out/**', 'src/builder/tests/smoke/**']");
  });
});
