.PHONY: test test-mutation test-smoke install install-py install-ts build build-check \
        typecheck compile test-py test-ts mutation-py mutation-ts pycompat-golden-check \
        ci-build validate smoke-matrix smoke-install smoke-run smoke-annotate \
        release-verify release-meta release-version changelog release-commit npm-creds release-npm

# ── Which runtime owns what ──────────────────────────────────────────────────
# Python: src/hooks/ (shipped to users, run as python3) and its tests. Gated by test-py/mutation-py.
# TypeScript: everything else executable — the compiler, the CI scripts, and their tests. Gated by
# test-ts/mutation-ts.
# The -py/-ts suffix is the SAME string in the make target, the CI job id and the CI display name,
# so a red check can be reproduced by copying its name into a terminal. Keep it that way.

install: install-py install-ts

install-py:
	pip install -e ".[dev]"

install-ts:
	npm ci

build: compile
	node .ts-out/bin/cli.mjs --target all

build-check: compile
	node .ts-out/bin/cli.mjs --target all --check

test: test-py test-ts

# The Python suite: src/hooks/ (the island, see CODE_OF_CONDUCT.md § Testing) plus whatever remains
# under tests/ (meta-guards, not build output — the compiler itself is TypeScript now).
test-py: build-check
	python -m pytest tests/ tests-python/ -v --cov=src/hooks --cov-branch --cov-report=term-missing --cov-fail-under=90

test-ts:
	npm run typecheck
	npx vitest run --coverage

# Type-check both TypeScript projects without running anything. Both are ESM; compile emits
# scripts-ts/'s .mts sources as .mjs into .ts-out/.
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
	python scripts/check_mutation_gate.py

# Stryker writes reports/mutation/mutation.json; the gate script applies the SAME thresholds the
# Python gate reads (scripts/mutation-gate.json), so the two runtimes cannot drift to two answers.
mutation-ts: compile
	npx stryker run || true
	node .ts-out/bin/mutationGate.mjs

# Live CLI smoke checks — do the built plugins actually install/load in the real Claude Code,
# OpenCode, and Cursor binaries? Skips silently if a given CLI isn't installed locally; install
# Claude Code + OpenCode with `npm install -g @anthropic-ai/claude-code opencode-ai`, and Cursor
# with `curl https://cursor.com/install -fsSL | bash`, to run the whole set.
test-smoke: build-check
	npx vitest run tests-ts/build/claudeCodeSmoke.spec.ts tests-ts/build/opencodeSmoke.spec.ts tests-ts/build/cursorSmoke.spec.ts tests-ts/build/grokBuildSmoke.spec.ts tests-ts/build/geminiCliSmoke.spec.ts tests-ts/build/copilotCliSmoke.spec.ts

# ── CI entry points ──────────────────────────────────────────────────────────
# The GitHub Actions workflows call ONLY `make <target>` — every step's logic lives here and under
# scripts/ci/, so it is testable and runnable locally. This is enforced by
# tests-ts/releasePipeline.spec.ts; add a target + a script, never an inline YAML block.

ci-build:
	bash scripts/ci/build_gates.sh

# The pyCompat character tables encode a specific Unicode version. This proves the committed golden
# dump matches the interpreter actually running — pyCompat.mts reproduces Python's own character
# classification (str.isspace()/splitlines()/isprintable()), and this is what keeps its hand-ported
# table honest against the real CPython behavior it must match, independent of the (now retired)
# dual-run parity harness that originally motivated it.
pycompat-golden-check:
	bash scripts/ci/pycompat_golden_check.sh

validate: compile
	node .ts-out/bin/validatePackage.mjs

smoke-matrix: compile
	node .ts-out/bin/smokeMatrix.mjs

smoke-install:
	bash scripts/ci/install_cli.sh

smoke-run:
	bash scripts/ci/run_smoke.sh

smoke-annotate:
	bash scripts/ci/annotate_smoke.sh

# ── Release entry points (release.yml) ───────────────────────────────────────
release-verify:
	bash scripts/ci/release_verify_checkout.sh

release-meta:
	bash scripts/ci/release_meta.sh

release-version: compile
	node .ts-out/bin/setVersion.mjs "$${NEW_VERSION}"

changelog: compile
	node .ts-out/bin/updateChangelog.mjs

release-commit:
	bash scripts/ci/release_commit.sh

npm-creds:
	bash scripts/ci/npm_creds.sh

release-npm:
	npm publish --access public
