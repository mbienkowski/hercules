.PHONY: test test-mutation test-smoke install install-py install-ts build build-check \
        typecheck compile test-py test-ts mutation-py mutation-ts \
        vulnerability-scan tripwire normative-gate mutation-report \
        ci-build validate smoke-matrix smoke-install smoke-run smoke-annotate \
        release-verify release-meta release-version changelog release-commit npm-creds release-npm

# ── Which runtime owns what ──────────────────────────────────────────────────
# Python owns src/scripts/hooks/ and src/scripts/tools/ (both shipped to users); TypeScript owns
# internal/{builder,release}/ and tests/budgets/. The -py/-ts suffix is the same string in the make
# target, the CI job id and the CI display name, so a red check reproduces by copying its name into a
# terminal. Keep it that way.

# A handful of tests/scripts/hooks/ specs run a shipped hook straight out of dist/<eco>/hooks/ via
# subprocess.run; without this, `python3 <script>` writes a __pycache__ into the committed dist/
# tree. Exported once here (every recipe's shell inherits it) rather than per target, so it covers
# every current and future test target uniformly.
export PYTHONDONTWRITEBYTECODE = 1

install: install-py install-ts

install-py:
	pip install -e ".[dev]"

install-ts:
	npm ci

# The build reads src/targets/<eco>.json as a RECIPE — every shipped file named explicitly, with the
# ordered sources it is made of — and renders each source whole through LiquidJS. `build-check`
# renders into a scratch tree and compares it with the committed dist/ by BYTES **and permission
# bits**: that tree is what every marketplace installs from, so the comparison is a supply-chain
# check, not a build-works check.
build: compile
	node .local/ts-out/builder/bin/recipe.mjs --target all

build-check: compile
	node .local/ts-out/builder/bin/recipe.mjs --target all --check

test: test-py test-ts

# The Python suite: src/scripts/hooks/ and src/scripts/tools/ (the two islands, see
# CODE_OF_CONDUCT.md § Testing) plus the repo-wide meta-guards under tests/repo/.
test-py: build-check
	python -m pytest tests/repo/ tests/scripts/hooks/ tests/scripts/tools/ -v --cov=src/scripts/hooks --cov=src/scripts/tools --cov-branch --cov-report=term-missing

test-ts:
	npm run typecheck
	npx vitest run --coverage

# Type-check both TypeScript projects without running anything.
typecheck:
	npm run typecheck

# `tsc -b` trusts tsbuildinfo, so drop the stamp when .local/ts-out/ is gone or compile becomes a no-op.
# `tsc` itself may be absent: release.yml's privileged job runs no `npm ci` and downloads a compiled
# .local/ts-out/ instead, so every compile-dependent target must work there too — hence the fallback to an
# already-populated .local/ts-out/, and a loud failure only when neither is available.
compile:
	@[ -d .local/ts-out ] || rm -f tsconfig.build.tsbuildinfo tsconfig.tests.tsbuildinfo
	@if [ -x node_modules/.bin/tsc ]; then \
		npm run compile; \
	elif [ -d .local/ts-out ] && [ -n "$$(ls -A .local/ts-out 2>/dev/null)" ]; then \
		echo "no local TypeScript toolchain (node_modules/.bin/tsc missing) — using the existing .local/ts-out/ as-is"; \
	else \
		echo "ERROR: .local/ts-out/ is missing or empty and there is no local TypeScript toolchain to compile it — run 'make install-ts' first" >&2; \
		exit 1; \
	fi

# ── Per-commit CI gates (phase-1 quality-gates reset) ─────────────────────────
# Both judge a push ONE COMMIT AT A TIME (an early compliant commit never excuses a later
# violating one) and fail LOUD on an unresolvable base — their jobs check out fetch-depth: 0.
tripwire:
	bash internal/release/ci/tripwire.sh

normative-gate:
	bash internal/release/ci/normative_gate.sh

# ── Mutation testing — a manual developer tool, never a gate ─────────────────
# Run by hand, on the change you are working on. No CI job runs these and no threshold blocks
# anything: mutmut and Stryker print their own kill rate and their own survivor list, which is what
# a campaign is actually read for. What to do about a survivor is a human call, in review.
# History that settled this: as a main-only CI gate it outgrew its ceiling, reported `cancelled`
# rather than `failed`, and silently blocked every release with no red check to explain it.
test-mutation: mutation-py mutation-ts

mutation-py:
	mutmut run
	mutmut results

mutation-ts: compile
	npx stryker run

# ── Dependency vulnerability scan ─────────────────────────────────────────────
# Fail on any high or critical CVE. npm carries the entire dependency surface: the shipped plugin is
# zero-runtime-dep and the Python hooks are stdlib-only, so the whole exposure is the dev toolchain
# in package-lock.json. --audit-level=high leaves moderate and low visible but non-blocking.
vulnerability-scan:
	npm audit --audit-level=high

# Live CLI smoke checks: do the built plugins install and load in the real binaries? Each leg skips
# silently when its CLI is not installed locally.
test-smoke: build-check
	npx vitest run --config vitest.smoke.config.mts


# ── CI entry points ──────────────────────────────────────────────────────────
# The GitHub Actions workflows call only `make <target>`, so every step is testable and runnable
# locally. Add a target plus an internal/release/ci/ script, never an inline YAML block.

ci-build:
	bash internal/release/ci/build_gates.sh

validate: compile
	node .local/ts-out/release/bin/validatePackage.mjs

smoke-matrix: compile
	node .local/ts-out/release/bin/smokeMatrix.mjs

smoke-install:
	bash internal/release/ci/install_cli.sh

smoke-run:
	bash internal/release/ci/run_smoke.sh

smoke-annotate:
	bash internal/release/ci/annotate_smoke.sh

# ── Release entry points (release.yml) ───────────────────────────────────────
release-verify:
	bash internal/release/ci/release_verify_checkout.sh

release-meta:
	bash internal/release/ci/release_meta.sh

release-version: compile
	node .local/ts-out/release/bin/setVersion.mjs "$${NEW_VERSION}"

changelog: compile
	node .local/ts-out/release/bin/updateChangelog.mjs

release-commit:
	bash internal/release/ci/release_commit.sh

npm-creds:
	bash internal/release/ci/npm_creds.sh

release-npm:
	npm publish --access public

mutation-report: compile
	bash internal/release/ci/mutation_report.sh
