import { globSync } from 'node:fs';
import { join } from 'node:path';

import { load as parseYaml } from 'js-yaml';
import { describe, expect, it } from 'vitest';

import { readRepoFile, repoRoot } from '../../support/repo';

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
  it('test, validate and smoke are peers that only run against a freshly built project', () => {
    expect(jobNeeds(CI_JOBS['test'])).toContain('build');
    expect(jobNeeds(CI_JOBS['validate'])).toContain('build');
    expect(jobNeeds(CI_JOBS['smoke'])).toEqual(['build']);
    const smokeIf = CI_JOBS['smoke']?.if ?? '';
    expect(smokeIf).toContain("needs.build.result == 'success'");
    expect(smokeIf).not.toContain('refs/heads/main');
    expect(smokeIf).not.toContain('pull_request');
  });

  it('CI is exactly the release-gating jobs, none main-only, with no separate discover job', () => {
    // These ARE the pipeline, each reproducible by `make <job id>`; mutation testing is off it.
    expect(Object.keys(CI_JOBS).sort()).toEqual([
      'build', 'smoke', 'test', 'validate', 'vulnerability-scan',
    ]);
    const jobText = JSON.stringify(CI_JOBS);
    expect(jobText).not.toContain('mutation');
    expect(jobText).not.toContain('mutmut');
    expect(jobText).not.toContain('stryker');
    // A job gated to main alone can land green while breaking a check no pull request ever ran.
    for (const [jobName, job] of Object.entries(CI_JOBS)) {
      expect(job.if ?? '', `job '${jobName}' is gated to main`).not.toContain('refs/heads/main');
    }
    expect(CI_JOBS).not.toHaveProperty('discover');
  });

  it('vulnerability-scan sits in the SAME tier as test/validate/smoke: needs only build, every commit', () => {
    expect(new Set(jobNeeds(CI_JOBS['vulnerability-scan']))).toEqual(new Set(['build']));
    const jobIf = CI_JOBS['vulnerability-scan']?.if ?? '';
    expect(jobIf).not.toContain('refs/heads/main');
    expect(jobIf).not.toContain('pull_request');
  });

  it("vulnerability-scan's job id and make target are the same string; the display name is a separate readable label", () => {
    expect(CI_JOBS['vulnerability-scan']?.['name']).toBe('Vulnerability scan');
    const runSteps = (CI_JOBS['vulnerability-scan']?.steps ?? []).map((s) => s.run).filter(Boolean) as string[];
    expect(runSteps.some((run) => run.trim() === 'make vulnerability-scan')).toBe(true);
  });
});

describe('the build-output tracked guard', () => {
  it('CI runs the build gates, whose script checks dist/ is tracked', () => {
    const gatesSh = readRepoFile('internal', 'release', 'ci', 'build_gates.sh');
    const buildRunSteps = (CI_JOBS['build']?.steps ?? []).map((s) => s.run).filter(Boolean);
    expect(buildRunSteps.some((run) => run?.includes('make ci-build'))).toBe(true);
    expect(gatesSh).toContain('git status --porcelain');
    expect(gatesSh).toContain('dist');
  });
});

describe('CI jobs that run compiled TypeScript scripts install the toolchain first', () => {
  // Build emits the smoke matrix and validate checks the package, both from compiled TypeScript.
  it.each(['build', 'validate'])("the '%s' job installs and compiles the TypeScript toolchain", (jobName) => {
    const runSteps = (CI_JOBS[jobName]?.steps ?? []).map((s) => s.run).filter(Boolean) as string[];
    expect(runSteps.some((run) => run.includes('make install-ts'))).toBe(true);
    expect(runSteps.some((run) => run.includes('make compile'))).toBe(true);
  });
});

describe('the release pipeline', () => {
  const releaseJob = RELEASE.jobs?.['release'];
  const releaseSteps = (releaseJob?.steps ?? []).map((s) => s.run).filter(Boolean) as string[];

  it('is a single job that installs, compiles, bumps the version, rebuilds and commits, in order', () => {
    // No separate unprivileged prepare job / artifact hand-off: the toolchain can never silently go
    // missing between jobs (e.g. an artifact step dropping a dot-prefixed output directory).
    expect(RELEASE.jobs).not.toHaveProperty('prepare');
    expect(RELEASE.permissions).toEqual({ contents: 'write' });
    const idx = (needle: string) => releaseSteps.findIndex((run) => run.includes(needle));
    const [installIdx, compileIdx, verIdx, buildIdx, commitIdx] =
      ['make install-ts', 'make compile', 'make release-version', 'make build', 'make release-commit'].map(idx);
    expect([installIdx, compileIdx, verIdx, buildIdx, commitIdx]).not.toContain(-1);
    expect(installIdx).toBeLessThan(compileIdx as number);
    expect(compileIdx).toBeLessThan(verIdx as number);
    expect(verIdx).toBeLessThan(buildIdx as number);
    expect(buildIdx).toBeLessThan(commitIdx as number);
    expect(readRepoFile('internal', 'release', 'ci', 'release_commit.sh')).toMatch(/git add[^\n]*\bdist\b/);
  });

  it('acts only on the CI-validated commit', () => {
    const verifySh = readRepoFile('internal', 'release', 'ci', 'release_verify_checkout.sh');
    const releaseYaml = readRepoFile('.github', 'workflows', 'release.yml');
    const headSha = 'github.event.workflow_run.head_sha';
    const pinned = releaseYaml.includes(`ref: \${{ ${headSha} }}`);
    const guarded =
      releaseYaml.includes(headSha) && verifySh.includes('rev-parse HEAD') && verifySh.includes('exit 1');
    expect(pinned || guarded).toBe(true);
  });

  it('runs the smoke matrix under a config that can actually discover it', () => {
    // A config-level exclusion beats an explicit file path, so a bare `$TEST` with no `--config` exits
    // 1 on every leg while `make test-smoke` stays green locally, hiding the drift.
    const script = readRepoFile('internal', 'release', 'ci', 'run_smoke.sh');
    expect(readRepoFile('vitest.config.mts')).toContain("'tests/dist/**/smoke.spec.ts'");
    expect(script).toContain('--config vitest.smoke.config.mts');

    const smokeConfig = readRepoFile('vitest.smoke.config.mts');
    expect(smokeConfig).toContain("'tests/dist/**/smoke.spec.ts'");
    expect(smokeConfig)
      .not.toContain("exclude: ['node_modules/**', 'dist/**', 'build/**', 'tests/dist/**/smoke.spec.ts']");
  });
});
