.PHONY: test test-mutation test-smoke install build build-check

install:
	pip install -e ".[dev]"

build:
	python -m scripts.build.cli --target all

build-check:
	python -m scripts.build.cli --target all --check

test: build-check
	python -m pytest tests/ -v --cov=scripts/build --cov=tests.metrics --cov=src/targets/claude-code/hooks --cov-branch --cov-report=term-missing --cov-fail-under=90

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
