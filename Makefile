.PHONY: test test-mutation test-smoke install install-py install-ts build build-check \
        typecheck compile test-py test-ts mutation-py mutation-ts \
        complexity-scan complexity-scan-ts complexity-scan-py vulnerability-scan \
        ci-build validate smoke-matrix smoke-install smoke-run smoke-annotate \
        release-verify release-meta release-version changelog release-commit npm-creds release-npm

# ── Which runtime owns what ──────────────────────────────────────────────────
# Python: src/hooks/ (shipped to users, run as python3) and its tests. Gated by test-py/mutation-py.
# TypeScript: everything else executable — the src/{builder,release,metrics}/ domains, and their
# tests. Gated by test-ts/mutation-ts.
# The -py/-ts suffix is the SAME string in the make target, the CI job id and the CI display name,
# so a red check can be reproduced by copying its name into a terminal. Keep it that way.

install: install-py install-ts

install-py:
	pip install -e ".[dev]"

install-ts:
	npm ci

build: compile
	node .ts-out/builder/bin/cli.mjs --target all

build-check: compile
	node .ts-out/builder/bin/cli.mjs --target all --check

test: test-py test-ts

# The Python suite: src/hooks/ (the island, see CODE_OF_CONDUCT.md § Testing) plus whatever remains
# under src/commons/repo/ (meta-guards, not build output — the compiler itself is TypeScript now).
test-py: build-check
	python -m pytest src/commons/repo/ src/hooks/tests/ -v --cov=src/hooks --cov-branch --cov-report=term-missing --cov-fail-under=90

test-ts:
	npm run typecheck
	npx vitest run --coverage

# Type-check both TypeScript projects without running anything. Both are ESM; compile emits
# src/builder/, src/release/ and src/metrics/'s .mts sources as .mjs into .ts-out/.
typecheck:
	npm run typecheck

# Drop the incremental build stamp when the output tree is gone: tsc -b trusts tsbuildinfo, so a
# manually deleted .ts-out would otherwise leave `make compile` a no-op with nothing emitted.
# Not `tsc -b --force`, which would forfeit incremental builds on every target that depends on this.
#
# `tsc` itself may be absent: release.yml's `release` job deliberately never runs `npm ci` (that is
# the whole point of its prepare/release split — see that file's own comment), so it has no
# node_modules at all and instead downloads an already-compiled .ts-out/ as a build artifact. Every
# target below that depends on `compile` (build, build-check, validate, smoke-matrix,
# release-version, changelog) must still work unmodified in that job — so this checks for a usable
# local toolchain first and, when there is none, trusts an already-populated .ts-out/ instead of
# failing on a missing `tsc` binary. Fails loudly only when NEITHER is available, since that is a
# real "nothing to build from" error, not a job that intentionally skips `npm ci`.
compile:
	@[ -d .ts-out ] || rm -f tsconfig.build.tsbuildinfo tsconfig.tests.tsbuildinfo
	@if [ -x node_modules/.bin/tsc ]; then \
		npm run compile; \
	elif [ -d .ts-out ] && [ -n "$$(ls -A .ts-out 2>/dev/null)" ]; then \
		echo "no local TypeScript toolchain (node_modules/.bin/tsc missing) — using the existing .ts-out/ as-is"; \
	else \
		echo "ERROR: .ts-out/ is missing or empty and there is no local TypeScript toolchain to compile it — run 'make install-ts' first" >&2; \
		exit 1; \
	fi

test-mutation: mutation-py mutation-ts

mutation-py:
	mutmut run || true
	mutmut results | tee mutmut-results.txt
	python src/release/check_mutation_gate.py

# Stryker writes reports/mutation/mutation.json; the gate script applies the SAME thresholds the
# Python gate reads (src/release/mutation-gate.json), so the two runtimes cannot drift to two answers.
mutation-ts: compile
	npx stryker run || true
	node .ts-out/release/bin/mutationGate.mjs

# ── Complexity gate ───────────────────────────────────────────────────────────
# A local "SonarQube-style" scan: every first-party function must stay under a CEILING of 15 on BOTH
# cyclomatic (independent paths) AND cognitive (SonarSource's nesting-aware metric) complexity — 15
# is SonarQube's own default for cognitive complexity. Cognitive is the one that catches "a junior
# can't follow these nested loops"; cyclomatic is a cheap second opinion. The SAME 15 governs both
# runtimes so neither can hide a hotspot the other would reject. Tests are excluded on both sides: a
# table-driven, assertion-dense spec is legitimately branchy and is not shipped. See
# CODE_OF_CONDUCT.md § Complexity.
complexity-scan: complexity-scan-ts complexity-scan-py

# TypeScript domains (compiler / release / metrics). Config + ceiling live in eslint.config.mjs.
complexity-scan-ts:
	npx eslint --max-warnings=0 .

# Shipped Python hooks. --select restricts flake8 to ONLY the two complexity checks (C901 = mccabe
# cyclomatic, CCR001 = cognitive) — no style/lint noise; --extend-exclude drops the hooks' own tests.
complexity-scan-py:
	flake8 --select=C901,CCR001 --max-complexity=15 --max-cognitive-complexity=15 --extend-exclude=tests src/hooks

# ── Dependency vulnerability scan ─────────────────────────────────────────────
# Fail on any HIGH or CRITICAL CVE in a dependency. npm carries the ENTIRE dependency surface: the
# shipped plugin is zero-runtime-dep and the Python hooks are stdlib-only (dependencies = [] in
# pyproject), so there is no pip runtime-CVE surface to scan — the whole exposure is the dev
# toolchain in package-lock.json. --audit-level=high exits non-zero only on high/critical; moderate
# and low remain visible but non-blocking, matching the "critical + high" bar. Audits the committed
# package-lock.json directly (no node_modules required); the CI job runs `make install-ts` before it
# so the resolved tree matches what ships.
vulnerability-scan:
	npm audit --audit-level=high

# Live CLI smoke checks — do the built plugins actually install/load in the real Claude Code,
# OpenCode, and Cursor binaries? Skips silently if a given CLI isn't installed locally; install
# Claude Code + OpenCode with `npm install -g @anthropic-ai/claude-code opencode-ai`, and Cursor
# with `curl https://cursor.com/install -fsSL | bash`, to run the whole set.
test-smoke: build-check
	npx vitest run src/builder/tests/smoke/claudeCodeSmoke.spec.ts src/builder/tests/smoke/opencodeSmoke.spec.ts src/builder/tests/smoke/cursorSmoke.spec.ts src/builder/tests/smoke/grokBuildSmoke.spec.ts src/builder/tests/smoke/geminiCliSmoke.spec.ts src/builder/tests/smoke/copilotCliSmoke.spec.ts

# ── CI entry points ──────────────────────────────────────────────────────────
# The GitHub Actions workflows call ONLY `make <target>` — every step's logic lives here and under
# src/release/ci/, so it is testable and runnable locally. This is enforced by
# src/release/tests/pipeline/releasePipeline.spec.ts; add a target + a script, never an inline YAML block.

ci-build:
	bash src/release/ci/build_gates.sh

validate: compile
	node .ts-out/release/bin/validatePackage.mjs

smoke-matrix: compile
	node .ts-out/release/bin/smokeMatrix.mjs

smoke-install:
	bash src/release/ci/install_cli.sh

smoke-run:
	bash src/release/ci/run_smoke.sh

smoke-annotate:
	bash src/release/ci/annotate_smoke.sh

# ── Release entry points (release.yml) ───────────────────────────────────────
release-verify:
	bash src/release/ci/release_verify_checkout.sh

release-meta:
	bash src/release/ci/release_meta.sh

release-version: compile
	node .ts-out/release/bin/setVersion.mjs "$${NEW_VERSION}"

changelog: compile
	node .ts-out/release/bin/updateChangelog.mjs

release-commit:
	bash src/release/ci/release_commit.sh

npm-creds:
	bash src/release/ci/npm_creds.sh

release-npm:
	npm publish --access public
