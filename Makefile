.PHONY: test test-mutation test-smoke install install-py install-ts build build-check \
        typecheck compile test-py test-ts mutation-py mutation-ts parity parity-tokens pycompat-golden-check \
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

build:
	python -m scripts.build.cli --target all

build-check:
	python -m scripts.build.cli --target all --check

test: test-py test-ts

# The Python suite. During the migration this still covers the compiler; it narrows to the
# src/hooks/ island as each area is ported. tests-python/ is the hooks island's own tree (see
# CODE_OF_CONDUCT.md § Testing) — separate from tests/ so it survives commit 16's compiler deletion.
test-py: build-check
	python -m pytest tests/ tests-python/ -v --cov=scripts/build --cov=src/hooks --cov-branch --cov-report=term-missing --cov-fail-under=90

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
compile:
	@[ -d .ts-out ] || rm -f tsconfig.build.tsbuildinfo tsconfig.tests.tsbuildinfo
	npm run compile

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
	python -m pytest tests/build/test_claude_code_smoke.py tests/build/test_opencode_smoke.py tests/build/test_cursor_smoke.py tests/build/test_grok_build_smoke.py tests/build/test_gemini_cli_smoke.py tests/build/test_copilot_cli_smoke.py -v

# ── CI entry points ──────────────────────────────────────────────────────────
# The GitHub Actions workflows call ONLY `make <target>` — every step's logic lives here and under
# scripts/ci/, so it is testable and runnable locally. This is enforced by
# tests/build/test_workflows_use_make.py; add a target + a script, never an inline YAML block.

ci-build:
	bash scripts/ci/build_gates.sh

# Go/no-go gate for moving token counting off Python: js-tiktoken must tokenize cl100k_base
# byte-identically to Python's tiktoken across this repo's real corpus. A single-token
# disagreement is a spec change to the budgets in tests/testdata/thresholds.json, not a port.
parity-tokens: compile
	bash scripts/ci/parity_tokens.sh

# The dual-run oracle for the migration: every fixture under tests/testdata/parity/ is fed to BOTH
# compilers and their canonical output byte-diffed. A port commit is not done until this is green.
parity: compile
	bash scripts/ci/parity.sh

# The pyCompat character tables encode a specific Unicode version. This proves the committed golden
# dump matches the interpreter actually running, so the tables cannot silently encode a different
# Unicode database than the one the parity harness compares against.
pycompat-golden-check:
	bash scripts/ci/pycompat_golden_check.sh

validate:
	python -m scripts.ci.validate_package

smoke-matrix:
	python -m scripts.ci.smoke_matrix

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

release-version:
	python -m scripts.set_version "$${NEW_VERSION}"

changelog:
	python scripts/update_changelog.py

release-commit:
	bash scripts/ci/release_commit.sh

npm-creds:
	bash scripts/ci/npm_creds.sh

release-npm:
	npm publish --access public
