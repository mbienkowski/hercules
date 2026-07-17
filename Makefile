.PHONY: test test-mutation install build build-check

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
