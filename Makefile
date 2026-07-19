.PHONY: test test-mutation test-smoke install build build-check \
        ci-build validate smoke-matrix smoke-install smoke-run smoke-annotate smoke-annotate-nightly \
        release-verify release-meta release-version changelog release-commit npm-creds release-npm

install:
	pip install -e ".[dev]"

build:
	python -m scripts.build.cli --target all

build-check:
	python -m scripts.build.cli --target all --check

test: build-check
	python -m pytest tests/ -v --cov=scripts/build --cov=tests.metrics --cov=src/targets/claude-code/hooks --cov=src/targets/cursor/hooks --cov-branch --cov-report=term-missing --cov-fail-under=90

test-mutation:
	mutmut run || true
	mutmut results | tee mutmut-results.txt
	python scripts/check_mutation_gate.py

# Live CLI smoke checks — do the built plugins actually install/load in the real Claude Code,
# OpenCode, and Cursor binaries? Skips silently if a given CLI isn't installed locally; install
# Claude Code + OpenCode with `npm install -g @anthropic-ai/claude-code opencode-ai`, and Cursor
# with `curl https://cursor.com/install -fsSL | bash`, to run the whole set.
test-smoke: build-check
	python -m pytest tests/build/test_claude_code_smoke.py tests/build/test_opencode_smoke.py tests/build/test_cursor_smoke.py -v

# ── CI entry points ──────────────────────────────────────────────────────────
# The GitHub Actions workflows call ONLY `make <target>` — every step's logic lives here and under
# scripts/ci/, so it is testable and runnable locally. This is enforced by
# tests/build/test_workflows_use_make.py; add a target + a script, never an inline YAML block.

ci-build:
	bash scripts/ci/build_gates.sh

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

smoke-annotate-nightly:
	bash scripts/ci/annotate_nightly.sh

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
